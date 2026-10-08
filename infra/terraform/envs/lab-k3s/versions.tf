# Day 13: root module for the existing home-lab k3s cluster.
# Adopts what is already running (imports.tf) and keeps it in sync with the
# repo. Works with `tofu` (OpenTofu >= 1.7) or `terraform` (>= 1.7).

terraform {
  required_version = ">= 1.7.0"

  required_providers {
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

  # Local state (terraform.tfstate, git-ignored). It holds Secret values once
  # create_secrets = true and the adopted live objects, so never commit it.
  #
  # Remote state option (same pattern as Day 12): uncomment, create the storage
  # first, then `tofu init -migrate-state`.
  #
  # backend "azurerm" {
  #   resource_group_name  = "ssi-tfstate-rg"
  #   storage_account_name = "<globally-unique-name>"
  #   container_name       = "tfstate"
  #   key                  = "ssi-lab-k3s.tfstate"
  #   use_azuread_auth     = true
  # }
}
