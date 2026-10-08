output "managed_manifests" {
  description = "Raw-manifest objects managed by this module (namespace/Kind/name)."
  value       = sort(concat(keys(local.namespace_docs), keys(local.object_docs)))
}

output "helm_releases" {
  description = "Helm releases managed by this module."
  value = compact([
    var.enable_nvidia_device_plugin ? "gpu-system/nvdp" : "",
    var.enable_observability ? "monitoring/kps" : "",
    var.enable_observability ? "monitoring/otel-collector" : "",
    var.enable_observability ? "monitoring-host/otel-agent" : "",
    var.enable_observability ? "monitoring/loki" : "",
    var.enable_observability ? "monitoring/tempo" : "",
    var.enable_langfuse ? "cert-manager/cert-manager" : "",
    var.enable_langfuse ? "clickhouse-operator/clickhouse-operator" : "",
    var.enable_langfuse ? "langfuse/langfuse" : "",
    var.enable_tailscale_ingress ? "tailscale/tailscale-operator" : "",
    local.helm_ssi ? "si-lab/ssi" : "",
  ])
}

output "required_secrets" {
  description = "Secrets (namespace/name) the stack expects. Created by the module only when create_secrets = true."
  value       = local.required_secret_names
}

output "chart_versions" {
  description = "Pinned Helm chart versions."
  value       = { for k, v in local.charts : k => "${v.chart} ${v.version}" }
}
