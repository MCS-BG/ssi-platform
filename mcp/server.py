"""Day 6 MCP server for the ai-ops-homelab cluster.

Tools:
  search_notes            semantic search over the day 4 pgvector 'chunks' table
  fo_list_entities        entity sets offered by the FO OData endpoint (the mock)
  fo_get_entity_metadata  keys and fields of one entity set, from /data/$metadata
  fo_query                read-only OData query against the mock FO service

Transport: MCP Streamable HTTP on :8000 at /mcp (stateless, JSON responses).
Built on the official MCP Python SDK 2.x, where FastMCP is named MCPServer.
"""
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

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama.si-lab.svc.cluster.local:11434")
DSN = os.environ.get("PG_DSN", "host=pgvector.si-lab.svc.cluster.local port=5432 dbname=rag user=rag")  # password comes from PGPASSWORD
FO_BASE_URL = os.environ.get("FO_BASE_URL", "http://fo-mock.si-lab.svc.cluster.local:8080").rstrip("/")
EMBED_MODEL = "nomic-embed-text"
PORT = int(os.environ.get("PORT", "8000"))
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    "MCP_ALLOWED_HOSTS",
    "127.0.0.1:*,localhost:*,mcp-server:*,mcp-server.si-lab:*,mcp-server.si-lab.svc:*,mcp-server.si-lab.svc.cluster.local:*",
).split(",") if h.strip()]
EDM = "{http://docs.oasis-open.org/odata/ns/edm}"

mcp = MCPServer(
    "ai-ops-homelab",
    instructions=(
        "Tools for the home AI lab. search_notes searches the lab notes. "
        "The fo_* tools read a MOCK Dynamics 365 finance and operations OData service with fake demo data "
        "(company usmf). Call fo_get_entity_metadata before fo_query to learn the exact field names."
    ),
    version="0.6.0",
)


# ---------- search_notes: same embedding and SQL as day 4 ask.py ----------

def embed(text):
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": [text]}, timeout=120)
    r.raise_for_status()
    return r.json()["embeddings"][0]


def to_vector(values):
    return "[" + ",".join(str(x) for x in values) + "]"


@mcp.tool()
def search_notes(query: str, k: int = 5) -> dict[str, Any]:
    """Search the ai-ops-homelab lab notes by meaning.

    Returns the k closest text chunks (1 to 20) with the Markdown file each came
    from and its cosine distance (lower is closer). Use it to answer questions
    about how the lab was built.
    """
    if not query.strip():
        raise ToolError("query must not be empty")
    k = max(1, min(int(k), 20))
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
    return {
        "query": query,
        "results": [
            {"source": source, "distance": round(float(distance), 4), "chunk": chunk}
            for source, chunk, distance in rows
        ],
    }


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
def fo_list_entities() -> dict[str, Any]:
    """List the entity sets (for example CustomersV3) that the mock FO OData service exposes."""
    sets, _ = _metadata()
    return {"source": "fo-mock (fake demo data)", "entity_sets": sorted(sets)}


@mcp.tool()
def fo_get_entity_metadata(entity: str) -> dict[str, Any]:
    """Return the key fields and all field names/types for one FO entity set, read from /data/$metadata."""
    _check_entity(entity)
    sets, types = _metadata()
    if entity not in sets:
        raise ToolError(f"Unknown entity set {entity}. Known: {', '.join(sorted(sets))}")
    info = types[sets[entity]]
    return {"entity_set": entity, "entity_type": sets[entity], "keys": info["keys"], "fields": info["fields"]}


@mcp.tool()
def fo_query(entity: str, filter: str | None = None, top: int = 10,
             select: str | None = None, cross_company: bool = False) -> dict[str, Any]:
    """Read records from a mock Dynamics 365 FO OData entity set (fake demo data).

    entity: entity set name, e.g. CustomersV3, VendorsV2, ReleasedProductsV2, SalesOrderHeadersV2.
    filter: OData $filter using eq joined by 'and', e.g. "CustomerGroupId eq '30'".
    top: max rows, 1 to 50. select: comma-separated field names.
    cross_company: true to include companies other than the default (usmf).
    """
    _check_entity(entity)
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
