# Helm releases: same chart, version and values files the lab was installed
# with (docs/day-02, day-07, day-08b). Values files in k8s/ stay the source of
# truth; only values that were passed with --set on the command line are
# expressed here.

locals {
  values_dir = "${local.repo_root}/k8s"

  # Chart pins, read from `helm list -A` on the live lab.
  charts = {
    nvdp = {
      repository = "https://nvidia.github.io/k8s-device-plugin"
      chart      = "nvidia-device-plugin"
      version    = "0.20.1"
    }
    kps = {
      repository = "https://prometheus-community.github.io/helm-charts"
      chart      = "kube-prometheus-stack"
      version    = "91.5.3"
    }
    otel = {
      repository = "https://open-telemetry.github.io/opentelemetry-helm-charts"
      chart      = "opentelemetry-collector"
      version    = "0.173.1"
    }
    loki = {
      repository = "https://grafana-community.github.io/helm-charts"
      chart      = "loki"
      version    = "18.13.5"
    }
    tempo = {
      repository = "https://grafana-community.github.io/helm-charts"
      chart      = "tempo"
      version    = "3.0.0"
    }
    cert_manager = {
      repository = "oci://quay.io/jetstack/charts"
      chart      = "cert-manager"
      version    = "v1.20.2"
    }
    clickhouse_operator = {
      repository = "oci://ghcr.io/clickhouse"
      chart      = "clickhouse-operator-helm"
      version    = "0.0.5"
    }
    langfuse = {
      repository = "https://langfuse.github.io/langfuse-k8s"
      chart      = "langfuse"
      version    = "2.1.2"
    }
    tailscale = {
      repository = "https://pkgs.tailscale.com/helmcharts"
      chart      = "tailscale-operator"
      version    = "1.102.4"
    }
  }

  # Langfuse: the two values passed outside the values file.
  langfuse_values = yamldecode(file("${local.values_dir}/day-07-langfuse-values.yaml"))
  langfuse_override = {
    langfuse = {
      nextauth = { url = var.langfuse_nextauth_url }
      additionalEnv = [
        for e in local.langfuse_values.langfuse.additionalEnv :
        merge(e, { for k, v in { value = var.langfuse_init_project_id } : k => v if contains(["LANGFUSE_INIT_PROJECT_ID", "LANGFUSE_INIT_PROJECT_NAME"], e.name) })
      ]
    }
  }
}

# ---- GPU ------------------------------------------------------------------

resource "helm_release" "nvdp" {
  count = var.enable_nvidia_device_plugin ? 1 : 0

  name       = "nvdp"
  namespace  = "gpu-system"
  repository = local.charts.nvdp.repository
  chart      = local.charts.nvdp.chart
  version    = local.charts.nvdp.version
  timeout    = var.helm_timeout

  set = var.nvidia_device_plugin_runtime_class == "" ? [] : [
    { name = "runtimeClassName", value = var.nvidia_device_plugin_runtime_class },
  ]

  depends_on = [kubectl_manifest.namespace]
}

# ---- Observability (quiet lane) -------------------------------------------

resource "helm_release" "kps" {
  count = var.enable_observability ? 1 : 0

  name       = "kps"
  namespace  = "monitoring"
  repository = local.charts.kps.repository
  chart      = local.charts.kps.chart
  version    = local.charts.kps.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-kube-prometheus-stack-values.yaml")]

  depends_on = [kubectl_manifest.namespace, kubernetes_secret_v1.app]
}

resource "helm_release" "otel_collector" {
  count = var.enable_observability ? 1 : 0

  name       = "otel-collector"
  namespace  = "monitoring"
  repository = local.charts.otel.repository
  chart      = local.charts.otel.chart
  version    = local.charts.otel.version
  timeout    = var.helm_timeout
  # Final stage C pipeline (traces -> Tempo + Langfuse, logs -> Loki).
  values = [
    file("${local.values_dir}/day-07-otel-collector-values.yaml"),
    file("${local.values_dir}/day-07-otel-collector-stage-c.yaml"),
  ]

  depends_on = [kubectl_manifest.namespace, kubernetes_secret_v1.app, helm_release.kps]
}

