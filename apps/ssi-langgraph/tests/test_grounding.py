"""Day 18 grounding tests: when every tool errored or came back empty, the answer is
written deterministically (no model call); mixed turns get a note in the answer prompt.
Each case runs through the control layer and the LangGraph engine (/ask and
/v1/chat/completions)."""
from __future__ import annotations

import json

import pytest

from conftest import cl
import graph
from test_server import base, call  # noqa: F401  (fixture reuse)

LIVE_TZ_ERROR = ("Microsoft Graph error 400: TimeZoneNotSupportedException: A valid TimeZone value must be "
                 "specified. The following TimeZone value is not supported: 'auto'.")
LIVE_CALL = ("productivity_m365_list_events", {"top": 50, "days": 7, "timezone": "auto"})
ENGINES = {"control_layer": lambda q: cl.run_ask(q), "langgraph": lambda q: graph.run_ask(q)}


@pytest.fixture(autouse=True)
def model_planner(monkeypatch):
    monkeypatch.setattr(cl, "PLANNER", "model")


@pytest.mark.parametrize("engine", ENGINES)
def test_live_case_all_errors_is_deterministic(fake, engine):
    """The exact live bug: Graph 400 on timezone 'auto' must not become 'you have no meetings'."""
    fake.chat_script = [[LIVE_CALL]]
    fake.tool_errors[("productivity", "m365_list_events")] = LIVE_TZ_ERROR
    out = ENGINES[engine]("Do I have meetings this week?")
    assert out["grounding"]["rule"] == "all_errors"
    assert out["answer"] == ("I couldn't read your calendar: Microsoft Graph returned an error "
                             "(timezone not supported).")
    assert "no meetings" not in out["answer"].lower()
    assert fake.generate_prompts == []  # the model never wrote the answer
    assert set(out) >= {"ok", "mode", "tool_calls", "answer", "model", "usage", "budgets", "planner", "memory"}


@pytest.mark.parametrize("engine", ENGINES)
def test_empty_events_is_deterministic(fake, engine):
    fake.chat_script = [[("productivity_m365_list_events", {"days": 7})]]
    fake.results[("productivity", "m365_list_events")] = {"source": "microsoft-graph", "returned": 0, "events": []}
    out = ENGINES[engine]("Do I have meetings this week?")
    assert out["grounding"]["rule"] == "empty"
    assert out["answer"] == "No meetings found in the next 7 days."
    assert fake.generate_prompts == []


@pytest.mark.parametrize("engine", ENGINES)
def test_empty_list_prs_is_deterministic(fake, engine):
    fake.chat_script = [[("engineering_list_prs", {"state": "open", "limit": 5})]]
    fake.results[("engineering", "list_prs")] = {"pull_requests": [], "returned": 0, "withheld": []}
    out = ENGINES[engine]("Any open PRs?")
    assert out["grounding"]["rule"] == "empty"
    assert out["answer"] == "No open pull requests found."


@pytest.mark.parametrize("engine", ENGINES)
def test_mixed_error_goes_to_the_model_with_a_note(fake, engine):
    fake.chat_script = [[LIVE_CALL, ("engineering_list_prs", {"state": "open", "limit": 5})]]
    fake.tool_errors[("productivity", "m365_list_events")] = LIVE_TZ_ERROR
    out = ENGINES[engine]("Open PRs and my meetings this week?")
    g = out["grounding"]
    assert g["rule"] == "none" and g["mixed"] is True
    assert g["failed"] == ["productivity.m365_list_events"] and g["empty"] == []
    prompt = fake.generate_prompts[-1]
    assert "FAILED and returned no data: productivity.m365_list_events" in prompt
    assert "do not invent data" in prompt and "count you give must match" in prompt
    assert out["answer"] == fake.answer


@pytest.mark.parametrize("engine", ENGINES)
def test_all_good_results_are_rule_none_without_note(fake, engine):
    fake.chat_script = [[("engineering_list_prs", {"state": "open", "limit": 5})]]
    out = ENGINES[engine]("Any open PRs?")
    assert out["grounding"] == {"rule": "none"}
    assert "Note:" not in fake.generate_prompts[-1]


def test_openai_route_uses_grounding(base, fake):  # noqa: F811
    fake.chat_script = [[LIVE_CALL]]
    fake.tool_errors[("productivity", "m365_list_events")] = LIVE_TZ_ERROR
    code, _, text = call(base, "POST", "/v1/chat/completions",
                         {"model": "ssi-langgraph", "messages": [{"role": "user", "content": "Do I have meetings this week?"}]})
    assert code == 200
    body = json.loads(text)
    assert body["choices"][0]["message"]["content"].startswith("I couldn't read your calendar")
    assert body["ssi"]["grounding"]["rule"] == "all_errors"


def test_error_reason_never_leaks_secrets():
    msg = "tool error: Microsoft Graph error 500: token=abc123secret Bearer eyJhbGciOi.eyJzdWIi.sig ghp_ABCDEF123"
    reason = cl.error_reason(msg)
    for leak in ("abc123secret", "eyJ", "ghp_", "Bearer"):
        assert leak not in reason
    assert reason.startswith("Microsoft Graph returned an error")


@pytest.mark.parametrize("result,empty", [
    ([], True), ({}, True), ({"events": []}, True), ({"returned": 0}, True),
    ({"pull_requests": [], "withheld": ["x"]}, True), ({"events": [{"s": 1}]}, False),
    ({"displayName": "Lab User"}, False), ({"error": "boom"}, False),
])
def test_hop_is_empty(result, empty):
    assert cl.hop_is_empty(result) is empty
