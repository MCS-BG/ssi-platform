output "managed_manifests" {
  description = "Objects managed from k8s/*.yaml (<namespace>/<Kind>/<name>)."
  value       = module.apps.managed_manifests
}

output "helm_releases" {
  description = "Helm releases managed by OpenTofu."
  value       = module.apps.helm_releases
}

output "chart_versions" {
  description = "Pinned Helm chart versions."
  value       = module.apps.chart_versions
}

output "required_secrets" {
  description = "Secrets the stack expects (created only when create_secrets = true)."
  value       = module.apps.required_secrets
}
