# SSI — Sovereign Super Intelligence

**SSI (Sovereign Super Intelligence)** is an agent platform that a business runs inside its own environment and fully owns: the model, the data, the tools, and the single agent loop that is allowed to call them. It connects an LLM to systems of record (Microsoft 365, ERP, engineering) through MCP servers, with a prompt-injection guard in front of every step that fails closed.

This repository is the working build of that platform. It was built day by day as an **independent lab pilot** on a two-node Kubernetes (k3s) cluster with a small local GPU, and packaged so the same stack can be deployed to AKS, EKS or GKE from code.

> **Honest status.** SSI is a lab pilot. It has no customers and no production use yet. The lab runs real Microsoft 365 data (read-only, one account), real GitHub data (read-only) and sample ERP data. The cloud environments (AKS, EKS, GKE) are written and validated (`tofu validate`, `bicep build`, `helm lint`) but **have not been deployed**.

## Architecture

![SSI control layer: one agent loop, Prompt Guard in front, Microsoft 365, ERP and engineering MCP slots behind it](diagrams/si-control-layer-real-world.png)

- **One control layer owns every tool call.** It plans which MCP tools to call, calls them, collects the JSON results and asks the model for the final answer. MCP servers never call each other; anything shared goes through the control layer.
- **Prompt Guard sits in front and fails closed.** Meta Prompt Guard 2 checks the user message and every tool result before it reaches the model. If the guard is down or the score is high, the request stops. In the lab an injection attempt scores 0.998 malicious in about 58 ms on CPU (see [Day 7](docs/day-07-observability.md)).
- **MCP slots, one per system of record.** Microsoft 365 productivity (Graph: mail, calendar, OneDrive; delegated, read-only), a business/ERP slot (Dynamics 365 Finance & Operations OData shape, sample data today) and an engineering slot (GitHub; read-only).
- **Conversation memory** lives in Postgres and belongs to the control layer only, so a follow-up question can build on earlier answers from any slot.
- **Local model by default.** Ollama serves a small model on the lab GPU. An OpenAI-compatible backend (for example vLLM on a bigger GPU) is built in and off by default.
- **Private by design.** Nothing is exposed to the public internet. A small gateway gives IDE clients one private base URL (`/control`, `/mcp/*`) with a bearer token at the edge; in an enterprise this becomes Private Link, VPN and Entra ID / OIDC.
- **Kubernetes-native guardrails.** A NetworkPolicy for each workload (the engineering slot is default-deny for egress), Pod Security baseline, images built in CI and pinned by commit SHA or digest, secrets created at deploy time and never stored in git.

A text version of the diagram is in [docs/si-control-layer-real-world-readable.md](docs/si-control-layer-real-world-readable.md).

## What is live, built, designed

| Component | Status |
| --- | --- |
| Control layer (agent loop, budgets, fail-closed guard calls) | **Live in the lab** |
| Prompt Guard 2 (CPU) on the chat path and in front of every MCP call | **Live in the lab** |
| Microsoft 365 MCP (Graph mail, calendar, OneDrive; read-only, device-code sign-in) | **Live in the lab** (one personal account) |
| Business / ERP MCP (D365 F&O OData shape) | **Live in the lab on sample data**; real D365 waits on an environment |
| Engineering MCP | **Live in the lab on real GitHub data** (read-only token, [Day 16](docs/day-16-real-cross-system-answers.md)) |
| Conversation memory in Postgres | **Live in the lab** |
| Model chooses the tools (validated plan, keyword fallback) | **Live in the lab** ([Day 16](docs/day-16-real-cross-system-answers.md)) |
| RAG on pgvector, Open WebUI chat, local model on GPU | **Live in the lab** |
| Private gateway + VS Code / Cursor connector extension | **Live in the lab** |
| Observability lane (traces, metrics, logs) | **Live in the lab** |
| Data MCP (Postgres facts) | Design only |
| AKS / EKS / GKE environments (OpenTofu), AKS (Bicep), Helm chart | **Validated, not deployed** |

## Repository layout

| Path | Contents |
| --- | --- |
| `apps/` | Source and Dockerfile for every service: `control-layer`, `prompt-guard`, `m365-mcp`, `mcp-server` (business slot), `engineering-mcp`, `ssi-gateway`, `rag-worker`, plus the `ssi-vscode-connector` IDE extension. |
| `charts/ssi/` | Helm chart for the SSI control plane on any Kubernetes cluster (gateway, control layer, MCP slots). |
| `infra/ansible/` | Builds the lab nodes: OS baseline, NVIDIA driver and container toolkit, k3s server and agent. |
| `infra/terraform/` | OpenTofu: one `apps` module for the whole stack, and environments for the lab (`lab-k3s`), `aks`, `eks` and `gke`. |
| `infra/bicep/` | Azure-native alternative for the AKS cluster. |
| `k8s/` | Every Kubernetes manifest and Helm values file, named after the build day that introduced it. |
| `.github/workflows/` | One image build per service, run as a CI build check with no push. The lab's published images on GHCR are built from its private repo and pinned by commit SHA. |
| `docs/` | One write-up per build day, plus a technical study guide. |
| `diagrams/` | Diagram sources (Python) and rendered images; earlier stages in `diagrams/history/`. |
| `ide/` | MCP client config examples (placeholders only). |
| `rag/`, `mcp/`, `prompt-guard/` | Early versions kept as history; `apps/` is the current source. |

