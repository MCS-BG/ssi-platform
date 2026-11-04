"""Day 17: the SSI agent as a LangGraph StateGraph.

Same job as the control layer's run_ask (apps/control-layer/server.py), written as an explicit
graph. Every node calls a control-layer function (see cl_bridge.py), so Prompt Guard, the MCP
slots, the model backend and the Day 15 memory behave exactly as in the control layer. What
LangGraph adds is the shape: typed state, named nodes, conditional edges, a step limit, and
a path you can print for every question.

    START -> guard_input -> load_memory -+-> agent ------+-> tools -+-> agent (next round)
                                         |               |          +-> answer
                                         |               +-> keyword_plan -> tools
                                         |               +-> answer
                                         +-> keyword_plan (PLANNER=keyword)
                                         +-> tools (/demo: fixed two-hop plan)
    answer -> save_memory -> END

Fail closed: a Prompt Guard refusal, or Prompt Guard being down, raises inside the node and
stops the graph; nothing is answered and nothing is stored.
"""
from __future__ import annotations

import json
import operator
import os
import uuid
from typing import Annotated, Any, TypedDict

# Nothing leaves the cluster: LangSmith tracing stays off unless someone sets it on purpose.
os.environ.setdefault("LANGSMITH_TRACING", "false")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")

from langgraph.graph import END, START, StateGraph  # noqa: E402

import cl_bridge  # noqa: E402

cl = cl_bridge.load()

ENGINE = "langgraph"
# Upper bound on node executions per question (LangGraph's own loop guard, on top of the
# control layer's MAX_TOOL_CALLS and PLANNER_MAX_ROUNDS budgets).
RECURSION_LIMIT = max(10, int(os.environ.get("LG_RECURSION_LIMIT", "25")))

DEMO_QUESTION = (
    "What open PRs touch the invoice service, and what customer account "
    "owns that invoice line in the business tools?"
)


class AgentState(TypedDict, total=False):
    # Input
    question: str
    conversation_id: str | None
    store: bool  # write the turn to memory at the end (False: OpenAI API call without an id)
    client_turns: list[dict[str, Any]]  # OpenAI API without an id: history sent by the client
    preset_plan: list[dict[str, Any]]  # /demo: fixed steps, no planner, no memory
    # Filled in by the nodes
    guard: dict[str, Any]
    turns: list[dict[str, Any]]
    memory_text: str
    memory: dict[str, Any]
    planner: dict[str, Any]
    offered: dict[str, dict[str, Any]]
    messages: Annotated[list[dict[str, Any]], operator.add]  # planner chat (appended)
    seen: list[str]
    rounds: int
    pending: list[dict[str, Any]]  # tool calls chosen and not yet run
    model_chosen: bool
    hops: Annotated[list[dict[str, Any]], operator.add]  # tool calls with results (appended)
    tokens: int
    route: str
    mode: str
    plan_source: str
    answer: str
    grounding: dict[str, Any]  # Day 18: all_errors | empty | none
    usage: dict[str, Any]


def _usage_tokens(usage: dict[str, Any] | None) -> int:
    usage = usage or {}
    return int(usage.get("eval_count") or 0) + int(usage.get("prompt_eval_count") or 0)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
def guard_input(state: AgentState) -> dict[str, Any]:
    """Prompt Guard on the question, before anything else (control layer run_ask, step 1)."""
    question = str(state.get("question") or "")
    if not question.strip():
        raise RuntimeError("question must not be empty")
    given = state.get("conversation_id")
    cid = cl.valid_conversation_id(given) if given not in (None, "") else uuid.uuid4().hex
    guard = cl.classify(question.strip())  # raises on "malicious" or Guard down (fail closed)
    return {"conversation_id": cid, "guard": guard}


