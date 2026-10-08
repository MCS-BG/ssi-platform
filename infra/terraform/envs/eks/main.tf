data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)

  # Internal NLB for ssi-gateway (in-tree controller annotations).
  internal_lb_annotations = {
    "service.beta.kubernetes.io/aws-load-balancer-internal" = "true"
    "service.beta.kubernetes.io/aws-load-balancer-type"     = "nlb"
  }

  gpus_per_node     = var.gpus_per_node
  gpu_node_selector = var.enable_gpu_pool ? { sku = "gpu" } : {}
  gpu_tolerations   = var.enable_gpu_pool ? [{ key = "sku", operator = "Equal", value = "gpu", effect = "NoSchedule" }] : []

  gpu_group = {
    gpu = {
      ami_type       = "AL2023_x86_64_NVIDIA"
      instance_types = [var.gpu_instance_type]
      min_size       = var.gpu_node_count
      max_size       = var.gpu_node_count
      desired_size   = var.gpu_node_count
      # Root volume for the large vLLM image; weights live on the PVC.
      block_device_mappings = {
        xvda = {
          device_name = "/dev/xvda"
          ebs         = { volume_size = 300, volume_type = "gp3", delete_on_termination = true }
        }
      }
      labels = { sku = "gpu" }
      taints = {
        gpu = { key = "sku", value = "gpu", effect = "NO_SCHEDULE" }
      }
    }
  }

  observability_group = {
    observability = {
      instance_types = [var.observability_instance_type]
      min_size       = 1
      max_size       = 1
      desired_size   = 1
      labels         = { "ailab/role" = "observability" }
      taints = {
        obs = { key = "ailab/role", value = "observability", effect = "NO_SCHEDULE" }
      }
    }
  }
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 6.0"

  name = "${var.name}-vpc"
  cidr = var.vpc_cidr
  azs  = local.azs

  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 48 + i)]

  enable_nat_gateway = true
  single_nat_gateway = true

  private_subnet_tags = { "kubernetes.io/role/internal-elb" = 1 }
  public_subnet_tags  = { "kubernetes.io/role/elb" = 1 }

  tags = var.tags
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 21.0"

  name               = "${var.name}-eks"
  kubernetes_version = var.kubernetes_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  # Private API is the enterprise default; public access only for a first run
  # from the terminal (restrict it to your IP, or use a VPN/bastion).
  endpoint_public_access                   = true
  enable_cluster_creator_admin_permissions = true

  addons = {
    coredns                = {}
    kube-proxy             = {}
    vpc-cni                = { before_compute = true }
    eks-pod-identity-agent = { before_compute = true }
    aws-ebs-csi-driver = {
      pod_identity_association = [{
        role_arn        = aws_iam_role.ebs_csi.arn
        service_account = "ebs-csi-controller-sa"
      }]
    }
  }

  eks_managed_node_groups = merge(
    {
      default = {
        instance_types = [var.node_instance_type]
        min_size       = var.node_count
        max_size       = var.node_count
        desired_size   = var.node_count
      }
    },
    var.enable_gpu_pool ? local.gpu_group : {},
    var.enable_observability ? local.observability_group : {},
  )

  tags = var.tags
}

# EBS CSI driver identity (Pod Identity) so PVCs get gp3 volumes.
resource "aws_iam_role" "ebs_csi" {
  name = "${var.name}-ebs-csi"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "pods.eks.amazonaws.com" }
      Action    = ["sts:AssumeRole", "sts:TagSession"]
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ebs_csi" {
  role       = aws_iam_role.ebs_csi.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonEBSCSIDriverPolicy"
}

resource "kubernetes_storage_class_v1" "gp3" {
  count = var.deploy_apps ? 1 : 0

  metadata {
    name        = "gp3"
    annotations = { "storageclass.kubernetes.io/is-default-class" = "true" }
  }

  storage_provisioner    = "ebs.csi.aws.com"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = true
  parameters             = { type = "gp3" }

  depends_on = [module.eks]
}

module "apps" {
  source = "../../apps"
  count  = var.deploy_apps ? 1 : 0

  # The EKS NVIDIA AMI ships the driver + container toolkit; the device plugin
  # still has to be installed. Without a GPU node group Ollama runs on CPU.
  enable_nvidia_device_plugin        = var.enable_gpu_pool
  nvidia_device_plugin_runtime_class = ""
  ollama_gpu                         = var.enable_gpu_pool
  ollama_runtime_class_name          = ""
  ollama_node_selector               = local.gpu_node_selector
  ollama_tolerations                 = local.gpu_tolerations
  storage_class_name                 = "gp3"

  ssi_control_plane_mode = var.ssi_control_plane_mode
  image_registry         = var.image_registry
  ssi_image_tag          = var.ssi_image_tag
  model_backend          = var.model_backend
  model_name             = var.model_name
  azure_openai_endpoint  = var.azure_openai_endpoint

  # vLLM on the GPU pool: one replica spanning all GPUs of one node.
  vllm_model_id               = var.vllm_model_id
  vllm_quantization           = var.vllm_quantization
  vllm_max_model_len          = var.vllm_max_model_len
  vllm_weights_size           = var.vllm_weights_size
  vllm_gpu_count              = local.gpus_per_node
  vllm_tensor_parallel_size   = local.gpus_per_node
  vllm_enable_expert_parallel = true
  vllm_memory_request         = "256Gi"
  vllm_memory_limit           = "1024Gi"
  vllm_shm_size               = "64Gi"
  vllm_node_selector          = local.gpu_node_selector
  vllm_tolerations            = local.gpu_tolerations

  # Fresh cluster: run the model pull Job once, no hostPath volumes, no Tailscale.
  enable_model_pull_job    = true
  enable_tailscale_ingress = false
  use_host_path_volumes    = false

  enable_observability = var.enable_observability
  enable_langfuse      = var.enable_observability

  gateway_load_balancer = {
    enabled     = var.gateway_internal_lb
    annotations = local.internal_lb_annotations
  }
  gateway_allowed_cidrs = var.gateway_allowed_cidrs

  create_secrets           = var.create_secrets
  pgvector_password        = lookup(var.app_secrets, "pgvector_password", null)
  webui_secret_key         = lookup(var.app_secrets, "webui_secret_key", null)
  ssi_gateway_token        = lookup(var.app_secrets, "ssi_gateway_token", null)
  grafana_admin_password   = lookup(var.app_secrets, "grafana_admin_password", null)
  langfuse_init_public_key = lookup(var.app_secrets, "langfuse_init_public_key", null)
  langfuse_init_secret_key = lookup(var.app_secrets, "langfuse_init_secret_key", null)
  langfuse_admin_email     = lookup(var.app_secrets, "langfuse_admin_email", null)
  langfuse_admin_password  = lookup(var.app_secrets, "langfuse_admin_password", null)
  hf_token                 = lookup(var.app_secrets, "hf_token", null)

  depends_on = [module.eks, kubernetes_storage_class_v1.gp3]
}
