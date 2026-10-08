# Adopt the live lab instead of recreating it. Every object below was
# checked against the cluster on 2026-10-06 (kubectl get ... -n si-lab, helm
# list -A). Import blocks need OpenTofu or Terraform >= 1.7 (for_each).
#
# After the first `tofu apply` has written these into state, the blocks are
# no-ops and can stay or be deleted. On a fresh, empty cluster (full rebuild)
# set adopt_existing = false: there is nothing to import, everything is created.

locals {
  api_version = {
    Namespace             = "v1"
    PersistentVolume      = "v1"
    PersistentVolumeClaim = "v1"
    Service               = "v1"
    ConfigMap             = "v1"
    Deployment            = "apps/v1"
    StatefulSet           = "apps/v1"
    NetworkPolicy         = "networking.k8s.io/v1"
    Ingress               = "networking.k8s.io/v1"
  }

  # Namespaces (cluster-scoped), adopted into module.apps.kubectl_manifest.namespace.
  adopt_namespaces = [
    "_cluster/Namespace/si-lab",
    "_cluster/Namespace/gpu-system",
    "_cluster/Namespace/monitoring",
    "_cluster/Namespace/monitoring-host",
    "_cluster/Namespace/langfuse",
    "_cluster/Namespace/cert-manager",
    "_cluster/Namespace/clickhouse-operator",
    "_cluster/Namespace/tailscale",
  ]

  # Everything else, adopted into module.apps.kubectl_manifest.this.
  # Key format: "<namespace or _cluster>/<Kind>/<name>".
  adopt_objects = [
    "_cluster/PersistentVolume/ollama-models-pv",
    "si-lab/PersistentVolumeClaim/ollama-models",
    "si-lab/Deployment/ollama",
    "si-lab/Service/ollama",
    "si-lab/ConfigMap/ollama-models",
    "si-lab/ConfigMap/ollama-pull-script",
    "si-lab/Service/pgvector",
    "si-lab/StatefulSet/pgvector",
    "_cluster/PersistentVolume/rag-docs-pv",
    "si-lab/PersistentVolumeClaim/rag-docs",
    "si-lab/Deployment/rag-worker",
    "si-lab/PersistentVolumeClaim/open-webui-data",
    "si-lab/Service/open-webui",
    "si-lab/ConfigMap/open-webui-theme",
    "si-lab/Deployment/open-webui",
    "si-lab/PersistentVolumeClaim/prompt-guard-cache",
    "si-lab/Service/prompt-guard",
    "si-lab/NetworkPolicy/prompt-guard-allow-si-lab",
    "si-lab/Deployment/prompt-guard",
    "si-lab/ConfigMap/fo-mock-code",
    "si-lab/Deployment/fo-mock",
    "si-lab/Service/fo-mock",
    "si-lab/NetworkPolicy/fo-mock-allow-mcp-server",
    "si-lab/NetworkPolicy/mcp-server-allow-si-lab",
    "si-lab/Service/mcp-server",
    "si-lab/Deployment/mcp-server",
    "si-lab/ConfigMap/mcp-test-code",
    "si-lab/ConfigMap/control-layer-code",
    "si-lab/Deployment/control-layer",
    "si-lab/Service/control-layer",
    "si-lab/NetworkPolicy/control-layer-allow-si-lab",
    "si-lab/ConfigMap/engineering-mcp-code",
    "si-lab/Deployment/engineering-mcp",
    "si-lab/Service/engineering-mcp",
    "si-lab/NetworkPolicy/engineering-mcp-allow-si-lab",
    "si-lab/ConfigMap/ssi-gateway-code",
    "si-lab/Deployment/ssi-gateway",
    "si-lab/Service/ssi-gateway",
    "si-lab/NetworkPolicy/ssi-gateway-allow",
    "si-lab/Ingress/ssi-gateway",
    "monitoring/NetworkPolicy/otel-collector-ingress",
    "monitoring/NetworkPolicy/loki-ingress",
    "monitoring/NetworkPolicy/tempo-ingress",
    "langfuse/NetworkPolicy/langfuse-same-namespace",
    "langfuse/NetworkPolicy/langfuse-web-ingress",
    "si-lab/Ingress/open-webui",
    "monitoring/Ingress/grafana",
    "langfuse/Ingress/langfuse",
    "langfuse/NetworkPolicy/langfuse-web-from-tailscale",
  ]

  # alekc/kubectl import ID: apiVersion//Kind//name[//namespace]
  import_id = {
    for k in concat(local.adopt_namespaces, local.adopt_objects) : k => join("//", compact([
      local.api_version[split("/", k)[1]],
      split("/", k)[1],
      split("/", k)[2],
      split("/", k)[0] == "_cluster" ? "" : split("/", k)[0],
    ]))
  }

  # Helm releases: import ID is <namespace>/<release>.
  adopt_helm = {
    nvdp                = "gpu-system/nvdp"
    kps                 = "monitoring/kps"
    otel_collector      = "monitoring/otel-collector"
    otel_agent          = "monitoring-host/otel-agent"
    loki                = "monitoring/loki"
    tempo               = "monitoring/tempo"
    cert_manager        = "cert-manager/cert-manager"
    clickhouse_operator = "clickhouse-operator/clickhouse-operator"
    langfuse            = "langfuse/langfuse"
    tailscale_operator  = "tailscale/tailscale-operator"
  }
}

import {
  for_each = var.adopt_existing ? toset(local.adopt_namespaces) : toset([])
  to       = module.apps.kubectl_manifest.namespace[each.key]
  id       = local.import_id[each.key]
}

import {
  for_each = var.adopt_existing ? toset(local.adopt_objects) : toset([])
  to       = module.apps.kubectl_manifest.this[each.key]
  id       = local.import_id[each.key]
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.nvdp) = 0 } : {}
  to       = module.apps.helm_release.nvdp[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.kps) = 0 } : {}
  to       = module.apps.helm_release.kps[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.otel_collector) = 0 } : {}
  to       = module.apps.helm_release.otel_collector[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.otel_agent) = 0 } : {}
  to       = module.apps.helm_release.otel_agent[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.loki) = 0 } : {}
  to       = module.apps.helm_release.loki[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.tempo) = 0 } : {}
  to       = module.apps.helm_release.tempo[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.cert_manager) = 0 } : {}
  to       = module.apps.helm_release.cert_manager[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.clickhouse_operator) = 0 } : {}
  to       = module.apps.helm_release.clickhouse_operator[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.langfuse) = 0 } : {}
  to       = module.apps.helm_release.langfuse[each.value]
  id       = each.key
}

import {
  for_each = var.adopt_existing ? { (local.adopt_helm.tailscale_operator) = 0 } : {}
  to       = module.apps.helm_release.tailscale_operator[each.value]
  id       = each.key
}
