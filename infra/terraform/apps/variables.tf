# ---------------------------------------------------------------------------
# Repo paths. The module reads the repo's own k8s/*.yaml, models/*.yaml,
# Helm values files and charts/ssi, so there is one source of truth.
# ---------------------------------------------------------------------------

variable "repo_root" {
  description = "Path to the ssi-platform checkout. Defaults to three levels above this module."
  type        = string
  default     = null
}

# ---------------------------------------------------------------------------
# Component toggles
# ---------------------------------------------------------------------------

variable "enable_ollama" {
  description = "Deploy Ollama (model slot = ollama). Only deployed when model_backend = ollama."
  type        = bool
  default     = true
}

variable "enable_model_pull_job" {
  description = "Run the one-shot ollama-pull Job (pins llama3.2:3b, nomic-embed-text and the starter models). Turn off on a cluster that already has the models."
  type        = bool
  default     = true
}

variable "enable_pgvector" {
  description = "Deploy pgvector (Postgres + vector extension) for RAG."
  type        = bool
  default     = true
}

variable "enable_pgvector_netpol" {
  description = "Apply k8s/day-06-netpol-pgvector.yaml (only mcp-server and rag-worker may reach pgvector)."
  type        = bool
  default     = true
}

variable "enable_rag_worker" {
  description = "Deploy the RAG worker."
  type        = bool
  default     = true
}

variable "enable_open_webui" {
  description = "Deploy Open WebUI (themed)."
  type        = bool
  default     = true
}

variable "enable_prompt_guard" {
  description = "Deploy Prompt Guard (fail-closed classifier used by the control layer)."
  type        = bool
  default     = true
}

variable "enable_business_mcp" {
  description = "Deploy the business MCP slot: mcp-server (fo_* tools) and fo-mock."
  type        = bool
  default     = true
}

variable "enable_smoke_test_job" {
  description = "Run the one-shot mcp-test Job (in-cluster MCP smoke test)."
  type        = bool
  default     = false
}

variable "enable_control_layer" {
  description = "Deploy the Day 10 control layer."
  type        = bool
  default     = true
}

variable "enable_engineering_mcp" {
  description = "Deploy the Day 10 engineering MCP slot."
  type        = bool
  default     = true
}

variable "enable_engineering_mcp_github" {
  description = "Day 16: run the engineering MCP slot on real GitHub data (read-only) instead of the Day 10 sample. Manifests mode takes k8s/day-16-engineering-mcp-github.yaml (plus its egress NetworkPolicy); helm mode sets engineeringMcp.github.enabled. The token Secret engineering-mcp-github (key token) is created by hand, or by create_secrets with github_token; without it the pod serves the sample."
  type        = bool
  default     = false
}

variable "engineering_mcp_github_owner" {
  description = "Helm mode only: GitHub account whose repositories the engineering MCP may read. Manifests mode: edit GITHUB_OWNER in k8s/day-16-engineering-mcp-github.yaml."
  type        = string
  default     = "MCS-BG"
}

variable "engineering_mcp_github_repos" {
  description = "Helm mode only: optional comma-separated repository allowlist for the engineering MCP (\"\" = every repo the token can see). Manifests mode: edit GITHUB_REPOS in k8s/day-16-engineering-mcp-github.yaml."
  type        = string
  default     = ""
}

variable "enable_m365_mcp" {
  description = "Deploy the Day 14 productivity MCP slot (m365-mcp: Microsoft 365 via Graph, read-only). Its sign-in Secret m365-mcp-auth is created by hand after the one-time device-code sign-in; without it the tools fail closed."
  type        = bool
  default     = false
}

variable "enable_conversation_memory" {
  description = "Day 15: the control layer stores each /ask turn in the pgvector database (table control_layer_turns) and recalls the last turns of the same conversation_id. Manifests mode deploys k8s/day-16-control-layer.yaml (memory on; false patches MEMORY_ENABLED=false) and adds NetworkPolicy pgvector-allow-control-layer (when enable_pgvector_netpol is on). Needs enable_pgvector; uses the existing pgvector-auth Secret."
  type        = bool
  default     = true
}

variable "control_layer_planner" {
  description = "Day 16: how the control layer picks MCP tools. \"model\" (default) = the chat model chooses through native tool calling, validated against each tool's schema and an allowlist, with automatic fallback to the keyword planner; \"keyword\" = the Day 15 keyword planner only."
  type        = string
  default     = "model"

  validation {
    condition     = contains(["model", "keyword"], var.control_layer_planner)
    error_message = "control_layer_planner must be \"model\" or \"keyword\"."
  }
}

