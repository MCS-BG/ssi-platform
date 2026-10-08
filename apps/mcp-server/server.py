"""Day 6 MCP server for the ai-ops-homelab cluster.

Tools:
  search_notes            semantic search over the day 4 pgvector 'chunks' table
  fo_list_entities        entity sets offered by the FO OData endpoint (the mock)
  fo_get_entity_metadata  keys and fields of one entity set, from /data/$metadata
  fo_query                read-only OData query against the mock FO service

Day 8b guardrails (Prompt Guard 2, http://prompt-guard.si-lab.svc.cluster.local:8080/classify):
  - before a tool runs, its user-supplied string arguments are classified; a malicious_score at or
    above PROMPT_GUARD_THRESHOLD (default 0.5) refuses the call with a tool error
  - after search_notes, every retrieved chunk is classified; flagged chunks are withheld
    (indirect prompt injection), the rest are returned
  - each check is a span with prompt_guard.* attributes and langfuse.observation.type=guardrail
  - if Prompt Guard is unreachable the call is refused, unless PROMPT_GUARD_FAIL_OPEN=true
The SDK's tools/call span (a TOOL observation in Langfuse) gets the arguments and result as
input/output, and the Ollama embedding call is an "embedding" observation (model, token count).

Transport: MCP Streamable HTTP on :8000 at /mcp (stateless, JSON responses).
Built on the official MCP Python SDK 2.x, where FastMCP is named MCPServer.
"""
import functools
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

import psycopg
import requests
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from opentelemetry import trace

from llmtrace import _text, observation, set_ollama_response, set_output

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama.si-lab.svc.cluster.local:11434")
DSN = os.environ.get("PG_DSN", "host=pgvector.si-lab.svc.cluster.local port=5432 dbname=rag user=rag")  # password comes from PGPASSWORD
FO_BASE_URL = os.environ.get("FO_BASE_URL", "http://fo-mock.si-lab.svc.cluster.local:8080").rstrip("/")
EMBED_MODEL = "nomic-embed-text"
# Keep the embedding model loaded in Ollama ("-1m" = until Ollama restarts or needs the VRAM).
# Only embedding calls send this; chat models keep the server default (OLLAMA_KEEP_ALIVE=10m).
EMBED_KEEP_ALIVE = os.environ.get("EMBED_KEEP_ALIVE", "-1m")
PORT = int(os.environ.get("PORT", "8000"))
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "MCP_ALLOWED_HOSTS",
    "127.0.0.1:*,localhost:*,mcp-server:*,mcp-server.si-lab:*,mcp-server.si-lab.svc:*,mcp-server.si-lab.svc.cluster.local:*",
).split(",") if h.strip()]
EDM = "{http://docs.oasis-open.org/odata/ns/edm}"

PROMPT_GUARD_URL = os.environ.get("PROMPT_GUARD_URL", "http://prompt-guard.si-lab.svc.cluster.local:8080/classify")
# 0.5 = the argmax decision of Meta's two-class model (benign / malicious), as in the model card.
PROMPT_GUARD_THRESHOLD = float(os.environ.get("PROMPT_GUARD_THRESHOLD", "0.5"))
PROMPT_GUARD_ENABLED = os.environ.get("PROMPT_GUARD_ENABLED", "true").lower() == "true"
PROMPT_GUARD_FAIL_OPEN = os.environ.get("PROMPT_GUARD_FAIL_OPEN", "false").lower() == "true"

mcp = MCPServer(
    "ai-ops-homelab",
    instructions=(
        "Tools for the home AI lab. search_notes searches the lab notes. "
        "The fo_* tools read a MOCK Dynamics 365 finance and operations OData service with fake demo data "
        "(company usmf). Call fo_get_entity_metadata before fo_query to learn the exact field names."
    ),
    version="0.8.1",
)


# ---------- search_notes: same embedding and SQL as day 4 ask.py ----------

def embed(text):
    with observation("ollama embed", "embedding", input=text, model=EMBED_MODEL,
                     operation="embeddings") as span:
        r = requests.post(f"{OLLAMA}/api/embed",
                          json={"model": EMBED_MODEL, "input": [text], "keep_alive": EMBED_KEEP_ALIVE},
                          timeout=120)
        r.raise_for_status()
        body = r.json()
        set_ollama_response(span, body)
        vector = body["embeddings"][0]
        set_output(span, {"dimensions": len(vector)})
        return vector


def to_vector(values):
    return "[" + ",".join(str(x) for x in values) + "]"


# ---------- Prompt Guard ----------

PROMPT_GUARD_MAX_CHARS = 20000  # the classifier answers 413 above this (MAX_CHARS in apps/prompt-guard)


