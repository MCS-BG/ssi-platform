#!/usr/bin/env python3
"""Day 7 icons for homelab_diagram.py --day 7 (run once after build_icons.py / build_icons_day06*.py).

Official project logos + the official Kubernetes kind badge (Deployment / StatefulSet / DaemonSet):
  * OpenTelemetry   Iconify logos/opentelemetry-icon        -> otel-collector (Deployment), otel-agent (DaemonSet)
  * Prometheus, Grafana, Prometheus operator, Loki, Tempo, cert-manager, ClickHouse, PostgreSQL, Redis
                    bundled with the mingrammer `diagrams` package
  * Langfuse        selfh.st icon set (Iconify selfhst/langfuse)
  * Valkey          Iconify logos/valkey-icon
  * SeaweedFS       selfh.st icon set (Iconify selfhst/seaweedfs)
  * Kubernetes      Iconify logos/kubernetes (kube-state-metrics has no logo of its own)
  * Meta            Iconify logos/meta-icon                  -> prompt-guard (Prompt Guard 2, CPU only on node gpu-node)
"""
from PIL import Image
from build_icons import ICONS, SRC, RES, fetch, svg_png, logo_with_badge

K8S = RES / "k8s"
DEP, STS, DS = K8S / "compute/deploy.png", K8S / "compute/sts.png", K8S / "compute/ds.png"

def res(p):
    return Image.open(RES / p).convert("RGBA")

def ico(slug, name):
    return svg_png(fetch(f"https://api.iconify.design/{slug}.svg?height=512", SRC / f"{name}.svg"), 400)

def main():
    otel = ico("logos/opentelemetry-icon", "opentelemetry")
    otel.save(ICONS / "otel_logo.png")
    lf = ico("selfhst/langfuse", "langfuse")
    lf.save(ICONS / "langfuse_logo.png")
    valkey = ico("logos/valkey-icon", "valkey")
    seaweed = ico("selfhst/seaweedfs", "seaweedfs")
    k8s = ico("logos/kubernetes", "kubernetes_d7")
    meta = ico("logos/meta-icon", "meta_d7")
    prom = res("onprem/monitoring/prometheus.png")
    ch = res("onprem/database/clickhouse.png")
    jobs = [
        (otel, DEP, "otelcol_deploy.png", 0.74), (otel, DS, "otelagent_ds.png", 0.74),
        (prom, DS, "nodeexporter_ds.png", 0.74), (prom, STS, "prometheus_sts.png", 0.74),
        (res("onprem/monitoring/grafana.png"), DEP, "grafana_deploy.png", 0.74),
        (res("onprem/monitoring/prometheus-operator.png"), DEP, "promop_deploy.png", 0.74),
        (k8s, DEP, "ksm_deploy.png", 0.70),
        (res("onprem/logging/loki.png"), STS, "loki_sts.png", 0.74),
        (res("onprem/tracing/tempo.png"), STS, "tempo_sts.png", 0.74),
        (lf, DEP, "langfuse_deploy.png", 0.74),
        (ch, STS, "clickhouse_sts.png", 0.74), (ch, DEP, "chop_deploy.png", 0.70),
        (res("onprem/database/postgresql.png"), STS, "lfpg_sts.png", 0.78),
        (valkey, DEP, "valkey_deploy.png", 0.70), (seaweed, DEP, "seaweedfs_deploy.png", 0.74),
        (res("onprem/certificates/cert-manager.png"), DEP, "certmanager_deploy.png", 0.74),
        (meta, DEP, "promptguard_deploy.png", 0.72),
    ]
    for logo, kind, name, box in jobs:
        logo_with_badge(logo, kind, name, box)
    print("day 7 icons written")

if __name__ == "__main__":
    main()
