"""SSI engineering MCP: GitHub repositories, issues, pull requests, code and commits.

Streamable-HTTP-shaped JSON-RPC on :8000 at /mcp (stateless). Stdlib only, so it
still runs from python:3.12-slim + a ConfigMap (the lab pattern, no pip install).

Two data sources (ENGINEERING_SOURCE):
  github  real data from the GitHub REST API, read-only (GET requests only).
          GITHUB_TOKEN = fine-grained token with read-only Contents, Issues,
          Pull requests and Metadata (K8s Secret engineering-mcp-github, key token).
          GITHUB_OWNER = the only account whose repositories may be read (default MCS-BG).
          GITHUB_REPOS = optional comma-separated allowlist of repository names.
          Without a token, ENGINEERING_SOURCE=github still reads PUBLIC repositories
          (60 requests/hour, no code search). Use that only for a smoke test.
  sample  the Day 10 sample data (invoice-service / billing-ui), unchanged.
Default: github when GITHUB_TOKEN is set, otherwise sample.

Guardrails in github mode (same Prompt Guard contract as m365-mcp and mcp-server):
  - free-text arguments (search queries, file paths, refs) are classified before a call;
    malicious_score >= PROMPT_GUARD_THRESHOLD refuses the call. The SSI gateway's
    /mcp/engineering route reaches this server without the control layer, so the
    check lives here too.
  - text read from GitHub (titles, bodies, comments, commit messages, file contents,
    code fragments) is classified on the way out; flagged items are withheld
    (indirect prompt injection through issues and pull requests).
  - Prompt Guard unreachable: refused unless PROMPT_GUARD_FAIL_OPEN=true.
  - every GitHub error (401, 403, 404, 422, rate limit, network) becomes a clear tool
    error (isError true). The token is never echoed.

Tracing: if the opentelemetry package is importable (built image), each tool call and
GitHub request gets a span; under the ConfigMap pattern the shim is a no-op.
"""
from __future__ import annotations

import base64
import contextlib
import datetime as dt
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlsplit

VERSION = "0.2.0"
PORT = int(os.environ.get("PORT", "8000"))
SAMPLE_PATH = os.environ.get("SAMPLE_DATA", "")

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_API = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "MCS-BG").strip() or "MCS-BG"
GITHUB_REPOS = [
    r.strip().split("/")[-1].lower()
    for r in os.environ.get("GITHUB_REPOS", "").split(",")
    if r.strip()
]
GITHUB_DEFAULT_REPO = os.environ.get("GITHUB_DEFAULT_REPO", "").strip()
GITHUB_TIMEOUT = float(os.environ.get("GITHUB_TIMEOUT", "15"))
GITHUB_CACHE_SECONDS = float(os.environ.get("GITHUB_CACHE_SECONDS", "60"))

_source = os.environ.get("ENGINEERING_SOURCE", "").strip().lower()
if _source not in ("", "github", "sample"):
    raise SystemExit(f"ENGINEERING_SOURCE must be github or sample, not {_source!r}")
SOURCE = _source or ("github" if GITHUB_TOKEN else "sample")

# Output budgets: results must stay small for a 3B-8B model.
BODY_MAX_CHARS = int(os.environ.get("BODY_MAX_CHARS", "600"))
FILE_MAX_CHARS = int(os.environ.get("FILE_MAX_CHARS", "4000"))
FILES_MAX = int(os.environ.get("FILES_MAX", "30"))
RESULT_MAX_CHARS = int(os.environ.get("RESULT_MAX_CHARS", "8000"))
LIST_DEFAULT = 10
LIST_MAX = 30

PROMPT_GUARD_URL = os.environ.get(
    "PROMPT_GUARD_URL", "http://prompt-guard.si-lab.svc.cluster.local:8080/classify"
)
PROMPT_GUARD_THRESHOLD = float(os.environ.get("PROMPT_GUARD_THRESHOLD", "0.5"))
PROMPT_GUARD_ENABLED = os.environ.get("PROMPT_GUARD_ENABLED", "true").lower() == "true"
PROMPT_GUARD_FAIL_OPEN = os.environ.get("PROMPT_GUARD_FAIL_OPEN", "false").lower() == "true"
PROMPT_GUARD_SCAN_CONTENT = os.environ.get("PROMPT_GUARD_SCAN_CONTENT", "true").lower() == "true"
PROMPT_GUARD_MAX_CHARS = 20000


class ToolError(Exception):
    """An error the caller should see as a tool result with isError true."""


# ---------- optional tracing (no-op without opentelemetry) ----------

try:  # pragma: no cover - depends on the image
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer("engineering-mcp")
except Exception:  # noqa: BLE001
    _tracer = None


def _attr_text(value: Any, limit: int = 8000) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more chars]"


@contextlib.contextmanager
def span(name: str, obs_type: str = "span", input: Any = None, **attrs: Any):
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as s:
        s.set_attribute("langfuse.observation.type", obs_type)
        if input is not None:
            s.set_attribute("langfuse.observation.input", _attr_text(input))
        for k, v in attrs.items():
            if v is not None:
                s.set_attribute(k, v)
        yield s


def span_output(s: Any, output: Any) -> None:
    if s is not None:
        s.set_attribute("langfuse.observation.output", _attr_text(output))


# ---------- sample data (Day 10, unchanged) ----------

