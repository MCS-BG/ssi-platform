#!/usr/bin/env bash
# Roll one phase of the observability move back to node obs-node, onto the ORIGINAL volumes
# (kept by migrate.sh: their PVs were set to Retain before the old PVCs were deleted).
# Run on node gpu-node from the repo root:
#   sudo PHASE=langfuse   BK=/mnt/ailab-data/backups/observability/<stamp>-langfuse   REF=<commit before the merge> bash scripts/observability-move/rollback.sh
#   sudo PHASE=monitoring BK=/mnt/ailab-data/backups/observability/<stamp>-monitoring REF=<commit before the merge> bash scripts/observability-move/rollback.sh
# Roll back monitoring before langfuse if both phases ran. Anything written on gpu-node after the
# move (new traces, metrics) is NOT carried back; it stays on /srv/observability.
set -euo pipefail
PHASE=${PHASE:?}; BK=${BK:?backup dir printed by migrate.sh}; REF=${REF:?git ref with the old values, e.g. the merge commit^1}
K="k3s kubectl"; export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
[[ -f $BK/old-pvs.txt ]] || { echo "$BK/old-pvs.txt missing"; exit 1; }
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
old(){ git show "$REF:k8s/$1" > "$T/$1"; grep -q "ailab/role: observability" "$T/$1" || { echo "$REF:k8s/$1 is not the obs-node version"; exit 1; }; echo "$T/$1"; }
log(){ echo "[$(date +%H:%M:%S)] $*"; }

stop_and_release(){ # ns
  local ns=$1
  log "delete the d-side PVCs (static PVs are Retain; data on gpu-node stays)"
  awk -v ns="$ns" '$1==ns{print $2}' "$BK/old-pvs.txt" | while read -r pvc; do $K -n "$ns" delete pvc "$pvc" --ignore-not-found --wait=true; done
  log "re-open the original obs-node PVs for the same PVC names"
  awk -v ns="$ns" '$1==ns{print $3}' "$BK/old-pvs.txt" | while read -r pv; do
    $K patch pv "$pv" --type json -p '[{"op":"remove","path":"/spec/claimRef/uid"},{"op":"remove","path":"/spec/claimRef/resourceVersion"}]' 2>/dev/null || true
  done
}

case $PHASE in
langfuse)
  NS=langfuse
  LF_URL=$(cat "$BK/nextauth-url")
  $K -n clickhouse-operator scale deploy/clickhouse-operator-controller-manager --replicas=0
  for d in langfuse-web langfuse-worker langfuse-redis langfuse-s3-all-in-one; do $K -n $NS scale deploy/$d --replicas=0; done
  for s in langfuse-postgresql langfuse-clickhouse-0-0 langfuse-keeper-0; do $K -n $NS scale sts/$s --replicas=0; done
  sleep 30
  stop_and_release $NS
  helm upgrade cert-manager oci://quay.io/jetstack/charts/cert-manager --version v1.20.2 --force-conflicts -n cert-manager -f "$(old day-07-cert-manager-values.yaml)" --wait
  helm upgrade langfuse langfuse/langfuse --version 2.1.2 --force-conflicts -n $NS -f "$(old day-07-langfuse-values.yaml)" \
    --set-string langfuse.nextauth.url="$LF_URL" --timeout 20m
  helm upgrade clickhouse-operator oci://ghcr.io/clickhouse/clickhouse-operator-helm --version 0.0.5 --force-conflicts -n clickhouse-operator \
    -f "$(old day-07-clickhouse-operator-values.yaml)" --wait
  $K -n clickhouse-operator scale deploy/clickhouse-operator-controller-manager --replicas=1
  $K -n $NS scale sts/langfuse-postgresql --replicas=1
  for d in langfuse-redis langfuse-s3-all-in-one langfuse-web langfuse-worker; do $K -n $NS scale deploy/$d --replicas=1; done
  ;;
monitoring)
  NS=monitoring
  $K -n $NS patch prometheus kps-prometheus --type merge -p '{"spec":{"replicas":0}}'
  $K -n $NS scale sts/tempo --replicas=0; $K -n $NS scale sts/loki --replicas=0
  sleep 30
  stop_and_release $NS
  helm upgrade kps prometheus-community/kube-prometheus-stack --version 91.5.3 --force-conflicts -n $NS -f "$(old day-07-kube-prometheus-stack-values.yaml)" --timeout 15m
  helm upgrade tempo grafana-community/tempo --version 3.0.0 --force-conflicts -n $NS -f "$(old day-07-tempo-values.yaml)"
  helm upgrade loki grafana-community/loki --version 18.13.5 --force-conflicts -n $NS -f "$(old day-07-loki-values.yaml)"
  helm upgrade otel-collector open-telemetry/opentelemetry-collector --version 0.173.1 --force-conflicts -n $NS \
    -f "$(old day-07-otel-collector-values.yaml)" -f "$(git show "$REF:k8s/day-07-otel-collector-stage-c.yaml" > "$T/c.yaml"; echo "$T/c.yaml")" --wait
  $K -n $NS patch prometheus kps-prometheus --type merge -p '{"spec":{"replicas":1}}'
  $K -n $NS scale sts/tempo --replicas=1; $K -n $NS scale sts/loki --replicas=1
  ;;
*) echo "unknown PHASE"; exit 1 ;;
esac
log "waiting for pods"; sleep 60; $K -n $NS get pods -o wide; $K -n $NS get pvc
