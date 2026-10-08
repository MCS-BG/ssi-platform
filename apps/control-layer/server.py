"""Day 10 control layer: guarded agent loop across business + engineering MCP.

POST   /ask                 {"question":"...", "conversation_id":"optional"}  loop with budgets
POST   /demo                runs the Andreas two-hop sample (engineering PR + business customer)
GET    /conversations/<id>  Day 15: stored turns of one conversation (oldest first)
DELETE /conversations/<id>  Day 15: forget one conversation
GET    /memory              Day 15: non-secret memory status
GET    /healthz

Calls Prompt Guard (fail closed), mcp-server, engineering-mcp, Ollama.
Day 14 adds the productivity slot: m365-mcp (Microsoft 365 via Graph, read-only,
signed in as one personal Microsoft account). M365_MCP_URL points at it.

Day 15 adds conversation memory: each /ask turn (question, tool hops with trimmed
results, answer) is stored in Postgres (table control_layer_turns in the existing
pgvector database) under a conversation_id. The next question with the same id
loads the last MEMORY_TURNS turns and gives them to the planner and to the answer
step, so follow-ups work across every MCP slot. MCPs still never talk to each
other; only the control layer reads and writes memory. psycopg is the only
non-stdlib package and is optional: without it, or without a reachable
Postgres, /ask works exactly as before (no memory) and the reason is logged.

Day 16 (real cross-system answers):
- PLANNER=model (default): the model chooses the tools with native tool calling.
  Tools are built from each slot's MCP tools/list inputSchema (engineering,
  business, productivity), filtered by an allowlist, and every chosen call is
  validated against its schema before it runs. No valid call, an unknown tool
  or bad arguments = automatic fallback to the keyword planner. PLANNER=keyword
  keeps the Day 15 behaviour.
- LLM_BACKEND=ollama (default, /api/chat + /api/generate) or openai (any
  OpenAI-compatible /v1 server such as vLLM: OPENAI_BASE_URL, OPENAI_MODEL,
  optional OPENAI_API_KEY). Used for planning and for the answer.
- ENGINEERING_DEFAULT_REPO replaces the sample repository name; engineering
  tool errors are explained in the answer like productivity ones; Prompt Guard
  refusals still stop the request. Tool results are classified by Prompt Guard
  before the model sees them (RESULT_GUARD).
GET /tools shows the tools currently offered to the model.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

try:  # Day 15 conversation memory; optional so the stdlib-only Day 10 deploy keeps working.
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - depends on the pod
    psycopg = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment,misc]

PORT = int(os.environ.get("PORT", "8080"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama.si-lab.svc.cluster.local:11434").rstrip("/")
MODEL = os.environ.get("MODEL", "llama3.2:3b")
PROMPT_GUARD_URL = os.environ.get(
    "PROMPT_GUARD_URL", "http://prompt-guard.si-lab.svc.cluster.local:8080/classify"
)
BUSINESS_MCP_URL = os.environ.get(
    "BUSINESS_MCP_URL", "http://mcp-server:8000/mcp"
)
ENGINEERING_MCP_URL = os.environ.get(
    "ENGINEERING_MCP_URL", "http://engineering-mcp:8000/mcp"
)
# Day 14 productivity slot (Microsoft 365 / Graph). The Host header must be in
# m365-mcp's MCP_ALLOWED_HOSTS; the short Service name is on its default list.
M365_MCP_URL = os.environ.get(
    "M365_MCP_URL", "http://m365-mcp.si-lab.svc.cluster.local:8000/mcp"
)
M365_MCP_HOST = os.environ.get("M365_MCP_HOST", "m365-mcp:8000")
MAX_TOOL_CALLS = int(os.environ.get("MAX_TOOL_CALLS", "4"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "512"))
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "60"))
# Day 16: GitHub repository used when a question does not name one ("" = leave repo
# out, so the engineering MCP searches every allowed repository of its owner).
ENGINEERING_DEFAULT_REPO = os.environ.get("ENGINEERING_DEFAULT_REPO", "").strip()
# Day 16: answer evidence budget (characters, shared fairly across tool hops).
EVIDENCE_MAX_CHARS = max(1000, int(os.environ.get("EVIDENCE_MAX_CHARS", "6000")))


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Day 15 conversation memory. DATABASE_URL wins; otherwise PG_DSN (libpq key=value,
# password from PGPASSWORD, the same pattern as mcp-server and rag-worker).
MEMORY_ENABLED = _env_bool("MEMORY_ENABLED", True)
MEMORY_DSN = (os.environ.get("DATABASE_URL") or os.environ.get("PG_DSN") or "").strip()
MEMORY_TURNS = max(0, min(int(os.environ.get("MEMORY_TURNS", "6")), 20))
MEMORY_MAX_CHARS = max(500, int(os.environ.get("MEMORY_MAX_CHARS", "2500")))
MEMORY_RESULT_CHARS = max(200, int(os.environ.get("MEMORY_RESULT_CHARS", "2000")))
MEMORY_CONNECT_TIMEOUT = max(1, int(os.environ.get("MEMORY_CONNECT_TIMEOUT", "3")))
MEMORY_RETRY_SECONDS = float(os.environ.get("MEMORY_RETRY_SECONDS", "30"))
MEMORY_TABLE = "control_layer_turns"
CONVERSATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

# ---------------------------------------------------------------------------
# Day 16: model backend and planner settings.
# ---------------------------------------------------------------------------
# LLM_BACKEND: "ollama" (lab) or "openai" (OpenAI-compatible /v1, e.g. vLLM on a rented
# GPU or a cloud GPU node pool). MODEL_API / MODEL_BASE_URL / MODEL_NAME are the older
# Day 12/13 names and still work.
LLM_BACKEND = (os.environ.get("LLM_BACKEND") or os.environ.get("MODEL_API") or "ollama").strip().lower()
if LLM_BACKEND not in ("ollama", "openai"):
    LLM_BACKEND = "ollama"
OPENAI_BASE_URL = (os.environ.get("OPENAI_BASE_URL") or os.environ.get("MODEL_BASE_URL") or "").strip().rstrip("/")
OPENAI_MODEL = (os.environ.get("OPENAI_MODEL") or os.environ.get("MODEL_NAME") or MODEL).strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()  # from a Secret; never logged
# Ollama context window for planning and answers (llama3.2:3b and qwen2.5:3b fit a 4 GB GPU at 4096).
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))

PLANNER = (os.environ.get("PLANNER") or "model").strip().lower()
if PLANNER not in ("model", "keyword"):
    PLANNER = "model"
PLANNER_MAX_ROUNDS = max(1, min(int(os.environ.get("PLANNER_MAX_ROUNDS", "2")), 4))
PLANNER_NUM_PREDICT = int(os.environ.get("PLANNER_NUM_PREDICT", "256"))
TOOLS_CACHE_SECONDS = float(os.environ.get("TOOLS_CACHE_SECONDS", "300"))
TOOL_ARG_MAX_CHARS = int(os.environ.get("TOOL_ARG_MAX_CHARS", "500"))
RESULT_GUARD = _env_bool("RESULT_GUARD", True)
RESULT_GUARD_CHARS = int(os.environ.get("RESULT_GUARD_CHARS", "8000"))

# Read-only tools the model may call. Anything else a slot lists is never offered.
DEFAULT_TOOL_ALLOWLIST = (
    "engineering.list_repos,engineering.list_prs,engineering.get_pr,engineering.list_issues,"
    "engineering.get_issue,engineering.search_code,engineering.get_file,engineering.list_commits,"
    "engineering.get_commit,"
    "business.fo_query,business.fo_list_entities,business.fo_get_entity_metadata,business.search_notes,"
    "productivity.m365_whoami,productivity.m365_list_mail,productivity.m365_get_mail,"
    "productivity.m365_list_events,productivity.m365_list_onedrive,productivity.m365_search_onedrive"
)
TOOL_ALLOWLIST = {
    tuple(item.strip().split(".", 1))
    for item in (os.environ.get("PLANNER_TOOL_ALLOWLIST") or DEFAULT_TOOL_ALLOWLIST).split(",")
    if "." in item
}
SLOT_HINTS = {
    "engineering": "GitHub code, pull requests, issues and commits",
    "business": "Dynamics 365 business records (customers, vendors, sales orders) and internal notes",
    "productivity": "the user's own Microsoft 365 mail, calendar and OneDrive",
}

# Short catalog so llama3.2:3b stays within the 4 GB card budget.
TOOL_CATALOG = """Tools (slot.name):
- engineering.list_repos args: none
- engineering.list_prs args: repo?, state?, limit?
- engineering.get_pr args: repo, number, include_patch?
- engineering.list_issues args: repo?, state?, limit?
- engineering.get_issue args: repo, number, include_comments?
- engineering.search_code args: query, repo?
- engineering.get_file args: repo, path, ref?, start_line?, end_line?
- engineering.list_commits args: repo, ref?, path?, limit?
- engineering.get_commit args: repo, sha
- business.fo_query args: entity, filter?, select?, top?
- business.fo_list_entities args: none
- business.search_notes args: query, k?
- productivity.m365_whoami args: none
- productivity.m365_list_mail args: top?, folder?, unread_only?
- productivity.m365_get_mail args: message_id
- productivity.m365_list_events args: days?, top?
- productivity.m365_list_onedrive args: path?
- productivity.m365_search_onedrive args: query
Reply with ONE line only:
TOOL slot.name {"arg":"value"}
or
FINAL your short answer
"""


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    accept: str | None = None,
    host: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": accept or "application/json"}
    if host:
        headers["Host"] = host
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout or HTTP_TIMEOUT) as resp:
            body = resp.read()
            if not body:
                return None
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype or body[:1] in (b"{", b"["):
                return json.loads(body.decode("utf-8"))
            return body.decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code} from {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"unreachable {url}: {e.reason}") from e


def classify(text: str) -> dict[str, Any]:
    """Fail closed: any Guard error stops the loop."""
    try:
        result = http_json("POST", PROMPT_GUARD_URL, {"text": text})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Prompt Guard unavailable, request refused: {e}") from e
    if not isinstance(result, dict) or "label" not in result:
        raise RuntimeError("Prompt Guard unavailable, request refused: bad response")
    if result.get("label") == "malicious":
        raise RuntimeError(
            f"Refused by Prompt Guard: malicious_score={result.get('malicious_score')}"
        )
    return result


def mcp_call(url: str, name: str, arguments: dict[str, Any] | None = None, host: str | None = None) -> dict[str, Any]:
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments or {}},
    }
    raw = http_json(
        "POST",
        url,
        body,
        accept="application/json, text/event-stream",
        host=host,
    )
    if not isinstance(raw, dict):
        raise RuntimeError(f"MCP bad response from {url}")
    if "error" in raw:
        raise RuntimeError(f"MCP error: {raw['error']}")
    result = raw.get("result") or {}
    if result.get("isError"):
        text = " ".join(
            c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)
        )
        raise RuntimeError(f"tool error: {text}")
    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]
    content = result.get("content") or []
    if content and isinstance(content[0], dict) and "text" in content[0]:
        try:
            return json.loads(content[0]["text"])
        except json.JSONDecodeError:
            return {"text": content[0]["text"]}
    return result


def call_tool(slot: str, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    classify(json.dumps({"slot": slot, "tool": name, "arguments": arguments or {}}, sort_keys=True))
    if slot == "engineering":
        # Short Host matches TransportSecuritySettings on MCP servers (and works for the sample).
        return mcp_call(ENGINEERING_MCP_URL, name, arguments, host="engineering-mcp:8000")
    if slot == "business":
        return mcp_call(BUSINESS_MCP_URL, name, arguments, host="mcp-server:8000")
    if slot == "productivity":
        return mcp_call(M365_MCP_URL, name, arguments, host=M365_MCP_HOST)
    raise RuntimeError(f"unknown slot: {slot}")


EXPLAINED_ERROR_SLOTS = ("productivity", "engineering")


def guard_result(slot: str, name: str, result: Any) -> Any:
    """Day 16: classify a tool result before any model reads it (indirect prompt
    injection through mail, issues, code ...). Flagged = withheld. Guard down = refused."""
    if not RESULT_GUARD:
        return result
    text = json.dumps(result, default=str)[:RESULT_GUARD_CHARS]
    try:
        verdict = http_json("POST", PROMPT_GUARD_URL, {"text": text})
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Prompt Guard unavailable, request refused: {e}") from e
    if not isinstance(verdict, dict) or "label" not in verdict:
        raise RuntimeError("Prompt Guard unavailable, request refused: bad response")
    if verdict.get("label") == "malicious":
        return {"withheld": f"[withheld by Prompt Guard: result of {slot}.{name}, malicious_score={verdict.get('malicious_score')}]"}
    return result


def run_step(step: dict[str, Any], model_chosen: bool = False) -> dict[str, Any]:
    """call_tool, except a productivity or engineering tool error (for example "not
    signed in to Microsoft 365", or a GitHub 404 / rate limit) becomes an error result
    the answer can explain. A call whose arguments the model chose (model planner) gets
    the same treatment in every slot, because a small model can write a filter the
    business system rejects; that must not sink the other systems' results.
    Prompt Guard refusals, from the control layer or from the MCP itself, still stop the
    loop (fail closed), and so do business tool errors in keyword / explicit plans."""
    try:
        result = call_tool(step["slot"], step["name"], step.get("arguments") or {})
    except RuntimeError as e:
        msg = str(e)
        explain = model_chosen or step["slot"] in EXPLAINED_ERROR_SLOTS
        if explain and msg.startswith("tool error:") and "Prompt Guard" not in msg:
            return {"error": msg}
        raise
    return guard_result(step["slot"], step["name"], result)


def active_model() -> str:
    return OPENAI_MODEL if LLM_BACKEND == "openai" else MODEL


def _openai_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {OPENAI_API_KEY}"} if OPENAI_API_KEY else {}


def _openai_chat(payload: dict[str, Any]) -> dict[str, Any]:
    if not OPENAI_BASE_URL:
        raise RuntimeError("LLM_BACKEND=openai but OPENAI_BASE_URL is not set")
    result = http_json("POST", f"{OPENAI_BASE_URL}/chat/completions", payload, extra_headers=_openai_headers())
    if not isinstance(result, dict) or not result.get("choices"):
        raise RuntimeError("OpenAI-compatible backend: bad response")
    return result


def ollama_generate(prompt: str, num_predict: int | None = None) -> dict[str, Any]:
    """One completion for the answer step and the text loop. The name is kept from
    Day 10; with LLM_BACKEND=openai it calls /v1/chat/completions instead. Returns the
    Ollama shape: response, prompt_eval_count, eval_count."""
    limit = MAX_TOKENS if num_predict is None else min(num_predict, MAX_TOKENS)
    if LLM_BACKEND == "openai":
        result = _openai_chat(
            {
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": limit,
            }
        )
        usage = result.get("usage") or {}
        return {
            "response": (result["choices"][0].get("message") or {}).get("content") or "",
            "prompt_eval_count": usage.get("prompt_tokens"),
            "eval_count": usage.get("completion_tokens"),
        }
    payload = {
        "model": active_model(),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": limit, "num_ctx": OLLAMA_NUM_CTX},
    }
    result = http_json("POST", f"{OLLAMA_URL}/api/generate", payload)
    if not isinstance(result, dict):
        raise RuntimeError("Ollama bad response")
    return result


def llm_chat(messages: list[dict[str, Any]], tools: list[dict[str, Any]], num_predict: int) -> dict[str, Any]:
    """Day 16: one chat turn with native tool calling. Returns
    {"content", "tool_calls": [{"id", "name", "arguments"}], "usage", "assistant"}
    where "assistant" is the message to append before the tool results."""
    limit = min(num_predict, MAX_TOKENS)
    if LLM_BACKEND == "openai":
        result = _openai_chat(
            {
                "model": OPENAI_MODEL,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0,
                "max_tokens": limit,
            }
        )
        msg = result["choices"][0].get("message") or {}
        calls = []
        for i, tc in enumerate(msg.get("tool_calls") or []):
            fn = tc.get("function") or {}
            calls.append({"id": tc.get("id") or f"call_{i}", "name": fn.get("name"), "arguments": fn.get("arguments")})
        usage = result.get("usage") or {}
        assistant = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}
        return {
            "content": msg.get("content") or "",
            "tool_calls": calls,
            "usage": {"prompt_eval_count": usage.get("prompt_tokens"), "eval_count": usage.get("completion_tokens")},
            "assistant": assistant,
        }
    payload = {
        "model": active_model(),
        "messages": messages,
        "tools": tools,
        "stream": False,
        "options": {"temperature": 0, "num_predict": limit, "num_ctx": OLLAMA_NUM_CTX},
    }
    result = http_json("POST", f"{OLLAMA_URL}/api/chat", payload)
    if not isinstance(result, dict) or not isinstance(result.get("message"), dict):
        raise RuntimeError("Ollama bad response from /api/chat")
    msg = result["message"]
    calls = []
    for i, tc in enumerate(msg.get("tool_calls") or []):
        fn = tc.get("function") or {}
        calls.append({"id": tc.get("id") or f"call_{i}", "name": fn.get("name"), "arguments": fn.get("arguments")})
    assistant = {"role": "assistant", "content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or []}
    return {
        "content": msg.get("content") or "",
        "tool_calls": calls,
        "usage": {"prompt_eval_count": result.get("prompt_eval_count"), "eval_count": result.get("eval_count")},
        "assistant": assistant,
    }


def parse_model_line(text: str) -> tuple[str, Any]:
    line = (text or "").strip().splitlines()[0].strip() if text else ""
    if line.upper().startswith("FINAL"):
        return "final", line[5:].strip(" :")
    m = re.match(r"TOOL\s+(engineering|business|productivity)\.([A-Za-z0-9_]+)\s+(\{.*\})\s*$", line, re.I)
    if m:
        try:
            args = json.loads(m.group(3))
        except json.JSONDecodeError:
            args = {}
        return "tool", {"slot": m.group(1).lower(), "name": m.group(2), "arguments": args}
    m2 = re.match(r"TOOL\s+(engineering|business|productivity)\.([A-Za-z0-9_]+)\s*$", line, re.I)
    if m2:
        return "tool", {"slot": m2.group(1).lower(), "name": m2.group(2), "arguments": {}}
    return "final", line or text.strip()


# ---------------------------------------------------------------------------
# Day 15: conversation memory (recall across questions), stored in Postgres.
# ---------------------------------------------------------------------------
class MemoryUnavailable(RuntimeError):
    """Postgres is not configured, not reachable, or failed a query."""


def _log(msg: str) -> None:
    print(f"memory: {msg}", flush=True)


def _dsn_label(dsn: str) -> str:
    """host/db/user only; never the password."""
    try:
        from psycopg.conninfo import conninfo_to_dict

        info = conninfo_to_dict(dsn)
        return f"host={info.get('host', '?')} dbname={info.get('dbname', '?')} user={info.get('user', '?')}"
    except Exception:  # noqa: BLE001
        return "dsn=(unparsed)"


class ConversationMemory:
    """Short-lived connections per call (low volume, one replica). If Postgres
    fails, calls raise MemoryUnavailable and the store backs off for
    MEMORY_RETRY_SECONDS so a down database does not slow every question."""

    def __init__(self, dsn: str, enabled: bool) -> None:
        self.dsn = dsn
        self.reason = ""
        if not enabled:
            self.reason = "MEMORY_ENABLED=false"
        elif psycopg is None:
            self.reason = "psycopg is not installed"
        elif not dsn:
            self.reason = "DATABASE_URL / PG_DSN not set"
        self.enabled = not self.reason
        self._lock = threading.Lock()
        self._schema_ready = False
        self._down_until = 0.0
        self.last_error = ""

    def status(self) -> dict[str, Any]:
        left = max(0.0, self._down_until - time.monotonic())
        return {
            "enabled": self.enabled,
            "reason": self.reason or None,
            "table": MEMORY_TABLE,
            "turns": MEMORY_TURNS,
            "max_chars": MEMORY_MAX_CHARS,
            "schema_ready": self._schema_ready,
            "reachable": self.enabled and left == 0.0 and not self.last_error,
            "retry_in_seconds": round(left, 1),
            "last_error": self.last_error or None,
        }

    def _mark_down(self, err: Exception) -> None:
        self.last_error = f"{type(err).__name__}: {' '.join(str(err).split())[:200]}"
        self._down_until = time.monotonic() + MEMORY_RETRY_SECONDS
        _log(f"postgres unavailable, answering without memory for {MEMORY_RETRY_SECONDS:.0f}s ({self.last_error})")

    def _connect(self) -> Any:
        if not self.enabled:
            raise MemoryUnavailable(f"conversation memory is disabled ({self.reason})")
        if time.monotonic() < self._down_until:
            raise MemoryUnavailable(f"conversation memory unavailable ({self.last_error})")
        try:
            conn = psycopg.connect(
                self.dsn,
                connect_timeout=MEMORY_CONNECT_TIMEOUT,
                autocommit=True,
                options="-c statement_timeout=5000",
            )
        except psycopg.Error as e:
            self._mark_down(e)
            raise MemoryUnavailable(f"conversation memory unavailable ({self.last_error})") from e
        try:
            if not self._schema_ready:
                self._ensure_schema(conn)
        except psycopg.Error as e:
            conn.close()
            self._mark_down(e)
            raise MemoryUnavailable(f"conversation memory unavailable ({self.last_error})") from e
        if self.last_error:
            _log("postgres reachable again, memory back on")
            self.last_error = ""
        return conn

    def _ensure_schema(self, conn: Any) -> None:
        with self._lock:
            if self._schema_ready:
                return
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {MEMORY_TABLE} (
                    id              bigserial PRIMARY KEY,
                    conversation_id text        NOT NULL,
                    created_at      timestamptz NOT NULL DEFAULT now(),
                    question        text        NOT NULL,
                    tool_calls      jsonb       NOT NULL DEFAULT '[]'::jsonb,
                    answer          text        NOT NULL DEFAULT '',
                    mode            text,
                    ok              boolean     NOT NULL DEFAULT true
                )"""
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {MEMORY_TABLE}_conv_idx "
                f"ON {MEMORY_TABLE} (conversation_id, id DESC)"
            )
            self._schema_ready = True
            _log(f"table {MEMORY_TABLE} ready")

    def _run(self, fn: Any) -> Any:
        conn = self._connect()
        try:
            return fn(conn)
        except psycopg.Error as e:
            self._mark_down(e)
            raise MemoryUnavailable(f"conversation memory unavailable ({self.last_error})") from e
        finally:
            conn.close()

    def startup(self) -> None:
        if not self.enabled:
            _log(f"off ({self.reason}); /ask works without recall")
            return
        _log(f"on, postgres {_dsn_label(self.dsn)}, last {MEMORY_TURNS} turns, {MEMORY_MAX_CHARS} chars")
        try:
            self._run(lambda conn: None)
        except MemoryUnavailable:
            pass  # already logged; retried on the next question

    def load(self, conversation_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        def q(conn: Any) -> list[dict[str, Any]]:
            rows = conn.execute(
                f"SELECT id, created_at, question, tool_calls, answer, mode, ok FROM {MEMORY_TABLE} "
                "WHERE conversation_id = %s ORDER BY id DESC LIMIT %s",
                (conversation_id, limit),
            ).fetchall()
            return [_row_to_turn(r) for r in reversed(rows)]

        return self._run(q)

    def save(self, conversation_id: str, turn: dict[str, Any]) -> None:
        def q(conn: Any) -> None:
            conn.execute(
                f"INSERT INTO {MEMORY_TABLE} (conversation_id, question, tool_calls, answer, mode, ok) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    conversation_id,
                    turn["question"],
                    Jsonb(turn["tool_calls"]),
                    turn.get("answer") or "",
                    turn.get("mode"),
                    bool(turn.get("ok", True)),
                ),
            )

        self._run(q)

    def forget(self, conversation_id: str) -> int:
        def q(conn: Any) -> int:
            cur = conn.execute(f"DELETE FROM {MEMORY_TABLE} WHERE conversation_id = %s", (conversation_id,))
            return int(cur.rowcount or 0)

        return self._run(q)


