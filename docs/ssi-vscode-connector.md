# SSI Connector for VS Code and Cursor

How an enterprise developer installs the **SSI Connector** and points the IDE at the company's private **SSI (Sovereign Super Intelligence)** endpoint.

**Extension:** SSI Connector (`ssi-lab.ssi-connector`, v0.1.0)  
**Source:** `apps/ssi-vscode-connector/`  
**Distribution:** VSIX (sideload). Not on the VS Code Marketplace yet.

## Mental model

```
Developer (VS Code / Cursor)
        │  SSI Connector: ssi.endpoint + token in Secret Storage
        ▼
Company private network (Private Link / VPN / internal network)
        │
        ▼
https://ssi.corp.example
  ├─ /control/healthz      → SSI control layer health (Connect check)
  ├─ /control/ask, /demo   → SSI control layer (the only agent loop)
  ├─ /mcp/business         → business MCP gateway
  └─ /mcp/engineering      → engineering MCP gateway
```

- The **control layer is the only agent loop**. It is the only part that combines business and engineering results.
- The MCP slots (business, engineering) are separate and **never talk to each other**.
- The extension connects the IDE to the control layer and the two MCP gateway paths. It doesn't run an agent loop of its own.
- SSI stays on the private network. It has no public endpoint.

## Prerequisites

1. You can reach your company's SSI hostname over Private Link, VPN, or the internal network.
2. The SSI gateway exposes:
   - the control layer under `ssi.controlPath` (default `/control`), so the health check is `GET /control/healthz`
   - business MCP at `ssi.businessMcpPath` (default `/mcp/business`)
   - engineering MCP at `ssi.engineeringMcpPath` (default `/mcp/engineering`)
3. A bearer token from your SSI administrator, if your gateway requires one.

## Install

From a terminal:

```bash
code --install-extension ssi-connector-0.1.0.vsix
```

Or in VS Code / Cursor: **Extensions** view → **…** menu → **Install from VSIX…** → pick `ssi-connector-0.1.0.vsix`. Reload the window if prompted.

## Connect

1. **Settings** → search **SSI** → set **`ssi.endpoint`**, e.g. `https://ssi.corp.example` (no trailing slash).
2. Command Palette → **SSI: Set Token** → paste your token. It goes into VS Code Secret Storage (your OS keychain), not settings.
3. Command Palette → **SSI: Connect**. The extension calls `GET {endpoint}{controlPath}/healthz`.
4. The status bar shows **SSI: Connected**. If it shows **SSI: Error**, the message says why (DNS / not on the private network, timeout, 401/403 token, 404 wrong `controlPath`, 5xx control layer down, untrusted TLS certificate).
5. Command Palette → **SSI: Copy MCP Config** → choose **VS Code** or **Cursor** → paste into `mcp.json` (below).

## Commands

| Command | Action |
| --- | --- |
| **SSI: Connect** | Asks for the endpoint if it is empty, checks control layer health, updates the status bar |
| **SSI: Disconnect** | Marks this window disconnected (token and mcp.json are unchanged) |
| **SSI: Set Token** | Password input box, saves to Secret Storage |
| **SSI: Clear Token** | Deletes the token from Secret Storage |
| **SSI: Show Connection Status** | Summary of endpoint, token present, health URL, MCP URLs, last result |
| **SSI: Copy MCP Config** | mcp.json snippet for VS Code or Cursor |

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `ssi.endpoint` | (empty) | Company SSI base URL, e.g. `https://ssi.corp.example` |
| `ssi.controlPath` | `/control` | Control layer prefix on the gateway. Health check is `{controlPath}/healthz` |
| `ssi.businessMcpPath` | `/mcp/business` | Business MCP gateway path |
| `ssi.engineeringMcpPath` | `/mcp/engineering` | Engineering MCP gateway path |
| `ssi.showStatusBar` | `true` | Show the status bar item |

The token is not a setting. A legacy `ssi.token` value from the scaffold build is moved into Secret Storage once and removed from settings.

## Wire MCP into the IDE agent

**SSI: Copy MCP Config** uses an `Authorization: Bearer <SSI_TOKEN>` placeholder. Your real token is only copied if you pick **Include my token** and confirm. Don't commit a real token in `mcp.json`.

### VS Code (`.vscode/mcp.json`)

```json
{
  "servers": {
    "ssi-business": {
      "type": "http",
      "url": "https://ssi.corp.example/mcp/business",
      "headers": { "Authorization": "Bearer <SSI_TOKEN>" }
    },
    "ssi-engineering": {
      "type": "http",
      "url": "https://ssi.corp.example/mcp/engineering",
      "headers": { "Authorization": "Bearer <SSI_TOKEN>" }
    }
  }
}
```

Command Palette → **MCP: List Servers** → start and trust both servers.

### Cursor (`.cursor/mcp.json` or `~/.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "ssi-business": {
      "url": "https://ssi.corp.example/mcp/business",
      "headers": { "Authorization": "Bearer <SSI_TOKEN>" }
    },
    "ssi-engineering": {
      "url": "https://ssi.corp.example/mcp/engineering",
      "headers": { "Authorization": "Bearer <SSI_TOKEN>" }
    }
  }
}
```

Cursor Settings → **MCP** → enable `ssi-business` and `ssi-engineering`. See also `ide/ssi-connector.mcp.json.example`.

## How the extension talks to SSI

| Call | Purpose |
| --- | --- |
| `GET {endpoint}{controlPath}/healthz` | Connect check. The control layer answers `200 ok` |
| MCP URLs | Copied for the IDE. Tool calls go IDE → gateway → that MCP slot |
| Later | Device-code sign-in; an "Ask SSI" command that POSTs to `{controlPath}/ask` |

Combining a business fact with an engineering fact in one loop is the **control layer's** job (`/ask`, `/demo`). When the IDE calls the two MCP gateways directly, they are two separate tool servers. They don't talk to each other.

## Build the VSIX from source

```bash
cd apps/ssi-vscode-connector
```

```bash
npm install
```

```bash
npm run compile
```

```bash
npm run package
```

The output is `ssi-connector-0.1.0.vsix`, which is git-ignored and never committed.

## Source map

| Path | Purpose |
| --- | --- |
| `apps/ssi-vscode-connector/` | Extension source (`package.json`, `src/extension.ts`, `media/icon.png`, README, LICENSE) |
| `apps/control-layer/server.py` | Control layer: `GET /healthz`, `POST /ask`, `POST /demo` |
| `ide/ssi-connector.mcp.json.example` | Remote MCP placeholders for Cursor |

---

### Home lab endpoint

In the home lab, set **`ssi.endpoint`** to `http://192.0.2.93:30808`. That is the Day 11 gateway (`docs/day-11-ssi-gateway.md`) on a NodePort on the lab host, reachable from any machine on the home LAN with nothing running on the laptop. Reserve 192.0.2.93 for the lab host in the router (DHCP reservation) so the endpoint doesn't move.

The lab link is plain HTTP, so the token crosses the home network unencrypted. That is fine for the lab only.

Fallback only (for example away from the home LAN): run `kubectl -n si-lab port-forward svc/ssi-gateway 18080:8080` and use `http://127.0.0.1:18080` while it runs.

### Real-world endpoint

In a company, `ssi.endpoint` is the same gateway behind an internal load balancer with a private DNS name and TLS (for example `https://ssi.company.internal`), reached over the company VPN or Private Link. It is never the Kubernetes API server. The API server is the admin endpoint for `kubectl` and deploys; routing app traffic through it would give every developer cluster credentials and push all traffic through the control plane.
