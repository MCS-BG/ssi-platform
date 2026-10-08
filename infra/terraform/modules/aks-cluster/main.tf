# Same scope as infra/bicep: RG, Log Analytics, ACR (+ AcrPull), AKS
# (system pool + optional user/GPU pool), private DNS placeholder.

locals {
  rg_name   = "${var.name_prefix}-aks-rg"
  aks_name  = "${var.name_prefix}-aks"
  law_name  = "${var.name_prefix}-law"
  acr_name  = "${var.name_prefix}acr${random_string.acr_suffix.result}"
  dns_zone  = "privatelink.${var.location}.azmk8s.io"
  gpu_label = var.user_pool_gpu ? { sku = "gpu" } : {}
  gpu_taint = var.user_pool_gpu ? ["sku=gpu:NoSchedule"] : []
}

resource "random_string" "acr_suffix" {
  length  = 8
  upper   = false
  special = false
}

resource "azurerm_resource_group" "this" {
  name     = local.rg_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = local.law_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = var.tags
}

resource "azurerm_container_registry" "this" {
  name                = local.acr_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  sku                 = "Basic"
  admin_enabled       = false
  tags                = var.tags
}

resource "azurerm_kubernetes_cluster" "this" {
  name                = local.aks_name
  location            = azurerm_resource_group.this.location
  resource_group_name = azurerm_resource_group.this.name
  dns_prefix          = substr(replace(local.aks_name, "-", ""), 0, 10)
  kubernetes_version  = var.kubernetes_version
  tags                = var.tags

  default_node_pool {
    name                 = "system"
    vm_size              = var.system_node_vm_size
    node_count           = var.system_node_count
    auto_scaling_enabled = false
  }

  identity {
    type = "SystemAssigned"
  }

  network_profile {
    network_plugin    = "azure"
    load_balancer_sku = "standard"
    outbound_type     = "loadBalancer"
  }

  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "user" {
  count = var.enable_user_pool ? 1 : 0

  name                  = "userpool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  mode                  = "User"
  vm_size               = var.user_pool_vm_size
  node_count            = var.user_pool_node_count
  node_labels           = local.gpu_label
  node_taints           = local.gpu_taint
  tags                  = var.tags
}

resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                            = azurerm_container_registry.this.id
  role_definition_name             = "AcrPull"
  principal_id                     = azurerm_kubernetes_cluster.this.kubelet_identity[0].object_id
  skip_service_principal_aad_check = true
}

# Optional pool for the quiet observability lane. The Day 7 Helm values pin
# Prometheus/Grafana/Loki/Tempo/Langfuse to nodes labelled and tainted
# ailab/role=observability (the lab's agent node); this pool matches that.
resource "azurerm_kubernetes_cluster_node_pool" "observability" {
  count = var.enable_observability_pool ? 1 : 0

  name                  = "obspool"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  mode                  = "User"
  vm_size               = var.observability_pool_vm_size
  node_count            = 1
  node_labels           = { "ailab/role" = "observability" }
  node_taints           = ["ailab/role=observability:NoSchedule"]
  tags                  = var.tags
}

# Placeholder only. Enterprise path: Internal LB -> Private Link Service ->
# private endpoint in the consumer VNet -> A record here. Not Tailscale.
resource "azurerm_private_dns_zone" "placeholder" {
  count = var.enable_private_dns ? 1 : 0

  name                = local.dns_zone
  resource_group_name = azurerm_resource_group.this.name
  tags                = var.tags
}
