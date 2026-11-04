#!/usr/bin/env bash
# Undo offload.sh: uncordon the obs-node and restore the saved Helm values.
set -euo pipefail
K="k3s kubectl"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
BK="${1:?usage: rollback.sh /mnt/ailab-data/backups/obs-node-offload/<stamp>}"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
$K uncordon obs-node
helm -n monitoring upgrade kps prometheus-community/kube-prometheus-stack --version 91.5.3 --force-conflicts --reset-values -f "$BK/kps-values.yaml"
helm -n monitoring-host upgrade otel-agent open-telemetry/opentelemetry-collector --version 0.173.1 --force-conflicts --reset-values -f "$BK/otel-agent-values.yaml"
$K get pods -A -o wide --field-selector spec.nodeName=obs-node
