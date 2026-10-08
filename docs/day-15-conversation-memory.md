# Day 15: conversation memory in the control layer (recall across questions)

Goal: let SSI (Sovereign Super Intelligence) remember a conversation. Until Day 14 every `/ask` started from zero: the control layer combined the MCP results for one question and then forgot them. From Day 15 the control layer stores each turn in Postgres and reloads the recent turns when the next question arrives with the same `conversation_id`. A follow-up such as "and what about next week?" or "show unread emails from that person" now builds on the earlier answers, whichever MCP slot produced them.

MCP servers still never talk to each other. Memory belongs to the control layer only: it reads and writes it, and it decides what goes into the model prompt. The MCP slots stay read-only and unchanged.

How to read these steps:

- Every code block has a label above it: **Terminal** (the laptop) or **Browser**.
- Each block holds one command. Quotes are zsh-safe.
- `kubectl` uses the same kubeconfig and SSH tunnel to the API as Day 14.

## What is new

| Object | Role |
| --- | --- |
| `apps/control-layer/server.py` | `/ask` accepts an optional `conversation_id` (one is generated and returned when missing). Each turn is stored; the last `MEMORY_TURNS` turns are loaded before planning. New routes `GET /conversations/<id>`, `DELETE /conversations/<id>`, `GET /memory`. |
| `k8s/day-15-control-layer-memory.yaml` | Supersedes the Day 10 ConfigMap `control-layer-code` and Deployment `control-layer` (adds an initContainer that installs `psycopg[binary]==3.3.6`, plus the memory settings). Adds NetworkPolicy `pgvector-allow-control-layer`. The Day 10 Service and NetworkPolicy stay as they are. |
| Table `control_layer_turns` | In the existing Day 4 pgvector database `rag`. Created by the control layer at startup (`CREATE TABLE IF NOT EXISTS`). No new database and no new Secret. |
| `charts/ssi` | `memory.*` values (Helm mode). The image now installs `psycopg` from `apps/control-layer/requirements.txt`. |
| `infra/terraform/apps` | `enable_conversation_memory` (default `true`, needs `enable_pgvector`). Manifests mode deploys the Day 15 file instead of the Day 10 ConfigMap + Deployment. |

### Routes

| Route | What it does |
| --- | --- |
| `POST /ask` `{"question":"...","conversation_id":"..."}` | Same loop as Day 14. The reply adds `conversation_id`, `memory` (`turns_loaded`, `stored`, and `error` if Postgres failed) and `plan_source` (`question`, `memory` or `fallback`). |
| `GET /conversations/<id>` | Stored turns of one conversation, oldest first: question, tool hops (slot, tool, arguments, trimmed result), answer, time. `404` when nothing is stored. |
| `DELETE /conversations/<id>` | Forgets the conversation: deletes every stored turn for that id. Returns `deleted_turns`. |
| `GET /memory` | Non-secret status: enabled, table ready, reachable, last error. |

A `conversation_id` is 1 to 128 characters from letters, digits, `_`, `.`, `:` and `-`. The generated ones are random 32-character hex strings. Through the private gateway the same routes are under `/control` (for example `POST /control/ask`, `DELETE /control/conversations/<id>`), behind the Bearer token as in Day 11.

## How recall works across the MCP slots

1. A question arrives with a `conversation_id`. Prompt Guard classifies it first, as before. A refused question is not stored.
2. The control layer loads the last `MEMORY_TURNS` turns (default 6) for that id from `control_layer_turns`.
3. **Planning.** The keyword planner still reads the new question first. If the question names no tool of its own ("And what about next week?", "Who organised it?"), the planner repeats the tools of the latest remembered turn and re-reads time windows and counts from the new question ("next week" = 14 days, "tomorrow" = 2, "today" = 1, "unread", "5 emails"). The tools run again; old results are never passed off as new ones. The same reading of time windows now applies to first questions too: "What is on my calendar today?" asks for 1 day instead of the default 7. Questions that go to the model-driven loop get the tail of the earlier conversation in the tool-choice prompt.
4. **Answer.** The answer prompt gets an "Earlier in this conversation" block (questions, tool calls with short result excerpts, answers), newest turns kept first, capped at `MEMORY_MAX_CHARS` (default 2500 characters) so `llama3.2:3b` keeps room for the new tool results. That is how "that person" or "that review" resolves to a name that came from a different slot in an earlier turn.
5. **Store.** After the answer, the turn is written: question, tool hops with each result trimmed to `MEMORY_RESULT_CHARS` (default 2000 characters; larger results are kept as a preview), answer, mode, time.

Example: "What meetings are on my calendar this week?" uses the productivity slot (`m365_list_events`). "Which open PRs and which customer account relate to that review?" uses the engineering and business slots, and the answer step sees the meeting from the first turn. The slots never saw each other's data; the control layer carried it.

### When Postgres is not there

Memory never blocks an answer:

