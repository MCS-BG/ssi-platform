output "resource_group_name" {
  description = "Resource group holding the SSI AKS cluster."
  value       = module.aks_cluster.resource_group_name
}

output "aks_name" {
  description = "AKS cluster name (az aks get-credentials)."
  value       = module.aks_cluster.aks_name
}

output "acr_login_server" {
  description = "ACR login server (optional mirror for image_registry)."
  value       = module.aks_cluster.acr_login_server
}

output "managed_manifests" {
  description = "Raw-manifest objects deployed by the apps module."
  value       = try(module.apps[0].managed_manifests, [])
}

output "helm_releases" {
  description = "Helm releases deployed by the apps module."
  value       = try(module.apps[0].helm_releases, [])
}
