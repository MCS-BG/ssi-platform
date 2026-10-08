# envs/gke: SSI on GKE

A VPC network with a subnet and secondary ranges, a GKE Standard cluster (VPC-native, Dataplane V2) with a default node pool, optional GPU and observability pools, plus the SSI stack. GKE installs the NVIDIA driver on the GPU pool itself, so the device plugin chart is off here.

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
gcloud auth application-default login
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

`enable_gpu_pool = false`. When on: `gpu_machine_type = "a3-highgpu-8g"` with `gpu_accelerator_type = "nvidia-h100-80gb"` (8x H100 80 GB), `gpu_node_count = 1`, `gpus_per_node = 8`, GKE-managed driver (`LATEST`). Label and taint `sku=gpu`; only the model server tolerates it.

Quota: Request **NVIDIA_H100_GPUS** quota (8 per node) in the region, and check A3 availability in your `zone`. Defaults are usually 0. DWS / reservations are the reliable way to get H100s for a fixed demo window.

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

GCP internal load balancer (`networking.gke.io/load-balancer-type: Internal`). Reach it over VPN / Private Service Connect.

`deletion_protection = true` by default; set it to false before `tofu destroy`.