variable "engineering_default_repo" {
  description = "Day 16: repository the control layer passes to engineering tools when a question names none (\"\" = let the engineering MCP decide). Must be readable by the engineering MCP's GitHub token."
  type        = string
  default     = "ssi-platform"
}

variable "enable_ssi_gateway" {
  description = "Deploy the Day 11 ssi-gateway (private front door for the SSI Connector)."
  type        = bool
  default     = true
}

variable "enable_observability" {
  description = "Deploy the quiet observability lane: kube-prometheus-stack (Prometheus + Grafana), OpenTelemetry collector + node agent, Loki, Tempo."
  type        = bool
  default     = true
}

variable "enable_langfuse" {
  description = "Deploy Langfuse (LLM traces) with its prerequisites cert-manager and clickhouse-operator."
  type        = bool
  default     = true
}

variable "enable_nvidia_device_plugin" {
  description = "Install the NVIDIA device plugin Helm chart into gpu-system."
  type        = bool
  default     = true
}

variable "nvidia_device_plugin_runtime_class" {
  description = "runtimeClassName passed to the device plugin chart. \"nvidia\" on k3s; empty string to omit (AKS GPU node images)."
  type        = string
  default     = "nvidia"
}

variable "enable_tailscale_ingress" {
  description = "Home-lab only: Tailscale operator + Ingresses for Open WebUI, Grafana, Langfuse and ssi-gateway. Not part of the product story; keep false on AKS."
  type        = bool
  default     = false
}

# ---------------------------------------------------------------------------
# SSI control plane (control-layer, business MCP, engineering MCP, gateway)
# ---------------------------------------------------------------------------

variable "ssi_control_plane_mode" {
  description = "\"manifests\" = the lab pattern (k8s/day-06/08b/10/11 YAML, code in ConfigMaps). \"helm\" = charts/ssi via helm_release (built images, AKS)."
  type        = string
  default     = "manifests"

  validation {
    condition     = contains(["manifests", "helm"], var.ssi_control_plane_mode)
    error_message = "ssi_control_plane_mode must be \"manifests\" or \"helm\"."
  }
}

variable "ssi_image_tag" {
  description = "Helm mode only: tag of the repo-built SSI images (latest, or better the short commit SHA the build workflow pushes) (<image_registry>/ssi-gateway, control-layer, mcp-server, engineering-mcp, m365-mcp). Publish them first (see docs/day-13)."
  type        = string
  default     = "latest"
}

variable "gateway_load_balancer" {
  description = "Expose ssi-gateway on a private cloud load balancer. annotations are cloud specific (AKS / EKS / GKE internal LB). Manifests mode adds a Service ssi-gateway-lb; helm mode sets the chart's gateway Service."
  type = object({
    enabled     = bool
    annotations = map(string)
  })
  default = {
    enabled     = false
    annotations = {}
  }
}

variable "gateway_service_type" {
  description = "Manifests mode: type of the ssi-gateway Service. \"ClusterIP\" (cloud default; pair with gateway_load_balancer for the internal LB) or \"NodePort\" (home lab: IDEs on the LAN reach the lab host directly, as in k8s/day-11-ssi-gateway.yaml)."
  type        = string
  default     = "ClusterIP"

  validation {
    condition     = contains(["ClusterIP", "NodePort"], var.gateway_service_type)
    error_message = "gateway_service_type must be \"ClusterIP\" or \"NodePort\"."
  }
}

variable "gateway_node_port" {
  description = "NodePort for ssi-gateway when gateway_service_type = NodePort (externalTrafficPolicy Local keeps the caller IP for the NetworkPolicy)."
  type        = number
  default     = 30808

  validation {
    condition     = var.gateway_node_port >= 30000 && var.gateway_node_port <= 32767
    error_message = "gateway_node_port must be in the NodePort range 30000-32767."
  }
}

variable "gateway_lan_cidr" {
  description = "Home LAN range allowed through the ssi-gateway NetworkPolicy to the NodePort (lab: 192.0.2.0/24). Empty = none (cloud)."
  type        = string
  default     = ""
}

variable "gateway_allowed_cidrs" {
  description = "Extra source CIDRs allowed through the ssi-gateway NetworkPolicy (for example the VNet range behind the internal LB / Private Link)."
  type        = list(string)
  default     = []
}

variable "private_endpoint_hostname" {
  description = "Helm mode only: private hostname shown in the chart NOTES (Private Link / internal DNS)."
  type        = string
  default     = ""
}

# ---------------------------------------------------------------------------
# Model slot
# ---------------------------------------------------------------------------

