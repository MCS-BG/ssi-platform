# Day 12 kept these resources in the infra/terraform root. If you applied Day 12
# and move its state file here, these blocks re-address the resources into the
# cluster module instead of recreating them. No-ops on a fresh state.

moved {
  from = random_string.acr_suffix
  to   = module.aks_cluster.random_string.acr_suffix
}

moved {
  from = azurerm_resource_group.this
  to   = module.aks_cluster.azurerm_resource_group.this
}

moved {
  from = azurerm_log_analytics_workspace.this
  to   = module.aks_cluster.azurerm_log_analytics_workspace.this
}

moved {
  from = azurerm_container_registry.this
  to   = module.aks_cluster.azurerm_container_registry.this
}

moved {
  from = azurerm_kubernetes_cluster.this
  to   = module.aks_cluster.azurerm_kubernetes_cluster.this
}

moved {
  from = azurerm_kubernetes_cluster_node_pool.user
  to   = module.aks_cluster.azurerm_kubernetes_cluster_node_pool.user
}

moved {
  from = azurerm_role_assignment.aks_acr_pull
  to   = module.aks_cluster.azurerm_role_assignment.aks_acr_pull
}

moved {
  from = azurerm_private_dns_zone.placeholder
  to   = module.aks_cluster.azurerm_private_dns_zone.placeholder
}
