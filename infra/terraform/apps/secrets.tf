# App Secrets. Default (create_secrets = false): the module only references
# these names; create them out of band (kubectl create secret ... as in the Day
# docs) or with a secret manager. With create_secrets = true the values come
# from sensitive variables (TF_VAR_* or an untracked secrets.auto.tfvars) and
# are stored in Terraform state, so keep state local and git-ignored or in
# customer-owned encrypted remote state.

locals {
  otlp_basic = var.langfuse_init_public_key == null || var.langfuse_init_secret_key == null ? null : "Basic ${base64encode("${var.langfuse_init_public_key}:${var.langfuse_init_secret_key}")}"

  app_secrets = {
    "si-lab/pgvector-auth" = {
      on   = var.enable_pgvector
      data = { POSTGRES_PASSWORD = var.pgvector_password }
    }
    "si-lab/open-webui-secret" = {
      on   = var.enable_open_webui
      data = { WEBUI_SECRET_KEY = var.webui_secret_key }
    }
    "si-lab/ssi-gateway-auth" = {
      on   = var.enable_ssi_gateway
      data = { token = var.ssi_gateway_token }
    }
    "si-lab/engineering-mcp-github" = {
      on   = var.enable_engineering_mcp && var.enable_engineering_mcp_github && nonsensitive(var.github_token != null)
      data = { token = var.github_token }
    }
    "si-lab/hf-token" = {
      on   = nonsensitive(var.hf_token != null)
      data = { token = var.hf_token }
    }
    "monitoring/grafana-admin" = {
      on   = var.enable_observability
      data = { "admin-user" = "admin", "admin-password" = var.grafana_admin_password }
    }
    "langfuse/langfuse-init" = {
      on = var.enable_langfuse
      data = {
        "public-key"    = var.langfuse_init_public_key
        "secret-key"    = var.langfuse_init_secret_key
        "user-email"    = var.langfuse_admin_email
        "user-password" = var.langfuse_admin_password
      }
    }
    "monitoring/langfuse-otlp-auth" = {
      on   = var.enable_observability && var.enable_langfuse
      data = { authorization = local.otlp_basic }
    }
  }

  # Secret names the stack expects (useful for a pre-flight check).
  required_secret_names = sort([for k, v in local.app_secrets : k if v.on])
}

resource "kubernetes_secret_v1" "app" {
  for_each = var.create_secrets ? { for k, v in local.app_secrets : k => v if v.on } : {}


  metadata {
    namespace = split("/", each.key)[0]
    name      = split("/", each.key)[1]
  }

  data = each.value.data

  lifecycle {
    precondition {
      condition     = alltrue([for v in values(each.value.data) : v != null && v != ""])
      error_message = "create_secrets = true but a value for ${each.key} is missing. Set it in secrets.auto.tfvars or TF_VAR_*."
    }
  }

  depends_on = [kubectl_manifest.namespace]
}
