provider "aws" {
  region = var.region
}

# Short-lived token for the cluster; credentials come from your AWS profile
# (aws sso login / AWS_PROFILE), never from a file in the repo.
data "aws_eks_cluster_auth" "this" {
  name = module.eks.cluster_name
}

locals {
  kube = {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_certificate_authority_data)
    token                  = data.aws_eks_cluster_auth.this.token
  }
}

provider "kubernetes" {
  host                   = local.kube.host
  cluster_ca_certificate = local.kube.cluster_ca_certificate
  token                  = local.kube.token
}

provider "kubectl" {
  host                   = local.kube.host
  cluster_ca_certificate = local.kube.cluster_ca_certificate
  token                  = local.kube.token
  load_config_file       = false
}

provider "helm" {
  kubernetes = {
    host                   = local.kube.host
    cluster_ca_certificate = local.kube.cluster_ca_certificate
    token                  = local.kube.token
  }
}
