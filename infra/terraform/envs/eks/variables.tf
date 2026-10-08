# Cluster inputs. App inputs are in apps-variables.tf.

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "name" {
  description = "Name prefix for the VPC and cluster."
  type        = string
  default     = "ssi"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version."
  type        = string
  default     = "1.34"
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.40.0.0/16"
}

variable "node_instance_type" {
  description = "Instance type for the default (system + apps) node group."
  type        = string
  default     = "m6i.2xlarge"
}

variable "node_count" {
  description = "Nodes in the default node group."
  type        = number
  default     = 2
}

variable "enable_gpu_pool" {
  description = "Add the GPU node group (label sku=gpu, taint sku=gpu:NoSchedule) for the model server. OFF by default: needs P-instance quota and is expensive."
  type        = bool
  default     = false
}

variable "gpu_instance_type" {
  description = "GPU instance type. Default p5.48xlarge = 8x H100 80GB."
  type        = string
  default     = "p5.48xlarge"
}

variable "gpu_node_count" {
  description = "GPU nodes (one vLLM replica per node)."
  type        = number
  default     = 1
}

variable "gpus_per_node" {
  description = "GPUs per GPU node (8 for p5.48xlarge)."
  type        = number
  default     = 8
}

variable "observability_instance_type" {
  description = "Instance type for the observability node group (enable_observability = true)."
  type        = string
  default     = "m6i.xlarge"
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "ssi"
    lab     = "day-13"
  }
}
