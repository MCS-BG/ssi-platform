# Day 10: Wire SI MCP into Cursor / VS Code (lab debug)

**Developer path:** install the **Sovereign Super Intelligence (SSI)** connector and point at a remote private-network base URL — see [`docs/ssi-vscode-connector.md`](ssi-vscode-connector.md) and `apps/ssi-vscode-connector/`. Remote MCP placeholders: `ide/ssi-connector.mcp.json.example`.

**This document** is the **lab debug** path only: kubectl port-forward to ClusterIP Services when no ingress/gateway exists yet. Do not treat port-forward as the product install story for developers.

Goal (debug): call the live lab MCP slots from the IDE over localhost. `si-business` is `mcp-server` (`fo_*`, notes). `si-engineering` is `engineering-mcp` (sample repos, PRs, issues). No cluster changes. No deploy. No phone.

How to read these steps:

- Every code block has a label above it: **Terminal**.
- Each block holds one command. No `#` comments inside fences. Quotes are zsh-safe.
- `kubectl` needs `KUBECONFIG=~/.kube/si-lab.yaml` and the private path to the API.

Private network: at home use Tailscale or the SSH tunnel to the lab host. At work, Private Link / VPN replaces Tailscale. After you are on the private net, the same localhost port-forwards work.

## Before you start

Confirm the deployments exist (Day 10 bridge already applied).

Terminal

```bash
export KUBECONFIG=~/.kube/si-lab.yaml
```

Terminal

```bash
kubectl -n si-lab get deploy,svc mcp-server engineering-mcp
```

Expected: both Deployments `1/1`, both Services ClusterIP on port `8000`.

## 1. Open the private path to the API (if needed)

At home, if you are not already on Tailscale to the lab host, open the SSH tunnel:

Terminal

```bash
ssh -fN -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 6443:127.0.0.1:6443 <ssh-user>@gpu-node
```

At work: join the enterprise private network (Private Link / VPN). Skip Tailscale. Keep using the same kubeconfig once the API is reachable.

## 2. Port-forward both MCP services

Option A — helper script (keeps both forwards in one terminal):

Terminal

```bash
~/ssi-platform/scripts/port-forward-si-mcp.sh
```

Option B — two manual forwards (separate Terminal tabs):

Terminal

```bash
kubectl -n si-lab port-forward svc/mcp-server 18001:8000
```

Terminal

```bash
kubectl -n si-lab port-forward svc/engineering-mcp 18002:8000
```

Leave those running. Local URLs:

| IDE server name | Local URL | Cluster Service |
| --- | --- | --- |
| `si-business` | `http://127.0.0.1:18001/mcp` | `mcp-server` |
| `si-engineering` | `http://127.0.0.1:18002/mcp` | `engineering-mcp` |

Use `127.0.0.1` (not a custom hostname). `mcp-server` rejects unknown `Host` headers with `421`.

## 3. Install the MCP config in Cursor (primary)

Primary schema is Cursor `mcpServers` with `url` (Streamable HTTP / SSE).

Workspace (recommended for this repo):

Terminal

```bash
mkdir -p ~/ssi-platform/.cursor
```

Terminal

```bash
cp ~/ssi-platform/ide/mcp.json.example ~/ssi-platform/.cursor/mcp.json
```

Or global (all projects):

Terminal

```bash
mkdir -p ~/.cursor
```

Terminal

```bash
cp ~/ssi-platform/ide/mcp.json.example ~/.cursor/mcp.json
```

If you already have a global `~/.cursor/mcp.json`, merge the `si-business` and `si-engineering` entries by hand instead of overwriting.

Example body (same as `ide/mcp.json.example`):

```json
{
  "mcpServers": {
    "si-business": {
      "url": "http://127.0.0.1:18001/mcp"
    },
    "si-engineering": {
      "url": "http://127.0.0.1:18002/mcp"
    }
  }
}
```

Reload Cursor MCP (Command Palette → **MCP: List Servers**, or restart the agent / Cursor). Enable `si-business` and `si-engineering` if they show as disabled.

## 4. VS Code / GitHub Copilot MCP (different schema)

VS Code workspace file is `.vscode/mcp.json` and uses a top-level `servers` object with `"type": "http"`. Portable Copilot format can also use `.mcp.json` or `~/.copilot/mcp-config.json` with `mcpServers` (same shape as Cursor).

Workspace VS Code format:

Terminal

```bash
mkdir -p ~/ssi-platform/.vscode
```

Terminal

```bash
cp ~/ssi-platform/ide/mcp.vscode.json.example ~/ssi-platform/.vscode/mcp.json
```

Example body (same as `ide/mcp.vscode.json.example`):

```json
{
  "servers": {
    "si-business": {
      "type": "http",
      "url": "http://127.0.0.1:18001/mcp"
    },
    "si-engineering": {
      "type": "http",
      "url": "http://127.0.0.1:18002/mcp"
    }
  }
}
```

Then Command Palette → **MCP: List Servers** → start / trust the two servers. Restart Copilot Chat if tools do not appear.

## 5. Smoke from the terminal (optional)

With port-forwards up:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18001/mcp -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Terminal

```bash
curl -s -X POST http://127.0.0.1:18002/mcp -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

Expected: business tools include `fo_query` / `fo_list_entities` (and notes search). Engineering tools include `list_prs`, `get_pr`, `list_issues`, `list_repos`.

## 6. Test in the IDE agent

In Cursor Agent (or VS Code Copilot Agent), ask:

1. List tools on `si-business` and `si-engineering`.
2. What is open PR 42 on `invoice-service`, and which customer account does it reference?
3. Look up customer `DEMO-C0001` with the business tools.

Expected: PR 42 Fix tax rounding, `customer_account` `DEMO-C0001`, and a business hop that returns Lakeside Bike Shop (or the same demo customer row from `fo_query`).

Stop the port-forwards when finished (Ctrl-C in the forward terminals, or stop the helper script).

## Notes

- Namespace is always `si-lab`.
- No Funnel. No PVC wipe. No cluster apply in this doc.
- Control layer (`control-layer` /demo) is a separate curl proof; this doc wires the IDE straight to the MCP Services.
- At home the private front door is Tailscale or SSH. At work it is Private Link / VPN. Localhost forwards are the same after you are on that net.
- **Port-forward = lab debug only.** The developer connector UX is SSI: Connect against `https://<private-host>/mcp/...` — [`docs/ssi-vscode-connector.md`](ssi-vscode-connector.md).

## Source map

| Path | Purpose |
| --- | --- |
| `apps/ssi-vscode-connector/` | **Developer connector** (SSI: Connect, remote endpoint) |
| `docs/ssi-vscode-connector.md` | Install / connect walkthrough |
| `ide/ssi-connector.mcp.json.example` | Remote MCP URL placeholders (product path) |
| `ide/mcp.json.example` | Cursor localhost debug (`mcpServers` + `url`) |
| `ide/mcp.vscode.json.example` | VS Code localhost debug (`servers` + `type: http`) |
| `scripts/port-forward-si-mcp.sh` | Lab debug: forwards both Services to 18001 / 18002 |
| `docs/day-10-control-layer-bridge-steps.md` | Cluster deploy + `/demo` proof |
