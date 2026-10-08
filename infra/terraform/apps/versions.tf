# Day 13: reusable "apps" module. Deploys the existing SSI (si-lab) stack onto
# any Kubernetes cluster. The root modules in ../envs/ configure the providers.
# Works unmodified with `tofu` (OpenTofu) or `terraform`.

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
}