resource "helm_release" "otel_agent" {
  count = var.enable_observability ? 1 : 0

  name       = "otel-agent"
  namespace  = "monitoring-host"
  repository = local.charts.otel.repository
  chart      = local.charts.otel.chart
  version    = local.charts.otel.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-otel-agent-values.yaml")]

  depends_on = [kubectl_manifest.namespace, helm_release.otel_collector]
}

resource "helm_release" "loki" {
  count = var.enable_observability ? 1 : 0

  name       = "loki"
  namespace  = "monitoring"
  repository = local.charts.loki.repository
  chart      = local.charts.loki.chart
  version    = local.charts.loki.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-loki-values.yaml")]

  depends_on = [kubectl_manifest.namespace]
}

resource "helm_release" "tempo" {
  count = var.enable_observability ? 1 : 0

  name       = "tempo"
  namespace  = "monitoring"
  repository = local.charts.tempo.repository
  chart      = local.charts.tempo.chart
  version    = local.charts.tempo.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-tempo-values.yaml")]

  depends_on = [kubectl_manifest.namespace]
}

# ---- Langfuse and its prerequisites ----------------------------------------

resource "helm_release" "cert_manager" {
  count = var.enable_langfuse ? 1 : 0

  name       = "cert-manager"
  namespace  = "cert-manager"
  repository = local.charts.cert_manager.repository
  chart      = local.charts.cert_manager.chart
  version    = local.charts.cert_manager.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-cert-manager-values.yaml")]

  depends_on = [kubectl_manifest.namespace]
}

resource "helm_release" "clickhouse_operator" {
  count = var.enable_langfuse ? 1 : 0

  name       = "clickhouse-operator"
  namespace  = "clickhouse-operator"
  repository = local.charts.clickhouse_operator.repository
  chart      = local.charts.clickhouse_operator.chart
  version    = local.charts.clickhouse_operator.version
  timeout    = var.helm_timeout
  values     = [file("${local.values_dir}/day-07-clickhouse-operator-values.yaml")]

  depends_on = [kubectl_manifest.namespace, helm_release.cert_manager]
}

resource "helm_release" "langfuse" {
  count = var.enable_langfuse ? 1 : 0

  name       = "langfuse"
  namespace  = "langfuse"
  repository = local.charts.langfuse.repository
  chart      = local.charts.langfuse.chart
  version    = local.charts.langfuse.version
  timeout    = var.helm_timeout
  values = [
    file("${local.values_dir}/day-07-langfuse-values.yaml"),
    yamlencode(local.langfuse_override),
  ]

  depends_on = [kubectl_manifest.namespace, kubernetes_secret_v1.app, helm_release.clickhouse_operator]
}

# ---- Home lab only: Tailscale operator ---------------------------------------

resource "helm_release" "tailscale_operator" {
  count = var.enable_tailscale_ingress ? 1 : 0

  name       = "tailscale-operator"
  namespace  = "tailscale"
  repository = local.charts.tailscale.repository
  chart      = local.charts.tailscale.chart
  version    = local.charts.tailscale.version
  timeout    = var.helm_timeout

  # OAuth client: bootstrap-only. Supplied on first install, then ignored so a
  # plan never needs the credential again (rotate it in the Tailscale admin
  # console + the operator-oauth Secret).
  set_sensitive = var.tailscale_oauth_client_id == null ? [] : [
    { name = "oauth.clientId", value = var.tailscale_oauth_client_id, type = "string" },
    { name = "oauth.clientSecret", value = var.tailscale_oauth_client_secret, type = "string" },
  ]

  # Adopted release (lab): the OAuth values live only in the release. Without
  # the credentials here, reuse them on upgrade instead of dropping them (which
  # would delete the operator-oauth Secret).
  reuse_values = var.tailscale_oauth_client_id == null

  lifecycle {
    ignore_changes = [set_sensitive]
  }

  depends_on = [kubectl_manifest.namespace]
}
