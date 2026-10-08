output "cluster_name" {
  description = "GKE cluster name (gcloud container clusters get-credentials ...)."
  value       = google_container_cluster.this.name
}

output "location" {
  description = "Cluster zone."
  value       = google_container_cluster.this.location
}

output "network" {
  description = "VPC network name."
  value       = google_compute_network.this.name
}

output "managed_manifests" {
  description = "Raw-manifest objects deployed by the apps module."
  value       = try(module.apps[0].managed_manifests, [])
}

output "helm_releases" {
  description = "Helm releases deployed by the apps module."
  value       = try(module.apps[0].helm_releases, [])
}