DEFAULT_SAMPLE = {
    "repos": [
        {"name": "invoice-service", "default_branch": "main", "description": "Invoice and tax calculation API"},
        {"name": "billing-ui", "default_branch": "main", "description": "Customer billing screens"},
    ],
    "pull_requests": [
        {
            "repo": "invoice-service",
            "number": 42,
            "title": "Fix tax rounding",
            "state": "open",
            "customer_account": "DEMO-C0001",
            "body": "Corrects half-cent rounding on invoice lines for Lakeside Bike Shop.",
        },
        {
            "repo": "billing-ui",
            "number": 7,
            "title": "Show credit memo",
            "state": "open",
            "customer_account": "DEMO-C0002",
            "body": "Display credit memos on the Prairie Outfitters billing page.",
        },
    ],
    "issues": [
        {
            "repo": "invoice-service",
            "number": 18,
            "title": "Missing company filter",
            "state": "open",
            "customer_account": "DEMO-C0001",
            "body": "Company filter missing when listing invoice lines for DEMO-C0001.",
        },
        {
            "repo": "billing-ui",
            "number": 3,
            "title": "Credit memo PDF blank",
            "state": "closed",
            "customer_account": "DEMO-C0002",
            "body": "Fixed in an earlier release.",
        },
    ],
}


