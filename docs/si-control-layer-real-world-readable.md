# Control layer — readable map (text)

Companion to `diagrams/si-control-layer-real-world.png`.
Observability (Langfuse · Grafana) stays in the design as a quiet lane — call it out only when changing an observability endpoint. Copilot UIs are one banner only.

Boxes top → bottom:

## 1. Title
**Sovereign Super Intelligence — control layer**  
One agent loop · MCP to systems of record · Power BI on the same data

## 2. Top row (left → right)

| Box | Role | Status |
| --- | --- | --- |
| **People** | Terminal only (no phone) → private network | private |
| **Open WebUI** | Human chat only | live |
| **Control layer** | The only agent loop (choose tool → read JSON → call model; budget; fail closed) | live (Day 10) |
| **Model** | Ollama · local slot | live |
| **Reporting** | Power BI Desktop + Postgres warehouse — not the agent loop | reporting |

**Private front door:** private network — VPN in the lab · Private Link / VPN at work.  
The lab VPN is the home path only. At work use Private Link or VPN. Open WebUI and the control layer stay off the public internet either way.

## 3. Prompt Guard (full band)
In front of chat and every MCP call · fail closed · **live**

## 4. Four MCP slots (left → right)

| Slot | Points at | Status |
| --- | --- | --- |
| **Microsoft 365 MCP** (productivity) | Microsoft Graph: mail, calendar, OneDrive (read-only, lab: `m365_*`) | live (Day 14) |
| **ERP MCP** | D365 / Dataverse (lab: `fo_*` sample) | sample live |
| **Engineering MCP** | GitHub · Azure DevOps (lab: sample issues/PRs) | live sample (Day 10) |
| **Data MCP** | Postgres facts | design |

## 5. Systems of record (under the slots)

| Under | System | Credential |
| --- | --- | --- |
| Productivity | Microsoft Graph | Entra app (delegated, read-only) |
| ERP | D365 / Dataverse | Entra app |
| Engineering | GitHub · ADO | token / App / PAT |
| Data | Postgres facts | DB read role |

## 6. Cross-share
MCPs do not peer. The control layer accumulates tool results in one loop, and from Day 15 it remembers each conversation in Postgres, so later questions can build on earlier answers from any slot.

## 7. Observability (quiet lane)
**Langfuse** — traces each hop (guard, model, MCP tool). **Grafana** — operations view only. Not the agent loop.

## 8. Copilot banner (one line)
**Copilot UIs not used** — M365 Copilot · GitHub Copilot · Copilot Studio → replaced by Control layer + Open WebUI.

## 9. One request (footer steps)
1. Person opens Open WebUI over a private network — VPN in the lab · Private Link / VPN at work  
2. Prompt Guard checks the message  
3. Control layer runs the agent loop  
4. Guard → chosen MCP → JSON back  
5. Result saved · model called again  
6. Other MCP slots as needed · then answer  

**Power BI path (separate):** Postgres warehouse → Power BI Desktop → charts  

**Credentials:** Entra apps / tokens in cluster secrets · no Copilot seats  

**Lab today:** Open WebUI, Prompt Guard, Microsoft 365 MCP (`m365_*`, Day 14), ERP MCP sample (`fo_*`), Engineering MCP sample, Control layer, Ollama, Langfuse, and Grafana are live in `si-lab`. Data MCP (Postgres facts) is still design. Andreas two-hop demo: `POST /demo` on `control-layer` (see `docs/day-10-control-layer-bridge-steps.md`).
