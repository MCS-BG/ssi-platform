variable "kubeconfig_path" {
  description = "Kubeconfig for the lab cluster (reached through the SSH tunnel to the lab host)."
  type        = string
  default     = "~/.kube/config"
}

variable "kube_context" {
  description = "Kubeconfig context. null = current context."
  type        = string
  default     = null
}

variable "tailnet_domain" {
  description = "Tailnet DNS suffix, e.g. example-tailnet.ts.net. Builds the Langfuse login URL. Empty = localhost port-forward URL."
  type        = string
  default     = ""
}

variable "adopt_existing" {
  description = "true = adopt the running lab (imports.tf). false = fresh cluster: create everything, import nothing."
  type        = bool
  default     = true
}

variable "pin_image_digests" {
  description = "Rewrite raw-manifest images to the digests recorded from the live lab (pins.tf). false keeps the live tags so the adopt plan is a no-op; true for a from-scratch rebuild."
  type        = bool
  default     = false
}

# Secrets: only needed when create_secrets = true (fresh cluster). Put values
# in secrets.auto.tfvars (git-ignored), never in a committed file.

variable "create_secrets" {
  description = "false on the existing lab (Secrets already exist). true on a rebuilt cluster."
  type        = bool
  default     = false
}

variable "pgvector_password" {
  type      = string
  default   = null
  sensitive = true
}

variable "webui_secret_key" {
  type      = string
  default   = null
  sensitive = true
}

variable "ssi_gateway_token" {
  type      = string
  default   = null
  sensitive = true
}

variable "grafana_admin_password" {
  type      = string
  default   = null
  sensitive = true
}

variable "langfuse_init_public_key" {
  type      = string
  default   = null
  sensitive = true
}

variable "langfuse_init_secret_key" {
  type      = string
  default   = null
  sensitive = true
}

variable "langfuse_admin_email" {
  type      = string
  default   = null
  sensitive = true
}

variable "langfuse_admin_password" {
  type      = string
  default   = null
  sensitive = true
}

variable "tailscale_oauth_client_id" {
  type      = string
  default   = null
  sensitive = true
}

variable "tailscale_oauth_client_secret" {
  type      = string
  default   = null
  sensitive = true
}

variable "hf_token" {
  description = "Hugging Face read token (Prompt Guard model is gated). Only used with create_secrets = true."
  type        = string
  default     = null
  sensitive   = true
}