def _row_to_turn(row: Any) -> dict[str, Any]:
    tid, created_at, question, tool_calls, answer, mode, ok = row
    return {
        "id": tid,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
        "question": question,
        "tool_calls": tool_calls or [],
        "answer": answer,
        "mode": mode,
        "ok": ok,
    }


MEMORY = ConversationMemory(MEMORY_DSN, MEMORY_ENABLED)


def valid_conversation_id(value: Any) -> str:
    cid = str(value or "")
    if not CONVERSATION_ID_RE.fullmatch(cid):
        raise RuntimeError(
            "invalid conversation_id: use 1-128 characters from letters, digits, '_', '.', ':' and '-'"
        )
    return cid


def trim_result(result: Any) -> Any:
    """Keep stored tool results small; big results become a text preview."""
    text = json.dumps(result, default=str)
    if len(text) <= MEMORY_RESULT_CHARS:
        return result
    return {"truncated": True, "preview": text[:MEMORY_RESULT_CHARS]}


def memory_context(turns: list[dict[str, Any]], max_chars: int = MEMORY_MAX_CHARS) -> tuple[str, int]:
    """Earlier turns as plain text, newest kept first when the size cap is hit.
    Returns (text oldest-first, number of turns included)."""
    blocks: list[str] = []
    used = 0
    for turn in reversed(turns):
        lines = [f"Q: {str(turn.get('question') or '')[:400]}"]
        for hop in turn.get("tool_calls") or []:
            res = json.dumps(hop.get("result"), default=str)[:300]
            args = json.dumps(hop.get("arguments") or {}, sort_keys=True)
            lines.append(f"Tool {hop.get('slot')}.{hop.get('name')} {args} -> {res}")
        lines.append(f"A: {str(turn.get('answer') or '')[:600]}")
        block = "\n".join(lines)
        if used + len(block) + 1 > max_chars:
            if not blocks:
                blocks.append(block[:max_chars])
            break
        blocks.append(block)
        used += len(block) + 1
    return "\n".join(reversed(blocks)), len(blocks)


