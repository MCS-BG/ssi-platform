# Infrastructure as code

Rebuild the SSI lab from the terminal, or run the same stack on a cloud. Full runbook: [`docs/day-13-iac-full-stack.md`](../docs/day-13-iac-full-stack.md).

| Folder | Tool | Status | What it does |
| --- | --- | --- | --- |
| `ansible/` | Ansible | **Supported** (step 1) | Builds the lab nodes: OS baseline, NVIDIA driver + container toolkit, k3s server/agent with a pinned node IP |
| `terraform/apps/` | OpenTofu module | **Supported** (step 2) | The whole SSI stack on any Kubernetes cluster: Helm releases + `k8s/*.yaml` |
| `terraform/envs/lab-k3s/` | OpenTofu | **Supported** | The live home lab, adopted with `import` blocks |
| `terraform/envs/aks/`, `eks/`, `gke/` | OpenTofu | **Supported** | Managed cluster + the same apps module (GPU pool off by default) |
| `terraform/modules/aks-cluster/` | OpenTofu module | Supported | Day 12 AKS infrastructure, used by `envs/aks` |
| `bicep/` | Bicep | Optional alternative | Azure-native version of the Day 12 cluster only. Not part of the supported rebuild path. |

Order for the lab: router DHCP reservations, then `ansible/`, then `terraform/envs/lab-k3s`.

Pins come from the live lab (2026-10-06): node versions in `ansible/group_vars/all.yml`, chart versions in `terraform/apps/helm.tf`, image digests and model IDs in `terraform/envs/lab-k3s/pins.tf`.

Never committed: `terraform.tfvars`, `secrets.auto.tfvars`, `ansible/inventory.ini`, `*.tfstate*`, `*.tfplan`, `.terraform/`. Each has an `.example` next to it.