def load_memory(state: AgentState) -> dict[str, Any]:
    """Day 15 recall: the last MEMORY_TURNS turns of this conversation from control_layer_turns.
    OpenAI API calls without a conversation id bring their own history instead; that text
    did not come through Prompt Guard yet, so it is classified here (fail closed)."""
    if state.get("preset_plan"):
        return {"turns": [], "memory_text": "", "memory": {}, "pending": list(state["preset_plan"]),
                "model_chosen": False, "mode": "demo", "route": "tools"}
    mem: dict[str, Any] = {"enabled": cl.MEMORY.enabled, "turns_loaded": 0, "stored": False}
    turns: list[dict[str, Any]] = []
    client_turns = state.get("client_turns")
    if client_turns is not None:
        turns = list(client_turns)[-cl.MEMORY_TURNS:] if cl.MEMORY_TURNS > 0 else []
        mem["source"] = "request"
    elif cl.MEMORY.enabled and cl.MEMORY_TURNS > 0:
        try:
            turns = cl.MEMORY.load(state["conversation_id"], cl.MEMORY_TURNS)
        except cl.MemoryUnavailable as e:
            mem["error"] = str(e)
    memory_text, used = cl.memory_context(turns) if turns else ("", 0)
    if memory_text and client_turns is not None:
        cl.classify(memory_text)
    mem["turns_loaded"] = used
    return {"turns": turns, "memory_text": memory_text, "memory": mem}


def agent(state: AgentState) -> dict[str, Any]:
    """One planning round of the Day 16 model planner: the model picks tool calls (native tool
    calling), each call is checked against the slot's schema and the allowlist. A first round
    with no valid call falls back to the keyword planner, exactly like the control layer."""
    info = dict(state.get("planner") or {
        "requested": "model", "used": "model", "backend": cl.LLM_BACKEND, "rounds": 0, "rejected": []})
    info["rejected"] = list(info.get("rejected") or [])
    offered = state.get("offered")
    new_messages: list[dict[str, Any]] = []
    if offered is None:
        offered = cl.discover_tools()
        info["tools_offered"] = len(offered)
        if not offered:
            info.update(used="keyword", fallback_reason="no MCP tools discovered")
            return {"planner": info, "offered": offered, "route": "keyword"}
        memory_text = state.get("memory_text") or ""
        earlier = (f"Earlier in this conversation (oldest first):\n{memory_text[-cl.MEMORY_MAX_CHARS:]}\n\n"
                   if memory_text else "")
        new_messages = [
            {"role": "system", "content": cl.planner_system_prompt()},
            {"role": "user", "content": earlier + f"Question: {state['question'].strip()}"},
        ]
    rnd = int(state.get("rounds") or 0)
    hops = state.get("hops") or []
    messages = list(state.get("messages") or []) + new_messages
    try:
        reply = cl.llm_chat(messages, cl.tool_definitions(offered), cl.PLANNER_NUM_PREDICT)
    except Exception as e:  # noqa: BLE001
        if rnd == 0:
            info.update(used="keyword", fallback_reason=f"model unavailable: {' '.join(str(e).split())[:160]}")
            return {"planner": info, "offered": offered, "route": "keyword"}
        return {"planner": info, "route": "answer"}
    info["rounds"] = rnd + 1
    tokens = int(state.get("tokens") or 0) + _usage_tokens(reply.get("usage"))
    base = {"planner": info, "offered": offered, "rounds": rnd + 1, "tokens": tokens}
    calls = reply.get("tool_calls") or cl.calls_from_content(reply.get("content") or "")
    if not calls:
        if rnd == 0:
            info.update(used="keyword", fallback_reason="model returned no tool calls")
            return {**base, "route": "keyword"}
        return {**base, "route": "answer"}
    seen = list(state.get("seen") or [])
    steps: list[dict[str, Any]] = []
    for call in calls:
        step, why = cl.validate_call(call, offered)
        if step is None:
            info["rejected"].append(why)
            if rnd == 0:
                info.update(used="keyword", fallback_reason=f"invalid tool call: {why}")
                return {**base, "route": "keyword"}
            steps = []
            break
        key = json.dumps([step["slot"], step["name"], step["arguments"]], sort_keys=True)
        if key in seen:
            continue
        seen.append(key)
        step["id"] = call.get("id") or f"call_{rnd}_{len(steps)}"
        steps.append(step)
    steps = steps[: max(0, cl.MAX_TOOL_CALLS - len(hops))]
    if not steps:
        return {**base, "seen": seen, "route": "answer"}
    return {
        **base,
        "seen": seen,
        "messages": new_messages + [cl._assistant_message(steps)],
        "pending": steps,
        "model_chosen": True,
        "mode": "ask-model-tools",
        "plan_source": "model",
        "route": "tools",
    }