- Postgres unreachable or a query fails: `/ask` still answers, without memory. The reply shows `"stored": false` and the error, the log says `memory: postgres unavailable, answering without memory for 30s`, and the control layer retries after 30 seconds (`MEMORY_RETRY_SECONDS`) so a down database does not slow every question. When Postgres is back, memory resumes by itself (`memory: postgres reachable again`).
- The control layer starts fine with Postgres down and creates the table on the first successful connection.
- `psycopg` not installed (for example the Day 10 manifest) or `MEMORY_ENABLED=false`: Day 14 behaviour, and the reply says why (`"reason"`).
- `/conversations` answers `503` while memory is unavailable. `/healthz` is not tied to Postgres, so the pod stays Ready.

### Settings

| Setting | Lab value | Notes |
| --- | --- | --- |
| `MEMORY_ENABLED` | `true` | `false` turns memory off; `conversation_id` is still returned. |
| `MEMORY_TURNS` | `6` | Turns loaded per question (maximum 20). |
| `MEMORY_MAX_CHARS` | `2500` | Size cap of the earlier-conversation block in the prompt. |
| `MEMORY_RESULT_CHARS` | `2000` (default) | Per tool result, when stored. |
| `PG_DSN` | `host=pgvector.si-lab.svc.cluster.local port=5432 dbname=rag user=rag` | Same as `mcp-server` and `rag-worker`. |
| `PGPASSWORD` | Secret `pgvector-auth`, key `POSTGRES_PASSWORD` | Existing Day 4 Secret. Marked optional: if it is missing the pod still runs, without memory. |
| `DATABASE_URL` | not set | Takes precedence over `PG_DSN`. For managed Postgres; comes from a Secret. |

## Step 1: Check the existing pieces (read-only)

Terminal

```bash
kubectl -n si-lab get statefulset/pgvector svc/pgvector secret/pgvector-auth deploy/control-layer
```

All four must exist. Nothing new needs to be created for the lab: the control layer uses the existing `pgvector-auth` Secret.

Terminal

```bash
kubectl -n si-lab get networkpolicy
```

Look for `pgvector-allow-clients` (Day 6: lets `mcp-server` and `rag-worker` reach pgvector). It may be missing since the namespace rename; step 2 puts it back.

## Step 2: Apply

