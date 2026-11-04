#!/usr/bin/env bash
# Move the last workloads (two DaemonSets) off the obs-node and cordon it.
# Run on gpu-node. Does not drain data, delete volumes, or remove the node.
set -euo pipefail
K="k3s kubectl"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
DRY="${DRY_RUN:-0}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BK="/mnt/ailab-data/backups/obs-node-offload/$STAMP"
run(){ echo "+ $*"; [ "$DRY" = 1 ] || eval "$@"; }

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
echo "== Preflight"
$K get node gpu-node obs-node
FREE_MI=$(awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo)
echo "d MemAvailable: ${FREE_MI}Mi (need > 1024Mi)"
[ "$FREE_MI" -gt 1024 ] || { echo "Not enough free RAM on gpu-node"; exit 1; }

echo "== Backup current state to $BK"
run "mkdir -p '$BK'"
run "$K get node obs-node -o yaml | tee '$BK/node-obs-node.yaml' >/dev/null"
run "helm -n monitoring get values kps -o yaml | tee '$BK/kps-values.yaml' >/dev/null"
run "helm -n monitoring-host get values otel-agent -o yaml | tee '$BK/otel-agent-values.yaml' >/dev/null"
run "$K get pods -A -o wide --field-selector spec.nodeName=obs-node | tee '$BK/obs-node-pods-before.txt'"

echo "== Upgrade releases with obs-node-excluding values"
run "helm -n monitoring upgrade kps prometheus-community/kube-prometheus-stack --version 91.5.3 --force-conflicts --reuse-values -f '$REPO/k8s/day-07-kube-prometheus-stack-values.yaml'"
run "helm -n monitoring-host upgrade otel-agent open-telemetry/opentelemetry-collector --version 0.173.1 --force-conflicts --reuse-values -f '$REPO/k8s/day-07-otel-agent-values.yaml'"

echo "== Wait for obs-node to be empty"
if [ "$DRY" != 1 ]; then
  for i in $(seq 1 30); do
    n=$($K get pods -A --field-selector spec.nodeName=obs-node --no-headers 2>/dev/null | wc -l)
    [ "$n" -eq 0 ] && break; sleep 5
  done
  $K get pods -A --field-selector spec.nodeName=obs-node
fi

echo "== Cordon the obs-node (stays joined)"
run "$K cordon obs-node"
echo "Done. Backup: $BK. Rollback: scripts/obs-node-offload/rollback.sh $BK"
