# The existing lab, expressed with the shared apps module. Every value below
# matches what is running today, so the first plan only adopts (imports.tf).

module "apps" {
  source = "../../apps"

  # Lab pattern: SSI control plane as raw manifests with code in ConfigMaps.
  ssi_control_plane_mode = "manifests"
  model_backend          = "ollama"
  model_name             = local.pins.ollama_chat_model

  # GPU on the lab host (k3s nvidia RuntimeClass + device plugin).
  enable_nvidia_device_plugin        = true
  nvidia_device_plugin_runtime_class = "nvidia"
  ollama_runtime_class_name          = "nvidia"

  # Models and RAG docs live on the lab host's external drive (static hostPath PVs).
  use_host_path_volumes = true

  # One-shot Jobs (model pull, MCP smoke test) already ran on the live lab and
  # were cleaned up; run them only on a fresh rebuild.
  enable_model_pull_job = !var.adopt_existing
  enable_smoke_test_job = !var.adopt_existing

  # Matches today's lab: the Day 6 pgvector NetworkPolicy is not applied in si-lab.
  enable_pgvector_netpol = false

  # Quiet observability lane on the agent node.
  enable_observability = true
  enable_langfuse      = true

  # Home-lab only private access.
  enable_tailscale_ingress = true

  # SSI Connector endpoint on the home LAN: http://192.0.2.93:30808 (lab host IP
  # reserved in the router). Cloud envs keep ClusterIP + the internal load balancer.
  gateway_service_type = "NodePort"
  gateway_node_port    = 30808
  gateway_lan_cidr     = "192.0.2.0/24"

  # Langfuse values passed with --set on Day 8b, and the headless-init project
  # ID the lab was initialised with before the si-lab rename.
  langfuse_nextauth_url    = var.tailnet_domain == "" ? "http://localhost:3002" : "https://langfuse.${var.tailnet_domain}"
  langfuse_init_project_id = "ai-lab"

  image_overrides = var.pin_image_digests ? local.pins.image_digests : {}

  create_secrets                = var.create_secrets
  pgvector_password             = var.pgvector_password
  webui_secret_key              = var.webui_secret_key
  ssi_gateway_token             = var.ssi_gateway_token
  grafana_admin_password        = var.grafana_admin_password
  langfuse_init_public_key      = var.langfuse_init_public_key
  langfuse_init_secret_key      = var.langfuse_init_secret_key
  langfuse_admin_email          = var.langfuse_admin_email
  langfuse_admin_password       = var.langfuse_admin_password
  tailscale_oauth_client_id     = var.tailscale_oauth_client_id
  tailscale_oauth_client_secret = var.tailscale_oauth_client_secret
  hf_token                      = var.hf_token
}
