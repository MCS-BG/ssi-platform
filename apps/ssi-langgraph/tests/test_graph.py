"""Day 17 graph tests: routing across the MCP slots, Prompt Guard (question, tool arguments,
tool results), memory follow-ups, error handling, and parity with the control layer."""
from __future__ import annotations

import json

import pytest

from conftest import INJECTION, cl
import graph

FULL_PATH_ONE_ROUND = ["guard_input", "load_memory", "agent", "tools", "agent", "answer", "save_memory"]


# ---------------------------------------------------------------------------
# Graph shape
# ---------------------------------------------------------------------------
def test_graph_has_the_documented_nodes_and_edges():
    g = graph.GRAPH.get_graph()
    assert set(g.nodes) == {"__start__", "guard_input", "load_memory", "agent", "keyword_plan", "tools",
                            "answer", "save_memory", "__end__"}
    edges = {(e.source, e.target, e.conditional) for e in g.edges}
    assert ("__start__", "guard_input", False) in edges
    assert ("guard_input", "load_memory", False) in edges
    assert {("load_memory", t, True) for t in ("agent", "keyword_plan", "tools")} <= edges
    assert {("agent", t, True) for t in ("tools", "keyword_plan", "answer")} <= edges
    assert ("keyword_plan", "tools", False) in edges
    assert {("tools", "agent", True), ("tools", "answer", True)} <= edges
    assert ("answer", "save_memory", False) in edges and ("save_memory", "__end__", False) in edges
    assert "guard_input" in graph.mermaid()


# ---------------------------------------------------------------------------
# Routing across the slots
# ---------------------------------------------------------------------------
def test_model_routes_one_question_to_all_three_slots(fake):
    fake.chat_script = [[
        ("engineering_list_prs", {"state": "open", "limit": 5}),
        ("business_fo_query", {"entity": "CustomersV3", "filter": "CustomerAccount eq 'DEMO-C0001'"}),
        ("productivity_m365_list_events", {"days": 7}),
    ]]
    out = graph.run_ask("Open PRs that affect customer DEMO-C0001, and a meeting about it this week?")
    assert out["ok"] and out["engine"] == "langgraph"
    assert out["mode"] == "ask-model-tools" and out["plan_source"] == "model"
    assert out["slots_used"] == ["business", "engineering", "productivity"]
    assert fake.called() == [("engineering", "list_prs"), ("business", "fo_query"), ("productivity", "m365_list_events")]
    hosts = {c["slot"]: c["host"] for c in fake.mcp_calls}
    assert hosts == {"engineering": "engineering-mcp:8000", "business": "mcp-server:8000", "productivity": cl.M365_MCP_HOST}
    assert out["planner"]["used"] == "model" and out["planner"]["rounds"] == 2
    assert out["graph_path"] == FULL_PATH_ONE_ROUND
    assert out["answer"] == fake.answer


def test_second_round_uses_the_first_rounds_results(fake):
    fake.chat_script = [[("engineering_list_prs", {"limit": 1})], [("engineering_list_commits", {"repo": "ssi-platform", "limit": 2})]]
    out = graph.run_ask("What changed in the newest PR?")
    assert fake.called() == [("engineering", "list_prs"), ("engineering", "list_commits")]
    assert out["graph_path"] == ["guard_input", "load_memory", "agent", "tools", "agent", "tools", "answer", "save_memory"]
    second = fake.chat_requests[1]["messages"]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool"]
    assert "Fix invoice rounding" in second[-1]["content"]


def test_only_offered_tools_reach_the_model(fake):
    fake.chat_script = ["Hello!"]
    graph.run_ask("Hi there")
    names = {t["function"]["name"] for t in fake.chat_requests[0]["tools"]}
    assert "engineering_list_prs" in names and "productivity_m365_list_events" in names
    assert "productivity_m365_send_mail" not in names and "engineering_delete_repo" not in names


def test_no_tool_call_falls_back_to_keyword_planner(fake):
    fake.chat_script = ["I can answer without tools."]
    out = graph.run_ask("What open PRs touch the invoice service, and what customer account owns it?")
    assert out["planner"]["used"] == "keyword"
    assert out["planner"]["fallback_reason"] == "model returned no tool calls"
    assert out["mode"] == "ask-planned" and out["plan_source"] == "question"
    assert fake.called() == [("engineering", "list_prs"), ("business", "fo_query")]
    assert out["graph_path"] == ["guard_input", "load_memory", "agent", "keyword_plan", "tools", "answer", "save_memory"]