## How to deploy

Nothing in this repo applies anything on its own. Every plan is read before it is applied, and secrets are created with `openssl rand` or read straight into Kubernetes Secrets.

**1. Lab cluster (two nodes, one GPU).**
Set the node addresses in `infra/ansible/inventory.ini` (copy from `inventory.example.ini`) and `host_vars/`, then:

```bash
cd infra/ansible && ansible-galaxy collection install -r requirements.yml
ansible-playbook -i inventory.ini playbooks/site.yml
```

**2. The SSI stack on any Kubernetes cluster (OpenTofu).**

```bash
cd infra/terraform/envs/lab-k3s        # or aks / eks / gke
cp terraform.tfvars.example terraform.tfvars
tofu init && tofu plan                 # read the plan, then tofu apply
```

**3. Control plane only (Helm).**

```bash
kubectl create namespace si-lab
kubectl -n si-lab create secret generic ssi-gateway-auth --from-literal=token="$(openssl rand -hex 32)"
helm upgrade --install ssi ./charts/ssi -n si-lab
```

The full runbooks are [Day 12 (AKS)](docs/day-12-ssi-on-aks.md) and [Day 13 (Ansible + OpenTofu, any cloud)](docs/day-13-iac-full-stack.md). The Microsoft 365 slot needs a one-time sign-in ([Day 14](docs/day-14-m365-mcp.md)).

## Checks

```bash
python3 apps/engineering-mcp/tests/test_server.py     # 49 offline checks
helm lint charts/ssi
tofu fmt -check -recursive infra/terraform
(cd infra/terraform/envs/aks && tofu init -backend=false && tofu validate)
bicep build infra/bicep/main.bicep --stdout >/dev/null
(cd apps/ssi-vscode-connector && npm ci && npx tsc -p . --noEmit)
```

## Build log

| Day | Topic | Write-up |
| --- | --- | --- |
| 1 | Host hardening | [day-01](docs/day-01-host-hardening.md) |
| 2 | Secure k3s with the GPU | [day-02](docs/day-02-secure-k3s.md) |
| 3 | Local model serving on the GPU | [day-03](docs/day-03-model-serving.md) |
| 4 | RAG with pgvector | [day-04](docs/day-04-rag.md) |
| 5 | Chat UI (5b: more models) | [day-05](docs/day-05-open-webui.md), [models](models/add-models-steps.md) |
| 6 | MCP server: notes search and a mock D365 F&O OData service | [day-06](docs/day-06-mcp-server.md), [steps](mcp/day-06-steps.md) |
| 6b | Second node for monitoring | [day-06b](docs/day-06b-second-node.md), [join steps](docs/day-06b-obs-node-join-steps.md) |
| 7 | Observability and Prompt Guard | [day-07](docs/day-07-observability.md), [steps](docs/day-07-observability-steps.md) |
| 8a | Repo layout, CI image builds, GHCR | [day-08a](docs/day-08a-steps.md) |
| 8b | Prompt Guard in the MCP server and the chat UI, private access | [day-08b](docs/day-08b-steps.md) |
| 9 | How models learn (teaching notes) | [day-09](docs/day-09-how-models-learn.md) |
| 10 | Control layer, engineering MCP, IDE connection | [day-10](docs/day-10-control-layer-bridge-steps.md), [IDE](docs/day-10-vscode-mcp.md) |
| 11 | Private SSI gateway for `/control` and `/mcp` | [day-11](docs/day-11-ssi-gateway.md) |
| 12 | SSI on AKS (Bicep or OpenTofu, then Helm) | [day-12](docs/day-12-ssi-on-aks.md) |
| 13 | Rebuild everything from code: Ansible + OpenTofu, any cloud | [day-13](docs/day-13-iac-full-stack.md) |
| 14 | Microsoft 365 productivity MCP | [day-14](docs/day-14-m365-mcp.md) |
| 15 | Conversation memory in the control layer | [day-15](docs/day-15-conversation-memory.md) |
| 16 | Real cross-system answers: real GitHub data, the model chooses the tools, optional bigger model | [day-16](docs/day-16-real-cross-system-answers.md) |

Earlier architecture stages are kept in [`diagrams/history/`](diagrams/history/).

The build-day write-ups describe the lab as it was built. Addresses, host names and device details in them are placeholders (`192.0.2.x`, `gpu-node`, `obs-node`, `<tailnet>`).

## License

MIT. See [LICENSE](LICENSE).