M365_WORDS = {
    "m365_list_events": r"\b(calendar|meetings?|events?|schedule|appointments?)\b",
    "m365_list_mail": r"\b(e-?mails?|mail|inbox|outlook|messages)\b",
    "m365_list_onedrive": r"\b(onedrive|my files|my documents)\b",
    "m365_whoami": r"\b(m365|microsoft 365|who am i|signed in)\b",
}
M365_ARGS = {
    "m365_list_events": {"days": 7, "top": 20},
    "m365_list_mail": {"top": 10},
    "m365_list_onedrive": {},
    "m365_whoami": {},
}


def productivity_plan(question: str) -> list[dict[str, Any]]:
    """Productivity (Microsoft 365) steps for questions about mail, calendar or OneDrive."""
    q = question.lower()
    return [
        {"slot": "productivity", "name": name, "arguments": tune_args(question, name, dict(M365_ARGS[name]))}
        for name, pattern in M365_WORDS.items()
        if re.search(pattern, q)
    ]


def tune_args(question: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Day 15: read time windows and counts from the question ("next week",
    "tomorrow", "unread", "5 emails") so a follow-up can change the window of
    the tool it inherits from memory."""
    q = question.lower()
    if name == "m365_list_events":
        m = re.search(r"\b(\d{1,2})\s+days?\b", q)
        if m:
            args["days"] = max(1, min(int(m.group(1)), 31))
        elif re.search(r"\bnext\s+month\b|\bthis\s+month\b|\b30\s+days\b", q):
            args["days"] = 31
        elif re.search(r"\bnext\s+week\b|\bweek\s+after\b", q):
            args["days"] = 14
        elif re.search(r"\btomorrow\b", q):
            args["days"] = 2
        elif re.search(r"\btoday\b|\btonight\b", q):
            args["days"] = 1
        elif re.search(r"\bthis\s+week\b", q):
            args["days"] = 7
    elif name == "m365_list_mail":
        if re.search(r"\bunread\b", q):
            args["unread_only"] = True
        m = re.search(r"\b(\d{1,2})\s+(?:e-?mails?|mails?|messages)\b", q)
        if m:
            args["top"] = max(1, min(int(m.group(1)), 25))
        elif re.search(r"\bmore\b|\bolder\b", q):
            args["top"] = min(25, int(args.get("top") or 10) * 2)
    return args


def eng_args(**extra: Any) -> dict[str, Any]:
    """Day 16: engineering arguments with the default repository, or no repo at all."""
    args = dict(extra)
    if ENGINEERING_DEFAULT_REPO:
        args["repo"] = ENGINEERING_DEFAULT_REPO
    return args


# Whole words only: "pr" must not fire on "prompt", "project", "price" or "productivity".
ENG_WORDS = re.compile(
    r"\b(prs?|pull requests?|issues?|repos?|repository|repositories|invoice-service|engineering"
    r"|commits?|code|github)\b"
)
BIZ_WORDS = re.compile(r"\b(customers?|accounts?|invoices?|fo_\w*|business|sales orders?|d365)\b")


def explicit_plan(question: str) -> list[dict[str, Any]]:
    """Steps the question asks for by itself (keywords), without any fallback."""
    q = question.lower()
    steps: list[dict[str, Any]] = productivity_plan(question)
    wants_eng = bool(ENG_WORDS.search(q))
    wants_biz = bool(BIZ_WORDS.search(q))
    if wants_eng and re.search(r"\b(prs?|pull requests?)\b", q):
        steps.append({"slot": "engineering", "name": "list_prs", "arguments": eng_args(state="open", limit=5)})
    elif wants_eng and re.search(r"\bissues?\b", q):
        steps.append({"slot": "engineering", "name": "list_issues", "arguments": eng_args(state="open", limit=5)})
    elif wants_eng and re.search(r"\bcommits?\b|\bchanged\b|\blatest change", q):
        steps.append({"slot": "engineering", "name": "list_commits", "arguments": eng_args(limit=5)})
    elif wants_eng:
        steps.append({"slot": "engineering", "name": "list_prs", "arguments": eng_args(state="open", limit=5)})
    if wants_biz:
        steps.append(
            {
                "slot": "business",
                "name": "fo_query",
                "arguments": {
                    "entity": "CustomersV3",
                    "filter": "CustomerAccount eq 'DEMO-C0001'",
                    "select": "CustomerAccount,OrganizationName,AddressCity,CustomerGroupId",
                    "top": 1,
                },
            }
        )
    return steps


def follow_up_plan(question: str, turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Day 15: a question with no tool keywords of its own ("and what about next
    week?") repeats the tools of the latest remembered turn that used any, with
    arguments re-read from the new question. Results are never reused; tools run again."""
    for turn in reversed(turns):
        hops = [h for h in (turn.get("tool_calls") or []) if h.get("slot") in ("engineering", "business", "productivity")]
        if not hops:
            continue
        steps: list[dict[str, Any]] = []
        for hop in hops:
            args = dict(hop.get("arguments") or {})
            if hop.get("name") == "search_notes":
                args["query"] = f"{turn.get('question', '')} {question}".strip()[:200]
            steps.append({"slot": hop["slot"], "name": hop["name"], "arguments": tune_args(question, hop["name"], args)})
        return steps
    return []


def plan_with_source(question: str, turns: list[dict[str, Any]] | None = None) -> tuple[list[dict[str, Any]], str]:
    """(steps, source): source is "question", "memory" (follow-up) or "fallback"."""
    steps = explicit_plan(question)
    source = "question"
    if not steps and turns:
        steps = follow_up_plan(question, turns)
        source = "memory"
    if not steps:
        steps = [{"slot": "business", "name": "search_notes", "arguments": {"query": question[:200], "k": 3}}]
        source = "fallback"
    return steps[:MAX_TOOL_CALLS], source


def planner(question: str, turns: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Deterministic two-hop plan for the Andreas sample and close variants,
    plus productivity steps when the question is about mail, calendar or OneDrive.
    Day 15: with remembered turns, a keyword-free follow-up inherits the last tools."""
    return plan_with_source(question, turns)[0]


def compact_evidence(tool_hops: list[dict[str, Any]], max_chars: int = EVIDENCE_MAX_CHARS) -> str:
    """Day 16: compact JSON (no indent) and a fair share of the budget per hop, so the
    last tool of a multi-tool question is not cut off by the first one."""
    if not tool_hops:
        return "[]"
    share = max(400, max_chars // len(tool_hops))
    lines = []
    for hop in tool_hops:
        result = json.dumps(hop.get("result"), separators=(",", ":"), default=str)
        if len(result) > share:
            result = result[:share] + "...(truncated)"
        args = json.dumps(hop.get("arguments") or {}, separators=(",", ":"), sort_keys=True)
        lines.append(f"{hop.get('slot')}.{hop.get('name')} {args} -> {result}")
    return "\n".join(lines)[:max_chars + 200]


def synthesize(question: str, tool_hops: list[dict[str, Any]], memory_text: str = "") -> tuple[str, dict[str, Any]]:
    evidence = compact_evidence(tool_hops)
    if memory_text:
        prompt = (
            "Answer the question using ONLY the tool results and the earlier conversation. "
            "Use the earlier conversation to resolve words like 'that', 'them' or 'next'. "
            "Be concise (3-6 sentences).\n"
            f"Earlier in this conversation (oldest first):\n{memory_text}\n\n"
            f"Question: {question}\n"
            f"Tool results:\n{evidence}\n"
            "Answer:"
        )
    else:
        prompt = (
            "Answer the question using ONLY the tool results. Be concise (3-6 sentences).\n"
            f"Question: {question}\n"
            f"Tool results:\n{evidence}\n"
            "Answer:"
        )
    gen = ollama_generate(prompt, num_predict=min(256, MAX_TOKENS))
    answer = (gen.get("response") or "").strip()
    usage = {
        "prompt_eval_count": gen.get("prompt_eval_count"),
        "eval_count": gen.get("eval_count"),
    }
    return answer, usage


# ---------------------------------------------------------------------------
# Day 16: the model chooses the tools (native tool calling).
# ---------------------------------------------------------------------------
SLOT_ENDPOINTS = {
    "engineering": (ENGINEERING_MCP_URL, "engineering-mcp:8000"),
    "business": (BUSINESS_MCP_URL, "mcp-server:8000"),
    "productivity": (M365_MCP_URL, M365_MCP_HOST),
}
_TOOLS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_TOOLS_LOCK = threading.Lock()


def mcp_list_tools(url: str, host: str) -> list[dict[str, Any]]:
    raw = http_json(
        "POST",
        url,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        accept="application/json, text/event-stream",
        host=host,
        timeout=min(HTTP_TIMEOUT, 10.0),
    )
    if not isinstance(raw, dict) or "error" in raw:
        raise RuntimeError(f"tools/list failed at {url}")
    tools = (raw.get("result") or {}).get("tools")
    if not isinstance(tools, list):
        raise RuntimeError(f"tools/list returned no tools at {url}")
    return [t for t in tools if isinstance(t, dict) and t.get("name")]


def _simplify_prop(prop: Any) -> dict[str, Any]:
    if not isinstance(prop, dict):
        return {"type": "string"}
    base = dict(prop)
    branches = prop.get("anyOf") or prop.get("oneOf")
    if isinstance(branches, list):
        non_null = [b for b in branches if isinstance(b, dict) and b.get("type") != "null"]
        if len(non_null) == 1:
            base = {**{k: v for k, v in prop.items() if k not in ("anyOf", "oneOf")}, **non_null[0]}
    out = {k: base[k] for k in ("type", "description", "enum", "minimum", "maximum", "items") if base.get(k) is not None}
    if base.get("default") is not None:
        out["default"] = base["default"]
    if isinstance(out.get("type"), list):  # ["string", "null"]
        types = [t for t in out["type"] if t != "null"]
        out["type"] = types[0] if types else "string"
    out.setdefault("type", "string")
    if "description" in out:
        out["description"] = str(out["description"])[:200]
    return out


def simplify_schema(schema: Any) -> dict[str, Any]:
    """MCP inputSchema (JSON Schema from the MCP SDK or hand-written) -> the small,
    flat schema sent to the model and used to validate its arguments."""
    schema = schema if isinstance(schema, dict) else {}
    props = {k: _simplify_prop(v) for k, v in (schema.get("properties") or {}).items()}
    out: dict[str, Any] = {"type": "object", "properties": props}
    required = [r for r in (schema.get("required") or []) if r in props]
    if required:
        out["required"] = required
    return out


def discover_tools() -> dict[str, dict[str, Any]]:
    """Tools offered to the model, keyed by function name "<slot>_<tool>". Built from
    each slot's tools/list and the allowlist; cached TOOLS_CACHE_SECONDS. A slot that
    does not answer is left out (retried after 30 s), so one MCP being down does not
    stop planning for the others."""
    now = time.monotonic()
    offered: dict[str, dict[str, Any]] = {}
    for slot, (url, host) in SLOT_ENDPOINTS.items():
        with _TOOLS_LOCK:
            cached = _TOOLS_CACHE.get(slot)
        if cached and now - cached[0] < TOOLS_CACHE_SECONDS:
            tools = cached[1]
        else:
            try:
                tools = mcp_list_tools(url, host)
            except Exception as e:  # noqa: BLE001
                print(f"planner: tools/list for {slot} failed ({' '.join(str(e).split())[:160]})", flush=True)
                tools = cached[1] if cached else []
                with _TOOLS_LOCK:
                    _TOOLS_CACHE[slot] = (now - TOOLS_CACHE_SECONDS + 30, tools)
            else:
                with _TOOLS_LOCK:
                    _TOOLS_CACHE[slot] = (now, tools)
        for tool in tools:
            name = str(tool["name"])
            if (slot, name) not in TOOL_ALLOWLIST:
                continue
            raw_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
            schema = simplify_schema(raw_schema)
            offered[f"{slot}_{name}"] = {
                "slot": slot,
                "name": name,
                "description": " ".join(str(tool.get("description") or "").split())[:300],
                "schema": schema,
                # A tool that publishes no properties (the Day 10 engineering sample) takes
                # plain scalar arguments, still length-checked.
                "open": not schema["properties"] and raw_schema.get("additionalProperties", True) is not False,
            }
    return offered


def tool_definitions(offered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Same function-tool format for Ollama /api/chat and OpenAI /v1/chat/completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": fname,
                "description": f"[{t['slot']}: {SLOT_HINTS.get(t['slot'], t['slot'])}] {t['description']}",
                "parameters": t["schema"],
            },
        }
        for fname, t in offered.items()
    ]


def _coerce(kind: Any, value: Any) -> tuple[bool, Any]:
    if kind == "integer":
        if isinstance(value, bool):
            return False, value
        if isinstance(value, int):
            return True, value
        if isinstance(value, float) and value.is_integer():
            return True, int(value)
        if isinstance(value, str) and re.fullmatch(r"-?\d{1,9}", value.strip()):
            return True, int(value.strip())
        return False, value
    if kind == "number":
        if isinstance(value, bool):
            return False, value
        if isinstance(value, (int, float)):
            return True, value
        try:
            return True, float(str(value).strip())
        except ValueError:
            return False, value
    if kind == "boolean":
        if isinstance(value, bool):
            return True, value
        if isinstance(value, str) and value.strip().lower() in ("true", "false"):
            return True, value.strip().lower() == "true"
        return False, value
    if kind == "string":
        if isinstance(value, str):
            return True, value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True, str(value)
        return False, value
    if kind == "array":
        return isinstance(value, list), value
    if kind == "object":
        return isinstance(value, dict), value
    return True, value


def validate_args(schema: dict[str, Any], args: Any, open_schema: bool = False) -> tuple[dict[str, Any] | None, str]:
    """Check model-chosen arguments against the tool's schema. Unknown arguments are
    dropped, empty ones count as omitted, safe type fixes ("5" -> 5) are applied;
    wrong types, values outside enum/minimum/maximum, over-long strings and missing
    required arguments make the call invalid."""
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object"
    props = schema.get("properties") or {}
    clean: dict[str, Any] = {}
    if open_schema and not props:
        for key, value in args.items():
            if value is None or value == "":
                continue
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,40}", key):
                return None, "argument names must be simple identifiers"
            if not isinstance(value, (str, int, float, bool)):
                return None, f"argument '{key}' must be a plain value"
            if isinstance(value, str) and len(value) > TOOL_ARG_MAX_CHARS:
                return None, f"argument '{key}' longer than {TOOL_ARG_MAX_CHARS} characters"
            clean[key] = value
        return clean, ""
    for key, value in args.items():
        if key not in props or value is None or value == "":
            continue
        prop = props[key]
        kind = prop.get("type")
        ok, value = _coerce(kind, value)
        if not ok:
            return None, f"argument '{key}' must be {kind}"
        if "enum" in prop and value not in prop["enum"]:
            return None, f"argument '{key}' must be one of {prop['enum']}"
        if kind in ("integer", "number"):
            if "minimum" in prop and value < prop["minimum"]:
                return None, f"argument '{key}' below minimum {prop['minimum']}"
            if "maximum" in prop and value > prop["maximum"]:
                return None, f"argument '{key}' above maximum {prop['maximum']}"
        if isinstance(value, str) and len(value) > TOOL_ARG_MAX_CHARS:
            return None, f"argument '{key}' longer than {TOOL_ARG_MAX_CHARS} characters"
        clean[key] = value
    missing = [r for r in schema.get("required") or [] if r not in clean]
    if missing:
        return None, f"missing required argument(s): {', '.join(missing)}"
    return clean, ""


def resolve_tool(name: Any, offered: dict[str, dict[str, Any]]) -> str | None:
    """Function name from the model -> offered key. Accepts "slot_tool", "slot.tool"
    and a bare tool name when it is unique."""
    if not isinstance(name, str) or not name:
        return None
    if name in offered:
        return name
    if "." in name and name.replace(".", "_", 1) in offered:
        return name.replace(".", "_", 1)
    bare = [k for k, t in offered.items() if t["name"] == name]
    return bare[0] if len(bare) == 1 else None


def validate_call(call: dict[str, Any], offered: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    fname = resolve_tool(call.get("name"), offered)
    if fname is None:
        return None, f"unknown tool: {str(call.get('name'))[:80]}"
    tool = offered[fname]
    if (tool["slot"], tool["name"]) not in TOOL_ALLOWLIST:
        return None, f"tool not allowed: {tool['slot']}.{tool['name']}"
    args = call.get("arguments")
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError:
            return None, f"{fname}: arguments are not valid JSON"
    if args is None:
        args = {}
    if (
        isinstance(args, dict)
        and tool["slot"] == "engineering"
        and ENGINEERING_DEFAULT_REPO
        and "repo" in (tool["schema"].get("required") or [])
        and not args.get("repo")
    ):
        args = {**args, "repo": ENGINEERING_DEFAULT_REPO}
    clean, why = validate_args(tool["schema"], args, bool(tool.get("open")))
    if clean is None:
        return None, f"{fname}: {why}"
    return {"slot": tool["slot"], "name": tool["name"], "arguments": clean, "fname": fname}, ""


def calls_from_content(content: str) -> list[dict[str, Any]]:
    """Small models sometimes write the tool call as JSON text instead of a structured
    tool call. Accept {"name": ..., "arguments"|"parameters": {...}} or a list of them."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("\n") + 1:] if "\n" in text else text
    if not text or text[0] not in "[{":
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data if isinstance(data, list) else [data]
    calls = []
    for i, item in enumerate(items):
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            args = item.get("arguments", item.get("parameters", {}))
            calls.append({"id": f"call_{i}", "name": item["name"], "arguments": args})
    return calls


def planner_system_prompt() -> str:
    slots = "; ".join(f"{s} = {h}" for s, h in SLOT_HINTS.items())
    repo = (
        f" The default GitHub repository is {ENGINEERING_DEFAULT_REPO}; use it when the question does not name one."
        if ENGINEERING_DEFAULT_REPO
        else ""
    )
    return (
        "You choose tool calls for SSI, a read-only assistant. Call the tools needed to answer the "
        f"question, at most {MAX_TOOL_CALLS} calls in total. Systems: {slots}. "
        "When the question needs data from several systems, call one tool for each system. "
        "Meetings and calendar questions use m365_list_events; mail questions use m365_list_mail. "
        "For business records, query the entity with a simple filter on its key field, or no filter. "
        "Only fill in arguments you are sure about; leave optional ones out. "
        "Greetings and questions about you need no tool: answer without a tool call. "
        "If earlier conversation is given, use it to resolve follow-ups such as 'that person' or "
        f"'next week'.{repo} When you have enough results, answer in one short sentence without a tool call."
    )


def _assistant_message(steps: list[dict[str, Any]]) -> dict[str, Any]:
    if LLM_BACKEND == "openai":
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": s["id"], "type": "function", "function": {"name": s["fname"], "arguments": json.dumps(s["arguments"])}}
                for s in steps
            ],
        }
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": s["fname"], "arguments": s["arguments"]}} for s in steps],
    }


