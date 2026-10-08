output "cluster_name" {
  description = "EKS cluster name (aws eks update-kubeconfig --name ...)."
  value       = module.eks.cluster_name
}

output "region" {
  description = "AWS region."
  value       = var.region
}

output "vpc_id" {
  description = "VPC ID."
  value       = module.vpc.vpc_id
}

output "managed_manifests" {
  description = "Raw-manifest objects deployed by the apps module."
  value       = try(module.apps[0].managed_manifests, [])
}

output "helm_releases" {
  description = "Helm releases deployed by the apps module."
  value       = try(module.apps[0].helm_releases, [])
}