def load_sample() -> dict[str, Any]:
    if SAMPLE_PATH and os.path.isfile(SAMPLE_PATH):
        with open(SAMPLE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_SAMPLE


DATA = load_sample()


def list_repos() -> dict[str, Any]:
    return {"source": "engineering-mcp (sample)", "repos": list(DATA.get("repos", []))}


def list_prs(repo: str | None = None, state: str = "open") -> dict[str, Any]:
    rows = DATA.get("pull_requests", [])
    out = [r for r in rows if (not repo or r.get("repo") == repo) and (state == "all" or r.get("state") == state)]
    return {"source": "engineering-mcp (sample)", "repo": repo, "state": state, "pull_requests": out, "returned": len(out)}


def get_pr(repo: str, number: int) -> dict[str, Any]:
    for r in DATA.get("pull_requests", []):
        if r.get("repo") == repo and int(r.get("number", -1)) == int(number):
            return {"source": "engineering-mcp (sample)", "pull_request": r}
    return {"source": "engineering-mcp (sample)", "error": f"PR {repo}#{number} not found"}


def list_issues(repo: str | None = None, state: str = "open") -> dict[str, Any]:
    rows = DATA.get("issues", [])
    out = [r for r in rows if (not repo or r.get("repo") == repo) and (state == "all" or r.get("state") == state)]
    return {"source": "engineering-mcp (sample)", "repo": repo, "state": state, "issues": out, "returned": len(out)}


def get_issue(repo: str, number: int) -> dict[str, Any]:
    for r in DATA.get("issues", []):
        if r.get("repo") == repo and int(r.get("number", -1)) == int(number):
            return {"source": "engineering-mcp (sample)", "issue": r}
    return {"source": "engineering-mcp (sample)", "error": f"Issue {repo}#{number} not found"}


# ---------- argument helpers ----------

_REPO_NAME = re.compile(r"[A-Za-z0-9._-]{1,100}")
_REF = re.compile(r"[A-Za-z0-9._/-]{1,200}")
_STATES = ("open", "closed", "all")


def _int(args: dict[str, Any], key: str, default: int | None = None, lo: int | None = None, hi: int | None = None) -> int:
    raw = args.get(key, default)
    if raw is None or raw == "":
        if default is None:
            raise ToolError(f"argument '{key}' is required")
        raw = default
    try:
        value = int(str(raw).strip().lstrip("#"))
    except ValueError:
        raise ToolError(f"argument '{key}' must be a whole number, got {raw!r}") from None
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def _bool(args: dict[str, Any], key: str, default: bool = False) -> bool:
    raw = args.get(key, default)
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _str(args: dict[str, Any], key: str) -> str:
    raw = args.get(key)
    return "" if raw is None else str(raw).strip()


def _state(args: dict[str, Any]) -> str:
    state = (_str(args, "state") or "open").lower()
    if state not in _STATES:
        raise ToolError(f"state must be one of open, closed, all (got {state!r})")
    return state


def _limit(args: dict[str, Any]) -> int:
    return _int(args, "limit", LIST_DEFAULT, 1, LIST_MAX)


def _ref(args: dict[str, Any], key: str, required: bool = False) -> str:
    value = _str(args, key)
    if not value:
        if required:
            raise ToolError(f"argument '{key}' is required")
        return ""
    if not _REF.fullmatch(value) or ".." in value:
        raise ToolError(f"argument '{key}' has characters that are not allowed: {value!r}")
    return value


def resolve_repo(args: dict[str, Any], required: bool = True) -> str | None:
    """Repository name inside GITHUB_OWNER. Accepts 'name' or 'owner/name'."""
    repo = _str(args, "repo") or GITHUB_DEFAULT_REPO
    if not repo:
        if required:
            raise ToolError("argument 'repo' is required. Call list_repos to see the repository names.")
        return None
    repo = repo.strip("/")
    if repo.lower().startswith("https://github.com/"):
        repo = repo[len("https://github.com/"):]
    if "/" in repo:
        owner, _, name = repo.partition("/")
        if owner.lower() != GITHUB_OWNER.lower():
            raise ToolError(f"Only repositories owned by {GITHUB_OWNER} can be read (got {owner}/{name}).")
        repo = name.split("/")[0]
    if not _REPO_NAME.fullmatch(repo):
        raise ToolError(f"Not a valid repository name: {repo!r}")
    if GITHUB_REPOS and repo.lower() not in GITHUB_REPOS:
        raise ToolError(
            f"Repository {repo} is not on this server's allowlist (GITHUB_REPOS): {', '.join(GITHUB_REPOS)}."
        )
    return repo


def _scope_qualifiers(repo: str | None) -> str:
    """Search qualifiers that keep a search inside the owner (and the allowlist)."""
    if repo:
        return f"repo:{GITHUB_OWNER}/{repo}"
    if GITHUB_REPOS:
        return " ".join(f"repo:{GITHUB_OWNER}/{r}" for r in GITHUB_REPOS)
    return f"user:{GITHUB_OWNER}"


def _trim(text: Any, limit: int = BODY_MAX_CHARS) -> str | None:
    if text is None:
        return None
    text = str(text).replace("\r\n", "\n").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + f" ... [{len(text) - limit} more chars]"


def _first_line(text: Any, limit: int = 200) -> str:
    line = (str(text or "").strip().splitlines() or [""])[0]
    return line if len(line) <= limit else line[:limit] + "..."


def _login(user: Any) -> str | None:
    return user.get("login") if isinstance(user, dict) else None


# ---------- GitHub REST client (GET only) ----------

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()
_rate = {"remaining": None, "reset": None}


def _reset_text(reset: str | None) -> str:
    try:
        when = dt.datetime.fromtimestamp(int(reset), dt.timezone.utc)
    except (TypeError, ValueError):
        return "later"
    wait = max(0, int(when.timestamp() - time.time()))
    return f"at {when.strftime('%H:%M')} UTC (in about {max(1, wait // 60)} min)"


def _github_message(body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8", errors="replace") or "{}")
        msg = data.get("message") or ""
        errors = data.get("errors")
        if errors:
            msg += " " + json.dumps(errors)[:200]
        return msg.strip()[:300]
    except (ValueError, AttributeError):
        return body.decode("utf-8", errors="replace")[:200]


def gh_get(path: str, params: dict[str, Any] | None = None, accept: str = "application/vnd.github+json",
           what: str | None = None) -> Any:
    """GET a GitHub REST path and return parsed JSON. Raises ToolError with a clear message."""
    query = {k: v for k, v in (params or {}).items() if v not in (None, "")}
    url = f"{GITHUB_API}{path}" + (f"?{urlencode(query)}" if query else "")
    key = f"{accept}|{url}"
    now = time.monotonic()
    if GITHUB_CACHE_SECONDS > 0:
        with _cache_lock:
            hit = _cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
    headers = {
        "Accept": accept,
        "User-Agent": f"ssi-engineering-mcp/{VERSION}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    label = what or path
    with span(f"github GET {path.split('?')[0]}", "span", input={"path": path, "params": query}) as s:
        for attempt in (1, 2):
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=GITHUB_TIMEOUT) as resp:
                    _rate["remaining"] = resp.headers.get("X-RateLimit-Remaining")
                    _rate["reset"] = resp.headers.get("X-RateLimit-Reset")
                    raw = resp.read()
                break
            except urllib.error.HTTPError as e:
                body = e.read() or b""
                msg = _github_message(body)
                remaining = e.headers.get("X-RateLimit-Remaining") if e.headers else None
                retry_after = e.headers.get("Retry-After") if e.headers else None
                if s is not None:
                    s.set_attribute("http.status_code", e.code)
                if e.code == 401:
                    raise ToolError(
                        "GitHub rejected the token (401 Bad credentials). The token in Secret "
                        "engineering-mcp-github (key token) is wrong, expired or revoked; create a new "
                        "fine-grained token and replace the Secret."
                        if GITHUB_TOKEN else
                        "GitHub needs a token for this call (401). Set GITHUB_TOKEN from Secret engineering-mcp-github."
                    ) from None
                if e.code in (403, 429) and (remaining == "0" or retry_after or "rate limit" in msg.lower()):
                    if retry_after:
                        raise ToolError(
                            f"GitHub secondary rate limit hit while reading {label}; retry after {retry_after} s."
                        ) from None
                    reset = e.headers.get("X-RateLimit-Reset") if e.headers else None
                    hint = "" if GITHUB_TOKEN else " Without a token the limit is 60 requests/hour; add GITHUB_TOKEN."
                    raise ToolError(f"GitHub rate limit reached; it resets {_reset_text(reset)}.{hint}") from None
                if e.code == 403:
                    raise ToolError(
                        f"GitHub refused access to {label} (403: {msg or 'forbidden'}). The fine-grained token "
                        f"needs read-only Contents, Issues, Pull requests and Metadata on this repository, with "
                        f"resource owner {GITHUB_OWNER}."
                    ) from None
                if e.code == 404:
                    raise ToolError(
                        f"Not found on GitHub: {label}. It does not exist, or the token cannot see it "
                        f"(a private repository that is not selected on the token looks like 404)."
                    ) from None
                if e.code == 422:
                    raise ToolError(f"GitHub could not process the request for {label} (422: {msg}).") from None
                if e.code >= 500 and attempt == 1:
                    time.sleep(1)
                    continue
                raise ToolError(f"GitHub error {e.code} for {label}: {msg or 'no detail'}") from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                reason = getattr(e, "reason", e)
                if attempt == 1:
                    time.sleep(1)
                    continue
                raise ToolError(
                    f"GitHub is unreachable ({reason}). Check DNS and the HTTPS (443) egress NetworkPolicy "
                    "engineering-mcp-egress."
                ) from None
        try:
            data = json.loads(raw.decode("utf-8")) if raw else None
        except ValueError:
            raise ToolError(f"GitHub returned a response that is not JSON for {label}.") from None
        span_output(s, {"bytes": len(raw), "rate_remaining": _rate["remaining"]})
    if GITHUB_CACHE_SECONDS > 0:
        with _cache_lock:
            if len(_cache) > 256:
                _cache.clear()
            _cache[key] = (now + GITHUB_CACHE_SECONDS, data)
    return data


# ---------- Prompt Guard (same contract as mcp-server / m365-mcp) ----------

def _pieces(text: str) -> list[str]:
    if len(text) <= PROMPT_GUARD_MAX_CHARS:
        return [text]
    step = PROMPT_GUARD_MAX_CHARS - 1000
    return [text[i:i + PROMPT_GUARD_MAX_CHARS] for i in range(0, len(text), step)]


def classify(text: str, stage: str, tool: str) -> tuple[bool, float | None]:
    """(blocked, score). Fails closed unless PROMPT_GUARD_FAIL_OPEN=true."""
    with span(f"prompt-guard {stage}", "guardrail", input={"tool": tool, "stage": stage, "text": text},
              **{"prompt_guard.stage": stage, "prompt_guard.tool": tool}) as s:
        try:
            score = 0.0
            for piece in _pieces(text):
                req = urllib.request.Request(
                    PROMPT_GUARD_URL,
                    data=json.dumps({"text": piece, "threshold": PROMPT_GUARD_THRESHOLD}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    part = json.loads(resp.read().decode("utf-8"))
                score = max(score, float(part["malicious_score"]))
        except Exception as e:  # noqa: BLE001
            if PROMPT_GUARD_FAIL_OPEN:
                span_output(s, {"error": str(e), "action": "allowed (fail open)"})
                return False, None
            span_output(s, {"error": str(e), "action": "refused (fail closed)"})
            raise ToolError(f"Prompt Guard unavailable, request refused: {type(e).__name__}") from None
        blocked = score >= PROMPT_GUARD_THRESHOLD
        span_output(s, {"malicious_score": score, "blocked": blocked})
        return blocked, score


def guard_input(tool: str, **arguments: Any) -> None:
    if not PROMPT_GUARD_ENABLED:
        return
    text = "\n".join(str(v) for v in arguments.values() if isinstance(v, str) and v.strip())
    if not text:
        return
    blocked, score = classify(text, "tool_input", tool)
    if blocked:
        raise ToolError(
            f"Refused by Prompt Guard: the {tool} arguments look like a prompt injection or jailbreak "
            f"(malicious_score {score:.3f} >= threshold {PROMPT_GUARD_THRESHOLD})."
        )


def _withheld(score: float | None) -> str:
    return f"[withheld by Prompt Guard: malicious_score {score or 0:.3f} >= threshold {PROMPT_GUARD_THRESHOLD}]"


def guard_items(tool: str, items: list[dict[str, Any]], fields: tuple[str, ...]) -> int:
    """Classify text read from GitHub; replace flagged fields in place. Returns withheld count.

    One Prompt Guard call for the whole batch; only if that is flagged, one call per item.
    """
    if not (PROMPT_GUARD_ENABLED and PROMPT_GUARD_SCAN_CONTENT):
        return 0

    def text_of(item: dict[str, Any]) -> str:
        return "\n".join(str(item[f]) for f in fields if item.get(f))

    texts = [text_of(i) for i in items]
    if not any(t.strip() for t in texts):
        return 0
    blocked, batch_score = classify("\n\n".join(texts), "retrieved_content", tool)
    if not blocked:
        return 0
    withheld = 0
    for item, text in zip(items, texts):
        if not text.strip():
            continue
        if len(items) == 1:
            flagged, score = True, batch_score
        else:
            flagged, score = classify(text, "retrieved_content", tool)
        if flagged:
            withheld += 1
            for f in fields:
                if item.get(f):
                    item[f] = _withheld(score)
            item["withheld"] = True
    return withheld


# ---------- shaping ----------

def _repo_from_url(url: str | None) -> str | None:
    return url.rstrip("/").split("/")[-1] if url else None


def _issue_row(i: dict[str, Any], repo: str | None = None) -> dict[str, Any]:
    return {
        "repo": repo or _repo_from_url(i.get("repository_url")),
        "number": i.get("number"),
        "title": _trim(i.get("title"), 200),
        "state": i.get("state"),
        "author": _login(i.get("user")),
        "labels": [lb.get("name") for lb in i.get("labels", []) if isinstance(lb, dict)][:5],
        "comments": i.get("comments"),
        "updated_at": i.get("updated_at"),
        "body": _trim(i.get("body"), 300),
        "url": i.get("html_url"),
    }


def _pr_row(p: dict[str, Any], repo: str | None = None) -> dict[str, Any]:
    row = {
        "repo": repo or _repo_from_url(p.get("repository_url")) or ((p.get("base") or {}).get("repo") or {}).get("name"),
        "number": p.get("number"),
        "title": _trim(p.get("title"), 200),
        "state": p.get("state"),
        "draft": p.get("draft"),
        "author": _login(p.get("user")),
        "updated_at": p.get("updated_at"),
        "body": _trim(p.get("body"), 300),
        "url": p.get("html_url"),
    }
    if p.get("head"):
        row["head"] = p["head"].get("ref")
        row["base"] = (p.get("base") or {}).get("ref")
    if p.get("merged_at") or (p.get("pull_request") or {}).get("merged_at"):
        row["merged_at"] = p.get("merged_at") or p["pull_request"]["merged_at"]
    return row


def _file_rows(files: list[dict[str, Any]], include_patch: bool) -> list[dict[str, Any]]:
    out = []
    for f in files[:FILES_MAX]:
        row = {
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
        }
        if include_patch and f.get("patch"):
            row["patch"] = _trim(f["patch"], 500)
        out.append(row)
    return out


def _fit(result: dict[str, Any]) -> dict[str, Any]:
    """Drop items from the longest list until the JSON fits RESULT_MAX_CHARS."""
    while len(json.dumps(result)) > RESULT_MAX_CHARS:
        lists = [(k, v) for k, v in result.items() if isinstance(v, list) and len(v) > 1]
        if not lists:
            break
        key, longest = max(lists, key=lambda kv: len(json.dumps(kv[1])))
        longest.pop()
        result["truncated"] = True
        if "returned" in result:
            result["returned"] = len(longest)
    return result


def _gh(result: dict[str, Any]) -> dict[str, Any]:
    result = {"source": "github", "owner": GITHUB_OWNER, **result}
    if not GITHUB_TOKEN:
        result["note"] = "unauthenticated: public repositories only"
    return _fit(result)


# ---------- GitHub tools ----------

def gh_list_repos(args: dict[str, Any]) -> dict[str, Any]:
    limit = _int(args, "limit", LIST_MAX, 1, 100)
    rows: list[dict[str, Any]] = []
    if GITHUB_TOKEN:
        data = gh_get("/user/repos", {"per_page": 100, "sort": "updated"}, what="the token's repositories")
        rows = [r for r in data or [] if (r.get("owner") or {}).get("login", "").lower() == GITHUB_OWNER.lower()]
    if not rows:
        data = gh_get(f"/users/{quote(GITHUB_OWNER)}/repos", {"per_page": 100, "sort": "updated"},
                      what=f"repositories of {GITHUB_OWNER}")
        rows = list(data or [])
    if GITHUB_REPOS:
        rows = [r for r in rows if r.get("name", "").lower() in GITHUB_REPOS]
    repos = [
        {
            "name": r.get("name"),
            "private": r.get("private"),
            "default_branch": r.get("default_branch"),
            "description": _trim(r.get("description"), 200),
            "language": r.get("language"),
            "open_issues_and_prs": r.get("open_issues_count"),
            "pushed_at": r.get("pushed_at"),
            "archived": r.get("archived"),
        }
        for r in rows[:limit]
    ]
    withheld = guard_items("list_repos", repos, ("description",))
    return _gh({"repos": repos, "returned": len(repos), "withheld": withheld})


def _search_issues(kind: str, repo: str | None, state: str, limit: int) -> list[dict[str, Any]]:
    q = f"is:{kind} {_scope_qualifiers(repo)}" + ("" if state == "all" else f" state:{state}")
    data = gh_get("/search/issues", {"q": q, "sort": "updated", "order": "desc", "per_page": limit},
                  what=f"{kind} search")
    return list((data or {}).get("items") or [])


def gh_list_prs(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args, required=False)
    state, limit = _state(args), _limit(args)
    if repo:
        data = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/pulls",
                      {"state": state, "sort": "updated", "direction": "desc", "per_page": limit},
                      what=f"pull requests of {GITHUB_OWNER}/{repo}")
        rows = [_pr_row(p, repo) for p in data or []]
    else:
        rows = [_pr_row(p) for p in _search_issues("pr", None, state, limit)]
    withheld = guard_items("list_prs", rows, ("title", "body"))
    return _gh({"repo": repo, "state": state, "pull_requests": rows, "returned": len(rows), "withheld": withheld})


def gh_get_pr(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args)
    number = _int(args, "number", None, 1)
    include_patch = _bool(args, "include_patch")
    p = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/pulls/{number}", what=f"pull request {repo}#{number}")
    files = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/pulls/{number}/files", {"per_page": FILES_MAX},
                   what=f"changed files of {repo}#{number}")
    pr = {
        "repo": repo,
        "number": p.get("number"),
        "title": _trim(p.get("title"), 200),
        "state": p.get("state"),
        "merged": p.get("merged"),
        "draft": p.get("draft"),
        "author": _login(p.get("user")),
        "head": (p.get("head") or {}).get("ref"),
        "base": (p.get("base") or {}).get("ref"),
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
        "merged_at": p.get("merged_at"),
        "commits": p.get("commits"),
        "additions": p.get("additions"),
        "deletions": p.get("deletions"),
        "changed_files": p.get("changed_files"),
        "body": _trim(p.get("body")),
        "url": p.get("html_url"),
    }
    file_rows = _file_rows(files or [], include_patch)
    withheld = guard_items("get_pr", [pr], ("title", "body"))
    if include_patch:
        withheld += guard_items("get_pr", file_rows, ("patch",))
    return _gh({
        "pull_request": pr,
        "files": file_rows,
        "files_truncated": (p.get("changed_files") or 0) > len(file_rows),
        "withheld": withheld,
    })


def gh_list_issues(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args, required=False)
    state, limit = _state(args), _limit(args)
    if repo:
        # The issues endpoint also returns pull requests; ask for extra and drop them.
        data = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/issues",
                      {"state": state, "sort": "updated", "direction": "desc", "per_page": min(100, limit * 3)},
                      what=f"issues of {GITHUB_OWNER}/{repo}")
        rows = [_issue_row(i, repo) for i in data or [] if "pull_request" not in i][:limit]
    else:
        rows = [_issue_row(i) for i in _search_issues("issue", None, state, limit)]
    withheld = guard_items("list_issues", rows, ("title", "body"))
    return _gh({"repo": repo, "state": state, "issues": rows, "returned": len(rows), "withheld": withheld})


def gh_get_issue(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args)
    number = _int(args, "number", None, 1)
    i = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/issues/{number}", what=f"issue {repo}#{number}")
    issue = _issue_row(i, repo)
    issue["body"] = _trim(i.get("body"))
    issue["created_at"] = i.get("created_at")
    issue["closed_at"] = i.get("closed_at")
    issue["assignees"] = [_login(a) for a in i.get("assignees") or []][:5]
    out: dict[str, Any] = {"issue": issue}
    if "pull_request" in i:
        out["note"] = f"#{number} is a pull request; get_pr returns its changed files."
    comments: list[dict[str, Any]] = []
    if _bool(args, "include_comments") and i.get("comments"):
        total = int(i["comments"])
        # newest 5: jump to the last page of 5
        page = max(1, (total + 4) // 5)
        data = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/issues/{number}/comments", {"per_page": 5, "page": page},
                      what=f"comments of {repo}#{number}")
        comments = [
            {"author": _login(c.get("user")), "created_at": c.get("created_at"), "body": _trim(c.get("body"), 300)}
            for c in data or []
        ]
        out["comments"] = comments
    withheld = guard_items("get_issue", [issue], ("title", "body")) + guard_items("get_issue", comments, ("body",))
    out["withheld"] = withheld
    return _gh(out)


def gh_search_code(args: dict[str, Any]) -> dict[str, Any]:
    query = _str(args, "query")
    if not query:
        raise ToolError("argument 'query' is required (words or an exact identifier to find in code)")
    if len(query) > 200:
        raise ToolError("query is too long (200 characters max)")
    if re.search(r"\b(repo|user|org):", query, re.I):
        raise ToolError("Do not put repo:/user:/org: in the query; pass repo instead.")
    if not GITHUB_TOKEN:
        raise ToolError("GitHub code search needs a token. Set GITHUB_TOKEN from Secret engineering-mcp-github.")
    repo = resolve_repo(args, required=False)
    limit = _int(args, "limit", LIST_DEFAULT, 1, 20)
    guard_input("search_code", query=query)
    data = gh_get("/search/code", {"q": f"{query} {_scope_qualifiers(repo)}", "per_page": limit},
                  accept="application/vnd.github.text-match+json", what="code search")
    rows = []
    for item in (data or {}).get("items") or []:
        rows.append({
            "repo": (item.get("repository") or {}).get("name"),
            "path": item.get("path"),
            "url": item.get("html_url"),
            "fragments": [_trim(m.get("fragment"), 300) for m in (item.get("text_matches") or [])[:2]],
        })
    for row in rows:  # fragments are a list; screen them as one text per hit
        row["_text"] = "\n".join(f for f in row["fragments"] if f)
    withheld = guard_items("search_code", rows, ("_text",))
    for row in rows:
        text = row.pop("_text", "")
        if row.get("withheld"):
            row["fragments"] = [text]
    return _gh({"query": query, "repo": repo, "total_count": (data or {}).get("total_count"),
                "results": rows, "returned": len(rows), "withheld": withheld})


def gh_get_file(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args)
    path = _str(args, "path").strip("/")
    if ".." in path.split("/") or len(path) > 400:
        raise ToolError(f"path is not allowed: {path!r}")
    ref = _ref(args, "ref")
    guard_input("get_file", path=path, ref=ref)
    data = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/contents/{quote(path)}", {"ref": ref},
                  what=f"{repo}:{path or '/'}" + (f"@{ref}" if ref else ""))
    if isinstance(data, list):
        entries = [{"name": e.get("name"), "type": e.get("type"), "size": e.get("size"), "path": e.get("path")}
                   for e in data[:50]]
        return _gh({"repo": repo, "path": path or "/", "ref": ref or None, "type": "dir",
                    "entries": entries, "returned": len(entries), "total_entries": len(data)})
    if not isinstance(data, dict) or data.get("type") != "file":
        raise ToolError(f"{repo}:{path} is a {data.get('type') if isinstance(data, dict) else 'unknown'}, not a file.")
    size = int(data.get("size") or 0)
    if not data.get("content") and size > 0:
        raise ToolError(f"{repo}:{path} is {size} bytes, too large to read through this tool (1 MB GitHub limit).")
    try:
        raw = base64.b64decode(data.get("content") or "")
    except ValueError:
        raise ToolError(f"{repo}:{path} could not be decoded.") from None
    if b"\x00" in raw[:4096]:
        raise ToolError(f"{repo}:{path} is a binary file ({size} bytes); only text files can be read.")
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    start = _int(args, "start_line", 1, 1)
    end = _int(args, "end_line", len(lines) or 1, start)
    selected = "\n".join(lines[start - 1:end])
    truncated = len(selected) > FILE_MAX_CHARS
    if truncated:
        selected = selected[:FILE_MAX_CHARS]
        last = start + selected.count("\n")
    else:
        last = min(end, len(lines))
    out = {"repo": repo, "path": data.get("path"), "ref": ref or None, "type": "file", "size": size,
           "total_lines": len(lines), "start_line": start, "end_line": last, "truncated": truncated,
           "content": selected, "url": data.get("html_url")}
    if truncated:
        out["hint"] = f"Content capped at {FILE_MAX_CHARS} characters; call again with start_line={last + 1}."
    withheld = guard_items("get_file", [out], ("content",))
    out["withheld"] = withheld
    return _gh(out)


