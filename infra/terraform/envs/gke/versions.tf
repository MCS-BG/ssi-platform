# Day 13: SSI on Google Kubernetes Engine (Standard). Plain google provider
# resources (VPC, subnet, GKE, node pools) + the shared apps module.
# OpenTofu >= 1.7.

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
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

  # Remote state: create the bucket first, uncomment, `tofu init`.
  #
  # backend "gcs" {
  #   bucket = "<your-tfstate-bucket>"
  #   prefix = "ssi-gke"
  # }
}
