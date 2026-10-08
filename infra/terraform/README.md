# OpenTofu: SSI stack on any Kubernetes

Day 12 started this folder as the AKS scaffolding. Day 13 turned it into one reusable app module plus one root per environment. All commands use OpenTofu (`tofu`). Runbook: `docs/day-13-iac-full-stack.md`.

```text
infra/terraform/
  apps/                  reusable module: the whole SSI stack (Helm releases + k8s/*.yaml)
  modules/aks-cluster/   Day 12 AKS infrastructure (RG, Log Analytics, ACR, AKS, pools, private DNS)
  envs/lab-k3s/          the live home lab, adopted with import blocks
  envs/aks/              modules/aks-cluster + apps
  envs/eks/              VPC + EKS (terraform-aws-modules) + apps
  envs/gke/              VPC + GKE Standard + apps
```

| Root | Providers | State |
| --- | --- | --- |
| `envs/lab-k3s` | kubernetes, kubectl (alekc), helm via `kubeconfig_path` | local, commented `azurerm` backend |
| `envs/aks` | azurerm `~> 4.0` + the three Kubernetes providers from the cluster outputs | local, commented `azurerm` backend |
| `envs/eks` | aws `~> 6.0`, terraform-aws-modules vpc `~> 6.0` / eks `~> 21.0` | local, commented `s3` backend |
| `envs/gke` | google `~> 8.0` | local, commented `gcs` backend |

## The apps module

- `kubectl_manifest` over the repo's `k8s/*.yaml`: the YAML files stay the one source of truth. A catalog in `apps/manifests.tf` picks which Day file supersedes which (for example Day 8a Prompt Guard over Day 7).
- `helm_release` for everything the lab installed with Helm, same charts, versions and values files as Days 7, 8b and 12.
- Toggles for every component (`enable_*`), `model_backend` (`ollama` or `vllm`), `image_registry`, `enable_tailscale_ingress` (default false; lab only), `gateway_load_balancer` for private cloud load balancers, `create_secrets` (default false: reference existing Secrets by name).
- Patches are applied only when a value differs from the lab, so the lab's objects render byte-identical to the repo YAML.

## Validate (no cloud login, no cluster)

Run in any root:

```bash
tofu init -backend=false
```

```bash
tofu validate
```

```bash
tofu fmt -check -recursive
```

`.terraform.lock.hcl` is created on the first `init`. Commit it so everyone gets the same provider builds.

## State

Bicep has no state file. OpenTofu does: the state maps the config to real resources and **contains every managed value, including Secret data**. Never commit it (the `.gitignore` here excludes it).

For a solo read-through or `validate`, local state or `-backend=false` is fine. For a customer deploy, keep state in storage the customer owns (Azure Storage for AKS, S3 for EKS, GCS for GKE): uncomment the backend block in that env's `versions.tf`, fill in the names, then run `tofu init -migrate-state`. For Azure:

1. Create a resource group, a storage account and a blob container (for example `tfstate`) in the customer's subscription.
2. Give the deploying identity **Storage Blob Data Contributor** on the container.
3. Uncomment `backend "azurerm"` in `envs/aks/versions.tf`.

## Day 12 AKS (cluster only)

The Day 12 resources moved from the root of this folder into `modules/aks-cluster`, called by `envs/aks`. `envs/aks/moved.tf` maps the old addresses, so an existing Day 12 state upgrades without recreating anything (move the state file into `envs/aks` first). Set `deploy_apps = false` for the Day 12 scope (cluster only, then Helm by hand as in `docs/day-12-ssi-on-aks.md`).

```bash
export ARM_SUBSCRIPTION_ID="$(az account show --query id -o tsv)"
```

```bash
tofu -chdir=envs/aks init
```

```bash
tofu -chdir=envs/aks plan -var 'deploy_apps=false' -out=day12.tfplan
```

```bash
tofu -chdir=envs/aks apply day12.tfplan
```

## Bicep vs OpenTofu

| | Bicep (`infra/bicep`, optional) | OpenTofu (supported) |
| --- | --- | --- |
| Scope | Azure only, cluster only | Any cloud plus the home lab, cluster and apps |
| State | None. Azure Resource Manager is the source of truth. | State file in storage you own |
| Preview | `az deployment sub what-if` | `tofu plan` |

The enterprise path is Private Link / VPN / internal DNS (internal load balancer for ssi-gateway). Tailscale is for reaching the home lab only.