def gh_list_commits(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args)
    ref = _ref(args, "ref") or _ref(args, "branch")
    path = _str(args, "path").strip("/")
    limit = _limit(args)
    if path:
        guard_input("list_commits", path=path)
    data = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/commits", {"sha": ref, "path": path, "per_page": limit},
                  what=f"commits of {GITHUB_OWNER}/{repo}")
    rows = [
        {
            "sha": (c.get("sha") or "")[:12],
            "message": _first_line((c.get("commit") or {}).get("message")),
            "author": ((c.get("commit") or {}).get("author") or {}).get("name"),
            "date": ((c.get("commit") or {}).get("author") or {}).get("date"),
            "url": c.get("html_url"),
        }
        for c in data or []
    ]
    withheld = guard_items("list_commits", rows, ("message",))
    return _gh({"repo": repo, "ref": ref or None, "path": path or None, "commits": rows,
                "returned": len(rows), "withheld": withheld})


def gh_get_commit(args: dict[str, Any]) -> dict[str, Any]:
    repo = resolve_repo(args)
    sha = _ref(args, "sha", required=True)
    include_patch = _bool(args, "include_patch")
    c = gh_get(f"/repos/{GITHUB_OWNER}/{repo}/commits/{quote(sha)}", what=f"commit {repo}@{sha}")
    commit = c.get("commit") or {}
    out = {
        "repo": repo,
        "sha": c.get("sha"),
        "message": _trim(commit.get("message"), 800),
        "author": (commit.get("author") or {}).get("name"),
        "date": (commit.get("author") or {}).get("date"),
        "parents": len(c.get("parents") or []),
        "stats": c.get("stats"),
        "url": c.get("html_url"),
    }
    files = c.get("files") or []
    file_rows = _file_rows(files, include_patch)
    withheld = guard_items("get_commit", [out], ("message",))
    if include_patch:
        withheld += guard_items("get_commit", file_rows, ("patch",))
    return _gh({"commit": out, "files": file_rows, "files_truncated": len(files) > len(file_rows),
                "withheld": withheld})


