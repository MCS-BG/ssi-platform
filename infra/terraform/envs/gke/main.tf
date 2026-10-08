locals {
  internal_lb_annotations = { "networking.gke.io/load-balancer-type" = "Internal" }

  # GKE taints GPU nodes with nvidia.com/gpu=present:NoSchedule itself and
  # installs the driver + device plugin; we add sku=gpu like the other clouds.
  gpus_per_node     = var.gpus_per_node
  gpu_node_selector = var.enable_gpu_pool ? { sku = "gpu" } : {}
  gpu_tolerations = var.enable_gpu_pool ? [
    { key = "sku", operator = "Equal", value = "gpu", effect = "NoSchedule" },
    { key = "nvidia.com/gpu", operator = "Exists", effect = "NoSchedule" },
  ] : []
}

resource "google_compute_network" "this" {
  project                 = var.project_id
  name                    = "${var.name}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "this" {
  project       = var.project_id
  name          = "${var.name}-nodes"
  region        = var.region
  network       = google_compute_network.this.id
  ip_cidr_range = var.subnet_cidr

  private_ip_google_access = true

  secondary_ip_range {
    range_name    = "pods"
    ip_cidr_range = var.pods_cidr
  }

  secondary_ip_range {
    range_name    = "services"
    ip_cidr_range = var.services_cidr
  }
}

resource "google_container_cluster" "this" {
  project  = var.project_id
  name     = "${var.name}-gke"
  location = var.zone

  network    = google_compute_network.this.id
  subnetwork = google_compute_subnetwork.this.id

  # Node pools are managed separately below.
  remove_default_node_pool = true
  initial_node_count       = 1

  networking_mode = "VPC_NATIVE"
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Dataplane V2 enforces the repo's NetworkPolicies.
  datapath_provider = "ADVANCED_DATAPATH"

  release_channel {
    channel = "REGULAR"
  }

  deletion_protection = var.deletion_protection
}

resource "google_container_node_pool" "default" {
  project    = var.project_id
  name       = "default"
  location   = var.zone
  cluster    = google_container_cluster.this.name
  node_count = var.node_count

  node_config {
    machine_type = var.node_machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}

resource "google_container_node_pool" "gpu" {
  count = var.enable_gpu_pool ? 1 : 0

  project    = var.project_id
  name       = "gpu"
  location   = var.zone
  cluster    = google_container_cluster.this.name
  node_count = var.gpu_node_count

  node_config {
    machine_type = var.gpu_machine_type
    disk_size_gb = 300
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    labels       = { sku = "gpu" }

    guest_accelerator {
      type  = var.gpu_accelerator_type
      count = var.gpus_per_node
      gpu_driver_installation_config {
        gpu_driver_version = "LATEST"
      }
    }

    taint {
      key    = "sku"
      value  = "gpu"
      effect = "NO_SCHEDULE"
    }
  }
}

resource "google_container_node_pool" "observability" {
  count = var.enable_observability ? 1 : 0

  project    = var.project_id
  name       = "observability"
  location   = var.zone
  cluster    = google_container_cluster.this.name
  node_count = 1

  node_config {
    machine_type = var.observability_machine_type
    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    labels       = { "ailab/role" = "observability" }

    taint {
      key    = "ailab/role"
      value  = "observability"
      effect = "NO_SCHEDULE"
    }
  }
}

module "apps" {
  source = "../../apps"
  count  = var.deploy_apps ? 1 : 0

  # GKE installs the NVIDIA driver and device plugin on GPU nodes itself.
  # Without a GPU pool Ollama runs on CPU.
  enable_nvidia_device_plugin = false
  ollama_gpu                  = var.enable_gpu_pool
  ollama_runtime_class_name   = ""
  ollama_node_selector        = local.gpu_node_selector
  ollama_tolerations          = local.gpu_tolerations
  storage_class_name          = "standard-rwo"

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

  depends_on = [google_container_node_pool.default]
}
