# envs/aks: SSI on AKS

The Day 12 AKS cluster (`../../modules/aks-cluster`: resource group, Log Analytics, ACR with AcrPull, AKS system pool, optional GPU and observability pools, private DNS placeholder) plus the SSI stack. `moved.tf` maps the Day 12 root addresses, so an existing Day 12 state upgrades in place.

## Run

All commands from this folder on the terminal. Read every plan before applying.

```bash
cp terraform.tfvars.example terraform.tfvars
```

```bash
cp secrets.auto.tfvars.example secrets.auto.tfvars
```

Fill `secrets.auto.tfvars` with `openssl rand` values (git-ignored, never pasted into chat).

```bash
az login
```

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
```

```bash
tofu init
```

First pass: cluster only (the Kubernetes and Helm providers need its endpoint).

```bash
tofu plan -var 'deploy_apps=false' -out=cluster.tfplan
```

```bash
tofu apply cluster.tfplan
```

Second pass: the SSI stack through `../../apps`.

```bash
tofu plan -out=apps.tfplan
```

```bash
tofu apply apps.tfplan
```

Delete the `*.tfplan` files afterwards. Tear down with `tofu destroy` when the demo is over.

Validate without a login:

```bash
tofu init -backend=false
```

```bash
tofu validate
```

## GPU pool (off by default)

`enable_gpu_pool = false`. When on: `gpu_pool_vm_size = "Standard_ND96isr_H100_v5"` (8x H100 80 GB), `gpu_pool_node_count = 1`, `gpus_per_node = 8`. Label and taint `sku=gpu`; only the model server (Ollama or vLLM) tolerates it.

Quota: Request quota for the **Standard NDSH100v5 Family vCPUs** (96 per node) in the region, under Subscriptions > Usage + quotas. Many subscriptions start at 0, and H100 capacity is limited to some regions. Also check `az aks get-versions --location <region>` and set `kubernetes_version` to a supported version (the Day 12 default is old).

Cost: check current on-demand pricing for the SKU and region before you turn it on, and turn it off after the demo.

Sizing for big open-weight models (Reflection AI Beam and similar): `docs/models/beam.md`.

## What the apps module gets here

- Same `../../apps` module as the home lab (`envs/lab-k3s`), so the same manifests, charts and versions.
- `ssi_control_plane_mode = "manifests"`: control layer, engineering MCP and ssi-gateway run from ConfigMaps, no extra images. Switch to `"helm"` after publishing the images (`docs/day-13-iac-full-stack.md`, "Images on the cloud").
- Repo-built images come from `image_registry` (default `ghcr.io/mcs-bg`); upstream images are unchanged.
- ssi-gateway gets a private (internal) load balancer, `gateway_allowed_cidrs` limits who may connect. No Tailscale (`enable_tailscale_ingress = false`).
- Ollama runs on CPU unless the GPU pool is on. `model_backend = "vllm"` needs the GPU pool.
- `enable_observability = true` adds a small tainted pool and the quiet lane (Prometheus, Grafana, Loki, Tempo, Langfuse).

## Private access

Azure internal load balancer (`service.beta.kubernetes.io/azure-load-balancer-internal`). Reach it over VPN / Private Link.

Bicep (`infra/bicep`) builds the same Day 12 cluster and stays as an optional Azure-native alternative; do not deploy both with the same names.