variable "model_backend" {
  description = "In-cluster model server: \"ollama\" (lab default, llama3.2:3b) or \"vllm\" (OpenAI-compatible server for large open-weight models on a GPU pool, e.g. Beam)."
  type        = string
  default     = "ollama"

  validation {
    condition     = contains(["ollama", "vllm"], var.model_backend)
    error_message = "model_backend must be \"ollama\" or \"vllm\"."
  }
}

variable "model_name" {
  description = "Chat model for the control layer (Ollama tag or Azure OpenAI deployment name)."
  type        = string
  default     = "llama3.2:3b"
}

variable "azure_openai_endpoint" {
  description = "Optional external model endpoint (Azure OpenAI), helm mode only. Empty = use the in-cluster model_backend."
  type        = string
  default     = ""
}

variable "image_registry" {
  description = "Registry/prefix for the images this repo builds (mcp-server, rag-worker, prompt-guard, and the charts/ssi images). Upstream public images (Ollama, pgvector, Open WebUI, python) are not affected."
  type        = string
  default     = "ghcr.io/mcs-bg"
}

variable "image_overrides" {
  description = "Optional image pins for the raw manifests: map of the image ref written in k8s/*.yaml to the ref to deploy (for example a tag@sha256 digest). Empty = images exactly as in the manifests."
  type        = map(string)
  default     = {}
}

# ---------------------------------------------------------------------------
# vLLM (model_backend = "vllm")
# ---------------------------------------------------------------------------

variable "vllm_image" {
  description = "Official vLLM OpenAI-compatible server image, pinned."
  type        = string
  default     = "vllm/vllm-openai:v0.31.0"
}

variable "vllm_model_id" {
  description = "Hugging Face model id (or local path under /models) served by vLLM."
  type        = string
  default     = "meta-llama/Llama-3.2-3B-Instruct"
}

variable "vllm_served_model_name" {
  description = "Model name exposed on the OpenAI API (and used by the control layer). Empty = vllm_model_id."
  type        = string
  default     = ""
}

variable "vllm_tensor_parallel_size" {
  description = "Tensor parallel size (normally = GPUs per node)."
  type        = number
  default     = 1
}

variable "vllm_enable_expert_parallel" {
  description = "Add --enable-expert-parallel (mixture-of-experts models)."
  type        = bool
  default     = false
}

variable "vllm_gpu_count" {
  description = "nvidia.com/gpu requested by the vLLM pod."
  type        = number
  default     = 1
}

variable "vllm_quantization" {
  description = "Weight quantization: fp8, awq or none."
  type        = string
  default     = "none"

  validation {
    condition     = contains(["fp8", "awq", "none"], var.vllm_quantization)
    error_message = "vllm_quantization must be fp8, awq or none."
  }
}

variable "vllm_max_model_len" {
  description = "Maximum context length served (bounds the KV cache)."
  type        = number
  default     = 32768
}

variable "vllm_extra_args" {
  description = "Extra vLLM CLI arguments."
  type        = list(string)
  default     = []
}

variable "vllm_weights_size" {
  description = "Size of the weights volume (PVC)."
  type        = string
  default     = "100Gi"
}

variable "vllm_weights_host_path" {
  description = "Optional hostPath for weights (bare-metal GPU node with local NVMe). Empty = dynamic PVC from storage_class_name."
  type        = string
  default     = ""
}

variable "vllm_shm_size" {
  description = "Shared memory (/dev/shm) for tensor-parallel workers."
  type        = string
  default     = "16Gi"
}

variable "vllm_cpu_request" {
  description = "CPU request for the vLLM pod."
  type        = string
  default     = "8"
}

variable "vllm_memory_request" {
  description = "Memory request for the vLLM pod."
  type        = string
  default     = "64Gi"
}

variable "vllm_memory_limit" {
  description = "Memory limit for the vLLM pod."
  type        = string
  default     = "128Gi"
}

variable "vllm_runtime_class_name" {
  description = "runtimeClassName for vLLM (\"nvidia\" on k3s; empty on managed clouds)."
  type        = string
  default     = ""
}

variable "vllm_node_selector" {
  description = "nodeSelector for vLLM (the GPU pool label)."
  type        = map(string)
  default     = {}
}

variable "vllm_tolerations" {
  description = "Tolerations for vLLM (the GPU pool taint)."
  type        = list(map(string))
  default     = []
}

variable "hf_token_secret_name" {
  description = "Secret (key: token) holding a Hugging Face token for gated weights. Shared with Prompt Guard's optional hf-token."
  type        = string
  default     = "hf-token"
}

