# Day 13: AKS root. Day 12 cluster (../../modules/aks-cluster) + the shared
# apps module (../../apps). OpenTofu >= 1.7.

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    kubectl = {
      source  = "alekc/kubectl"
      version = "~> 2.1"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 3.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.0"
    }
  }

  # Remote state (recommended beyond a solo run). State can contain sensitive
  # values: create customer-owned storage first, uncomment, `tofu init`.
  #
  # backend "azurerm" {
  #   resource_group_name  = "ssi-tfstate-rg"
  #   storage_account_name = "<globally-unique-name>"
  #   container_name       = "tfstate"
  #   key                  = "ssi-aks.tfstate"
  #   use_azuread_auth     = true
  # }
}
