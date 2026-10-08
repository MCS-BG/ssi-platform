variable "location" {
  description = "Azure region for all resources."
  type        = string
  default     = "eastus"
}

variable "name_prefix" {
  description = "Short lowercase alphanumeric prefix for resource names."
  type        = string
  default     = "ssi"

  validation {
    condition     = can(regex("^[a-z0-9]{3,12}$", var.name_prefix))
    error_message = "name_prefix must be 3-12 lowercase letters or digits."
  }
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

variable "enable_user_pool" {
  description = "Create an optional user node pool (CPU or GPU)."
  type        = bool
  default     = false
}

variable "user_pool_vm_size" {
  description = "VM size for the optional user pool. Use an NC/ND SKU for a GPU model slot."
  type        = string
  default     = "Standard_D4s_v5"
}

variable "user_pool_node_count" {
  description = "Node count for the optional user pool."
  type        = number
  default     = 1
}

variable "user_pool_gpu" {
  description = "Mark the user pool as GPU: adds a sku=gpu label and NoSchedule taint so only model workloads land there."
  type        = bool
  default     = false
}

variable "enable_observability_pool" {
  description = "Day 13: add a node pool labelled/tainted ailab/role=observability for Grafana/Langfuse."
  type        = bool
  default     = false
}

variable "observability_pool_vm_size" {
  description = "VM size for the optional observability pool."
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
    lab     = "day-12"
  }
}
