## Day 12 blurb (paste into README later)

| Day | Write-up | Step file |
| --- | --- | --- |
| 12 | Promote SSI to AKS with Bicep or Terraform/OpenTofu, then Helm (Private Link path; same `si-lab` control plane) | [docs/day-12-ssi-on-aks.md](docs/day-12-ssi-on-aks.md) |

### Layout additions

| Path | Contents |
| --- | --- |
| `infra/bicep/` | Day 12 minimal AKS scaffolding: RG, AKS, ACR, Log Analytics, private DNS placeholder. |
| `infra/terraform/envs/aks` | Same scaffolding in OpenTofu (`tofu`), the supported path from Day 13. Keeps a state file: use customer-owned remote state, never commit it. |
| `charts/ssi/` | Helm chart for `ssi-gateway`, `control-layer`, `mcp-server`, `engineering-mcp`. Gateway token via Secret `ssi-gateway-auth` (never in git). |

Day 12 teaches the k3s → AKS mapping and a small deploy path. Enterprise reachability is Private Link / VPN / internal DNS. Tailscale stays home-lab only. Prompt Guard, dual MCP slots, and customer ownership of the SSI platform do not change.
