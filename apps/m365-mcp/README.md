# m365-mcp

SSI productivity MCP slot: read-only Microsoft 365 (mail, calendar, OneDrive) through Microsoft Graph, signed in as one personal Microsoft account with delegated OAuth (MSAL, device code).

| File | Purpose |
| --- | --- |
| `server.py` | MCP server (`MCPServer`, Streamable HTTP on `:8000` at `/mcp`, `/healthz`, `/authz`). Tools: `m365_whoami`, `m365_list_mail`, `m365_get_mail`, `m365_list_events`, `m365_list_onedrive`, `m365_search_onedrive`. |
| `login.py` | One-time device-code sign-in. Writes the MSAL token cache outside the repo (`~/.ssi/m365-token-cache.json`, mode 0600) and prints the `kubectl` command for the Secret `m365-mcp-auth`. |
| `llmtrace.py` | Langfuse-friendly OpenTelemetry spans (copied from `apps/mcp-server`). |
| `Dockerfile` | `python:3.12.14-slim-trixie`, non-root 10001, starts through `opentelemetry-instrument`. |

Without the Secret the server still starts and stays healthy; every tool returns a "Not signed in to Microsoft 365" error. Prompt Guard checks every string argument and the mail content returned (fail closed).

Full steps (Entra app registration, sign-in, Secret, deploy, smoke test): [docs/day-14-m365-mcp.md](../../docs/day-14-m365-mcp.md).

Run locally (no sign-in needed to see the tools):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
PROMPT_GUARD_ENABLED=false .venv/bin/python server.py
```
