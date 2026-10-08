# Day 16: Real cross-system answers

Goal: SSI (Sovereign Super Intelligence) answers questions with real data from each system it is connected to, not sample data. Day 16 is built in four parts: real GitHub data in the engineering MCP slot, the model choosing the tools, an off-by-default switch to a bigger model, and real D365. The first three are built; real D365 waits on an environment URL.

| Part | Status |
| --- | --- |
| [1. Engineering MCP on real GitHub data](#1-engineering-mcp-on-real-github-data) | Built and tested offline. Not applied yet. |
| [2. Model chooses the tools](#2-model-chooses-the-tools) | Built, tested offline and with the real `llama3.2:3b`. Not applied yet. Apply together with part 1. |
| [3. Bigger model via vLLM (off by default, not in the lab)](#3-bigger-model-via-vllm-off-by-default-not-in-the-lab) | Built (OpenAI-compatible backend), tested against a stub. Off by default. |
| [4. Real D365 (Dataverse or Finance and Operations OData)](#4-real-d365-dataverse-or-finance-and-operations-odata) | TODO: waiting on the environment URL. |

How to read these steps:

- Every code block has a label above it: **Terminal** (the laptop) or **Browser**.
- Each block holds one command. Quotes are zsh-safe.
- `kubectl` must point at the lab cluster, as set up on Day 2 and Day 8.

---

## 1. Engineering MCP on real GitHub data

Until today the engineering slot (`engineering-mcp`) served two made-up repositories. It now reads real repositories, issues, pull requests, code and commits from GitHub through the REST API. It uses a fine-grained token that can only read. The server sends GET requests and nothing else, so it cannot change anything on GitHub.

The MCP interface did not change: same JSON-RPC at `/mcp`, same Service, and the tool names the control layer already calls (`list_repos`, `list_prs`, `get_pr`, `list_issues`, `get_issue`) still work. Four tools are new.

### What is new

| Object | Role |
| --- | --- |
| `apps/engineering-mcp/server.py` | GitHub REST backend added next to the Day 10 sample. Still stdlib only, so it runs from a ConfigMap on `python:3.12-slim` with no pip install. |
| `apps/engineering-mcp/tests/test_server.py` | Offline tests. A local stub plays GitHub and Prompt Guard, so every tool and every error path is checked without a token or network. |
| `k8s/day-16-engineering-mcp-github.yaml` | New ConfigMap and Deployment, with the same names as Day 10 so applying upgrades the slot in place. Also adds an egress NetworkPolicy. The token comes from the Secret `engineering-mcp-github`, which you create yourself. |
| `charts/ssi` | `engineeringMcp.github.*` values: token Secret, owner, allowlist and the egress policy. Off by default. |
| `infra/terraform/apps` | `enable_engineering_mcp_github` (default `false`) switches the manifests to the Day 16 file, or sets the chart values in Helm mode. `github_token` is used only when `create_secrets = true`. |
| `docs/day-16-control-layer-catalog.patch.md` | Control-layer changes so the planner and the model know about the new tools. Applied in part 2. |

### Data source switch

| `ENGINEERING_SOURCE` | Behaviour |
| --- | --- |
| unset (default) | `github` if `GITHUB_TOKEN` is set, otherwise `sample`. Applying the manifest before the Secret exists keeps the Day 10 sample running. |
| `github` | Real GitHub data. If there's no token, it reads public repositories only (60 requests an hour, no code search). Use that only for a smoke test. |
| `sample` | The Day 10 sample (`invoice-service`, `billing-ui`), unchanged. |

Other settings: `GITHUB_OWNER` (default `MCS-BG`) is the only account whose repositories can be read. `GITHUB_REPOS` is an optional comma-separated allowlist of repository names. `GITHUB_CACHE_SECONDS` (default 60) caches identical GET requests to save rate limit. `RESULT_MAX_CHARS` and `FILE_MAX_CHARS` keep results small.

### Tools

| Tool | GitHub REST call (GET) | Notes |
| --- | --- | --- |
| `list_repos` | `/user/repos`, falling back to `/users/{owner}/repos` | Only repositories of `GITHUB_OWNER`, filtered by the allowlist. |
| `list_prs` | `/repos/{owner}/{repo}/pulls`; with no repo, `/search/issues` (`is:pr user:{owner}`) | `state` open, closed or all. `limit` 1 to 30. Newest update first. |
| `get_pr` | `/repos/{owner}/{repo}/pulls/{n}` + `/pulls/{n}/files` | Changed files capped at 30 (file name, status, lines added and removed). `include_patch=true` adds short diffs. |
| `list_issues` | `/repos/{owner}/{repo}/issues`; with no repo, `/search/issues` | Pull requests are removed (GitHub returns them as issues too). |
| `get_issue` | `/repos/{owner}/{repo}/issues/{n}` (+ `/comments`) | `include_comments=true` adds the newest 5 comments. |
| `search_code` | `/search/code` | Needs a token. Scoped to the owner (or one repo, or the allowlist). Returns paths and up to 2 matching fragments per hit. |
| `get_file` | `/repos/{owner}/{repo}/contents/{path}` | Text files only. `start_line` and `end_line` select a range. Content is capped, and the reply says which `start_line` to ask for next. A folder path returns a folder listing instead. |
| `list_commits` | `/repos/{owner}/{repo}/commits` | Optional `ref` (branch) and `path`. Returns the short sha, the first line of the message, the author and the date. |
| `get_commit` | `/repos/{owner}/{repo}/commits/{sha}` | Message, stats and changed files. |

Every result is trimmed so a 3B to 8B model can read it. Bodies are cut at 600 characters (300 in lists), and lists are shortened until the whole result fits `RESULT_MAX_CHARS` (3000 in the manifest).

### Guardrails

- **Read-only by construction.** The server makes only GET requests, and the token can only read.
- **One owner.** A `repo` outside `GITHUB_OWNER`, or outside `GITHUB_REPOS` when that is set, is refused before any call to GitHub.
- **Prompt Guard on the way in.** Search queries, file paths and refs are classified before the call, using the same contract as `mcp-server` and `m365-mcp`. This check lives in the MCP itself because the SSI gateway's `/mcp/engineering` route reaches this server without going through the control layer.
- **Prompt Guard on the way out.** Issue and pull request titles and bodies, comments, commit messages, code fragments and file contents are classified before they reach the model. A flagged item is replaced with `[withheld by Prompt Guard ...]`. Anyone can open an issue on a public repository, so this is the main indirect prompt-injection channel.
- **Fail closed.** If Prompt Guard is down, the tool call is refused (`PROMPT_GUARD_FAIL_OPEN=false`).
- **Clear errors, never a crash.** Every GitHub failure comes back as a tool error (`isError: true`) the answer can explain:

| GitHub reply | Tool error says |
| --- | --- |
| 401 | The token in Secret `engineering-mcp-github` is wrong, expired or revoked. |
| 403 with rate limit used up | When the limit resets, in UTC. |
| 403 or 429 with `Retry-After` | Secondary rate limit, and how many seconds to wait. |
| 403 otherwise | The token is missing a permission, with the list of permissions it needs. |
| 404 | It doesn't exist, or the token can't see it. A private repository that isn't selected on the token also returns 404. |
| 422 | GitHub could not process the request (usually a bad search query). |
| 5xx | Retried once, then reported. |
| No connection | GitHub is unreachable: check DNS and the egress NetworkPolicy. |

The token is never written to a log or a tool result.

### Egress NetworkPolicy

`si-lab` has no default-deny policy today. Every existing policy only limits incoming traffic. `engineering-mcp-egress` makes this one pod default-deny for outgoing traffic and then allows only:

- DNS (`kube-dns` in `kube-system`, port 53)
- Prompt Guard (port 8080)
- the OpenTelemetry collector in `monitoring` (ports 4317 and 4318)
- HTTPS (port 443) to public addresses, which is how it reaches `api.github.com`

A NetworkPolicy can't match a hostname, so 443 is open to any public IP. Private, link-local and shared address ranges are excluded, which keeps out the cloud metadata endpoint and every in-cluster or LAN service. Incoming traffic is unchanged: the Day 10 policy still lets the control layer and the gateway call the pod.

### Step 1: Create the GitHub token (once)

**Browser:** github.com, then **Settings**, then **Developer settings**, then **Personal access tokens**, then **Fine-grained tokens**, then **Generate new token**.

| Field | Value |
| --- | --- |
| Token name | `ssi-engineering-mcp` |
| Resource owner | `MCS-BG` |
| Expiration | 90 days (put a reminder in the calendar to rotate it) |
| Repository access | **Only select repositories**: the repositories SSI may read (at least `ssi-platform`) |
| Repository permissions | **Contents: Read-only**, **Issues: Read-only**, **Pull requests: Read-only**, **Metadata: Read-only** (GitHub adds Metadata automatically) |
| Account permissions | none |

Copy the token once. Don't paste it into chat, a file in the repo, or a ticket.

### Step 2: Store the token in the cluster (once, and on every rotation)

**Terminal:**

```bash
kubectl -n si-lab create secret generic engineering-mcp-github --from-literal=token=<PASTE_TOKEN>
```

To keep the token out of shell history, put a space in front of the command (zsh with `HIST_IGNORE_SPACE`), or use `--from-file=token=/dev/stdin` and paste the token, then press Ctrl-D.

To rotate the token later, delete the Secret, create it again, and restart the pod:

**Terminal:**

```bash
kubectl -n si-lab delete secret engineering-mcp-github
```

### Step 3: Apply

Rolling out with part 2 (the normal case): skip this step and use the single combined `kubectl apply` in [part 2](#apply-together-with-part-1), then come back for the restart, status and log checks below. The commands here are for the engineering MCP on its own.

**Terminal:**

```bash
kubectl apply -f ~/ssi-platform/k8s/day-16-engineering-mcp-github.yaml
```

**Terminal:**

```bash
kubectl -n si-lab rollout restart deployment/engineering-mcp
```

**Terminal:**

```bash
kubectl -n si-lab rollout status deployment/engineering-mcp --timeout=120s
```

**Terminal** (the first log line should say `source=github owner=MCS-BG token=set`):

```bash
kubectl -n si-lab logs deployment/engineering-mcp --tail=5
```

With OpenTofu instead, set `enable_engineering_mcp_github = true` and run plan and apply as on Day 13. Manifests mode then takes `k8s/day-16-engineering-mcp-github.yaml`. Helm mode sets `engineeringMcp.github.enabled=true` and uses `engineering_mcp_github_owner` and `engineering_mcp_github_repos`.

### Step 4: Test

**Terminal** (leave it running):

```bash
kubectl -n si-lab port-forward deployment/engineering-mcp 8000:8000
```

**Terminal** (a second window):

```bash
curl -s http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_repos","arguments":{}}}'
```

**Terminal:**

```bash
curl -s http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"list_commits","arguments":{"repo":"ssi-platform","limit":3}}}'
```

**Terminal** (needs the token):

```bash
curl -s http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"search_code","arguments":{"query":"planner","repo":"ssi-platform"}}}'
```

Expected: `"isError": false` and `"source": "github"` in each result. If a call fails, the error text says why (see the table under Guardrails).

Offline tests (no cluster, no token, no network). Run them from the repo root:

**Terminal:**

```bash
python3 apps/engineering-mcp/tests/test_server.py
```

Expected last line: `49 checks passed`.

### Control layer follow-up

The Day 15 control layer asked for `repo: invoice-service`, which exists only in the sample. Part 2 replaces that with `ENGINEERING_DEFAULT_REPO=ssi-platform` and makes engineering tool errors explainable, so **apply this step together with part 2** (one `kubectl apply`, see part 2). Applying only this file leaves `/demo` and keyword plans asking GitHub for `invoice-service` and failing.

### Azure DevOps equivalent

The same slot can read Azure Repos and Azure Boards instead of GitHub. Only the backend changes; the tools, guardrails, NetworkPolicy and Secret pattern stay the same.

| GitHub | Azure DevOps (REST, `api-version=7.1`) |
| --- | --- |
| `list_repos` | `GET https://dev.azure.com/{org}/{project}/_apis/git/repositories` |
| `list_prs`, `get_pr` | `GET .../_apis/git/repositories/{repo}/pullrequests?searchCriteria.status=active`, then `.../pullrequests/{id}/iterations/{n}/changes` for the changed files |
| `list_issues`, `get_issue` | Work items: `GET .../_apis/wit/workitems?ids=...`. Listing needs a WIQL query, which is a read-only `POST .../_apis/wit/wiql`. That would be the one allowed POST. |
| `get_file` | `GET .../_apis/git/repositories/{repo}/items?path=...&versionDescriptor.version=...` |
| `list_commits`, `get_commit` | `GET .../_apis/git/repositories/{repo}/commits` and `.../commits/{id}/changes` |
| `search_code` | Code Search: `POST https://almsearch.dev.azure.com/{org}/{project}/_apis/search/codesearchresults` (read-only) |

There are two ways to authenticate:

- **PAT (quickest).** User settings, then **Personal access tokens**. Pick one organization only, a short expiry, and the scopes **Code: Read**, **Work Items: Read** and **Project and Team: Read**. It is sent as HTTP Basic with an empty user name. Store it in the same kind of Secret (`engineering-mcp-ado`, key `token`).
- **Entra ID (preferred for a business).** Use the Azure DevOps resource `499b84ac-1321-427f-aa17-267ca6975798` with the delegated `user_impersonation` scope. The token comes from the same device-code sign-in pattern as the Day 14 M365 MCP, reusing the same Entra app with one added API permission. Unattended options are a service principal or a managed identity (workload identity on AKS) added as a user in the organization with **Basic** access and reader permissions. Organizations can restrict or turn off PAT creation, so Entra is the long-term path.

---

## 2. Model chooses the tools

Until today the control layer picked tools with keywords: "PR" meant `list_prs`, "meeting" meant `m365_list_events`, and so on. Now the chat model picks them. The control layer gives the model the real tool list of every MCP slot and checks every call the model makes before anything runs. When the model gets it wrong, the Day 15 keyword planner takes over, so the worst case is the old behaviour.

### How it works

1. **Prompt Guard on the question**, as before. A flagged question is refused before any model or tool sees it.
2. **Tool discovery.** The control layer calls `tools/list` on the engineering, business and productivity MCPs and keeps only the tools on the allowlist (below). Each tool's `inputSchema` is simplified (the MCP SDK's `anyOf [type, null]`, titles and defaults are flattened) so a 3B model can read it. The list is cached for 5 minutes (`TOOLS_CACHE_SECONDS`). A slot that is down is left out and retried after 30 seconds; the other slots still work.
3. **Native tool calling.** `POST /api/chat` on Ollama with `tools` = those schemas, function names `<slot>_<tool>` (for example `engineering_list_prs`). The model returns structured `tool_calls`. The system prompt names the three systems, the default repository and the call budget. **Day 15 memory** (earlier turns of the same `conversation_id`) goes into the prompt, so a follow-up like "and next week?" is resolved by the model.
4. **Validation, before any call runs.** Every call must:
   - name a tool that was offered (allowlist plus the live `tools/list`),
   - pass the tool's JSON schema: required arguments present, types right (safe conversions such as `"5"` to `5` are allowed), `enum`, `minimum` and `maximum` respected, strings at most 500 characters (`TOOL_ARG_MAX_CHARS`),
   - stay within `MAX_TOOL_CALLS` (4) for the whole question.
   Unknown arguments are dropped. A missing required `repo` on an engineering tool is filled from `ENGINEERING_DEFAULT_REPO`. Repeated identical calls run once.
5. **Run and screen.** Calls go through the same MCP path as before. Every tool result is classified by Prompt Guard before any model reads it (`RESULT_GUARD`); a flagged result is replaced by `withheld`. The model then gets the results and may make one more round of calls (`PLANNER_MAX_ROUNDS`, default 2), for example `get_pr` after `list_prs`.
6. **Answer.** The answer step is unchanged from Day 15, with evidence compacted to `EVIDENCE_MAX_CHARS` (6000) and shared fairly between the tools that ran.

### When the keyword planner takes over

The whole question falls back to the Day 15 keyword plan when, in the first round:

- the model returns no tool calls (for example a greeting, or a follow-up it cannot place),
- it names a tool that was not offered (for example `m365_send_mail`, which is not on the allowlist), or
- any argument fails the schema (wrong type, value outside `enum`, `limit` above the maximum, required argument missing), or
- the model server is down or answers badly.

The reply says which planner ran and why: `"planner": {"requested": "model", "used": "keyword", "fallback_reason": "..."}`. Invalid calls in a later round just end the planning; the results already collected are kept.

### Errors and guardrails

| Situation | Behaviour |
| --- | --- |
| Engineering or productivity tool error (GitHub 404 or rate limit, not signed in to Microsoft 365) | Explained in the answer; the other systems still answer. |
| Business tool error on arguments the **model** wrote (for example an OData filter D365 rejects) | Explained in the answer; the other systems still answer. |
| Business tool error in a keyword plan | Stops the request, as on Day 15. |
| Prompt Guard refusal, in the control layer or inside an MCP | Stops the request (fail closed), in every slot. Changed from Day 14, where the productivity slot explained these instead. |
| Prompt Guard down | Refused, as before. |

Write tools are not on the allowlist, so the model cannot call them even if an MCP offers them. The default allowlist (`PLANNER_TOOL_ALLOWLIST` to change it):

| Slot | Tools |
| --- | --- |
| engineering | `list_repos`, `list_prs`, `get_pr`, `list_issues`, `get_issue`, `search_code`, `get_file`, `list_commits`, `get_commit` |
| business | `fo_query`, `fo_list_entities`, `fo_get_entity_metadata`, `search_notes` |
| productivity | `m365_whoami`, `m365_list_mail`, `m365_get_mail`, `m365_list_events`, `m365_list_onedrive`, `m365_search_onedrive` |

### Settings

| Variable | Lab value | Meaning |
| --- | --- | --- |
| `PLANNER` | `model` | `model` = the model picks tools, with keyword fallback. `keyword` = the Day 15 keyword planner only (same code, Day 15 behaviour). |
| `MODEL` | `llama3.2:3b` | Ollama model for planning and answers. `qwen2.5:3b` is the alternative (see the check below); pull it with the Day 5 model job first. |
| `LLM_BACKEND` | `ollama` | `openai` = any OpenAI-compatible server (part 3). |
| `OLLAMA_NUM_CTX` | `4096` | Context window for `/api/chat`. The tool list takes about 2,000 tokens. |
| `ENGINEERING_DEFAULT_REPO` | `ssi-platform` | Repository used when a question names none (keyword plans, `/demo`, and required `repo` arguments). Empty = leave `repo` out and let the engineering MCP decide. Replaces the hard-coded `invoice-service` from the sample. |
| `PLANNER_MAX_ROUNDS` | `2` | Tool-calling rounds per question (1 to 4). |
| `MAX_TOOL_CALLS` | `4` | Tool calls per question, across all rounds. |
| `EVIDENCE_MAX_CHARS` | `6000` | Tool results passed to the answer step. |
| `RESULT_GUARD` | `true` | Prompt Guard on every tool result. |

`GET /tools` on the control layer shows the tools the model is offered right now, per slot.

The keyword planner also got the catalog fixes from [day-16-control-layer-catalog.patch.md](day-16-control-layer-catalog.patch.md): whole-word keywords (`pr` no longer matches "prompt", "project" or "productivity"), commit questions go to `list_commits`, and the nine engineering tools are in the tool catalog.

### Real-model check (llama3.2:3b on CPU)

Ten questions through the full control layer: the real engineering MCP in github mode against a GitHub stub, business and productivity MCP stubs with the real `tools/list` schemas, and Ollama running `llama3.2:3b` on CPU (no GPU, so the times are worst case; on the lab GPU they are a few seconds).

| Question | Tools the model chose | Result |
| --- | --- | --- |
| Most recent commits in ssi-platform | `list_commits` repo=ssi-platform | Right |
| List the open pull requests | `list_prs` state=open | Right |
| Show me the open issues | `list_issues` state=open | Right |
| Where is the planner function defined | `search_code` query="planner function" | Right |
| Look up customer DEMO-C0001 | `fo_query` CustomersV3 | Right tool, but the OData filter was wrong (wrong field name, or empty). With real D365 that call fails and the answer explains it. |
| Any unread emails | `m365_list_mail` unread_only=true | Right tool, `top=1` is too small. |
| Meetings this week | `m365_list_events` days=7 | Right |
| Open PRs that might affect DEMO-C0001, and a meeting about it this week | `list_prs` + `m365_list_events` + `fo_query`, with `limit` above the maximum | Schema check rejected it, keyword fallback answered with the right three tools. In an earlier run the model picked OneDrive search instead of the calendar. |
| Follow-up "And what about next week?" (Day 15 memory) | `m365_list_events` | Resolved from memory, but `days=7` instead of 14. In an earlier run the model returned no call and the keyword fallback (with memory) answered it. |
| "Hi! Who are you?" | `m365_whoami` | Unnecessary but harmless read-only call. |

Verdict: llama3.2:3b reliably emits well-formed tool calls and picks the right tool for single-system questions (every time across two runs). It is weak at arguments (OData filters, `top` and `limit`, date windows) and at questions spanning three systems. Schema validation, the allowlist and the keyword fallback are what make it safe to switch on: a bad call never runs and the question is still answered. For better arguments, try `qwen2.5:3b` or a larger model via part 3. Latency on CPU: 7 to 14 seconds for a single-system question, about 25 seconds for a cross-system one or a cold start.

The same ten questions with **`qwen2.5:3b`** (also CPU): the right tool for every single-system question, no fallbacks, and better arguments (`fo_query` filter on a plausible key field with correct OData quoting, sensible `top` values). But it misspelled the repository once (`ai-ops-homelab`, which GitHub answered with a 404 the answer explained), skipped `list_prs` in the three-system question, kept `days=7` for "next week", and also called `m365_whoami` for the greeting. Neither 3B model is clearly better overall: `llama3.2:3b` stays the default (already pulled, slightly faster), and `qwen2.5:3b` is worth trying when argument quality matters more than the occasional wrong repository name.

### Apply (together with part 1)

The control layer and the engineering MCP go together: `ENGINEERING_DEFAULT_REPO=ssi-platform` exists only on real GitHub, not in the Day 10 sample. Create the token Secret from part 1 first (step 2). Then:

**Terminal:**

```bash
kubectl apply -f ~/ssi-platform/k8s/day-06-netpol-pgvector.yaml -f ~/ssi-platform/k8s/day-16-engineering-mcp-github.yaml -f ~/ssi-platform/k8s/day-16-control-layer.yaml
```

`k8s/day-16-control-layer.yaml` carries the Day 15 memory and its pgvector NetworkPolicy, so it replaces the Day 15 file. The Day 6 policy goes in the same command, for the reason given in the Day 15 doc.

**Terminal:**

```bash
kubectl -n si-lab rollout status deployment/control-layer --timeout=180s
```

**Terminal** (the first line should show `model=llama3.2:3b` and `planner=model backend=ollama engineering_default_repo=ssi-platform`):

```bash
kubectl -n si-lab logs deployment/control-layer --tail=5
```

### Test

**Terminal** (leave it running):

```bash
kubectl -n si-lab port-forward deployment/control-layer 8080:8080
```

**Terminal** (a second window):

```bash
curl -s http://127.0.0.1:8080/tools
```

**Terminal:**

```bash
curl -s http://127.0.0.1:8080/ask -H 'Content-Type: application/json' -d '{"question":"What are the latest commits in ssi-platform, and do I have meetings this week?"}'
```

Expected: `"planner": {"requested": "model", "used": "model", ...}` and `tool_calls` with `list_commits` and `m365_list_events`. `"used": "keyword"` with a `fallback_reason` is fine too: the model's call was rejected and the keyword planner answered.

Roll back to Day 15 planning without changing the code: set `PLANNER=keyword` (`kubectl -n si-lab set env deployment/control-layer PLANNER=keyword`), or apply `k8s/day-15-control-layer-memory.yaml`.

OpenTofu: `control_layer_planner` (default `"model"`) and `engineering_default_repo` (default `"ssi-platform"`). Manifests mode now always takes `k8s/day-16-control-layer.yaml` for the control layer and patches the env only when a setting differs from the lab defaults. Helm: `controlLayer.planner`, `controlLayer.engineeringDefaultRepo`, `controlLayer.ollamaNumCtx`.

## 3. Bigger model via vLLM (off by default, not in the lab)

A 3B model is enough to pick one tool. It is not good at arguments and multi-system questions (see the check above). A larger open-weight model fixes that, but it does not fit the lab GPU (4 GB of VRAM). So vLLM is an **off-by-default switch** for a rented GPU server or a cloud GPU node pool (AKS, EKS or GKE). The lab stays on Ollama.

### The switch

The control layer speaks two APIs for both planning and answers:

| `LLM_BACKEND` | Calls | Used for |
| --- | --- | --- |
| `ollama` (default) | `/api/chat` (tools) and `/api/generate` | The lab. |
| `openai` | `POST {OPENAI_BASE_URL}/chat/completions` with `tools` | vLLM, Azure OpenAI, or any OpenAI-compatible server. |

| Variable | Meaning |
| --- | --- |
| `OPENAI_BASE_URL` | Base URL ending in `/v1`. In-cluster vLLM: `http://vllm.si-lab.svc.cluster.local:8000/v1`. Azure OpenAI: `https://<resource>.openai.azure.com/openai/v1`. |
| `OPENAI_MODEL` | The served model name (vLLM `--served-model-name`) or the Azure deployment name. Defaults to `MODEL`. |
| `OPENAI_API_KEY` | Optional. Read only from the Secret `control-layer-llm` (key `OPENAI_API_KEY`); never in git, values or logs. In-cluster vLLM needs none. |

The Day 13 names (`MODEL_API`, `MODEL_BASE_URL`, `MODEL_NAME`) are still read as aliases.

Everything from part 2 stays the same: the same tool schemas, validation, allowlist, Prompt Guard on questions and results, memory and keyword fallback. Only the transport changes (OpenAI tool calls carry JSON-string arguments and `tool_call_id`; the control layer handles both).

### Turning it on

OpenTofu (recommended): set `model_backend = "vllm"` with the `vllm_*` variables from Day 13 (model id, GPU count, quantization, node selector and tolerations for the GPU pool). OpenTofu deploys `k8s/day-13-vllm.yaml.tftpl`, skips Ollama, and patches the control layer with `LLM_BACKEND=openai`, `OPENAI_BASE_URL` and `OPENAI_MODEL`. Helm mode sets `controlLayer.modelBaseUrl` and `controlLayer.modelName`; the chart then sets `LLM_BACKEND=openai` itself.

By hand (manifests mode), with an endpoint that needs a key:

**Terminal:**

```bash
kubectl -n si-lab create secret generic control-layer-llm --from-literal=OPENAI_API_KEY=<PASTE_KEY>
```

**Terminal:**

```bash
kubectl -n si-lab set env deployment/control-layer LLM_BACKEND=openai OPENAI_BASE_URL=https://<endpoint>/v1 OPENAI_MODEL=<model>
```

Back to Ollama: `kubectl -n si-lab set env deployment/control-layer LLM_BACKEND=ollama`.

vLLM needs tool calling switched on for the model, through `vllm_extra_args`, for example `["--enable-auto-tool-choice", "--tool-call-parser", "llama3_json"]` for Llama 3.x, or `"hermes"` for Qwen 2.5. Without it vLLM ignores `tools`, the model returns no calls, and every question falls back to the keyword planner (visible in `fallback_reason`).

### Model choice and sizing

| Model class | GPU memory (rough) | Notes |
| --- | --- | --- |
| 7B to 8B instruct (Llama 3.1 8B, Qwen 2.5 7B) | one 24 GB GPU | Big step up in arguments over 3B. Cheapest useful option. |
| 14B to 32B (Qwen 2.5 14B/32B, AWQ quantized) | one 48 to 80 GB GPU | Good multi-system planning. |
| 70B class | 2 to 4 x 80 GB, tensor parallel | Only when the smaller ones are not enough. |

Keep `vllm_max_model_len` at 8192 or more: the tool list alone is about 2,000 tokens.

### Cost and teardown checklist (rented GPUs)

- Rented GPUs bill by the hour whether or not anyone asks a question. Note the hourly price before you start.
- Put model weights on a persistent volume (`vllm_weights_host_path` or the storage class) so a restart does not download them again.
- Keep the vLLM Service cluster-internal (ClusterIP). Never expose it publicly; the control layer is the only client.
- When done: set `model_backend = "ollama"` and apply, check that no vLLM pod or GPU node is left (`kubectl get nodes`), then scale the GPU node pool to zero or delete the rented server.

### Tested

Offline, with an OpenAI-compatible stub: tool calls with JSON-string arguments, `tool_call_id` on tool results, the Bearer key sent only when the Secret is set, and answers through `/v1/chat/completions`. Not run against a real vLLM server (nothing to run it on in the lab).

## 4. Real D365 (Dataverse or Finance and Operations OData)

**TODO: waiting on the environment URL.** Nothing is built yet. Planned design:

- The business slot (`mcp-server`, `fo_*` tools) moves from `fo-mock` to a real environment, either **Dataverse** (`https://{org}.crm.dynamics.com/api/data/v9.2/`) or **Finance and Operations OData** (`https://{env}.operations.dynamics.com/data/`).
- Auth: **Entra delegated sign-in** (device code), reusing the Day 14 Entra app with one added API permission: Dynamics CRM `user_impersonation` for Dataverse, or Dynamics ERP `AX.FullAccess` (delegated) for Finance and Operations. The token cache lives only in a Kubernetes Secret, as with `m365-mcp-auth`. Reads are GET only, and Prompt Guard screens content on the way out.
- Needs from the owner: the environment URL, and which of the two it is.
