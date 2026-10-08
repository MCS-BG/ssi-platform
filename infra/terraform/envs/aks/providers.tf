# azurerm 4.x needs a subscription ID. Supply it through the environment
# (ARM_SUBSCRIPTION_ID) rather than committing it to the repo.
provider "azurerm" {
  features {}
}

# Cluster credentials come straight from the cluster module outputs. On the very
# first run the cluster does not exist yet: run `tofu apply -target=module.aks_cluster`
# first (or set deploy_apps = false), then a normal plan/apply.
locals {
  kube = {
    host                   = module.aks_cluster.kube_host
    client_certificate     = base64decode(module.aks_cluster.kube_client_certificate)
    client_key             = base64decode(module.aks_cluster.kube_client_key)
    cluster_ca_certificate = base64decode(module.aks_cluster.kube_cluster_ca_certificate)
  }
}

provider "kubernetes" {
  host                   = local.kube.host
  client_certificate     = local.kube.client_certificate
  client_key             = local.kube.client_key
  cluster_ca_certificate = local.kube.cluster_ca_certificate
}

provider "kubectl" {
  host                   = local.kube.host
  client_certificate     = local.kube.client_certificate
  client_key             = local.kube.client_key
  cluster_ca_certificate = local.kube.cluster_ca_certificate
  load_config_file       = false
}

provider "helm" {
  kubernetes = {
    host                   = local.kube.host
    client_certificate     = local.kube.client_certificate
    client_key             = local.kube.client_key
    cluster_ca_certificate = local.kube.cluster_ca_certificate
  }
}
