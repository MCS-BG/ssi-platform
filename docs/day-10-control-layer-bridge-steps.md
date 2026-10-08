# Day 10: Control layer + engineering MCP bridge

Goal: deploy the minimum needed to validate Andreas’s scenario. One control-layer loop calls the live business MCP (`mcp-server` / `fo_*`) and a new engineering MCP (sample repos, issues, PRs), then answers with `llama3.2:3b`. No Copilot seats. No Funnel. No PVC wipe.

How to read these steps:

- Every code block has a label above it: **Terminal**.
- Each block holds one command. No `#` comments inside fences. Quotes are zsh-safe.
- `kubectl` needs `KUBECONFIG=~/.kube/si-lab.yaml` and the SSH tunnel to the API (Day 2 / Day 8).

## What is new

| Object | Role |
| --- | --- |
| `engineering-mcp` | Sample engineering tools: `list_repos`, `list_prs`, `get_pr`, `list_issues`, `get_issue`. JSON-RPC at `/mcp`. |
| `control-layer` | Guarded agent loop. Calls Prompt Guard, business MCP, engineering MCP, Ollama. Budgets: 4 tool calls, 512 tokens. |
| `POST /demo` | Scripted two-hop proof for Andreas. |
| `POST /ask` | Same loop with a planner for business+engineering questions. |

Primary demo is `curl` to `control-layer`. Open WebUI is unchanged (no click required for this proof).

## Before you start

Terminal

```bash
ssh -fN -o ServerAliveInterval=30 -o ExitOnForwardFailure=yes -L 6443:127.0.0.1:6443 <ssh-user>@gpu-node
```

Terminal

```bash
export KUBECONFIG=~/.kube/si-lab.yaml
```

Terminal

```bash
kubectl -n si-lab get deploy,svc
```

Expected: `mcp-server`, `prompt-guard`, `ollama`, `open-webui`, `rag-worker`, `fo-mock` Ready. `control-layer` and `engineering-mcp` are missing until the next steps.

## 1. Apply engineering MCP

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-10-engineering-mcp.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deploy/engineering-mcp --timeout=120s
```

Terminal

```bash
kubectl -n si-lab get deploy,svc engineering-mcp
```

Expected: Deployment `1/1`, Service ClusterIP on port `8000`.

DNS inside the cluster: `http://engineering-mcp.si-lab.svc.cluster.local:8000/mcp`

## 2. Apply control layer

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-10-control-layer.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deploy/control-layer --timeout=120s
```

Terminal

```bash
kubectl -n si-lab get deploy,svc control-layer
```

Expected: Deployment `1/1` on node `gpu-node`, Service ClusterIP on port `8080`.

DNS inside the cluster: `http://control-layer.si-lab.svc.cluster.local:8080`

## 3. Smoke the engineering tools

Terminal

```bash
kubectl -n si-lab port-forward svc/engineering-mcp 18010:8000
```

In a second Terminal tab:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18010/mcp -H 'Content-Type: application/json' -H 'Accept: application/json' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_prs","arguments":{"repo":"invoice-service","state":"open"}}}'
```

Expected: PR `42` Fix tax rounding with `customer_account` `DEMO-C0001`. Stop the port-forward when done.

## 4. Prove the two-hop demo

Terminal

```bash
kubectl -n si-lab port-forward svc/control-layer 18080:8080
```

Second Terminal tab:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/demo -H 'Content-Type: application/json' -d '{}'
```

Expected JSON fields:

- `ok`: true
- `slots_used`: includes `business` and `engineering`
- `tool_calls`: first `engineering.list_prs` on `invoice-service`, then `business.fo_query` for `DEMO-C0001`
- `answer`: short text from `llama3.2:3b` that mentions the PR and the customer

Same question through `/ask`:

Terminal

```bash
curl -s -X POST http://127.0.0.1:18080/ask -H 'Content-Type: application/json' -d '{"question":"What open PRs touch the invoice service, and what customer account owns that invoice line in the business tools?"}'
```

Stop the port-forward when done.

## 5. Confirm Ready state

Terminal

```bash
kubectl -n si-lab get deploy control-layer engineering-mcp mcp-server prompt-guard ollama
```

Expected: all `1/1`.

## Notes

- Images for Day 10 are `python:3.12-slim` plus ConfigMaps (`engineering-mcp-code`, `control-layer-code`). Dockerfiles under `apps/engineering-mcp` and `apps/control-layer` are ready for a later GHCR pin; the lab host has no Docker daemon today.
- Prompt Guard stays fail closed. If `/classify` is down, `/demo` and `/ask` return an error and do not call MCP.
- Business MCP already classifies tool arguments on its own path. The control layer also classifies before each tool hop.
- Sample engineering data links PR/issue rows to `DEMO-C0001` so the business hop has a concrete account.
- Open WebUI does not need a new click for this proof. Optional later: add a tool or pipe that posts to `http://control-layer.si-lab.svc.cluster.local:8080/ask`.
- Do not Funnel. Do not wipe PVCs. Do not require Copilot.

## Source map

| Path | Purpose |
| --- | --- |
| `apps/engineering-mcp/server.py` | Sample engineering MCP |
| `apps/control-layer/server.py` | Control layer loop |
| `k8s/day-10-engineering-mcp.yaml` | ConfigMap, Deployment, Service, NetworkPolicy |
| `k8s/day-10-control-layer.yaml` | ConfigMap, Deployment, Service, NetworkPolicy |
| `docs/business-engineering-mcp-bridge.md` | Design note this day implements |
| `docs/agent-lab.md` | Control-layer shape |


## Troubleshooting

### Short Service DNS for business MCP

`mcp-server` rejects FQDN `Host` headers (`421 Invalid Host header`). The control layer therefore calls `http://mcp-server:8000/mcp` and `http://engineering-mcp:8000/mcp` (short names). Pods in `si-lab` resolve those via the search domain `si-lab.svc.cluster.local`.

### CoreDNS and a moved lab-host IP

If new Services do not resolve, check `kubectl get endpoints kubernetes`. The address must be the lab host's current LAN IP. If DHCP changed it, patch both Endpoints and EndpointSlice, then restart CoreDNS:

Terminal

```bash
kubectl get endpoints kubernetes
```

Terminal

```bash
kubectl -n kube-system rollout restart deploy/coredns
```
