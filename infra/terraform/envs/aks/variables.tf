# Cluster inputs (Day 12 module). App inputs are in apps-variables.tf.

variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "name_prefix" {
  description = "Short lowercase alphanumeric prefix for resource names."
  type        = string
  default     = "ssi"
}

variable "kubernetes_version" {
  description = "AKS Kubernetes version. Set explicitly for real runs."
  type        = string
  default     = "1.31.2"
}

variable "system_node_vm_size" {
  description = "VM size for the system node pool."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "system_node_count" {
  description = "Node count for the system node pool."
  type        = number
  default     = 1
}

variable "enable_gpu_pool" {
  description = "Add the GPU pool (sku=gpu label + sku=gpu:NoSchedule taint) for the model server. OFF by default: 8xH100 nodes need quota and are expensive."
  type        = bool
  default     = false
}

variable "gpu_pool_vm_size" {
  description = "GPU VM size. Default 8x H100 80GB (ND H100 v5). Needs NDv5 quota in the region."
  type        = string
  default     = "Standard_ND96isr_H100_v5"
}

variable "gpu_pool_node_count" {
  description = "Number of GPU nodes (one vLLM replica per node)."
  type        = number
  default     = 1
}

variable "gpus_per_node" {
  description = "GPUs per GPU node (8 for Standard_ND96isr_H100_v5)."
  type        = number
  default     = 8
}

variable "observability_pool_vm_size" {
  description = "VM size for the observability pool (enable_observability = true)."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "enable_private_dns" {
  description = "Create the private DNS zone placeholder for the Private Link path."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default = {
    project = "ssi"
    lab     = "day-13"
  }
}
