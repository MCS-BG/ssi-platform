# Day 12: SSI on AKS (Bicep or OpenTofu, then Helm)

Goal: promote the home-lab **Sovereign Super Intelligence (SSI)** stack from k3s to **Azure Kubernetes Service** using a small infrastructure-as-code (IaC) layer (Bicep **or** OpenTofu) and a Helm chart. One teaching+deploy day — not a full AKS landing-zone marathon. The same control plane (gateway, control-layer, business MCP, engineering MCP) runs in namespace `si-lab`. Prompt Guard stays fail-closed. Enterprise reachability is **Private Link / VPN / internal DNS**. Tailscale stays home-lab outside reachability only.

How to read these steps:

- Every code block has a label above it: **Terminal**.
- Each block holds one command. No `#` comments inside fences. Quotes are zsh-safe.
- You run `az login` on the terminal (interactive). This lab does **not** apply anything to a subscription for you.
- Pin image tags to your ACR or GHCR before a real install.

## Pick your IaC

Both folders provision the same thing: resource group, AKS (system pool + optional user/GPU pool), ACR with AcrPull, Log Analytics, and a private DNS placeholder. Pick one for step 2. Every step after provisioning is the same.

| | Bicep (`infra/bicep/`, optional alternative) | OpenTofu (`infra/terraform/envs/aks`, supported from Day 13) |
| --- | --- | --- |
| Scope | Azure-native, first-party | Multi-cloud, same workflow on any provider |
| State | No state file. Azure Resource Manager is the source of truth. | State file. Keep it in customer-owned remote storage. |
| Preview | `what-if` | `plan` |
| Pick it when | The customer is all-in on Azure and wants no state to manage | The customer wants IaC that can move with the platform (AKS, EKS, GKE, home lab) |

OpenTofu (`tofu`) is the open-source fork of Terraform and the CLI this repo uses.

## Mapping: si-lab k3s → AKS

| Home lab (k3s) | AKS / Azure | Notes |
| --- | --- | --- |
| Namespace `si-lab` | Namespace `si-lab` | Same name; Helm can create it. |
| Ollama on GPU node | Azure GPU node pool **or** Azure OpenAI | Swappable model slot. Chart values: `controlLayer.ollamaUrl` / `modelBaseUrl`. |
| Day 11 `ssi-gateway` ClusterIP (+ optional Tailscale Ingress) | Internal Load Balancer + Private Link | Enterprise hostname replaces Tailscale. |
| Tailscale Ingress hostname | Private Link / internal DNS hostname | Tailscale is **not** the product story. |
| `control-layer` + `mcp-server` + `engineering-mcp` | Same Deployments via Helm `charts/ssi` | Values-driven; pin images. |
| Prompt Guard (Day 7/8) | Unchanged Deployment in `si-lab` | Fail-closed; chart does not redeploy it. |
| Quiet obs: Grafana + Langfuse | Grafana/Langfuse on AKS **or** Azure Monitor + keep Langfuse | Mention endpoints only when a step updates them; still part of the architecture. |

### Architecture (quiet obs included)

| Layer | Components |
| --- | --- |
| Edge | SSI Connector → private base URL (Private Link hostname) → `ssi-gateway` |
| Control | `control-layer` (only agent loop); Prompt Guard fail-closed |
| MCP slots | `mcp-server` (business), `engineering-mcp` (engineering) — no peer; cross-share only via shared loop state |
| Model slot | Ollama (GPU pool) or Azure OpenAI |
| Quiet observability | Grafana + Langfuse (and/or Azure Monitor + Langfuse) |

Data sources stay agnostic. D365 is one example MCP backend, not a hard dependency.

## Before you start

- Day 11 understood on k3s (gateway routes, Bearer Secret pattern, SSI Connector).
- Azure CLI on the terminal (`az`), `kubectl`, `helm`.
- For step 2, either Bicep (`az bicep`) **or** OpenTofu (`tofu`, 1.7 or later).
- A subscription you own for a **lab** deploy (optional today — reading the templates is enough for the teaching pass).

## 1. Sign in to Azure (you do this)

Terminal

```bash
az login
```

Terminal

```bash
az account show --query '{name:name,id:id,tenantId:tenantId}' -o table
```

Expected: the lab subscription you intend to use. Switch with `az account set --subscription <id>` if needed.

## 2. Provision the platform (pick one path)

