# Helm mode (AKS and any cluster with built images): charts/ssi deploys the
# SSI control plane (gateway, control-layer, business MCP, engineering MCP, M365 MCP)
# from the local chart path. The lab uses the raw manifests instead
# (ssi_control_plane_mode = "manifests"); both share the same object names.

locals {
  ssi_chart_dir = "${local.repo_root}/charts/ssi"

  ssi_chart_override = {
    namespace               = "si-lab"
    createNamespace         = false
    privateEndpointHostname = var.private_endpoint_hostname
    images = {
      for k, name in {
        gateway        = "ssi-gateway"
        controlLayer   = "control-layer"
        mcpServer      = "mcp-server"
        engineeringMcp = "engineering-mcp"
        m365Mcp        = "m365-mcp"
      } : k => { repository = "${trimsuffix(var.image_registry, "/")}/${name}", tag = var.ssi_image_tag, pullPolicy = "IfNotPresent" }
    }
    service = {
      gateway = {
        type        = var.gateway_load_balancer.enabled ? "LoadBalancer" : "ClusterIP"
        port        = 8080
        annotations = var.gateway_load_balancer.enabled ? var.gateway_load_balancer.annotations : {}
      }
      controlLayer   = { port = 8080 }
      mcpServer      = { port = 8000 }
      engineeringMcp = { port = 8000 }
      m365Mcp        = { port = 8000 }
    }
    m365Mcp = { enabled = var.enable_m365_mcp }
    memory  = { enabled = local.memory }
    engineeringMcp = {
      github = {
        enabled = var.enable_engineering_mcp_github
        owner   = var.engineering_mcp_github_owner
        repos   = var.engineering_mcp_github_repos
      }
    }
    controlLayer = merge(
      {
        ollamaUrl              = "http://ollama:11434"
        model                  = local.use_vllm ? local.vllm_served_name : var.model_name
        planner                = var.control_layer_planner
        engineeringDefaultRepo = var.engineering_default_repo
      },
      { for k, v in { modelBaseUrl = "http://vllm:8000/v1", modelName = local.vllm_served_name } : k => v if local.use_vllm && var.azure_openai_endpoint == "" },
      { for k, v in { modelBaseUrl = var.azure_openai_endpoint, modelName = var.model_name } : k => v if var.azure_openai_endpoint != "" }
    )
  }
}

resource "helm_release" "ssi" {
  count = local.helm_ssi ? 1 : 0

  name      = "ssi"
  namespace = "si-lab"
  chart     = local.ssi_chart_dir
  timeout   = var.helm_timeout

  values = [
    file("${local.ssi_chart_dir}/values.yaml"),
    yamlencode(local.ssi_chart_override),
  ]

  depends_on = [kubectl_manifest.namespace, kubernetes_secret_v1.app, kubectl_manifest.this]
}

# Manifests mode: the Day 11 ssi-gateway Service is NodePort 30808 on the home lab
# (k8s/day-11-ssi-gateway.yaml) and is patched back to ClusterIP on cloud envs
# (gateway_service_type in manifests.tf); a second Service puts it on a private cloud LB.
resource "kubernetes_service_v1" "gateway_lb" {
  count = !local.helm_ssi && var.enable_ssi_gateway && var.gateway_load_balancer.enabled ? 1 : 0

  metadata {
    name        = "ssi-gateway-lb"
    namespace   = "si-lab"
    annotations = var.gateway_load_balancer.annotations
    labels      = { app = "ssi-gateway" }
  }

  spec {
    type     = "LoadBalancer"
    selector = { app = "ssi-gateway" }

    port {
      name        = "http"
      port        = 8080
      target_port = 8080
    }
  }

  depends_on = [kubectl_manifest.this]
}