def _pieces(text):
    """Split very long text into overlapping pieces the classifier accepts; the highest score wins."""
    if len(text) <= PROMPT_GUARD_MAX_CHARS:
        return [text]
    step = PROMPT_GUARD_MAX_CHARS - 1000
    return [text[i:i + PROMPT_GUARD_MAX_CHARS] for i in range(0, len(text), step)]


def classify(text, stage, tool):
    """Classify one text with Prompt Guard inside a guardrail span. Returns (blocked, score).

    Raises ToolError if Prompt Guard cannot be reached and PROMPT_GUARD_FAIL_OPEN is false.
    """
    with observation(f"prompt-guard {stage}", "guardrail",
                     input={"tool": tool, "stage": stage, "text": text},
                     **{"prompt_guard.stage": stage, "prompt_guard.tool": tool,
                        "prompt_guard.threshold": PROMPT_GUARD_THRESHOLD}) as span:
        try:
            result = None
            for piece in _pieces(text):
                r = requests.post(PROMPT_GUARD_URL, json={"text": piece, "threshold": PROMPT_GUARD_THRESHOLD},
                                  timeout=15)
                r.raise_for_status()
                part = r.json()
                if result is None or float(part["malicious_score"]) > float(result["malicious_score"]):
                    result = part
            score = float(result["malicious_score"])
        except (requests.RequestException, ValueError, KeyError) as e:
            span.set_attribute("prompt_guard.error", f"{type(e).__name__}: {e}")
            span.set_attribute("langfuse.observation.level", "ERROR")
            if PROMPT_GUARD_FAIL_OPEN:
                set_output(span, {"error": str(e), "action": "allowed (fail open)"})
                return False, None
            set_output(span, {"error": str(e), "action": "refused (fail closed)"})
            raise ToolError(f"Prompt Guard unavailable, request refused: {type(e).__name__}") from e
        blocked = score >= PROMPT_GUARD_THRESHOLD
        span.set_attribute("prompt_guard.malicious_score", score)
        span.set_attribute("prompt_guard.label", str(result.get("label", "")))
        span.set_attribute("prompt_guard.blocked", blocked)
        span.set_attribute("prompt_guard.latency_ms", float(result.get("latency_ms") or 0.0))
        span.set_attribute("langfuse.observation.metadata.malicious_score", f"{score:.4f}")
        span.set_attribute("langfuse.observation.metadata.blocked", str(blocked).lower())
        if blocked:
            span.set_attribute("langfuse.observation.level", "WARNING")
            span.set_attribute("langfuse.observation.status_message",
                               f"malicious_score {score:.4f} >= threshold {PROMPT_GUARD_THRESHOLD}")
        set_output(span, {**result, "threshold": PROMPT_GUARD_THRESHOLD, "blocked": blocked})
        return blocked, score


def guard_input(tool, **arguments):
    """Refuse the tool call if its user-supplied text looks like a prompt attack."""
    if not PROMPT_GUARD_ENABLED:
        return
    text = "\n".join(str(v) for v in arguments.values() if isinstance(v, str) and v.strip())
    if not text:
        return
    blocked, score = classify(text, "input", tool)
    if blocked:
        raise ToolError(
            f"Refused by Prompt Guard: the {tool} arguments look like a prompt injection or jailbreak "
            f"(malicious_score {score:.3f} >= threshold {PROMPT_GUARD_THRESHOLD})."
        )


def guard_chunks(tool, results):
    """Withhold retrieved chunks that look like indirect prompt injection."""
    if not PROMPT_GUARD_ENABLED:
        return results, 0
    withheld = 0
    for item in results:
        blocked, score = classify(item["chunk"], "retrieved_chunk", tool)
        if blocked:
            withheld += 1
            item["chunk"] = (f"[withheld by Prompt Guard: malicious_score {score:.3f} >= "
                             f"threshold {PROMPT_GUARD_THRESHOLD}]")
            item["withheld"] = True
    return results, withheld


