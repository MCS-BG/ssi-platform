# Sovereign Super Intelligence — real-world control layer

This note matches the poster `diagrams/si-control-layer-real-world.png`. It describes how the control layer replaces Microsoft Copilot UIs in a real deployment, while Power BI stays a separate reporting client on the same warehouse.

The lab has Open WebUI, Prompt Guard, a business MCP sample (`fo_*`), RAG, Ollama, Langfuse, Grafana, plus the Day 10 `control-layer` and the `engineering-mcp` (real GitHub, read-only, Day 16) in namespace `si-lab`.

Langfuse and Grafana stay in the architecture as the observability lane. Prefer not to spotlight them in write-ups except when changing an observability endpoint.

## What replaces what

| monitoring node | Role in this architecture |
| --- | --- |
| Open WebUI | Human chat. A person asks. It is not the agent loop. |
| Control layer | The only agent loop. Chooses tools, reads results, calls the model again, stops on a budget. This is the agent UI. |
| MCP slots | Tools that wrap systems of record. Not Copilot. |
| Power BI Desktop | Charts only. Reads Postgres/SQL. Not the agent loop. Not Copilot. |
| M365 Copilot / GitHub Copilot / Copilot Studio | Not used as UIs. Replaced by control layer + Open WebUI. |

You do not buy Copilot seats for this path. You do register apps and tokens for each MCP backend.

## Plain steps of one request

1. A person on a terminal or phone opens Open WebUI over a private network (VPN in the lab; not the public internet).
2. Prompt Guard classifies the chat message. If Guard cannot answer, the call stops.
3. The control layer starts the agent loop (`control-layer` Service in `si-lab`; curl `/demo` or `/ask`). If the request carries a `conversation_id`, it first loads that conversation's recent turns from Postgres (Day 15).
4. The model proposes tool calls (Day 16: native tool calling with the tools each MCP lists, Ollama or any OpenAI-compatible server). The control layer checks each call against the tool's schema and an allowlist, and checks budget (max tool calls, max tokens). If no valid call comes back, the keyword planner picks the tools instead. See `docs/day-16-real-cross-system-answers.md`.
5. Prompt Guard sits in front of the chosen MCP path. Fail closed again if Guard is down.
6. The control layer calls that MCP over HTTP inside the cluster and gets JSON back. That JSON is the context result.
7. The result is appended to conversation state. The model is called again with that history.
8. If another system is needed, the loop picks another MCP slot. Prior results may supply IDs or names as tool arguments.
9. When the budget says stop, or the model answers without another tool, the person sees the reply in Open WebUI. The control layer saves the turn (question, tool hops, answer) under the same `conversation_id`.
10. Langfuse records every hop (which MCP, which tool). Grafana stays operations only.

MCP servers never talk to each other. Within one question, tool results accumulate in the loop until the budget stops.

Across questions, the control layer keeps conversation memory (Day 15). Each turn (question, tool hops with trimmed results, answer) is stored in Postgres under a `conversation_id`, and the next question with the same id starts with the last six turns: the planner uses them to resolve follow-ups such as "and what about next week?", and the answer step sees them. A calendar answer from the Microsoft 365 slot can therefore feed a business or engineering follow-up. Only the control layer reads or writes that memory; `DELETE /conversations/<id>` forgets a conversation. See `docs/day-15-conversation-memory.md`.

## MCP slots and credentials

None of these require a Copilot license. Each needs normal API credentials stored as cluster secrets.

### Business productivity MCP → Microsoft Graph

- **Systems:** SharePoint, Teams, Outlook (and related Graph resources you consent to).
- **Credential:** Entra app registration with admin consent for the Graph scopes you need.
- **Not:** an M365 Copilot seat.
- **Lab:** Day 14 `m365-mcp` is live as the `productivity` slot: read-only mail, calendar and OneDrive for one personal Microsoft account (delegated sign-in through a public client app and a one-time device code; refresh token only in a cluster Secret). SharePoint and Teams need a work or school account and are not part of it. See `docs/day-14-m365-mcp.md`.

### Business ERP MCP → D365 / Dataverse / F&O OData

- **Systems:** Dynamics 365 entities over Dataverse and/or Finance & Operations OData. Many entities and security rules — not “one table.”
- **Credential:** Entra app registration with consent for those APIs.
- **Lab stand-in:** the live sample tools `fo_list_entities`, `fo_get_entity_metadata`, and `fo_query` show the shape. Swap the mock for real OData when a tenant is ready.

### Engineering MCP → GitHub and Azure DevOps

- **GitHub:** issues and pull requests via a fine-scoped token or a GitHub App (repo/issues/PR read as needed). Private repos need org access, not Copilot.
- **Azure DevOps:** work items via a PAT or an Entra app with work-item read.
- **Not:** a GitHub Copilot seat.

### Optional data MCP → Postgres financial facts

- **Shape:** period / account / amount (and related dimensions you define).
- **Credential:** database role with read on those tables; connection string in a secret.
- **Purpose:** agent tools that query the same warehouse Power BI uses for charts.

## Context and model (unchanged roles)

- **RAG / document store:** evidence only. Chunks enter the prompt. They do not update weights. They are not the system of record for ERP, Graph, or engineering work.
- **Ollama local slot:** default model path on the lab host GPU. The slot can be swapped.
- **Closed model off-lab:** optional dashed path. Using it sends data off the lab.

## Power BI path (separate from the agent loop)

The cluster does not become Power BI. Power BI Desktop (and a gateway when the network needs one) is the reporting client.

1. Facts live in Postgres (or a SQL mirror you publish for other connectors).
2. Desktop uses the PostgreSQL connector (or SQL Server connector against a mirror).
3. If Desktop or the Power BI service cannot reach the database, put an On-premises Data Gateway in front.
4. Charts are painted there. Power BI does not choose tools, does not call the model, and is not an MCP hop in Langfuse.

The optional data MCP and Power BI can read the same warehouse. That is the shared data product. The agent path and the chart path stay different.

## Build order (no Copilot license step)

1. Deploy the control layer in `si-lab` (only it may run the tool loop; budgets; fail closed).
2. Keep Prompt Guard in front of chat and every MCP path.
3. Business MCP: keep the sample; add Entra apps for Graph and real D365/Dataverse when ready.
4. Engineering MCP: GitHub token or App; Azure DevOps PAT or Entra app later.
5. Optional data MCP: Postgres financial facts shared with Power BI.
6. Wire the controller to each MCP base URL; accumulate JSON results in loop state; keep conversation memory in Postgres so follow-ups work (Day 15).
7. Trace every hop in Langfuse; leave Grafana as ops.
8. Lock network and secrets (private network only; tokens out of prompts when possible).
9. Prove with a multi-slot sample chat, then swap sample backends for real credentials.
10. Point Power BI Desktop at the same Postgres/SQL warehouse (gateway only if required).

## Diagram

- Script: `diagrams/si_control_layer_real_world.py`
- Poster: `diagrams/si-control-layer-real-world.png` (and `.svg`)

Related lab notes: `docs/sovereign-super-intelligence.md`, `docs/business-engineering-mcp-bridge.md`.
