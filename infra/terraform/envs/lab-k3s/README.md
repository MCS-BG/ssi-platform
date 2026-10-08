# envs/lab-k3s: the live home lab

The running k3s lab, expressed with the shared `../../apps` module. `imports.tf` adopts every object that already runs (8 namespaces, 49 manifests, 10 Helm releases), so nothing is recreated. Node-level pieces (k3s, NVIDIA) belong to `infra/ansible`.

| File | Purpose |
| --- | --- |
| `main.tf` | Calls `../../apps` with the lab's values (manifests mode, Ollama on the GPU, hostPath volumes, observability, Tailscale ingress) |
| `pins.tf` | Versions read from the live lab: k3s, Ollama, model IDs, image digests |
| `imports.tf` | `import` blocks for everything running (`adopt_existing = true`) |
| `providers.tf` | kubernetes, kubectl, helm via `kubeconfig_path` (default `~/.kube/config`) |
| `terraform.tfvars.example` | Non-secret settings |
| `secrets.auto.tfvars.example` | Only for a fresh rebuild (`create_secrets = true`) |

## Run

```bash
cp terraform.tfvars.example terraform.tfvars
```

```bash
export TF_VAR_kubeconfig_path="$KUBECONFIG"
```

```bash
tofu init
```

```bash
tofu plan
```

The first plan (2026-10-06): `67 to import, 0 to add, 67 to change, 0 to destroy`. The changes are provider adoption bookkeeping plus 5 small label/namespace fixes where the repo is newer; `docs/day-13-iac-full-stack.md` explains each group. Apply once after reading it; the next plan is clean.

## Modes

| Variable | Live lab | Fresh rebuild |
| --- | --- | --- |
| `adopt_existing` | `true` (import) | `false` (create) |
| `pin_image_digests` | `false` (tags exactly as in `k8s/*.yaml`) | `true` (digests from `pins.tf`) |
| `create_secrets` | `false` (Secrets exist, referenced by name) | `true` + `secrets.auto.tfvars` |

Do not set `create_secrets = true` against the live lab; it would overwrite the existing Secrets.