def traced_tool(func):
    """Add the tool's arguments and result to the SDK's "tools/call" span.

    The MCP SDK already opens a span per tool call with gen_ai.operation.name=execute_tool,
    which Langfuse shows as a TOOL observation, but without input or output. This fills them in
    and names the trace. functools.wraps keeps the signature and docstring, which the SDK reads
    to build the tool's input schema.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        span = trace.get_current_span()
        span.set_attribute("langfuse.observation.input", _text(kwargs))
        span.set_attribute("langfuse.trace.name", f"mcp {func.__name__}")
        result = func(*args, **kwargs)
        set_output(span, result)
        return result
    return wrapper


@mcp.tool()
@traced_tool
def search_notes(query: str, k: int = 5) -> dict[str, Any]:
    """Search the ai-ops-homelab lab notes by meaning.

    Returns the k closest text chunks (1 to 20) with the Markdown file each came
    from and its cosine distance (lower is closer). Use it to answer questions
    about how the lab was built.
    """
    if not query.strip():
        raise ToolError("query must not be empty")
    k = max(1, min(int(k), 20))
    guard_input("search_notes", query=query)
    try:
        qvec = to_vector(embed("search_query: " + query))  # nomic-embed-text task prefix, as in ask.py
        with psycopg.connect(DSN, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT source, chunk, embedding <=> %s::vector AS distance "
                "FROM chunks ORDER BY distance LIMIT %s",
                (qvec, k),
            )
            rows = cur.fetchall()
    except (requests.RequestException, psycopg.Error) as e:
        # Surface backend problems (Ollama or Postgres unreachable) to the caller.
        raise ToolError(f"search_notes backend error: {type(e).__name__}: {e}") from e
    results, withheld = guard_chunks("search_notes", [
        {"source": source, "distance": round(float(distance), 4), "chunk": chunk}
        for source, chunk, distance in rows
    ])
    return {"query": query, "withheld": withheld, "results": results}


# ---------- fo_*: read-only OData against the mock FO service ----------

def _odata_get(path, params=None):
    try:
        r = requests.get(f"{FO_BASE_URL}/data/{path}", params=params, timeout=15,
                         headers={"Accept": "application/json", "OData-Version": "4.0"})
    except requests.RequestException as e:
        raise ToolError(f"FO OData service unreachable: {type(e).__name__}: {e}") from e
    if r.status_code >= 400:
        try:
            message = r.json()["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = r.text[:300]
        raise ToolError(f"OData error {r.status_code}: {message}")
    return r


def _metadata():
    root = ET.fromstring(_odata_get("$metadata").content)
    sets = {}
    for es in root.iter(EDM + "EntitySet"):
        sets[es.get("Name")] = es.get("EntityType").rsplit(".", 1)[-1]
    types = {}
    for et in root.iter(EDM + "EntityType"):
        keys = [p.get("Name") for p in et.iter(EDM + "PropertyRef")]
        fields = [{"name": p.get("Name"), "type": p.get("Type")} for p in et.iter(EDM + "Property")]
        types[et.get("Name")] = {"keys": keys, "fields": fields}
    return sets, types


def _check_entity(entity):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,79}", entity or ""):
        raise ToolError("entity must be an OData entity set name such as CustomersV3")


@mcp.tool()
@traced_tool
def fo_list_entities() -> dict[str, Any]:
    """List the entity sets (for example CustomersV3) that the mock FO OData service exposes."""
    sets, _ = _metadata()
    return {"source": "fo-mock (fake demo data)", "entity_sets": sorted(sets)}


@mcp.tool()
@traced_tool
def fo_get_entity_metadata(entity: str) -> dict[str, Any]:
    """Return the key fields and all field names/types for one FO entity set, read from /data/$metadata."""
    _check_entity(entity)
    guard_input("fo_get_entity_metadata", entity=entity)
    sets, types = _metadata()
    if entity not in sets:
        raise ToolError(f"Unknown entity set {entity}. Known: {', '.join(sorted(sets))}")
    info = types[sets[entity]]
    return {"entity_set": entity, "entity_type": sets[entity], "keys": info["keys"], "fields": info["fields"]}


@mcp.tool()
@traced_tool
def fo_query(entity: str, filter: str | None = None, top: int = 10,
             select: str | None = None, cross_company: bool = False) -> dict[str, Any]:
    """Read records from a mock Dynamics 365 FO OData entity set (fake demo data).

    entity: entity set name, e.g. CustomersV3, VendorsV2, ReleasedProductsV2, SalesOrderHeadersV2.
    filter: OData $filter using eq joined by 'and', e.g. "CustomerGroupId eq '30'".
    top: max rows, 1 to 50. select: comma-separated field names.
    cross_company: true to include companies other than the default (usmf).
    """
    _check_entity(entity)
    guard_input("fo_query", entity=entity, filter=filter, select=select)
    params = {"$top": str(max(1, min(int(top), 50))), "$count": "true"}
    if filter:
        params["$filter"] = filter
    if select:
        params["$select"] = select
    if cross_company:
        params["cross-company"] = "true"
    body = _odata_get(entity, params).json()
    return {
        "source": "fo-mock (fake demo data)",
        "entity_set": entity,
        "matched": body.get("@odata.count"),
        "returned": len(body.get("value", [])),
        "records": body.get("value", []),
    }


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok\n")


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=PORT,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=ALLOWED_HOSTS,
            allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
        ),
    )