def keyword_plan(state: AgentState) -> dict[str, Any]:
    """Day 10-15 keyword planner (with the Day 15 memory follow-up): the fallback of the model
    planner, or the only planner with PLANNER=keyword."""
    steps, source = cl.plan_with_source(state["question"], state.get("turns") or [])
    info = state.get("planner") or {"requested": "keyword", "used": "keyword", "backend": cl.LLM_BACKEND}
    if info.get("requested") == "model":
        print(f"planner: keyword fallback ({info.get('fallback_reason')})", flush=True)
    return {"planner": info, "pending": steps, "model_chosen": False, "plan_source": source,
            "mode": "ask-planned", "route": "tools"}


def tools(state: AgentState) -> dict[str, Any]:
    """Run the pending calls through the control layer's run_step: Prompt Guard on the call,
    the MCP slot, Prompt Guard on the result (flagged = withheld, Guard down = refused).
    Productivity and engineering tool errors (and any error of a model-chosen call) come back
    as {"error": ...} for the answer to explain; everything else stops the graph."""
    done = len(state.get("hops") or [])
    new_hops: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    for step in state.get("pending") or []:
        if done + len(new_hops) >= cl.MAX_TOOL_CALLS:
            break
        plain = {"slot": step["slot"], "name": step["name"], "arguments": step.get("arguments") or {}}
        result = cl.run_step(plain, model_chosen=bool(state.get("model_chosen")))
        new_hops.append({**plain, "result": result})
        if step.get("fname"):
            messages.append(cl._tool_message(step, result))
    return {"hops": new_hops, "messages": messages, "pending": []}


def answer(state: AgentState) -> dict[str, Any]:
    """The control layer's answer step: only the tool results and the earlier conversation."""
    memory_text = "" if state.get("preset_plan") else state.get("memory_text") or ""
    text, usage, grounding = cl.grounded_answer(state["question"], state.get("hops") or [], memory_text)
    return {"answer": text, "usage": usage, "grounding": grounding, "tokens": int(state.get("tokens") or 0) + _usage_tokens(usage)}


def save_memory(state: AgentState) -> dict[str, Any]:
    """Store the turn (question, tool hops with trimmed results, answer) in control_layer_turns,
    the same table and format as the control layer, so either engine can continue a
    conversation. A memory failure never fails the question."""
    if state.get("preset_plan"):
        return {}
    mem = dict(state.get("memory") or {})
    if not state.get("store", True):
        mem["stored"] = False
        mem["reason"] = "no conversation_id: the request carried its own history"
        return {"memory": mem}
    if cl.MEMORY.enabled:
        turn = {
            "question": state["question"].strip(),
            "tool_calls": [
                {**{k: v for k, v in h.items() if k != "result"}, "result": cl.trim_result(h.get("result"))}
                for h in state.get("hops") or []
            ],
            "answer": state.get("answer") or "",
            "mode": f"{ENGINE}:{state.get('mode') or 'ask'}",
            "ok": True,
        }
        try:
            cl.MEMORY.save(state["conversation_id"], turn)
            mem["stored"] = True
        except cl.MemoryUnavailable as e:
            mem.setdefault("error", str(e))
    elif cl.MEMORY.reason:
        mem["reason"] = cl.MEMORY.reason
    return {"memory": mem}


# ---------------------------------------------------------------------------
# Edges
# ---------------------------------------------------------------------------
def route_after_memory(state: AgentState) -> str:
    if state.get("preset_plan"):
        return "tools"
    return "agent" if cl.PLANNER == "model" else "keyword_plan"


def route_after_agent(state: AgentState) -> str:
    return {"tools": "tools", "keyword": "keyword_plan"}.get(state.get("route") or "", "answer")


def route_after_tools(state: AgentState) -> str:
    planner = state.get("planner") or {}
    if (
        state.get("model_chosen")
        and planner.get("used") == "model"
        and int(state.get("rounds") or 0) < cl.PLANNER_MAX_ROUNDS
        and len(state.get("hops") or []) < cl.MAX_TOOL_CALLS
    ):
        return "agent"
    return "answer"


