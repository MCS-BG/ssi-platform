# Day 16: suggested control-layer changes for the GitHub engineering MCP

**Status: applied in Day 16 part 2** (`apps/control-layer/server.py`, `k8s/day-16-control-layer.yaml`). Kept as the record of what changed and why. Differences from the suggestion: `/demo` uses `ENGINEERING_DEFAULT_REPO` too; Prompt Guard refusals from an MCP stay fatal (the `"Prompt Guard" not in str(e)` variant); engineering errors on model-written arguments are explained in every slot; the evidence is compacted (no indent, a fair share per tool) with a 6000-character budget (`EVIDENCE_MAX_CHARS`). See [day-16-real-cross-system-answers.md](day-16-real-cross-system-answers.md#2-model-chooses-the-tools).

The engineering MCP keeps every tool name the control layer already calls, so nothing breaks at the protocol level. Four changes are needed for real cross-system answers.

## 1. Tool catalog (the model's tool list)

Replace the four `engineering.*` lines in `TOOL_CATALOG` with these nine. Arguments ending in `?` are optional. In github mode, `repo` is a repository name in `MCS-BG`.

```diff
 TOOL_CATALOG = """Tools (slot.name):
-- engineering.list_prs args: repo?, state?
-- engineering.list_issues args: repo?, state?
-- engineering.get_issue args: repo, number
-- engineering.list_repos args: none
+- engineering.list_repos args: none
+- engineering.list_prs args: repo?, state?, limit?
+- engineering.get_pr args: repo, number, include_patch?
+- engineering.list_issues args: repo?, state?, limit?
+- engineering.get_issue args: repo, number, include_comments?
+- engineering.search_code args: query, repo?
+- engineering.get_file args: repo, path, ref?, start_line?, end_line?
+- engineering.list_commits args: repo, ref?, path?, limit?
+- engineering.get_commit args: repo, sha
 - business.fo_query args: entity, filter?, select?, top?
```

This adds about 90 tokens to the prompt. When part 2 (model chooses the tools) lands, this text block is replaced by the `inputSchema` that `tools/list` already returns for every engineering tool.

## 2. Planner: stop asking for the sample repository

`planner()` and `run_demo()` hard-code `{"repo": "invoice-service"}`. That repository only exists in the sample. In github mode it returns `Not found on GitHub: pull requests of MCS-BG/invoice-service ...`.

Suggested change: add a default repository setting, and leave `repo` out when it isn't set (the MCP then searches every allowed repository of the owner).

```diff
+ENGINEERING_DEFAULT_REPO = os.environ.get("ENGINEERING_DEFAULT_REPO", "")
+
+
+def eng_args(**extra: Any) -> dict[str, Any]:
+    args = dict(extra)
+    if ENGINEERING_DEFAULT_REPO:
+        args["repo"] = ENGINEERING_DEFAULT_REPO
+    return args
+
 ...
-    if wants_eng and ("pr" in q or "pull" in q):
-        steps.append({"slot": "engineering", "name": "list_prs", "arguments": {"repo": "invoice-service", "state": "open"}})
-    elif wants_eng and "issue" in q:
-        steps.append({"slot": "engineering", "name": "list_issues", "arguments": {"repo": "invoice-service", "state": "open"}})
-    elif wants_eng:
-        steps.append({"slot": "engineering", "name": "list_prs", "arguments": {"repo": "invoice-service", "state": "open"}})
+    if wants_eng and re.search(r"\b(prs?|pull requests?)\b", q):
+        steps.append({"slot": "engineering", "name": "list_prs", "arguments": eng_args(state="open", limit=5)})
+    elif wants_eng and re.search(r"\bissues?\b", q):
+        steps.append({"slot": "engineering", "name": "list_issues", "arguments": eng_args(state="open", limit=5)})
+    elif wants_eng and re.search(r"\bcommits?\b|\bchanged\b|\blatest change", q):
+        steps.append({"slot": "engineering", "name": "list_commits", "arguments": eng_args(limit=5)})
+    elif wants_eng:
+        steps.append({"slot": "engineering", "name": "list_prs", "arguments": eng_args(state="open", limit=5)})
```

Also fix `wants_eng`: `"pr" in q` is a substring test, so it fires on "prompt", "project", "price" and "productivity". Use word boundaries, as above, and add `commit` and `code` to the engineering keywords.

Lab values: `ENGINEERING_DEFAULT_REPO=ssi-platform` in the control-layer Deployment env. For `/demo` (the two-hop sample with `DEMO-C0001`), either keep a sample-mode engineering MCP, or leave `run_demo` pointed at `invoice-service` and document that `/demo` needs `ENGINEERING_SOURCE=sample`.

## 3. Engineering tool errors become explainable, like productivity

Today `run_step` turns only productivity tool errors into a result the answer can explain. Every other slot fails closed, which stops the whole `/ask`. Real GitHub errors (404 for a repository the token can't see, rate limits, an expired token) are normal operating conditions, not attacks. They should be explained in the answer, not end the request.

```diff
 def run_step(step: dict[str, Any]) -> dict[str, Any]:
     try:
         return call_tool(step["slot"], step["name"], step.get("arguments") or {})
     except RuntimeError as e:
-        if step["slot"] == "productivity" and str(e).startswith("tool error:"):
+        if step["slot"] in ("productivity", "engineering") and str(e).startswith("tool error:"):
             return {"error": str(e)}
         raise
```

Prompt Guard refusals (`Refused by Prompt Guard`, `Prompt Guard unavailable`) still raise before the MCP is called, so the loop still fails closed on Guard. The engineering MCP's own Guard refusals come back as `tool error: Refused by Prompt Guard ...` and get explained instead of crashing the request. If you want those to stay fatal too, add `and "Prompt Guard" not in str(e)` to the condition.

## 4. Evidence budget

`synthesize()` keeps 3500 characters of evidence across all tool calls, and the model loop keeps 800 characters per hop. The Day 16 manifest sets `RESULT_MAX_CHARS=3000` and `FILE_MAX_CHARS=2500` on the engineering MCP, so one GitHub result fits. With two or more hops, raise the `synthesize` cut to about 6000 characters when the model allows it. That is fine for `llama3.2:3b` with its default context. Or drop `indent=2` from the `json.dumps` there, which saves about 25%.

## Nothing else changes

- Slot name, URL and Host header: still `engineering`, `http://engineering-mcp:8000/mcp`, `engineering-mcp:8000`.
- `mcp_call` already reads `structuredContent` and treats `isError: true` as `tool error: ...`, which is exactly what the GitHub backend returns.
- The SSI gateway's `/mcp/engineering` route needs no change. The new tools appear in `tools/list` on their own.
