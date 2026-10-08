"""Small helpers that turn Ollama calls into Langfuse-friendly OpenTelemetry spans (Day 8b).

The spans go through the same path as the Day 7 zero-code spans: the OTel SDK that
opentelemetry-instrument sets up, then the collector, then Tempo and Langfuse.
Langfuse maps these attributes (https://langfuse.com/integrations/native/opentelemetry):
  langfuse.observation.type          "generation", "embedding", "retriever", "chain", "guardrail"
  langfuse.observation.input/output  JSON strings shown as Input / Output
  gen_ai.request.model               model name (generation-like observations)
  gen_ai.usage.input_tokens/...      token usage
  langfuse.trace.name                trace name
Without opentelemetry-instrument (plain "python ask.py") the OTel API is a no-op.
"""
import json
from contextlib import contextmanager

from opentelemetry import trace

tracer = trace.get_tracer("ai-ops-homelab")
MAX_CHARS = 8000  # keep span attributes a sensible size


def _text(value):
    """JSON (or plain text) for a span attribute, cut to MAX_CHARS."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + f"... [{len(text) - MAX_CHARS} more chars]"


@contextmanager
def observation(name, obs_type, input=None, model=None, operation=None, trace_name=None, **attrs):
    """Start a span that Langfuse shows as an observation of the given type."""
    with tracer.start_as_current_span(name) as span:
        span.set_attribute("langfuse.observation.type", obs_type)
        if trace_name:
            span.set_attribute("langfuse.trace.name", trace_name)
        if input is not None:
            span.set_attribute("langfuse.observation.input", _text(input))
        if model:
            span.set_attribute("gen_ai.provider.name", "ollama")
            span.set_attribute("gen_ai.system", "ollama")
            span.set_attribute("gen_ai.request.model", model)
        if operation:
            span.set_attribute("gen_ai.operation.name", operation)
        for key, value in attrs.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


def set_output(span, output):
    span.set_attribute("langfuse.observation.output", _text(output))


def set_ollama_response(span, body):
    """Copy model name and token counts from an Ollama /api/embed or /api/generate response."""
    if body.get("model"):
        span.set_attribute("gen_ai.response.model", body["model"])
    if body.get("prompt_eval_count") is not None:
        span.set_attribute("gen_ai.usage.input_tokens", int(body["prompt_eval_count"]))
    if body.get("eval_count") is not None:
        span.set_attribute("gen_ai.usage.output_tokens", int(body["eval_count"]))
