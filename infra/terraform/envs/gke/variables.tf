# Cluster inputs. App inputs are in apps-variables.tf.

variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "region" {
  description = "GCP region."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "Zone for the zonal cluster and node pools (GPU capacity is zonal)."
  type        = string
  default     = "us-central1-a"
}

variable "name" {
  description = "Name prefix for the network and cluster."
  type        = string
  default     = "ssi"
}

variable "subnet_cidr" {
  description = "Primary subnet range (nodes)."
  type        = string
  default     = "10.50.0.0/20"
}

variable "pods_cidr" {
  description = "Secondary range for pods."
  type        = string
  default     = "10.52.0.0/14"
}

variable "services_cidr" {
  description = "Secondary range for services."
  type        = string
  default     = "10.56.0.0/20"
}

variable "node_machine_type" {
  description = "Machine type for the default node pool."
  type        = string
  default     = "e2-standard-8"
}

variable "node_count" {
  description = "Nodes in the default pool."
  type        = number
  default     = 2
}

variable "enable_gpu_pool" {
  description = "Add the GPU node pool (label sku=gpu, taint sku=gpu:NoSchedule) for the model server. OFF by default: needs H100 quota and is expensive."
  type        = bool
  default     = false
}

variable "gpu_machine_type" {
  description = "GPU machine type. Default a3-highgpu-8g = 8x H100 80GB."
  type        = string
  default     = "a3-highgpu-8g"
}

variable "gpu_accelerator_type" {
  description = "Accelerator attached to the GPU machine type."
  type        = string
  default     = "nvidia-h100-80gb"
}

variable "gpu_node_count" {
  description = "GPU nodes (one vLLM replica per node)."
  type        = number
  default     = 1
}

variable "gpus_per_node" {
  description = "GPUs per GPU node (8 for a3-highgpu-8g)."
  type        = number
  default     = 8
}

variable "observability_machine_type" {
  description = "Machine type for the observability pool (enable_observability = true)."
  type        = string
  default     = "e2-standard-4"
}

variable "deletion_protection" {
  description = "GKE deletion protection. Keep true outside throwaway demos."
  type        = bool
  default     = true
}
