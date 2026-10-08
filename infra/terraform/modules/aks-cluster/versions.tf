# Day 12 AKS infrastructure (resource group, Log Analytics, ACR, AKS, optional
# user/GPU pool, private DNS placeholder), moved here unchanged on Day 13 so
# envs/aks can reuse it. The root module configures the providers and backend.

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
  }
}
