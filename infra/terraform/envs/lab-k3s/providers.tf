# All three providers read the same kubeconfig. Default ~/.kube/config; point
# it at your lab kubeconfig with TF_VAR_kubeconfig_path="$KUBECONFIG".

provider "kubectl" {
  config_path      = pathexpand(var.kubeconfig_path)
  config_context   = var.kube_context
  load_config_file = true
}

provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}

provider "helm" {
  kubernetes = {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = var.kube_context
  }
}
