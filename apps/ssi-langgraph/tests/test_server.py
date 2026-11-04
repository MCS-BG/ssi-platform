"""Day 17 HTTP tests: the control layer's routes and the OpenAI-compatible routes, served
by server.Handler on a loopback port (the fakes still play every backend)."""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from conftest import INJECTION, cl
import server


@pytest.fixture
def base(fake):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def call(base, method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode()


def test_healthz_graph_and_models(base):
    assert call(base, "GET", "/healthz")[0::2] == (200, "ok\n")
    code, ctype, text = call(base, "GET", "/graph")
    assert code == 200 and "graph TD" in text and "save_memory" in text
    code, _, text = call(base, "GET", "/v1/models")
    assert code == 200 and json.loads(text)["data"][0]["id"] == "ssi-langgraph"


def test_ask_has_the_control_layer_reply_shape(base, fake):
    fake.chat_script = [[("engineering_list_prs", {"state": "open"})]]
    code, _, text = call(base, "POST", "/ask", {"question": "Open PRs?"})
    out = json.loads(text)
    assert code == 200
    for key in ("ok", "mode", "question", "guard", "tool_calls", "slots_used", "answer", "model", "usage",
                "budgets", "planner", "conversation_id", "memory"):
        assert key in out
    assert out["engine"] == "langgraph" and out["graph_path"][0] == "guard_input"


def test_ask_refused_by_guard_is_503_like_the_control_layer(base):
    code, _, text = call(base, "POST", "/ask", {"question": INJECTION})
    assert code == 503 and json.loads(text)["error"].startswith("Refused by Prompt Guard")


def test_ask_bad_input_is_400(base):
    assert call(base, "POST", "/ask", {"question": ""})[0] == 400
    assert call(base, "POST", "/nope", {})[0] == 404


def test_tools_route_lists_only_allowlisted_tools(base):
    code, _, text = call(base, "GET", "/tools")
    functions = {t["function"] for t in json.loads(text)["tools"]}
    assert code == 200 and "engineering_list_prs" in functions and "productivity_m365_send_mail" not in functions


def test_demo_route(base, fake):
    code, _, text = call(base, "POST", "/demo", {})
    assert code == 200 and json.loads(text)["slots_used"] == ["business", "engineering"]


def test_conversations_routes_use_the_same_memory(base, fake, mem, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    call(base, "POST", "/ask", {"question": "What meetings are on my calendar this week?", "conversation_id": "day17-http"})
    code, _, text = call(base, "GET", "/conversations/day17-http")
    assert code == 200 and json.loads(text)["turns"][0]["mode"] == "langgraph:ask-planned"
    assert json.loads(call(base, "DELETE", "/conversations/day17-http")[2])["deleted_turns"] == 1
    assert call(base, "GET", "/conversations/day17-http")[0] == 404


def test_chat_completions_without_id_uses_request_history(base, fake, mem):
    fake.chat_script = [[("productivity_m365_list_mail", {"top": 5})]]
    body = {"model": "ssi-langgraph", "messages": [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "What meetings do I have this week?"},
        {"role": "assistant", "content": "Invoice review with Dana on Friday."},
        {"role": "user", "content": [{"type": "text", "text": "Any mail from her?"}]},
    ]}
    code, _, text = call(base, "POST", "/v1/chat/completions", body)
    out = json.loads(text)
    assert code == 200 and out["object"] == "chat.completion"
    assert out["choices"][0]["message"] == {"role": "assistant", "content": fake.answer}
    assert out["choices"][0]["finish_reason"] == "stop" and out["usage"]["total_tokens"] == 120
    assert out["ssi"]["memory"]["turns_loaded"] == 1 and out["ssi"]["memory"]["stored"] is False
    assert out["ssi"]["tool_calls"] == [{"slot": "productivity", "name": "m365_list_mail", "arguments": {"top": 5}}]
    assert mem.rows == {}


def test_chat_completions_with_id_uses_stored_memory(base, fake, mem, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    msg = lambda q: {"messages": [{"role": "user", "content": q}]}  # noqa: E731
    call(base, "POST", "/v1/chat/completions", msg("What meetings are on my calendar this week?"), {"X-SSI-Conversation-Id": "oa-1"})
    code, _, text = call(base, "POST", "/v1/chat/completions", {**msg("And what about next week?"), "conversation_id": "oa-1"})
    out = json.loads(text)
    assert code == 200 and out["ssi"]["conversation_id"] == "oa-1"
    assert out["ssi"]["plan_source"] == "memory" and out["ssi"]["tool_calls"][0]["arguments"]["days"] == 14
    assert len(mem.rows["oa-1"]) == 2


def test_chat_completions_stream(base, fake):
    fake.chat_script = ["hi"]
    code, ctype, text = call(base, "POST", "/v1/chat/completions", {"stream": True, "messages": [{"role": "user", "content": "Hello"}]})
    events = [line[6:] for line in text.split("\n") if line.startswith("data: ")]
    assert code == 200 and ctype.startswith("text/event-stream")
    assert events[-1] == "[DONE]"
    first = json.loads(events[0])
    assert first["object"] == "chat.completion.chunk" and first["choices"][0]["delta"]["content"] == fake.answer
    assert json.loads(events[1])["choices"][0]["finish_reason"] == "stop"


def test_chat_completions_errors(base, fake):
    code, _, text = call(base, "POST", "/v1/chat/completions", {"messages": [{"role": "user", "content": INJECTION}]})
    assert code == 400 and json.loads(text)["error"]["type"] == "prompt_guard_refused"
    code, _, text = call(base, "POST", "/v1/chat/completions", {"messages": []})
    assert code == 400 and json.loads(text)["error"]["type"] == "invalid_request_error"
    code, _, _ = call(base, "POST", "/v1/chat/completions", {"messages": [{"role": "assistant", "content": "hi"}]})
    assert code == 400
    fake.guard_down = True
    code, _, text = call(base, "POST", "/v1/chat/completions", {"messages": [{"role": "user", "content": "Hello"}]})
    assert code == 503 and "Prompt Guard unavailable" in json.loads(text)["error"]["message"]


def test_openai_inputs_pairs_history():
    q, cid, turns = server.openai_inputs({"messages": [
        {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"}, {"role": "user", "content": "d"}]}, None)
    assert q == "d" and cid is None
    assert turns == [{"question": "a", "tool_calls": [], "answer": "b"}, {"question": "c", "tool_calls": [], "answer": ""}]
    assert server.openai_inputs({"messages": [{"role": "user", "content": "x"}], "metadata": {"conversation_id": "m-1"}}, None)[1] == "m-1"
