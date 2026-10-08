# SSI Connector

**SSI Connector** connects VS Code and Cursor to **SSI (Sovereign Super Intelligence)**, the private AI platform your company runs on its own network.

Install the extension, point it at your company's private SSI endpoint, store your token, and connect. The IDE agent can then use the SSI business and engineering MCP gateways.

## How it fits

```
VS Code / Cursor  ──►  company private network (Private Link / VPN)  ──►  https://ssi.corp.example
                                                                            ├─ /control/...        SSI control layer (the only agent loop)
                                                                            ├─ /mcp/business       business MCP gateway
                                                                            └─ /mcp/engineering    engineering MCP gateway
```

- The **SSI control layer** runs the only agent loop. It is the only part that combines results from more than one MCP slot.
- The **business** and **engineering** MCP gateways are separate slots. They never talk to each other.
- This extension checks that the control layer is healthy and gives your IDE the two MCP gateway URLs. It does not run an agent loop of its own.
- SSI stays on your company's private network. It has no public internet endpoint.

## Quick start

1. Install the VSIX: `code --install-extension ssi-connector-0.1.0.vsix`, or open **Extensions → … → Install from VSIX…** in VS Code or Cursor.
2. Open Settings, search **SSI**, and set **`ssi.endpoint`** to your company's SSI base URL, for example `https://ssi.corp.example`.
3. Run **SSI: Set Token** from the Command Palette and paste the bearer token your SSI administrator gave you.
4. Run **SSI: Connect**. The status bar shows **SSI: Connected**, or **SSI: Error** with the reason.
5. Run **SSI: Copy MCP Config**, pick VS Code or Cursor, and paste the JSON into `mcp.json`.

## Commands

| Command | What it does |
| --- | --- |
| **SSI: Connect** | Asks for `ssi.endpoint` if it is not set, then calls `GET {endpoint}{controlPath}/healthz` and updates the status bar |
| **SSI: Disconnect** | Marks this window as disconnected. Leaves your token and mcp.json alone |
| **SSI: Set Token** | Saves your bearer token in VS Code Secret Storage (password input box) |
| **SSI: Clear Token** | Removes the token from Secret Storage |
| **SSI: Show Connection Status** | Opens a summary: endpoint, token set or not, health URL, MCP URLs, last result |
| **SSI: Copy MCP Config** | Copies an `mcp.json` snippet for VS Code (`servers`, `type: http`) or Cursor (`mcpServers`) |

Status bar: **SSI: Connected** · **SSI: Disconnected** · **SSI: Error** (click to retry).

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `ssi.endpoint` | (empty) | Your company's SSI base URL, no trailing slash. Example: `https://ssi.corp.example` |
| `ssi.controlPath` | `/control` | Where the gateway exposes the SSI control layer. Health check: `{controlPath}/healthz` |
| `ssi.businessMcpPath` | `/mcp/business` | Business MCP gateway path |
| `ssi.engineeringMcpPath` | `/mcp/engineering` | Engineering MCP gateway path |
| `ssi.showStatusBar` | `true` | Show the SSI status bar item |

The token is **not** a setting. It lives in VS Code Secret Storage (your operating system keychain). If an older build saved a token in `ssi.token`, the extension moves it into Secret Storage once and removes it from settings.

## MCP config

**SSI: Copy MCP Config** writes an `Authorization: Bearer <SSI_TOKEN>` placeholder by default. It only puts your real token on the clipboard if you choose **Include my token** and confirm. Don't commit an `mcp.json` that contains a real token.

VS Code (`.vscode/mcp.json`):

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

Cursor (`.cursor/mcp.json` or `~/.cursor/mcp.json`):

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

## Troubleshooting

| Message | Fix |
| --- | --- |
| Hostname did not resolve / timed out | Join your company's VPN or private network and check `ssi.endpoint` |
| 401 / 403 | Run **SSI: Set Token** with a valid token |
| 404 on `/healthz` | `ssi.controlPath` doesn't match your gateway. Ask your SSI administrator |
| 502 / 503 / 504 | The gateway is up but the control layer isn't responding |
| TLS certificate not trusted | Install your company's root CA on this machine |

## Build from source

```bash
npm install
npm run compile
npm run package
```

This produces `ssi-connector-0.1.0.vsix`.

## License

MIT. See [LICENSE](LICENSE).

---

### Lab debugging

In a lab cluster with no gateway, `kubectl port-forward` to the ClusterIP Services can stand in for debugging (see `docs/day-10-vscode-mcp.md` in the repo). The connector doesn't use it.
