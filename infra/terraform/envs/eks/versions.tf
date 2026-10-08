# Day 13: SSI on Amazon EKS. Open-source terraform-aws-modules (VPC + EKS) and
# the shared apps module (../../apps). OpenTofu >= 1.7.

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
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
  # backend "s3" {
  #   bucket       = "<your-tfstate-bucket>"
  #   key          = "ssi-eks.tfstate"
  #   region       = "us-east-1"
  #   use_lockfile = true
  # }
}
