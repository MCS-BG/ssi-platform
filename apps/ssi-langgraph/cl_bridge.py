"""Day 17: load the SSI control layer as a library, so the LangGraph agent uses the SAME code.

The LangGraph app replaces only the orchestration (which step runs next). Every step it runs
is a function of the existing control layer (apps/control-layer/server.py):

- Prompt Guard on the question, on tool arguments and on tool results: classify, run_step,
  guard_result (fail closed).
- The three MCP slots (engineering, business, productivity): discover_tools, tool_definitions,
  validate_call, run_step, the keyword planner plan_with_source.
- The model backend (LLM_BACKEND=ollama or openai, same env names): llm_chat, synthesize.
- Day 15 memory (table control_layer_turns): MEMORY, memory_context, trim_result.

Importing the control layer only reads its environment variables and builds the memory
object; it opens no connection and starts no server (main() runs only as __main__).

Where the file comes from (first match wins):
  CONTROL_LAYER_PATH            explicit path
  <this folder>/control_layer.py   the container image and the Day 17 ConfigMap
  ../control-layer/server.py       a checkout of the repository (tests, local runs)
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from types import ModuleType

HERE = pathlib.Path(__file__).resolve().parent

# Names the LangGraph agent calls. A control layer older than Day 16 lacks some of them;
# that stops startup with a clear message instead of failing on the first question.
REQUIRED = (
    "classify",
    "run_step",
    "guard_result",
    "discover_tools",
    "tool_definitions",
    "validate_call",
    "calls_from_content",
    "llm_chat",
    "planner_system_prompt",
    "_assistant_message",
    "_tool_message",
    "plan_with_source",
    "synthesize",
    "eng_args",
    "memory_context",
    "trim_result",
    "valid_conversation_id",
    "active_model",
    "MEMORY",
    "MemoryUnavailable",
    "PLANNER",
    "PLANNER_MAX_ROUNDS",
    "PLANNER_NUM_PREDICT",
    "MAX_TOOL_CALLS",
    "MAX_TOKENS",
    "MEMORY_TURNS",
    "MEMORY_MAX_CHARS",
    "LLM_BACKEND",
)


def control_layer_path() -> pathlib.Path:
    explicit = os.environ.get("CONTROL_LAYER_PATH", "").strip()
    if explicit:
        return pathlib.Path(explicit)
    for candidate in (HERE / "control_layer.py", HERE.parent / "control-layer" / "server.py"):
        if candidate.is_file():
            return candidate
    raise RuntimeError(
        "control layer source not found: set CONTROL_LAYER_PATH, or put control_layer.py next to server.py"
    )


def load() -> ModuleType:
    """Import the control layer once as module "control_layer" and check its API."""
    if "control_layer" in sys.modules:
        return sys.modules["control_layer"]
    path = control_layer_path()
    spec = importlib.util.spec_from_file_location("control_layer", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load the control layer from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["control_layer"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop("control_layer", None)
        raise
    missing = [name for name in REQUIRED if not hasattr(module, name)]
    if missing:
        sys.modules.pop("control_layer", None)
        raise RuntimeError(
            f"control layer at {path} is older than Day 16 (missing: {', '.join(missing)}); "
            "use apps/control-layer/server.py from Day 16 or later"
        )
    return module
