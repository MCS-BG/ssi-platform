# Day 12 Bicep (SSI on AKS scaffolding)

> **Optional Azure-native alternative.** The supported path from Day 13 on is OpenTofu (`infra/terraform/envs/aks`) plus Ansible for the home lab. See `infra/README.md`.

Minimal, readable modules for the Day 12 teaching deploy. This is **not** a full production AKS landing zone.

| File | Role |
| --- | --- |
| `main.bicep` | Subscription-scoped entry: RG + modules |
| `modules/aks.bicep` | AKS system pool (+ optional CPU user pool), Container Insights, AcrPull |
| `modules/acr.bicep` | Azure Container Registry (Basic) |
| `modules/logAnalytics.bicep` | Log Analytics workspace |
| `modules/privateDns.bicep` | Private DNS zone placeholder + Private Link notes |
| `main.bicepparam` | Sample parameters |

## Parameters

- `location`, `namePrefix`, `kubernetesVersion`
- Optional user pool flags; GPU pool is documented, not created (model slot stays swappable)

## Deploy (from the terminal; you run `az login`)

```bash
az deployment sub create --location eastus --template-file infra/bicep/main.bicep --parameters infra/bicep/main.bicepparam
```

Do not commit secrets. Do not treat Tailscale as the enterprise path — use Private Link / VPN / internal DNS.
