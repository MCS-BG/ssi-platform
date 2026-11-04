"""Day 17: SSI LangGraph agent, an HTTP service next to the control layer.

Same routes and replies as the control layer, so the gateway, the SSI Connector and the
Day 15/16 curl tests work unchanged against it (plus "engine" and "graph_path"):

POST   /ask                  {"question":"...", "conversation_id":"optional"}  the graph
POST   /demo                 the Andreas two-hop sample, through the graph
GET    /conversations/<id>   Day 15 memory, same table control_layer_turns
DELETE /conversations/<id>
GET    /memory
GET    /tools                tools offered to the model (same discovery and allowlist)
GET    /healthz

New in Day 17:

GET    /graph                the graph as Mermaid text (drawn by LangGraph itself)
GET    /v1/models            OpenAI-compatible model list (one model, LG_MODEL_ID)
POST   /v1/chat/completions  OpenAI-compatible chat. The last user message is the question.
                             With a conversation id ("conversation_id" in the body or in
                             "metadata", or the X-SSI-Conversation-Id header) the Day 15
                             memory is used and the turn is stored; without one, the earlier
                             user/assistant messages of the request are the memory (checked by
                             Prompt Guard first) and nothing is stored. "stream": true returns
                             the answer as server-sent events.

Configuration: the control layer's environment variables, unchanged (PROMPT_GUARD_URL, the
three *_MCP_URL slots, LLM_BACKEND / OLLAMA_URL / MODEL / OPENAI_*, PLANNER, MEMORY_*, PG_DSN
...). Day 17 adds LG_MODEL_ID and LG_RECURSION_LIMIT. No auth here, like the control layer:
ClusterIP only, the gateway's Bearer token guards the way in.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import graph

cl = graph.cl

LG_MODEL_ID = os.environ.get("LG_MODEL_ID", "ssi-langgraph").strip() or "ssi-langgraph"


def _content_text(content: Any) -> str:
    """OpenAI message content: a string, or a list of parts ({"type":"text","text":...})."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(p.get("text") or "") for p in content if isinstance(p, dict) and p.get("type") in ("text", "input_text")
        )
    return ""


def openai_inputs(body: dict[str, Any], header_cid: str | None) -> tuple[str, Any, list[dict[str, Any]] | None]:
    """(question, conversation_id, client_turns). client_turns is None when an id is given."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise RuntimeError("messages must be a non-empty list")
    convo = [
        (m.get("role"), _content_text(m.get("content")))
        for m in messages
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    if not convo or convo[-1][0] != "user" or not convo[-1][1].strip():
        raise RuntimeError("the last message must be a non-empty user message")
    question = convo[-1][1]
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    cid = body.get("conversation_id") or metadata.get("conversation_id") or header_cid or None
    if cid:
        return question, cid, None
    turns: list[dict[str, Any]] = []
    for role, text in convo[:-1]:
        if role == "user":
            turns.append({"question": text, "tool_calls": [], "answer": ""})
        elif turns and not turns[-1]["answer"]:
            turns[-1]["answer"] = text
    return question, None, turns


def openai_reply(out: dict[str, Any]) -> dict[str, Any]:
    usage = out.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_eval_count") or 0)
    completion_tokens = int(usage.get("eval_count") or 0)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": LG_MODEL_ID,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": out.get("answer") or ""}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
        "ssi": {
            "engine": out.get("engine"),
            "conversation_id": out.get("conversation_id"),
            "mode": out.get("mode"),
            "plan_source": out.get("plan_source"),
            "planner": out.get("planner"),
            "slots_used": out.get("slots_used"),
            "tool_calls": [{k: v for k, v in h.items() if k != "result"} for h in out.get("tool_calls") or []],
            "memory": out.get("memory"),
            "guard": out.get("guard"),
            "graph_path": out.get("graph_path"),
            "grounding": out.get("grounding"),
        },
    }


def sse_body(reply: dict[str, Any]) -> bytes:
    """The whole answer as one streamed chunk, then the stop chunk and [DONE]."""
    base = {"id": reply["id"], "object": "chat.completion.chunk", "created": reply["created"], "model": reply["model"]}
    first = {**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply["choices"][0]["message"]["content"]}, "finish_reason": None}]}
    last = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "ssi": reply["ssi"]}
    return (f"data: {json.dumps(first)}\n\ndata: {json.dumps(last, default=str)}\n\ndata: [DONE]\n\n").encode("utf-8")


def openai_error(message: str) -> tuple[int, dict[str, Any]]:
    if message.startswith("Refused by Prompt Guard"):
        code, kind = 400, "prompt_guard_refused"
    elif "Guard" in message or "unavailable" in message:
        code, kind = 503, "service_unavailable"
    else:
        code, kind = 400, "invalid_request_error"
    return code, {"error": {"message": message, "type": kind, "code": kind}}


class Handler(cl.Handler):
    """The control layer's handler (healthz, memory, tools, conversations) with the graph
    behind /ask and /demo, and the OpenAI-compatible routes."""

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/graph":
            self._send(200, graph.mermaid().encode("utf-8"), "text/plain; charset=utf-8")
            return
        if path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": LG_MODEL_ID, "object": "model", "created": 0, "owned_by": "ssi"}]})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/v1/chat/completions":
            self._chat_completions()
            return
        try:
            if path == "/demo":
                body = self._read_json()
                out = graph.run_demo(body.get("question"))
            elif path == "/ask":
                body = self._read_json()
                out = graph.run_ask(str(body.get("question") or ""), body.get("conversation_id"))
            else:
                self._send(404, b'{"error":"not found"}\n')
                return
            self._send(200, json.dumps(out, default=str).encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            err = {"ok": False, "engine": graph.ENGINE, "error": str(e)}
            self._send(503 if "Guard" in str(e) or "unavailable" in str(e) else 400, json.dumps(err).encode("utf-8"))

    def _chat_completions(self) -> None:
        try:
            body = self._read_json()
            question, cid, client_turns = openai_inputs(body, self.headers.get("X-SSI-Conversation-Id"))
            if cid is None:
                out = graph.run_ask(question, None, client_turns=client_turns, store=False)
            else:
                out = graph.run_ask(question, cid)
            reply = openai_reply(out)
        except Exception as e:  # noqa: BLE001
            code, err = openai_error(str(e))
            self._json(code, err)
            return
        if body.get("stream"):
            self._send(200, sse_body(reply), "text/event-stream; charset=utf-8")
            return
        self._json(200, reply)


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", cl.PORT), Handler)
    print(
        f"ssi-langgraph on 0.0.0.0:{cl.PORT} engine=langgraph model={cl.active_model()} "
        f"planner={cl.PLANNER} backend={cl.LLM_BACKEND} max_tool_calls={cl.MAX_TOOL_CALLS} "
        f"max_rounds={cl.PLANNER_MAX_ROUNDS} recursion_limit={graph.RECURSION_LIMIT} model_id={LG_MODEL_ID}"
        + (f" engineering_default_repo={cl.ENGINEERING_DEFAULT_REPO}" if cl.ENGINEERING_DEFAULT_REPO else ""),
        flush=True,
    )
    cl.MEMORY.startup()  # never blocks or fails startup; Postgres down = no recall
    server.serve_forever()


if __name__ == "__main__":
    main()
