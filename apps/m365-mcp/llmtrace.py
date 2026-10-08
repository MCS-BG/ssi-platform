"""Small helpers that turn calls into Langfuse-friendly OpenTelemetry spans.

Copied lightly from apps/mcp-server/llmtrace.py. Without opentelemetry-instrument
the OTel API is a no-op.
"""
import json
from contextlib import contextmanager

from opentelemetry import trace

tracer = trace.get_tracer("m365-mcp")
MAX_CHARS = 8000


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
            span.set_attribute("gen_ai.request.model", model)
        if operation:
            span.set_attribute("gen_ai.operation.name", operation)
        for key, value in attrs.items():
            if value is not None:
                span.set_attribute(key, value)
        yield span


def set_output(span, output):
    span.set_attribute("langfuse.observation.output", _text(output))