variable "hf_token" {
  description = "Hugging Face read token for gated models (Prompt Guard download, vLLM). Creates Secret hf-token (key token) when create_secrets = true. Never commit it."
  type        = string
  default     = null
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Scheduling and storage
# ---------------------------------------------------------------------------

variable "ollama_gpu" {
  description = "Request one NVIDIA GPU for Ollama (as in the lab). false = CPU-only Ollama (no GPU limit, no runtimeClassName): slow, but works on any node."
  type        = bool
  default     = true
}

variable "ollama_runtime_class_name" {
  description = "runtimeClassName for the Ollama pod. \"nvidia\" matches the lab manifest; empty string removes it (AKS GPU pools)."
  type        = string
  default     = "nvidia"
}

variable "ollama_node_selector" {
  description = "Optional nodeSelector for Ollama (for example { sku = \"gpu\" } on an AKS GPU pool)."
  type        = map(string)
  default     = {}
}

variable "ollama_tolerations" {
  description = "Optional tolerations for Ollama (for example the sku=gpu:NoSchedule taint)."
  type        = list(map(string))
  default     = []
}

variable "use_host_path_volumes" {
  description = "Lab only: keep the static hostPath PVs for Ollama models and RAG docs (external drive on the lab host). false = dynamic PVCs from storage_class_name."
  type        = bool
  default     = true
}

variable "storage_class_name" {
  description = "StorageClass for the Ollama and RAG PVCs when use_host_path_volumes = false. null = cluster default."
  type        = string
  default     = null
}

variable "ollama_models_volume_size" {
  description = "Size of the Ollama models PVC when use_host_path_volumes = false."
  type        = string
  default     = "50Gi"
}

# ---------------------------------------------------------------------------
# Observability overrides (values files stay the source of truth)
# ---------------------------------------------------------------------------

variable "langfuse_nextauth_url" {
  description = "Public URL Langfuse redirects to after login (langfuse.nextauth.url)."
  type        = string
  default     = "http://localhost:3002"
}

variable "langfuse_init_project_id" {
  description = "Langfuse headless-init project ID/name. The values file says si-lab; a lab initialised before the rename may still use the old ID."
  type        = string
  default     = "si-lab"
}

# ---------------------------------------------------------------------------
# Secrets. Values are never written to files: pass them with TF_VAR_* or a
# secret manager. With create_secrets = false the module only references the
# Secrets by name, and they must already exist in the cluster.
# ---------------------------------------------------------------------------

variable "create_secrets" {
  description = "Create the app Secrets from the sensitive variables below. false = reference existing Secrets by name (lab default)."
  type        = bool
  default     = false
}

variable "pgvector_password" {
  description = "pgvector-auth / POSTGRES_PASSWORD."
  type        = string
  default     = null
  sensitive   = true
}

variable "webui_secret_key" {
  description = "open-webui-secret / WEBUI_SECRET_KEY."
  type        = string
  default     = null
  sensitive   = true
}

variable "ssi_gateway_token" {
  description = "ssi-gateway-auth / token (Bearer token for the SSI Connector)."
  type        = string
  default     = null
  sensitive   = true
}

variable "github_token" {
  description = "Fine-grained, read-only GitHub token for the engineering MCP (Secret engineering-mcp-github). Only used with create_secrets = true and enable_engineering_mcp_github = true. Lands in Terraform state."
  type        = string
  default     = null
  sensitive   = true
}

variable "grafana_admin_password" {
  description = "grafana-admin / admin-password (user is admin)."
  type        = string
  default     = null
  sensitive   = true
}

variable "langfuse_init_public_key" {
  description = "langfuse-init / public-key (also used to build langfuse-otlp-auth)."
  type        = string
  default     = null
  sensitive   = true
}

variable "langfuse_init_secret_key" {
  description = "langfuse-init / secret-key (also used to build langfuse-otlp-auth)."
  type        = string
  default     = null
  sensitive   = true
}

variable "langfuse_admin_email" {
  description = "langfuse-init / user-email."
  type        = string
  default     = null
  sensitive   = true
}

variable "langfuse_admin_password" {
  description = "langfuse-init / user-password."
  type        = string
  default     = null
  sensitive   = true
}

variable "tailscale_oauth_client_id" {
  description = "Tailscale operator OAuth client ID (home lab only). Used on first install; later changes are ignored."
  type        = string
  default     = null
  sensitive   = true
}

variable "tailscale_oauth_client_secret" {
  description = "Tailscale operator OAuth client secret (home lab only). Used on first install; later changes are ignored."
  type        = string
  default     = null
  sensitive   = true
}

# ---------------------------------------------------------------------------
# Apply behaviour
# ---------------------------------------------------------------------------

variable "wait_for_rollout" {
  description = "Wait for Deployments/StatefulSets to roll out on apply."
  type        = bool
  default     = true
}

variable "helm_timeout" {
  description = "Seconds to wait for each Helm release."
  type        = number
  default     = 1200
}