def _tool_message(step: dict[str, Any], result: Any) -> dict[str, Any]:
    text = json.dumps(result, separators=(",", ":"), default=str)[:1500]
    if LLM_BACKEND == "openai":
        return {"role": "tool", "tool_call_id": step["id"], "content": text}
    return {"role": "tool", "tool_name": step["fname"], "content": text}


def run_model_planner(
    question: str, guard: dict[str, Any], memory_text: str
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Returns (response, planner_info). response None = fall back to the keyword
    planner (planner_info["fallback_reason"] says why)."""
    info: dict[str, Any] = {"requested": "model", "used": "model", "backend": LLM_BACKEND, "rounds": 0, "rejected": []}
    offered = discover_tools()
    info["tools_offered"] = len(offered)
    if not offered:
        info.update(used="keyword", fallback_reason="no MCP tools discovered")
        return None, info
    tools = tool_definitions(offered)
    user = (f"Earlier in this conversation (oldest first):\n{memory_text[-MEMORY_MAX_CHARS:]}\n\n" if memory_text else "")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": planner_system_prompt()},
        {"role": "user", "content": user + f"Question: {question.strip()}"},
    ]
    hops: list[dict[str, Any]] = []
    seen: set[str] = set()
    tokens = 0
    for rnd in range(PLANNER_MAX_ROUNDS):
        if len(hops) >= MAX_TOOL_CALLS:
            break
        try:
            reply = llm_chat(messages, tools, PLANNER_NUM_PREDICT)
        except Exception as e:  # noqa: BLE001
            if rnd == 0:
                info.update(used="keyword", fallback_reason=f"model unavailable: {' '.join(str(e).split())[:160]}")
                return None, info
            break
        info["rounds"] = rnd + 1
        tokens += int(reply["usage"].get("eval_count") or 0) + int(reply["usage"].get("prompt_eval_count") or 0)
        calls = reply["tool_calls"] or calls_from_content(reply["content"])
        if not calls:
            if rnd == 0:
                info.update(used="keyword", fallback_reason="model returned no tool calls")
                return None, info
            break
        steps: list[dict[str, Any]] = []
        for call in calls:
            step, why = validate_call(call, offered)
            if step is None:
                info["rejected"].append(why)
                if rnd == 0:
                    info.update(used="keyword", fallback_reason=f"invalid tool call: {why}")
                    return None, info
                steps = []
                break
            key = json.dumps([step["slot"], step["name"], step["arguments"]], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            step["id"] = call.get("id") or f"call_{rnd}_{len(steps)}"
            steps.append(step)
        steps = steps[: MAX_TOOL_CALLS - len(hops)]
        if not steps:
            break
        messages.append(_assistant_message(steps))
        for step in steps:
            plain = {"slot": step["slot"], "name": step["name"], "arguments": step["arguments"]}
            result = run_step(plain, model_chosen=True)
            hops.append({**plain, "result": result})
            messages.append(_tool_message(step, result))
    answer, usage = synthesize(question, hops, memory_text)
    tokens += int(usage.get("eval_count") or 0) + int(usage.get("prompt_eval_count") or 0)
    return {
        "ok": True,
        "mode": "ask-model-tools",
        "plan_source": "model",
        "question": question,
        "guard": {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")},
        "tool_calls": hops,
        "slots_used": sorted({h["slot"] for h in hops}),
        "answer": answer,
        "model": active_model(),
        "usage": usage,
        "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops), "tokens_seen": tokens},
    }, info


def run_demo(question: str | None = None) -> dict[str, Any]:
    q = question or (
        "What open PRs touch the invoice service, and what customer account "
        "owns that invoice line in the business tools?"
    )
    guard = classify(q)
    hops: list[dict[str, Any]] = []
    plan = [
        {"slot": "engineering", "name": "list_prs", "arguments": eng_args(state="open", limit=5)},
        {
            "slot": "business",
            "name": "fo_query",
            "arguments": {
                "entity": "CustomersV3",
                "filter": "CustomerAccount eq 'DEMO-C0001'",
                "select": "CustomerAccount,OrganizationName,AddressCity,CustomerGroupId",
                "top": 1,
            },
        },
    ]
    for step in plan:
        if len(hops) >= MAX_TOOL_CALLS:
            break
        result = run_step(step)
        hops.append({**step, "result": result})
    answer, usage = synthesize(q, hops)
    return {
        "ok": True,
        "mode": "demo",
        "question": q,
        "guard": {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")},
        "tool_calls": hops,
        "slots_used": sorted({h["slot"] for h in hops}),
        "answer": answer,
        "model": active_model(),
        "usage": usage,
        "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops)},
    }


def run_ask(question: str, conversation_id: Any = None) -> dict[str, Any]:
    """Day 15 wrapper: Prompt Guard first, then load memory for conversation_id
    (generated when missing), run the Day 10/14 loop, store the turn. A memory
    failure never fails the question; it is logged and reported in "memory"."""
    if not question or not question.strip():
        raise RuntimeError("question must not be empty")
    cid = valid_conversation_id(conversation_id) if conversation_id not in (None, "") else uuid.uuid4().hex
    guard = classify(question.strip())

    mem: dict[str, Any] = {"enabled": MEMORY.enabled, "turns_loaded": 0, "stored": False}
    turns: list[dict[str, Any]] = []
    if MEMORY.enabled and MEMORY_TURNS > 0:
        try:
            turns = MEMORY.load(cid, MEMORY_TURNS)
        except MemoryUnavailable as e:
            mem["error"] = str(e)
    memory_text, used = memory_context(turns) if turns else ("", 0)
    mem["turns_loaded"] = used

    if PLANNER == "model":
        out, pinfo = run_model_planner(question, guard, memory_text)
        if out is None:
            print(f"planner: keyword fallback ({pinfo.get('fallback_reason')})", flush=True)
            out = _run_ask_loop(question, guard, turns, memory_text, force_planned=True)
    else:
        pinfo = {"requested": "keyword", "used": "keyword", "backend": LLM_BACKEND}
        out = _run_ask_loop(question, guard, turns, memory_text)
    out["planner"] = pinfo

    if MEMORY.enabled:
        turn = {
            "question": question.strip(),
            "tool_calls": [{**{k: v for k, v in h.items() if k != "result"}, "result": trim_result(h.get("result"))} for h in out.get("tool_calls") or []],
            "answer": out.get("answer") or "",
            "mode": out.get("mode") or out.get("stopped"),
            "ok": bool(out.get("ok")),
        }
        try:
            MEMORY.save(cid, turn)
            mem["stored"] = True
        except MemoryUnavailable as e:
            mem.setdefault("error", str(e))
    elif MEMORY.reason:
        mem["reason"] = MEMORY.reason
    out["conversation_id"] = cid
    out["memory"] = mem
    return out


def _run_ask_loop(
    question: str,
    guard: dict[str, Any],
    turns: list[dict[str, Any]],
    memory_text: str,
    force_planned: bool = False,
) -> dict[str, Any]:
    """Day 10-15 keyword path. force_planned (Day 16 fallback from the model planner)
    always runs the keyword plan instead of handing single-slot questions to the
    text-based model loop."""
    hops: list[dict[str, Any]] = []
    tokens_used = 0

    # Prefer a deterministic plan when the question clearly needs both slots.
    plan, plan_source = plan_with_source(question, turns)
    needs_both = any(s["slot"] == "engineering" for s in plan) and any(s["slot"] == "business" for s in plan)
    needs_productivity = any(s["slot"] == "productivity" for s in plan)
    if needs_both or needs_productivity or force_planned:
        for step in plan:
            if len(hops) >= MAX_TOOL_CALLS:
                return {
                    "ok": False,
                    "stopped": "max_tool_calls",
                    "question": question,
                    "tool_calls": hops,
                    "answer": f"Stopped: max_tool_calls={MAX_TOOL_CALLS}",
                    "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops)},
                }
            result = run_step(step)
            hops.append({**step, "result": result})
        answer, usage = synthesize(question, hops, memory_text)
        tokens_used += int(usage.get("eval_count") or 0) + int(usage.get("prompt_eval_count") or 0)
        return {
            "ok": True,
            "mode": "ask-planned",
            "plan_source": plan_source,
            "question": question,
            "guard": {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")},
            "tool_calls": hops,
            "slots_used": sorted({h["slot"] for h in hops}),
            "answer": answer,
            "model": active_model(),
            "usage": usage,
            "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops), "tokens_seen": tokens_used},
        }

    # Model-driven loop for other questions (short prompts). Day 15: the tail of
    # the remembered conversation goes in front so the model can resolve follow-ups.
    earlier = f"Earlier in this conversation:\n{memory_text[-1200:]}\n\n" if memory_text else ""
    history = f"Question: {question.strip()}\n"
    for _ in range(MAX_TOOL_CALLS + 1):
        if tokens_used >= MAX_TOKENS:
            return {
                "ok": False,
                "stopped": "max_tokens",
                "question": question,
                "tool_calls": hops,
                "answer": f"Stopped: max_tokens={MAX_TOKENS}",
                "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops), "tokens_seen": tokens_used},
            }
        prompt = TOOL_CATALOG + "\n" + earlier + history[-2500:] + "\nNext:"
        gen = ollama_generate(prompt, num_predict=120)
        tokens_used += int(gen.get("eval_count") or 0) + int(gen.get("prompt_eval_count") or 0)
        kind, payload = parse_model_line(gen.get("response") or "")
        if kind == "final":
            return {
                "ok": True,
                "mode": "ask-model",
                "question": question,
                "guard": {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")},
                "tool_calls": hops,
                "slots_used": sorted({h["slot"] for h in hops}),
                "answer": payload,
                "model": active_model(),
                "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops), "tokens_seen": tokens_used},
            }
        if len(hops) >= MAX_TOOL_CALLS:
            return {
                "ok": False,
                "stopped": "max_tool_calls",
                "question": question,
                "tool_calls": hops,
                "answer": f"Stopped: max_tool_calls={MAX_TOOL_CALLS}",
                "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops), "tokens_seen": tokens_used},
            }
        step = payload
        result = run_step(step)
        hops.append({**step, "result": result})
        history += f"TOOL {step['slot']}.{step['name']} -> {json.dumps(result)[:800]}\n"

    answer, usage = synthesize(question, hops, memory_text)
    return {
        "ok": True,
        "mode": "ask-model",
        "question": question,
        "guard": {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")},
        "tool_calls": hops,
        "slots_used": sorted({h["slot"] for h in hops}),
        "answer": answer,
        "model": active_model(),
        "usage": usage,
        "budgets": {"max_tool_calls": MAX_TOOL_CALLS, "max_tokens": MAX_TOKENS, "tool_calls_used": len(hops)},
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"invalid json: {e}") from e
        if not isinstance(data, dict):
            raise RuntimeError("body must be a JSON object")
        return data

    def _json(self, code: int, obj: Any) -> None:
        self._send(code, json.dumps(obj, default=str).encode("utf-8"))

    def _conversation(self, path: str, method: str) -> None:
        """Day 15: GET reads one conversation's stored turns, DELETE forgets it."""
        try:
            cid = valid_conversation_id(unquote(path[len("/conversations/"):]))
        except RuntimeError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        try:
            if method == "DELETE":
                deleted = MEMORY.forget(cid)
                self._json(200, {"ok": True, "conversation_id": cid, "deleted_turns": deleted})
                return
            turns = MEMORY.load(cid, 200)
        except MemoryUnavailable as e:
            self._json(503, {"ok": False, "error": str(e)})
            return
        if not turns:
            self._json(404, {"ok": False, "conversation_id": cid, "error": "no stored turns for this conversation_id"})
            return
        self._json(200, {"ok": True, "conversation_id": cid, "turns": turns})

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/memory":
            self._json(200, MEMORY.status())
            return
        if path == "/tools":
            offered = discover_tools()
            self._json(
                200,
                {
                    "planner": PLANNER,
                    "backend": LLM_BACKEND,
                    "model": active_model(),
                    "tools": [{"function": k, "slot": t["slot"], "name": t["name"], "parameters": t["schema"]} for k, t in offered.items()],
                },
            )
            return
        if path.startswith("/conversations/"):
            self._conversation(path, "GET")
            return
        self._send(404, b'{"error":"not found"}\n')

    def do_DELETE(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path.startswith("/conversations/"):
            self._conversation(path, "DELETE")
            return
        self._send(404, b'{"error":"not found"}\n')

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        try:
            if path == "/demo":
                body = self._read_json()
                out = run_demo(body.get("question"))
            elif path == "/ask":
                body = self._read_json()
                out = run_ask(str(body.get("question") or ""), body.get("conversation_id"))
            else:
                self._send(404, b'{"error":"not found"}\n')
                return
            payload = json.dumps(out).encode("utf-8")
            self._send(200, payload)
        except Exception as e:  # noqa: BLE001
            err = {"ok": False, "error": str(e)}
            self._send(503 if "Guard" in str(e) or "unavailable" in str(e) else 400, json.dumps(err).encode("utf-8"))


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(
        f"control-layer on 0.0.0.0:{PORT} model={MODEL} "
        f"max_tool_calls={MAX_TOOL_CALLS} max_tokens={MAX_TOKENS} planner={PLANNER} backend={LLM_BACKEND}"
        + (f" openai_base_url={OPENAI_BASE_URL} openai_model={OPENAI_MODEL}" if LLM_BACKEND == "openai" else "")
        + (f" engineering_default_repo={ENGINEERING_DEFAULT_REPO}" if ENGINEERING_DEFAULT_REPO else ""),
        flush=True,
    )
    MEMORY.startup()  # never blocks or fails startup; Postgres down = no recall
    server.serve_forever()


if __name__ == "__main__":
    main()