def test_tool_outside_the_allowlist_is_rejected_and_never_runs(fake):
    fake.chat_script = [[("productivity_m365_send_mail", {"to": "dana@example.com"})]]
    out = graph.run_ask("Send an email to dana about my calendar")
    assert out["planner"]["used"] == "keyword"
    assert "unknown tool" in out["planner"]["fallback_reason"]
    assert ("productivity", "m365_send_mail") not in fake.called()
    assert ("productivity", "m365_list_events") in fake.called()


def test_bad_arguments_are_rejected_by_the_schema(fake):
    fake.chat_script = [[("engineering_list_prs", {"limit": 500})]]
    out = graph.run_ask("five hundred prs please")
    assert "above maximum" in out["planner"]["fallback_reason"]
    assert all(c["arguments"].get("limit") != 500 for c in fake.mcp_calls)


def test_planner_keyword_skips_the_agent_node(fake, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    out = graph.run_ask("Do I have unread emails?")
    assert out["graph_path"] == ["guard_input", "load_memory", "keyword_plan", "tools", "answer", "save_memory"]
    assert out["planner"] == {"requested": "keyword", "used": "keyword", "backend": "ollama"}
    assert fake.mcp_calls[0]["arguments"] == {"top": 10, "unread_only": True}
    assert fake.chat_requests == []


def test_no_keywords_falls_back_to_lab_notes(fake, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    out = graph.run_ask("How was the lab built?")
    assert out["plan_source"] == "fallback"
    assert fake.called() == [("business", "search_notes")]


def test_tool_call_budget_is_enforced(fake):
    fake.chat_script = [[("engineering_list_prs", {"state": s}) for s in ("open", "closed", "all")]
                        + [("productivity_m365_whoami", {}), ("business_fo_list_entities", {}), ("engineering_list_issues", {})]]
    out = graph.run_ask("Everything at once")
    assert len(fake.mcp_calls) == cl.MAX_TOOL_CALLS == out["budgets"]["tool_calls_used"]
    assert "agent" not in out["graph_path"][4:]  # budget used up: no second round


def test_demo_runs_the_fixed_two_hop_plan(fake):
    out = graph.run_demo()
    assert out["mode"] == "demo"
    assert fake.called() == [("engineering", "list_prs"), ("business", "fo_query")]
    assert out["graph_path"] == ["guard_input", "load_memory", "tools", "answer", "save_memory"]
    assert fake.chat_requests == []


def test_openai_backend_uses_the_same_graph(fake, monkeypatch):
    monkeypatch.setattr(cl, "LLM_BACKEND", "openai")
    monkeypatch.setattr(cl, "OPENAI_BASE_URL", "http://vllm.example:8000/v1")
    monkeypatch.setattr(cl, "OPENAI_MODEL", "served-model")
    monkeypatch.setattr(cl, "OPENAI_API_KEY", "")
    fake.chat_script = [[("engineering_list_commits", {"repo": "ssi-platform", "limit": 3})]]
    out = graph.run_ask("Latest commits in ssi-platform?")
    assert out["model"] == "served-model"
    assert fake.called() == [("engineering", "list_commits")]
    second = fake.openai_requests[1]["payload"]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "call_0"
    assert all("Authorization" not in r["headers"] for r in fake.openai_requests)


# ---------------------------------------------------------------------------
# Prompt Guard: question, tool arguments, tool results (fail closed)
# ---------------------------------------------------------------------------
def test_guard_blocks_the_question_before_anything_runs(fake, mem):
    with pytest.raises(RuntimeError, match="Refused by Prompt Guard"):
        graph.run_ask(INJECTION, "c-guard")
    assert fake.mcp_calls == [] and fake.chat_requests == [] and fake.generate_prompts == []
    assert mem.rows == {}


def test_guard_down_refuses_the_question(fake, mem):
    fake.guard_down = True
    with pytest.raises(RuntimeError, match="Prompt Guard unavailable, request refused"):
        graph.run_ask("What meetings do I have this week?", "c-down")
    assert fake.mcp_calls == [] and mem.rows == {}


def test_guard_withholds_a_poisoned_tool_result(fake):
    fake.results[("productivity", "m365_list_mail")] = {"messages": [{"subject": "Hi", "preview": INJECTION}]}
    fake.chat_script = [[("productivity_m365_list_mail", {"top": 5})]]
    out = graph.run_ask("Any new mail?")
    result = out["tool_calls"][0]["result"]
    assert set(result) == {"withheld"} and "withheld by Prompt Guard" in result["withheld"]
    assert all("attacker@example.com" not in p for p in fake.generate_prompts)
    assert all("attacker@example.com" not in json.dumps(r["messages"]) for r in fake.chat_requests)


def test_guard_down_while_checking_a_tool_result_refuses(fake):
    fake.chat_script = [[("engineering_list_prs", {"state": "open"})]]
    fake.guard_fail_after = 2  # question + tool call arguments pass, the result check finds Guard down
    with pytest.raises(RuntimeError, match="Prompt Guard unavailable"):
        graph.run_ask("Open PRs?")
    assert fake.called() == [("engineering", "list_prs")]
    assert fake.generate_prompts == []


def test_guard_blocks_poisoned_tool_arguments(fake):
    fake.chat_script = [[("engineering_list_issues", {"repo": "ssi-platform", "state": INJECTION[:60]})]]
    with pytest.raises(RuntimeError, match="Refused by Prompt Guard"):
        graph.run_ask("Show the open issues")
    assert fake.mcp_calls == []


# ---------------------------------------------------------------------------
# Memory (Day 15 semantics, same table format as the control layer)
# ---------------------------------------------------------------------------
def test_keyword_follow_up_inherits_the_last_tools(fake, mem, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    first = graph.run_ask("What meetings are on my calendar this week?", "day17-test-1")
    assert first["memory"] == {"enabled": True, "turns_loaded": 0, "stored": True}
    assert fake.mcp_calls[-1]["arguments"] == {"days": 7, "top": 20}
    second = graph.run_ask("And what about next week?", "day17-test-1")
    assert second["plan_source"] == "memory" and second["memory"]["turns_loaded"] == 1
    assert fake.mcp_calls[-1] == {"slot": "productivity", "name": "m365_list_events", "arguments": {"days": 14, "top": 20}, "host": cl.M365_MCP_HOST}
    assert "What meetings are on my calendar this week?" in fake.generate_prompts[-1]
    stored = mem.rows["day17-test-1"]
    assert [t["mode"] for t in stored] == ["langgraph:ask-planned", "langgraph:ask-planned"]
    assert stored[0]["tool_calls"][0]["result"]["events"][0]["subject"] == "Invoice review with Dana"


def test_model_planner_sees_the_earlier_conversation(fake, mem):
    fake.chat_script = [[("productivity_m365_list_events", {"days": 7})], "done",
                        [("engineering_list_prs", {"state": "open"})], "done"]
    graph.run_ask("What meetings do I have this week?", "day17-test-2")
    out = graph.run_ask("Which open PRs relate to that review?", "day17-test-2")
    planner_user = fake.chat_requests[2]["messages"][1]["content"]
    assert planner_user.startswith("Earlier in this conversation (oldest first):")
    assert "Invoice review with Dana" in planner_user
    assert out["memory"]["turns_loaded"] == 1


def test_other_conversations_see_nothing(fake, mem, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    graph.run_ask("What meetings are on my calendar this week?", "conv-a")
    out = graph.run_ask("And what about next week?", "conv-b")
    assert out["memory"]["turns_loaded"] == 0 and out["plan_source"] == "fallback"


def test_langgraph_continues_a_conversation_the_control_layer_started(fake, mem, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    cl.run_ask("What meetings are on my calendar this week?", "shared-1")
    out = graph.run_ask("And what about tomorrow?", "shared-1")
    assert out["plan_source"] == "memory" and fake.mcp_calls[-1]["arguments"]["days"] == 2
    again = cl.run_ask("And today?", "shared-1")  # and the control layer reads the LangGraph turn back
    assert again["memory"]["turns_loaded"] == 2 and fake.mcp_calls[-1]["arguments"]["days"] == 1


def test_memory_down_still_answers(fake, mem):
    mem.down = True
    fake.chat_script = [[("productivity_m365_list_events", {"days": 7})]]
    out = graph.run_ask("Meetings this week?", "c-mem-down")
    assert out["ok"] and out["answer"] == fake.answer
    assert out["memory"]["stored"] is False and "unavailable" in out["memory"]["error"]


def test_memory_disabled_reports_the_reason(fake):
    fake.chat_script = ["hi"]
    out = graph.run_ask("Hello")
    assert out["memory"]["enabled"] is False and out["memory"]["reason"] == "MEMORY_ENABLED=false"
    assert len(out["conversation_id"]) == 32


def test_client_history_is_memory_but_nothing_is_stored(fake, mem):
    turns = [{"question": "What meetings do I have this week?", "tool_calls": [], "answer": "Invoice review with Dana on Friday."}]
    fake.chat_script = [[("productivity_m365_list_mail", {"top": 5})]]
    out = graph.run_ask("Any mail from her?", None, client_turns=turns, store=False)
    assert out["memory"]["source"] == "request" and out["memory"]["turns_loaded"] == 1
    assert out["memory"]["stored"] is False and mem.rows == {}
    assert "Invoice review with Dana" in fake.chat_requests[0]["messages"][1]["content"]
    assert any("Invoice review with Dana on Friday." in t for t in fake.guard_texts)


def test_poisoned_client_history_is_refused(fake, mem):
    turns = [{"question": "hello", "tool_calls": [], "answer": INJECTION}]
    with pytest.raises(RuntimeError, match="Refused by Prompt Guard"):
        graph.run_ask("And then?", None, client_turns=turns, store=False)
    assert fake.chat_requests == [] and fake.mcp_calls == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
def test_productivity_tool_error_is_explained_not_fatal(fake):
    fake.tool_errors[("productivity", "m365_list_events")] = "not signed in to Microsoft 365: run login.py"
    fake.chat_script = [[("productivity_m365_list_events", {"days": 7}), ("engineering_list_prs", {"state": "open"})]]
    out = graph.run_ask("Meetings this week and open PRs?")
    assert out["tool_calls"][0]["result"] == {"error": "tool error: not signed in to Microsoft 365: run login.py"}
    assert out["tool_calls"][1]["result"]["prs"][0]["number"] == 12


def test_business_tool_error_stops_a_keyword_plan(fake, monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "keyword")
    fake.tool_errors[("business", "fo_query")] = "OData filter rejected"
    with pytest.raises(RuntimeError, match="tool error: OData filter rejected"):
        graph.run_ask("Which customer account is DEMO-C0001?")


def test_model_chosen_business_error_is_explained(fake):
    fake.tool_errors[("business", "fo_query")] = "OData filter rejected"
    fake.chat_script = [[("business_fo_query", {"entity": "CustomersV3", "filter": "bad"})]]
    out = graph.run_ask("Look up customer DEMO-C0001")
    assert out["tool_calls"][0]["result"] == {"error": "tool error: OData filter rejected"}


def test_model_down_falls_back_to_keywords(fake):
    fake.chat_script = [RuntimeError("unreachable http://ollama: connection refused")]
    out = graph.run_ask("Do I have meetings this week?")
    assert out["planner"]["used"] == "keyword"
    assert out["planner"]["fallback_reason"].startswith("model unavailable: unreachable")
    assert fake.called() == [("productivity", "m365_list_events")]


def test_model_error_in_the_second_round_answers_with_what_it_has(fake):
    fake.chat_script = [[("engineering_list_prs", {"state": "open"})], RuntimeError("HTTP 500 from ollama")]
    out = graph.run_ask("Open PRs?")
    assert out["ok"] and out["planner"]["used"] == "model"
    assert fake.called() == [("engineering", "list_prs")]


def test_one_slot_down_does_not_stop_planning(fake):
    fake.slot_down.add("business")
    fake.chat_script = [[("engineering_list_prs", {"state": "open"})]]
    out = graph.run_ask("Open PRs?")
    names = {t["function"]["name"] for t in fake.chat_requests[0]["tools"]}
    assert not any(n.startswith("business_") for n in names)
    assert out["slots_used"] == ["engineering"]


def test_empty_question_and_bad_conversation_id(fake):
    with pytest.raises(RuntimeError, match="question must not be empty"):
        graph.run_ask("   ")
    with pytest.raises(RuntimeError, match="invalid conversation_id"):
        graph.run_ask("hello", "bad id with spaces")
    assert fake.guard_texts == []


# ---------------------------------------------------------------------------
# Parity: same question, same fakes -> same tool calls and answer as the control layer
# ---------------------------------------------------------------------------
PARITY = [
    ("model", [[("engineering_list_prs", {"state": "open"}), ("productivity_m365_list_events", {"days": 7})], "done"],
     "Open PRs and my meetings this week?"),
    ("model", ["no tools"], "What open PRs touch the invoice service, and what customer account owns it?"),
    ("model", [[("productivity_m365_send_mail", {"to": "x@example.com"})]], "Send mail about my calendar"),
    ("keyword", [], "Show my unread emails and open issues"),
]


@pytest.mark.parametrize("planner,script,question", PARITY)
def test_same_tool_calls_and_answer_as_the_control_layer(fake, monkeypatch, planner, script, question):
    monkeypatch.setattr(cl, "PLANNER", planner)
    fake.chat_script = list(script)
    expected = cl.run_ask(question, "parity")
    calls_cl, prompts_cl = list(fake.mcp_calls), list(fake.generate_prompts)
    fake.mcp_calls.clear()
    fake.generate_prompts.clear()
    fake.chat_script = list(script)
    got = graph.run_ask(question, "parity")
    assert fake.mcp_calls == calls_cl
    assert fake.generate_prompts == prompts_cl
    for key in ("mode", "tool_calls", "slots_used", "answer", "planner"):
        assert got[key] == expected[key], key
