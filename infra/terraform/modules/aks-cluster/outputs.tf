output "resource_group_name" {
  description = "Resource group holding the SSI AKS scaffolding."
  value       = azurerm_resource_group.this.name
}

output "aks_name" {
  description = "AKS cluster name (use with az aks get-credentials)."
  value       = azurerm_kubernetes_cluster.this.name
}

output "acr_login_server" {
  description = "ACR login server for pinning chart images."
  value       = azurerm_container_registry.this.login_server
}

output "log_analytics_workspace_id" {
  description = "Log Analytics workspace ID."
  value       = azurerm_log_analytics_workspace.this.id
}

output "private_dns_zone_name" {
  description = "Private DNS zone placeholder name (empty when disabled)."
  value       = var.enable_private_dns ? azurerm_private_dns_zone.placeholder[0].name : ""
}

# Day 13: connection details for the kubernetes / helm / kubectl providers.
output "kube_host" {
  description = "AKS API server URL."
  value       = azurerm_kubernetes_cluster.this.kube_config[0].host
  sensitive   = true
}

output "kube_client_certificate" {
  description = "Client certificate (base64) from the cluster's kubeconfig."
  value       = azurerm_kubernetes_cluster.this.kube_config[0].client_certificate
  sensitive   = true
}

output "kube_client_key" {
  description = "Client key (base64) from the cluster's kubeconfig."
  value       = azurerm_kubernetes_cluster.this.kube_config[0].client_key
  sensitive   = true
}

output "kube_cluster_ca_certificate" {
  description = "Cluster CA (base64)."
  value       = azurerm_kubernetes_cluster.this.kube_config[0].cluster_ca_certificate
  sensitive   = true
}