# ---------- tool registry ----------

def _schema(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": props, "additionalProperties": True}
    if required:
        schema["required"] = required
    return schema


_REPO = {"type": "string", "description": f"Repository name in {GITHUB_OWNER} (from list_repos)."}
_STATE = {"type": "string", "enum": list(_STATES), "default": "open"}
_LIMIT = {"type": "integer", "minimum": 1, "maximum": LIST_MAX, "default": LIST_DEFAULT}
_NUMBER = {"type": "integer", "minimum": 1}


def _sample_only(name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    def handler(args: dict[str, Any]) -> dict[str, Any]:
        raise ToolError(f"{name} needs real GitHub data: set ENGINEERING_SOURCE=github and GITHUB_TOKEN.")
    return handler


GITHUB_TOOLS: dict[str, dict[str, Any]] = {
    "list_repos": {
        "description": f"List {GITHUB_OWNER} GitHub repositories (name, default branch, description, language).",
        "inputSchema": _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
        "handler": gh_list_repos,
    },
    "list_prs": {
        "description": "List pull requests, newest update first. Optional repo (all repos when omitted), "
                       "state (open|closed|all), limit.",
        "inputSchema": _schema({"repo": _REPO, "state": _STATE, "limit": _LIMIT}),
        "handler": gh_list_prs,
    },
    "get_pr": {
        "description": "Get one pull request by repo and number, with its changed files "
                       "(include_patch=true adds short diffs).",
        "inputSchema": _schema({"repo": _REPO, "number": _NUMBER, "include_patch": {"type": "boolean"}},
                               ["repo", "number"]),
        "handler": gh_get_pr,
    },
    "list_issues": {
        "description": "List issues (pull requests excluded), newest update first. Optional repo, "
                       "state (open|closed|all), limit.",
        "inputSchema": _schema({"repo": _REPO, "state": _STATE, "limit": _LIMIT}),
        "handler": gh_list_issues,
    },
    "get_issue": {
        "description": "Get one issue by repo and number (include_comments=true adds the newest 5 comments).",
        "inputSchema": _schema({"repo": _REPO, "number": _NUMBER, "include_comments": {"type": "boolean"}},
                               ["repo", "number"]),
        "handler": gh_get_issue,
    },
    "search_code": {
        "description": f"Search code in {GITHUB_OWNER} repositories (default branch). query = words or an "
                       "identifier; optional repo, limit. Returns paths and matching fragments.",
        "inputSchema": _schema({"query": {"type": "string"}, "repo": _REPO,
                                "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, ["query"]),
        "handler": gh_search_code,
    },
    "get_file": {
        "description": "Read a text file (or list a folder) from a repo. path, optional ref (branch, tag or "
                       f"commit), start_line, end_line. Content is capped at {FILE_MAX_CHARS} characters.",
        "inputSchema": _schema({"repo": _REPO, "path": {"type": "string"}, "ref": {"type": "string"},
                                "start_line": {"type": "integer", "minimum": 1},
                                "end_line": {"type": "integer", "minimum": 1}}, ["repo", "path"]),
        "handler": gh_get_file,
    },
    "list_commits": {
        "description": "List recent commits of a repo (sha, first line of message, author, date). "
                       "Optional ref (branch), path, limit.",
        "inputSchema": _schema({"repo": _REPO, "ref": {"type": "string"}, "path": {"type": "string"},
                                "limit": _LIMIT}, ["repo"]),
        "handler": gh_list_commits,
    },
    "get_commit": {
        "description": "Get one commit by repo and sha: message, stats and changed files "
                       "(include_patch=true adds short diffs).",
        "inputSchema": _schema({"repo": _REPO, "sha": {"type": "string"}, "include_patch": {"type": "boolean"}},
                               ["repo", "sha"]),
        "handler": gh_get_commit,
    },
}

SAMPLE_TOOLS: dict[str, dict[str, Any]] = {
    "list_repos": {
        "description": "List sample engineering repositories.",
        "handler": lambda args: list_repos(),
    },
    "list_prs": {
        "description": "List pull requests. Optional repo and state (open|closed|all).",
        "handler": lambda args: list_prs(args.get("repo"), args.get("state", "open")),
    },
    "get_pr": {
        "description": "Get one pull request by repo and number.",
        "handler": lambda args: get_pr(str(args.get("repo", "")), int(args.get("number", 0))),
    },
    "list_issues": {
        "description": "List issues. Optional repo and state (open|closed|all).",
        "handler": lambda args: list_issues(args.get("repo"), args.get("state", "open")),
    },
    "get_issue": {
        "description": "Get one issue by repo and number.",
        "handler": lambda args: get_issue(str(args.get("repo", "")), int(args.get("number", 0))),
    },
}
for _name in ("search_code", "get_file", "list_commits", "get_commit"):
    SAMPLE_TOOLS[_name] = {
        "description": f"{GITHUB_TOOLS[_name]['description']} (not available in sample mode)",
        "handler": _sample_only(_name),
    }

TOOLS = GITHUB_TOOLS if SOURCE == "github" else SAMPLE_TOOLS


def tools_list() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": name,
                "description": meta["description"],
                "inputSchema": meta.get("inputSchema") or {"type": "object", "additionalProperties": True},
            }
            for name, meta in TOOLS.items()
        ]
    }


def tools_call(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    if name not in TOOLS:
        return {
            "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
            "isError": True,
        }
    if not isinstance(arguments, dict):
        arguments = {}
    with span(f"mcp {name}", "tool", input=arguments, **{"langfuse.trace.name": f"mcp {name}"}) as s:
        try:
            result = TOOLS[name]["handler"](arguments)
        except ToolError as e:
            span_output(s, {"error": str(e)})
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:  # noqa: BLE001 — surface tool errors to caller, never crash
            span_output(s, {"error": f"{type(e).__name__}: {e}"})
            return {
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True,
            }
        span_output(s, result)
    text = json.dumps(result, indent=2)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": result,
        "isError": False,
    }


def handle_rpc(body: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params") or {}
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "engineering-mcp", "version": VERSION},
                "instructions": f"Engineering data source: {SOURCE}"
                                + (f" (GitHub owner {GITHUB_OWNER}, read-only)" if SOURCE == "github" else ""),
            },
        }
    if method == "notifications/initialized":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": tools_list()}
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        return {"jsonrpc": "2.0", "id": req_id, "result": tools_call(name, arguments)}
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
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

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path in ("/healthz", "/"):
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return
        self._send(404, b'{"error":"not found"}\n')

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if path != "/mcp":
            self._send(404, b'{"error":"not found"}\n')
            return
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, b'{"error":"invalid json"}\n')
            return
        if isinstance(body, list):
            out: Any = [handle_rpc(item) for item in body]
        else:
            out = handle_rpc(body)
        payload = json.dumps(out).encode("utf-8")
        self._send(200, payload)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    detail = ""
    if SOURCE == "github":
        detail = (f" owner={GITHUB_OWNER} token={'set' if GITHUB_TOKEN else 'none (public only)'}"
                  f" repos={','.join(GITHUB_REPOS) or 'all'}"
                  f" prompt_guard={'on' if PROMPT_GUARD_ENABLED else 'off'}")
    print(f"engineering-mcp {VERSION} source={SOURCE}{detail} listening on 0.0.0.0:{PORT} (/mcp, /healthz)",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