This creates scaffolding only. It does **not** install the SSI Helm chart. Skip the deploy commands if this is a read-only teaching pass. You do not need a live subscription to learn the day.

### Option A: Bicep

Files: `infra/bicep/`. Parameters: `infra/bicep/main.bicepparam` (`location`, `namePrefix`, `kubernetesVersion`).

Terminal

```bash
cd ~/ssi-platform
```

Terminal

```bash
az bicep build --file infra/bicep/main.bicep
```

Expected: no errors.

Terminal

```bash
az deployment sub what-if --location eastus --template-file infra/bicep/main.bicep --parameters infra/bicep/main.bicepparam
```

Expected: a list of resources to create. Nothing is applied yet.

Terminal

```bash
az deployment sub create --location eastus --template-file infra/bicep/main.bicep --parameters infra/bicep/main.bicepparam --name ssi-day12
```

Expected: provisioning succeeds. Note the outputs `resourceGroupName`, `aksName`, `acrLoginServer`, and `privateLinkNotes`.

### Option B: OpenTofu

Files: `infra/terraform/envs/aks` (calls `infra/terraform/modules/aks-cluster`; Day 13 moved the Day 12 files there). Variables: `location`, `name_prefix`, `kubernetes_version`, `enable_gpu_pool`. Unlike Bicep, this path keeps a **state file**. For a solo lab run, local state is fine. For a customer, uncomment the `azurerm` backend in `envs/aks/versions.tf` and point it at storage they own (see `infra/terraform/README.md`). Never commit state.

`deploy_apps=false` keeps today's scope: cluster only, then Helm by hand below. Day 13 (`docs/day-13-iac-full-stack.md`) deploys the whole stack from the same folder instead.

Terminal

```bash
cd ~/ssi-platform/infra/terraform/envs/aks
```

Terminal

```bash
cp terraform.tfvars.example terraform.tfvars
```

Terminal

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
```

Terminal

```bash
tofu init
```

Terminal

```bash
tofu plan -var 'deploy_apps=false' -out=day12.tfplan
```

Terminal

```bash
tofu apply day12.tfplan
```

Terminal

```bash
tofu output
```

Expected: `plan` lists the resources to create, then `apply` creates them. Outputs: `resource_group_name`, `aks_name`, `acr_login_server`.

Terminal

```bash
cd ~/ssi-platform
```

### After provisioning: same for both paths

From here on, Bicep and OpenTofu users run the same steps: credentials, namespace, Secret, Prompt Guard, Helm, smoke test, and the SSI Connector. The cluster does not know which IaC tool built it. With the default `namePrefix` / `name_prefix` of `ssi`, both paths name things `ssi-aks-rg` and `ssi-aks`.

## 3. Get cluster credentials

Replace the names with your Bicep deployment outputs or `tofu output`.

Terminal

```bash
az aks get-credentials --resource-group ssi-aks-rg --name ssi-aks --overwrite-existing
```

Terminal

```bash
kubectl get nodes -o wide
```

Expected: system pool Ready. (Optional GPU pool is a later add — model slot can be Azure OpenAI instead.)

## 4. Namespace + gateway Secret

Do not commit the token.

Terminal

```bash
kubectl create namespace si-lab --dry-run=client -o yaml | kubectl apply -f -
```

Terminal

```bash
kubectl -n si-lab create secret generic ssi-gateway-auth --from-literal=token="$(openssl rand -hex 32)"
```

If the Secret already exists and you need to rotate:

Terminal

```bash
kubectl -n si-lab delete secret ssi-gateway-auth
```

Then recreate with the command above. Save the token for **SSI: Set Token** in the SSI Connector.

Terminal

```bash
kubectl -n si-lab get secret ssi-gateway-auth -o jsonpath='{.data.token}' | base64 -d; echo
```

## 5. Ensure Prompt Guard is present

Prompt Guard is unchanged. On a fresh AKS cluster, apply the existing Day 7/8 manifest (or your hardened image) before the control layer will accept traffic.

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-07-prompt-guard.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deploy/prompt-guard --timeout=180s
```

Adjust image pins for ACR as needed. Fail-closed behavior stays as on k3s.

## 6. Helm install SSI chart

Pin `images.*` to tags you built into ACR/GHCR. Overlay Internal LB for the Private Link path.

Terminal