def build_graph() -> Any:
    g = StateGraph(AgentState)
    g.add_node("guard_input", guard_input)
    g.add_node("load_memory", load_memory)
    g.add_node("agent", agent)
    g.add_node("keyword_plan", keyword_plan)
    g.add_node("tools", tools)
    g.add_node("answer", answer)
    g.add_node("save_memory", save_memory)
    g.add_edge(START, "guard_input")
    g.add_edge("guard_input", "load_memory")
    g.add_conditional_edges("load_memory", route_after_memory, ["agent", "keyword_plan", "tools"])
    g.add_conditional_edges("agent", route_after_agent, ["tools", "keyword_plan", "answer"])
    g.add_edge("keyword_plan", "tools")
    g.add_conditional_edges("tools", route_after_tools, ["agent", "answer"])
    g.add_edge("answer", "save_memory")
    g.add_edge("save_memory", END)
    return g.compile()


GRAPH = build_graph()


def mermaid() -> str:
    return GRAPH.get_graph().draw_mermaid()


def _invoke(inputs: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Run the graph; returns (final state, node path)."""
    path: list[str] = []
    final: dict[str, Any] = {}
    for mode, chunk in GRAPH.stream(inputs, {"recursion_limit": RECURSION_LIMIT}, stream_mode=["updates", "values"]):
        if mode == "updates":
            path.extend(chunk.keys())
        else:
            final = chunk
    return final, path


def _guard_view(state: dict[str, Any]) -> dict[str, Any]:
    guard = state.get("guard") or {}
    return {"label": guard.get("label"), "malicious_score": guard.get("malicious_score")}


def run_ask(
    question: str,
    conversation_id: Any = None,
    *,
    client_turns: list[dict[str, Any]] | None = None,
    store: bool = True,
) -> dict[str, Any]:
    """Same request and reply as the control layer's POST /ask, plus "engine" and "graph_path"."""
    inputs: dict[str, Any] = {"question": question, "conversation_id": conversation_id, "store": store}
    if client_turns is not None:
        inputs["client_turns"] = client_turns
    state, path = _invoke(inputs)
    hops = state.get("hops") or []
    return {
        "ok": True,
        "engine": ENGINE,
        "mode": state.get("mode"),
        "plan_source": state.get("plan_source"),
        "question": question,
        "guard": _guard_view(state),
        "tool_calls": hops,
        "slots_used": sorted({h["slot"] for h in hops}),
        "answer": state.get("answer") or "",
        "grounding": state.get("grounding") or {"rule": "none"},
        "model": cl.active_model(),
        "usage": state.get("usage") or {},
        "budgets": {"max_tool_calls": cl.MAX_TOOL_CALLS, "max_tokens": cl.MAX_TOKENS,
                    "tool_calls_used": len(hops), "tokens_seen": int(state.get("tokens") or 0)},
        "planner": state.get("planner") or {},
        "conversation_id": state.get("conversation_id"),
        "memory": state.get("memory") or {},
        "graph_path": path,
    }


def demo_plan() -> list[dict[str, Any]]:
    """The control layer's /demo two-hop plan (engineering PR + business customer)."""
    return [
        {"slot": "engineering", "name": "list_prs", "arguments": cl.eng_args(state="open", limit=5)},
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


def run_demo(question: str | None = None) -> dict[str, Any]:
    q = question or DEMO_QUESTION
    state, path = _invoke({"question": q, "preset_plan": demo_plan(), "store": False})
    hops = state.get("hops") or []
    return {
        "ok": True,
        "engine": ENGINE,
        "mode": "demo",
        "question": q,
        "guard": _guard_view(state),
        "tool_calls": hops,
        "slots_used": sorted({h["slot"] for h in hops}),
        "answer": state.get("answer") or "",
        "grounding": state.get("grounding") or {"rule": "none"},
        "model": cl.active_model(),
        "usage": state.get("usage") or {},
        "budgets": {"max_tool_calls": cl.MAX_TOOL_CALLS, "max_tokens": cl.MAX_TOKENS, "tool_calls_used": len(hops)},
        "graph_path": path,
    }
