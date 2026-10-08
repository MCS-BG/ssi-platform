# Helm chart: `ssi`

Packages the Sovereign Super Intelligence (SSI) control plane for Kubernetes:

| Workload | Role |
| --- | --- |
| `ssi-gateway` | Private front door (`/healthz`, `/control/*`, `/mcp/business`, `/mcp/engineering`) |
| `control-layer` | Only agent loop; Prompt Guard fail-closed; budgets. Day 15: conversation memory in Postgres (`memory.*` values; default the pgvector database with the `pgvector-auth` Secret, or a `DATABASE_URL` Secret for managed Postgres; see [docs/day-15-conversation-memory.md](../../docs/day-15-conversation-memory.md)). Day 16: the model chooses the tools (`controlLayer.planner`, `engineeringDefaultRepo`); `controlLayer.modelBaseUrl` switches to an OpenAI-compatible backend, key from `openaiApiKeySecretName` ([docs/day-16-real-cross-system-answers.md](../../docs/day-16-real-cross-system-answers.md)). |
| `mcp-server` | Business MCP slot (data-source agnostic; D365 is one example backend) |
| `engineering-mcp` | Engineering MCP slot |
| `m365-mcp` | Productivity MCP slot: Microsoft 365 (mail, calendar, OneDrive) through Graph, read-only, delegated sign-in. Needs the Secret `m365-mcp-auth` (see [docs/day-14-m365-mcp.md](../../docs/day-14-m365-mcp.md)); without it the tools fail closed. `m365Mcp.enabled: false` leaves it out. |

Prompt Guard is **not** redeployed by this chart — leave the existing Deployment. MCP slots do not peer; they share state only through the control layer.

## Create the gateway Secret (do not commit tokens)

```bash
kubectl -n si-lab create secret generic ssi-gateway-auth --from-literal=token="$(openssl rand -hex 32)"
```

## Install

```bash
helm upgrade --install ssi ./charts/ssi -n si-lab --create-namespace
```

For AKS Internal LB (Private Link path):

```bash
helm upgrade --install ssi ./charts/ssi -n si-lab -f charts/ssi/values.yaml -f charts/ssi/values-aks-internal-lb.yaml
```

Thin-wrapper note: on k3s the lab often mounts source via ConfigMaps (`k8s/day-10-*.yaml`, `k8s/day-11-ssi-gateway.yaml`). This chart prefers built images for AKS; pin `images.*` to your ACR tags.
