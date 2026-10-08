provider "google" {
  project = var.project_id
  region  = var.region
}

# Access token from your gcloud login (gcloud auth application-default login);
# nothing is stored in the repo.
data "google_client_config" "this" {}

locals {
  kube = {
    host                   = "https://${google_container_cluster.this.endpoint}"
    cluster_ca_certificate = base64decode(google_container_cluster.this.master_auth[0].cluster_ca_certificate)
    token                  = data.google_client_config.this.access_token
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
