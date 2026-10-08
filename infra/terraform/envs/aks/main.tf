# Day 13: SSI on AKS = Day 12 cluster module + the shared apps module.

locals {
  internal_lb_annotations = { "service.beta.kubernetes.io/azure-load-balancer-internal" = "true" }

  # GPU pool: label + taint sku=gpu so only the model server lands there.
  gpus_per_node     = var.gpus_per_node
  gpu_node_selector = var.enable_gpu_pool ? { sku = "gpu" } : {}
  gpu_tolerations   = var.enable_gpu_pool ? [{ key = "sku", operator = "Equal", value = "gpu", effect = "NoSchedule" }] : []
}

module "aks_cluster" {
  source = "../../modules/aks-cluster"

  location             = var.location
  name_prefix          = var.name_prefix
  kubernetes_version   = var.kubernetes_version
  system_node_vm_size  = var.system_node_vm_size
  system_node_count    = var.system_node_count
  enable_user_pool     = var.enable_gpu_pool
  user_pool_vm_size    = var.gpu_pool_vm_size
  user_pool_node_count = var.gpu_pool_node_count
  user_pool_gpu        = var.enable_gpu_pool
  enable_private_dns   = var.enable_private_dns
  tags                 = var.tags

  enable_observability_pool  = var.enable_observability
  observability_pool_vm_size = var.observability_pool_vm_size
}

module "apps" {
  source = "../../apps"
  count  = var.deploy_apps ? 1 : 0

  # AKS GPU node images ship the NVIDIA driver and make nvidia the default
  # containerd runtime, so no RuntimeClass. Without a GPU pool Ollama runs on CPU.
  enable_nvidia_device_plugin        = var.enable_gpu_pool
  nvidia_device_plugin_runtime_class = ""
  ollama_gpu                         = var.enable_gpu_pool
  ollama_runtime_class_name          = ""
  ollama_node_selector               = local.gpu_node_selector
  ollama_tolerations                 = local.gpu_tolerations
  storage_class_name                 = "managed-csi"

  ssi_control_plane_mode = var.ssi_control_plane_mode
  image_registry         = var.image_registry
  ssi_image_tag          = var.ssi_image_tag
  model_backend          = var.model_backend
  model_name             = var.model_name
  azure_openai_endpoint  = var.azure_openai_endpoint

  # vLLM on the GPU pool: one replica spanning all GPUs of one node.
  vllm_model_id               = var.vllm_model_id
  vllm_quantization           = var.vllm_quantization
  vllm_max_model_len          = var.vllm_max_model_len
  vllm_weights_size           = var.vllm_weights_size
  vllm_gpu_count              = local.gpus_per_node
  vllm_tensor_parallel_size   = local.gpus_per_node
  vllm_enable_expert_parallel = true
  vllm_memory_request         = "256Gi"
  vllm_memory_limit           = "1024Gi"
  vllm_shm_size               = "64Gi"
  vllm_node_selector          = local.gpu_node_selector
  vllm_tolerations            = local.gpu_tolerations

  # Fresh cluster: run the model pull Job once, no hostPath volumes, no Tailscale.
  enable_model_pull_job    = true
  enable_tailscale_ingress = false
  use_host_path_volumes    = false

  enable_observability = var.enable_observability
  enable_langfuse      = var.enable_observability

  gateway_load_balancer = {
    enabled     = var.gateway_internal_lb
    annotations = local.internal_lb_annotations
  }
  gateway_allowed_cidrs = var.gateway_allowed_cidrs

  create_secrets           = var.create_secrets
  pgvector_password        = lookup(var.app_secrets, "pgvector_password", null)
  webui_secret_key         = lookup(var.app_secrets, "webui_secret_key", null)
  ssi_gateway_token        = lookup(var.app_secrets, "ssi_gateway_token", null)
  grafana_admin_password   = lookup(var.app_secrets, "grafana_admin_password", null)
  langfuse_init_public_key = lookup(var.app_secrets, "langfuse_init_public_key", null)
  langfuse_init_secret_key = lookup(var.app_secrets, "langfuse_init_secret_key", null)
  langfuse_admin_email     = lookup(var.app_secrets, "langfuse_admin_email", null)
  langfuse_admin_password  = lookup(var.app_secrets, "langfuse_admin_password", null)
  hf_token                 = lookup(var.app_secrets, "hf_token", null)

  depends_on = [module.aks_cluster]
}