```bash
helm upgrade --install ssi ~/ssi-platform/charts/ssi -n si-lab -f ~/ssi-platform/charts/ssi/values.yaml -f ~/ssi-platform/charts/ssi/values-aks-internal-lb.yaml --set privateEndpointHostname='ssi.privatelink.example.internal'
```

Terminal

```bash
kubectl -n si-lab rollout status deploy/ssi-gateway --timeout=180s
```

Terminal

```bash
kubectl -n si-lab get deploy,svc -l app.kubernetes.io/part-of=ssi
```

Expected: `ssi-gateway`, `control-layer`, `mcp-server`, `engineering-mcp` present; `ssi-gateway` Service type `LoadBalancer` with an **internal** IP when the overlay is applied.

### Model slot (swap without rewriting the loop)

| Choice | What to set |
| --- | --- |
| Ollama on a GPU node pool | Add GPU pool later; `--set controlLayer.ollamaUrl=http://ollama:11434` |
| Azure OpenAI | `--set controlLayer.modelBaseUrl='https://<your-aoai>.openai.azure.com'` and model name values your image understands |

Control-layer remains the only agent loop either way.

## 7. Smoke `/healthz` and `/control/healthz` over the private path

Until Private Link DNS is wired, port-forward from the terminal is a valid smoke (same probes as Day 11).

Terminal

```bash
kubectl -n si-lab port-forward svc/ssi-gateway 18080:8080
```

In a second Terminal tab:

Terminal

```bash
TOKEN="$(kubectl -n si-lab get secret ssi-gateway-auth -o jsonpath='{.data.token}' | base64 -d)"
```

Terminal

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18080/healthz
```

Expected: `200`.

Terminal

```bash
curl -sS -H "Authorization: Bearer ${TOKEN}" http://127.0.0.1:18080/control/healthz
```

Expected: `ok` (or the control-layer health body you already know from Day 10/11).

Terminal

```bash
curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:18080/control/healthz
```

Expected: `401` (no Bearer).

When Private Link + internal DNS are ready, repeat the same curls against `https://<private-hostname>` instead of port-forward. Do not publish a public Ingress for this lab story.

## 8. Point SSI Connector at the private base URL

1. Install the VSIX if needed (`docs/ssi-vscode-connector.md`).
2. Set **`ssi.endpoint`** to the private base URL (Private Link / VPN / internal DNS). No trailing slash. Example shape: `https://ssi.privatelink.example.internal`.
3. **SSI: Set Token** → paste the Secret value.
4. **SSI: Connect** → status bar **SSI: Connected**.
5. Leave path defaults: `ssi.controlPath=/control`, `ssi.businessMcpPath=/mcp/business`, `ssi.engineeringMcpPath=/mcp/engineering`.

Port-forward debug remains `http://127.0.0.1:18080` on the terminal only.

## Quiet observability note

Grafana and Langfuse stay in the architecture as the quiet observability lane. Day 12 does not require moving them. If you later host them on AKS or forward metrics to Azure Monitor while keeping Langfuse, update only those endpoints in values / runbooks — do not couple them into the agent loop.

## What this does not change

- **Prompt Guard** fail-closed behavior and its place in front of model/tool paths.
- **Dual MCP** slots (business / engineering) that do **not** peer; cross-share only via control-layer shared loop state.
- **Ownership model**: customer-owned private AI platform (SSI). No Microsoft-as-employer framing; FDE-shaped delivery of SSI. No Copilot seats required for this path.
- Home-lab **Tailscale** remains outside the product/enterprise story.

## Source map

| Path | Purpose |
| --- | --- |
| `infra/bicep/` | Option A (optional Azure-native alternative): RG, AKS, ACR, Log Analytics, private DNS placeholder (no state) |
| `infra/terraform/envs/aks` | Option B: same scope in OpenTofu (`azurerm ~> 4.0`; state file); Day 13 adds the full stack |
| `charts/ssi/` | Helm packaging for gateway + control-layer + MCP slots |
| `k8s/day-11-ssi-gateway.yaml` | k3s reference gateway (Day 11) |
| `k8s/day-10-control-layer.yaml` | k3s control-layer reference |
| `k8s/day-07-prompt-guard.yaml` | Prompt Guard (unchanged contract) |
| `docs/ssi-vscode-connector.md` | SSI Connector install + Connect |
| `docs/day-12-readme-blurb.md` | README paste blurb |
| `docs/day-12-study-guide-bullets.md` | FDE interview talking points |
