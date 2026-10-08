# envs/eks: SSI on EKS

A VPC (public + private subnets, one NAT gateway) and an EKS cluster with a managed node group, built from the open-source `terraform-aws-modules/vpc` and `terraform-aws-modules/eks` modules, plus the EBS CSI driver (pod identity), a default `gp3` StorageClass and the SSI stack.

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
aws sso login
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

`enable_gpu_pool = false`. When on: `gpu_instance_type = "p5.48xlarge"` (8x H100 80 GB), `gpu_node_count = 1`, `gpus_per_node = 8`, EKS NVIDIA AMI (`AL2023_x86_64_NVIDIA`), 300 GB root volume. Label and taint `sku=gpu`; only the model server tolerates it.

Quota: Request **Running On-Demand P instances** vCPU quota (192 per p5.48xlarge) in Service Quotas for the region. Default is usually 0. P5 capacity is scarce; EC2 Capacity Blocks for ML are the reliable way to get it for a fixed demo window.

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

AWS internal NLB (`service.beta.kubernetes.io/aws-load-balancer-internal: "true"`). Reach it over VPN / PrivateLink.