> Day 16 note: `k8s/day-16-control-layer.yaml` carries this memory code plus the Day 16 model planner, and the same pgvector policy. When rolling out Day 15 and Day 16 together, apply the Day 16 file instead of this one (see [Day 16 part 2](day-16-real-cross-system-answers.md#apply-together-with-part-1)).

Apply the Day 6 pgvector policy and the Day 15 file together. This matters: Kubernetes NetworkPolicies add up, but as soon as **any** policy selects the pgvector pod, only the sources listed in some policy may connect. Applying `pgvector-allow-control-layer` alone would cut `mcp-server` (`search_notes`) and `rag-worker` off from pgvector.

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-06-netpol-pgvector.yaml -f ~/ssi-platform/k8s/day-15-control-layer-memory.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deployment/control-layer --timeout=180s
```

Terminal

```bash
kubectl -n si-lab logs deploy/control-layer -c control-layer --tail=20
```

Expected lines: `memory: on, postgres host=pgvector.si-lab.svc.cluster.local dbname=rag user=rag, last 6 turns, 2500 chars` and `memory: table control_layer_turns ready`.

From now on, apply this file instead of `k8s/day-10-control-layer.yaml` when the control layer changes.

Helm mode: `memory.enabled: true` (default) with `memory.dsn`, `memory.passwordSecretName` and `memory.passwordSecretKey`, or `memory.databaseUrlSecretName` for a `DATABASE_URL` Secret. The image from `build-control-layer.yml` now contains `psycopg`. The chart has no NetworkPolicies; apply `pgvector-allow-control-layer` from the Day 15 file together with the Day 6 `pgvector-allow-clients` policy. OpenTofu: `enable_conversation_memory = true` (default) deploys the Day 15 objects in manifests mode and the policy in both modes.

## Step 3: Test recall with two follow-up questions

Terminal

```bash
kubectl -n si-lab port-forward svc/control-layer 18080:8080
```

In a second terminal:

Terminal

```bash
curl -s http://127.0.0.1:18080/memory
```

Expected: `"enabled": true`, `"schema_ready": true`, `"reachable": true`.

Question 1:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/ask -H 'Content-Type: application/json' -d '{"question":"What meetings are on my calendar this week?","conversation_id":"day15-test-1"}'
```

Expected: `"memory": {"enabled": true, "turns_loaded": 0, "stored": true}` and a `productivity` / `m365_list_events` hop with `"days": 7`.

Follow-up 1 (no tool words of its own):

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/ask -H 'Content-Type: application/json' -d '{"question":"And what about next week?","conversation_id":"day15-test-1"}'
```

Expected: `"turns_loaded": 1`, `"plan_source": "memory"`, and `m365_list_events` again with `"days": 14`.

Follow-up 2 (different slots, same conversation):

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/ask -H 'Content-Type: application/json' -d '{"question":"Which open PRs and which customer account relate to that?","conversation_id":"day15-test-1"}'
```

Expected: `"turns_loaded": 2` and `"slots_used": ["business", "engineering"]`. The answer can refer to the meetings from the first two turns.

A different conversation does not see any of it:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/ask -H 'Content-Type: application/json' -d '{"question":"And what about next week?","conversation_id":"day15-test-2"}'
```

Expected: `"turns_loaded": 0`. This conversation starts empty, so nothing from `day15-test-1` reaches the planner or the answer.

Read the stored history:

Terminal

```bash
curl -s http://127.0.0.1:18080/conversations/day15-test-1
```

The same rows straight from Postgres:

Terminal

```bash
kubectl -n si-lab exec pgvector-0 -- psql -U rag -d rag -c 'SELECT conversation_id, count(*), max(created_at) FROM control_layer_turns GROUP BY 1'
```

## Step 4: Forget a conversation

Terminal

```bash
curl -s -X DELETE http://127.0.0.1:18080/conversations/day15-test-1
```

Expected: `"deleted_turns": 3`. A `GET` on the same id now answers `404`, and the next question with that id starts with `"turns_loaded": 0`.

Terminal

```bash
curl -s -X DELETE http://127.0.0.1:18080/conversations/day15-test-2
```

## What is stored, and for how long

Memory holds questions, answers and trimmed tool results, so it can contain mail subjects and previews, meeting subjects and business records. It stays in the lab Postgres, which only `mcp-server`, `rag-worker` and now the control layer may reach when the pgvector policies are applied. There is no automatic expiry yet. Delete a conversation with `DELETE /conversations/<id>`, or everything older than 30 days with:

Terminal

```bash
kubectl -n si-lab exec pgvector-0 -- psql -U rag -d rag -c "DELETE FROM control_layer_turns WHERE created_at < now() - interval '30 days'"
```

Anyone who can reach the control layer and knows a `conversation_id` can read that conversation. Inside the cluster the Day 10 policy limits callers to pods in `si-lab`; from outside, the gateway requires the Bearer token. Use the generated random ids rather than guessable ones.

## Roll back

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-10-control-layer.yaml
```

Terminal

```bash
kubectl -n si-lab delete networkpolicy pgvector-allow-control-layer
```

Keep `pgvector-allow-clients` (Day 6); it was part of the lab before Day 15. The table stays and is harmless. To remove it as well: `DROP TABLE control_layer_turns;` in `psql`.

## Managed Postgres on Azure and AWS

The control layer only needs a Postgres connection string, so the lab StatefulSet can be swapped for a managed service without code changes.

| Lab | Azure | AWS |
| --- | --- | --- |
| `pgvector` StatefulSet (Postgres 17) in `si-lab` | Azure Database for PostgreSQL flexible server | Amazon RDS for PostgreSQL (or Aurora PostgreSQL) |
| Secret `pgvector-auth` + `PGPASSWORD` | Secret with `DATABASE_URL`, synced from Azure Key Vault (Secrets Store CSI driver); Microsoft Entra authentication is the passwordless option | Secret with `DATABASE_URL`, synced from AWS Secrets Manager (Secrets Store CSI driver or External Secrets); IAM database authentication is the passwordless option |
| NetworkPolicy `pgvector-allow-control-layer` | Private access (VNet integration or private endpoint) and network security group rules for 5432 | Database in private subnets; security group allowing 5432 from the cluster (security groups for pods for per-workload rules) |
| Plain connection inside the cluster | TLS required by default: `sslmode=require` | TLS enforced by default on current versions (`rds.force_ssl`): `sslmode=require` |

Create the Secret with placeholders filled in (URL-encode special characters in the password; never commit it):

Terminal

```bash
kubectl -n si-lab create secret generic control-layer-memory --from-literal=DATABASE_URL='postgresql://<user>:<password>@<host>:5432/<database>?sslmode=require'
```

Then Helm: `--set memory.databaseUrlSecretName=control-layer-memory`. In manifests, replace the `PG_DSN` and `PGPASSWORD` entries with `DATABASE_URL` from that Secret. A dedicated database role that can only create and use `control_layer_turns` is better than reusing the RAG owner role.

## Tested before release

Run on a local Postgres 17 with Prompt Guard, the three MCP slots and Ollama stubbed (35 of 35 checks passed):

- Question 1 stores a turn and returns a generated `conversation_id`.
- Question 2 with the same id loads question 1; the follow-up re-runs `m365_list_events` with 14 days; the answer prompt contains the first question and its result.
- Engineering and business follow-ups see the productivity results from earlier turns; "that person" carries a name from an earlier turn into the mail step.
- A different id loads nothing.
- `DELETE` removes every turn; `GET` then answers `404`.
- Postgres stopped: `/ask` still answers (`stored: false`), the next question inside the back-off does not wait on a connection, `/conversations` answers `503`, `/healthz` stays `ok`, and memory resumes when Postgres is back. Starting with Postgres down works too.
- `MEMORY_ENABLED=false` and a Python without `psycopg` both behave like Day 14; `/demo` is unchanged; Prompt Guard refusals are not stored.

## Later

- Summaries of long conversations instead of only the last turns.
- Automatic expiry (a small CronJob running the 30-day `DELETE`).
- Per-user conversation ownership once the gateway carries user identity.
