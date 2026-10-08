# Shared app-layer inputs (identical in envs/aks, envs/eks and envs/gke).

variable "deploy_apps" {
  description = "Deploy the SSI stack (../../apps). false = cluster only (the Day 12 scope)."
  type        = bool
  default     = true
}

variable "ssi_control_plane_mode" {
  description = "\"manifests\" = lab manifests with code in ConfigMaps (works with no image build). \"helm\" = charts/ssi with published images (image_registry + ssi_image_tag)."
  type        = string
  default     = "manifests"
}

variable "image_registry" {
  description = "Registry/prefix for the images this repo builds. Upstream public images are untouched."
  type        = string
  default     = "ghcr.io/mcs-bg"
}

variable "ssi_image_tag" {
  description = "Helm mode only: tag of the published SSI images."
  type        = string
  default     = "latest"
}

variable "model_backend" {
  description = "\"ollama\" (Llama 3.2 3B, CPU or GPU) or \"vllm\" (large open-weight model on the GPU pool, e.g. Beam; see docs/models/beam.md)."
  type        = string
  default     = "ollama"
}

variable "model_name" {
  description = "Ollama chat model tag."
  type        = string
  default     = "llama3.2:3b"
}

variable "vllm_model_id" {
  description = "Hugging Face model id served by vLLM (model_backend = vllm)."
  type        = string
  default     = "meta-llama/Llama-3.2-3B-Instruct"
}

variable "vllm_quantization" {
  description = "fp8, awq or none."
  type        = string
  default     = "fp8"
}

variable "vllm_max_model_len" {
  description = "Maximum context served by vLLM (bounds KV-cache memory)."
  type        = number
  default     = 32768
}

variable "vllm_weights_size" {
  description = "Weights volume size (about 1.2x the checkpoint size)."
  type        = string
  default     = "1Ti"
}

variable "azure_openai_endpoint" {
  description = "Optional external model endpoint (helm mode only)."
  type        = string
  default     = ""
}

variable "enable_observability" {
  description = "Add the observability node pool and deploy Prometheus/Grafana/Loki/Tempo/Langfuse (quiet lane)."
  type        = bool
  default     = false
}

variable "gateway_internal_lb" {
  description = "Expose ssi-gateway on a private (internal) cloud load balancer."
  type        = bool
  default     = true
}

variable "gateway_allowed_cidrs" {
  description = "Private source ranges allowed to reach ssi-gateway through its NetworkPolicy (VNet/VPC ranges)."
  type        = list(string)
  default     = ["10.0.0.0/8"]
}

variable "create_secrets" {
  description = "Create the app Secrets from app_secrets. false = create them yourself before apply."
  type        = bool
  default     = true
}

variable "app_secrets" {
  description = "Secret values, set in secrets.auto.tfvars (git-ignored). Keys: pgvector_password, webui_secret_key, ssi_gateway_token, grafana_admin_password, langfuse_init_public_key, langfuse_init_secret_key, langfuse_admin_email, langfuse_admin_password, hf_token."
  type        = map(string)
  default     = {}
  sensitive   = true
}
