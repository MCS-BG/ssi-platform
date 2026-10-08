# Day 11: SSI private front door (`/control` + `/mcp`)

Goal: give the **SSI Connector** one private base URL that path-routes to the Day 10 control layer and the two MCP slots, with a lab Bearer token at the edge. Prompt Guard stays fail-closed on the existing Day 10 / Day 8b paths. No Copilot seats. No public internet exposure.

How to read these steps:

- Every code block has a label above it: **Terminal**.
- Each block holds one command. No `#` comments inside fences. Quotes are zsh-safe.
- `kubectl` needs `KUBECONFIG=~/.kube/si-lab.yaml` and the private path to the API (Day 2 / Day 8).

## Routing table

| External path (SSI Connector default) | Upstream | Notes |
| --- | --- | --- |
| `GET /healthz` | gateway itself | Probe only. No auth. |
| `GET /control/healthz` | `control-layer:8080/healthz` | Connect check. Bearer required. |
| `POST /control/ask`, `/control/demo` | `control-layer:8080/ask`, `/demo` | Prefix `/control` stripped. Bearer required. |
| `POST /mcp/business` | `mcp-server:8000/mcp` | Host rewritten to `mcp-server:8000` (allowlist). Bearer required. |
| `POST /mcp/engineering` | `engineering-mcp:8000/mcp` | Host rewritten to `engineering-mcp:8000`. Bearer required. |

Auth is a shared secret in Secret `ssi-gateway-auth` (key `token`). Enterprise replaces this with Entra / OIDC at the edge later. The gateway does **not** forward the edge Bearer token to ClusterIP backends.

## Where the hostname comes from

| Environment | How you reach `ssi-gateway` |
| --- | --- |
| Home lab | `http://192.0.2.93:30808` from any machine on the home LAN. The Service is a NodePort (30808) on the lab host, so nothing has to run on your laptop. Reserve 192.0.2.93 for the lab host in the router (DHCP reservation); if the IP moves, the endpoint breaks. Fallback only: `kubectl port-forward svc/ssi-gateway 18080:8080`. |
| Enterprise | The same gateway behind an internal load balancer with a private DNS name (for example `https://ssi.company.internal`) and TLS, reached over the company VPN or Private Link. Never the Kubernetes API server: that is the admin endpoint for `kubectl` and deploys, not an app endpoint. |

The lab link is plain HTTP, so the Bearer token crosses the home network unencrypted. That is acceptable for the lab only; the enterprise path always uses TLS.

How the lab NodePort is locked down:

- `externalTrafficPolicy: Local` keeps the caller's real IP, and the NetworkPolicy `ssi-gateway-allow` admits the home LAN (`192.0.2.0/24`) next to the in-cluster callers it already allowed. The node that answers must run the gateway pod (the lab host does).
- Every route except `/healthz` still needs the Bearer token.
- The lab host firewall (ufw) did not need a rule for this: k3s's own forwarding rules accept NodePort traffic. If a request from the LAN times out, run this on the lab host: `sudo ufw allow from 192.0.2.0/24 to any port 30808 proto tcp`.

## Before you start

Day 10 must be Ready: `control-layer`, `engineering-mcp`, `mcp-server`, `prompt-guard`.

Terminal

```bash
export KUBECONFIG=~/.kube/si-lab.yaml
```

Terminal

```bash
kubectl -n si-lab get deploy control-layer engineering-mcp mcp-server prompt-guard
```

Expected: all `1/1`.

## 1. Create the gateway token Secret

Do this once. Do not commit the token.

Terminal

```bash
kubectl -n si-lab create secret generic ssi-gateway-auth --from-literal=token="$(openssl rand -hex 32)"
```

If the Secret already exists and you need to rotate:

Terminal

```bash
kubectl -n si-lab delete secret ssi-gateway-auth
```

Then recreate it with the command above and restart the gateway Deployment after apply.

Save the token for the SSI Connector (**SSI: Set Token**). To print it later:

Terminal

```bash
kubectl -n si-lab get secret ssi-gateway-auth -o jsonpath='{.data.token}' | base64 -d; echo
```

## 2. Apply the gateway

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-11-ssi-gateway.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deploy/ssi-gateway --timeout=120s
```

Terminal

```bash
kubectl -n si-lab get deploy,svc,ingress ssi-gateway
```

Expected: Deployment `1/1`, Service `NodePort` with `8080:30808/TCP`. The Ingress `ssi-gateway` is an optional lab extra; if its operator is missing, the Ingress stays without an address and the NodePort still works.

## 3. Smoke from the LAN

From any machine on the home LAN. No port-forward needed.

Terminal

```bash
TOKEN="$(kubectl -n si-lab get secret ssi-gateway-auth -o jsonpath='{.data.token}' | base64 -d)"
```

Terminal

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://192.0.2.93:30808/healthz
```

Expected: `200`.

Terminal

```bash
curl -sS -H "Authorization: Bearer ${TOKEN}" http://192.0.2.93:30808/control/healthz
```

Expected: `ok`.

Terminal

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://192.0.2.93:30808/control/healthz
```

Expected: `401` (no Bearer).

Terminal

```bash
curl -sS -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" -d '{}' http://192.0.2.93:30808/control/demo | head -c 400; echo
```

Expected: JSON with `"ok": true`, `slots_used` including `business` and `engineering`. Prompt Guard still runs inside the control layer (fail closed).

Fallback if the LAN endpoint is unreachable (for example away from home): run `kubectl -n si-lab port-forward svc/ssi-gateway 18080:8080` in its own tab and use `http://127.0.0.1:18080` in the commands above.

## 4. Point the SSI Connector at the lab endpoint

1. Install the VSIX if needed (`docs/ssi-vscode-connector.md`).
2. Set **`ssi.endpoint`** to `http://192.0.2.93:30808` (no trailing slash).
   - Fallback only: `http://127.0.0.1:18080` while a `kubectl port-forward svc/ssi-gateway 18080:8080` is running.
3. **SSI: Set Token** → paste the Secret value.
4. **SSI: Connect** → status bar **SSI: Connected**.
5. **SSI: Copy MCP Config** → paste into Cursor / VS Code `mcp.json`.

Leave path settings at defaults: `ssi.controlPath=/control`, `ssi.businessMcpPath=/mcp/business`, `ssi.engineeringMcpPath=/mcp/engineering`.

## What this does not change

- Day 10 `control-layer` budgets, Prompt Guard fail-closed behavior, and the Andreas `/demo` path.
- Day 8b Prompt Guard inside `mcp-server` tool calls.
- Open WebUI, Grafana, Langfuse Tailscale Ingresses from Day 8b.

## Source map

| Path | Purpose |
| --- | --- |
| `apps/ssi-gateway/server.py` | Gateway source (stdlib) |
| `k8s/day-11-ssi-gateway.yaml` | ConfigMap, Deployment, NodePort Service (30808), NetworkPolicy (LAN ipBlock), optional lab Ingress |
| `infra/terraform/apps/manifests.tf` | Same objects in OpenTofu; `gateway_service_type`, `gateway_node_port`, `gateway_lan_cidr` (lab-k3s: NodePort 30808, `192.0.2.0/24`; cloud envs: ClusterIP + internal load balancer) |
| `docs/ssi-vscode-connector.md` | Developer install + Connect |
| `k8s/day-10-control-layer.yaml` | Upstream `/healthz`, `/ask`, `/demo` |
| `k8s/day-10-engineering-mcp.yaml` | Upstream engineering `/mcp` |
