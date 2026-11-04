#!/usr/bin/env bash
# Move Langfuse (phase 1) or the monitoring stack (phase 2) from node obs-node to node gpu-node,
# keeping all history. Run on node gpu-node from the repo root, ONLY after the operator approves the PR
# and infra/observability/storage-setup.sh has run. Docs: docs/observability-move.md.
#
#   sudo PHASE=langfuse   bash scripts/observability-move/migrate.sh
#   sudo PHASE=monitoring bash scripts/observability-move/migrate.sh
#
# How it works, per volume: stop the workload, copy the old local-path volume from obs-node
# with a short-lived read-only "mover" pod (tar stream over the Kubernetes API; d has no SSH
# to obs-node), delete the old PVC (its PV is first set to Retain, so the data on obs-node stays
# as the rollback copy), pre-create a static PV on gpu-node bound to the same PVC name, then
# "helm upgrade" with the values in this branch, which pin every pod to gpu-node.
# Postgres is also dumped (pg_dump -Fc) before the stop, as a verified, portable backup.
set -euo pipefail
# All helm upgrades use --force-conflicts: Helm 4 applies server-side and otherwise refuses
# fields this script changed with kubectl (replicas), as happened on 2026-10-11.
PHASE=${PHASE:?set PHASE=langfuse or PHASE=monitoring}
K="k3s kubectl"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
MNT=/srv/observability
BK=/mnt/ailab-data/backups/observability/$(date +%Y%m%d-%H%M%S)-$PHASE
MOVER_IMAGE=${MOVER_IMAGE:-docker.io/library/busybox:1.37}
REPO=$(git rev-parse --show-toplevel)

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
[[ $(hostname) == [Dd] ]] || { echo "run on node gpu-node"; exit 1; }
mountpoint -q $MNT || { echo "$MNT not mounted; run infra/observability/storage-setup.sh"; exit 1; }
# ext4 does not list nodiscard (it is the default), so assert that discard is absent.
! findmnt -no OPTIONS $MNT | grep -qw discard || { echo "$MNT is mounted with discard"; exit 1; }
command -v helm >/dev/null || { echo "helm missing"; exit 1; }
mkdir -p "$BK"
log(){ echo "[$(date +%H:%M:%S)] $*"; }

helm_repos(){
  helm repo add langfuse https://langfuse.github.io/langfuse-k8s >/dev/null 2>&1 || true
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo add grafana-community https://grafana-community.github.io/helm-charts >/dev/null 2>&1 || true
  helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
  helm repo update >/dev/null
}

# old PV name for a PVC; refuse to continue unless it is the obs-node local-path volume
old_pv(){ $K -n "$1" get pvc "$2" -o jsonpath='{.spec.volumeName}'; }

retain(){ # ns pvc
  local pv; pv=$(old_pv "$1" "$2")
  [[ $pv == obs-* ]] && { echo "$1/$2 already on $pv (moved)"; return 1; }
  $K patch pv "$pv" -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}' >/dev/null
  echo "$1 $2 $pv" >> "$BK/old-pvs.txt"
}

copy_volume(){ # ns pvc destdir
  local ns=$1 pvc=$2 dest=$MNT/$3 pod=obs-mover-$RANDOM
  [[ -z $(ls -A "$dest") ]] || { echo "$dest is not empty; refusing to overwrite"; exit 1; }
  log "copy $ns/$pvc -> $dest"
  $K -n "$ns" apply -f - >/dev/null <<POD
apiVersion: v1
kind: Pod
metadata: {name: $pod, labels: {app: obs-mover}}
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  nodeSelector: {kubernetes.io/hostname: obs-node}
  tolerations: [{key: ailab/role, operator: Equal, value: observability, effect: NoSchedule}]
  containers:
    - name: mover
      image: $MOVER_IMAGE
      command: [sleep, "3600"]
      # root with only DAC_OVERRIDE: enough to read every file (pg data is 0700), nothing else.
      securityContext: {runAsUser: 0, allowPrivilegeEscalation: false, capabilities: {drop: [ALL], add: [DAC_OVERRIDE]}}
      volumeMounts: [{name: src, mountPath: /src, readOnly: true}]
  volumes: [{name: src, persistentVolumeClaim: {claimName: $pvc, readOnly: true}}]
POD
  $K -n "$ns" wait --for=condition=Ready pod/$pod --timeout=180s >/dev/null
  $K -n "$ns" exec $pod -- sh -c 'cd /src && find . | wc -l && du -sk .' > "$BK/$3.src-stats"
  $K -n "$ns" exec $pod -- tar -C /src -cf - . | tar -C "$dest" --numeric-owner -xpf -
  local n; n=$(cd "$dest" && find . | wc -l)
  [[ $n == $(head -1 "$BK/$3.src-stats") ]] || { echo "file count mismatch for $3: src $(head -1 "$BK/$3.src-stats") dst $n"; exit 1; }
  $K -n "$ns" delete pod $pod --wait=false >/dev/null
  log "  ok: $n entries, $(du -sh "$dest" | cut -f1)"
}

scale_wait(){ # ns kind/name replicas
  $K -n "$1" scale "$2" --replicas="$3" >/dev/null
}
wait_gone(){ # ns selector-ish pod name prefix
  for _ in $(seq 60); do
    $K -n "$1" get pods --no-headers 2>/dev/null | grep -q "^$2" || return 0; sleep 5; done
  echo "pods $1/$2* still running"; exit 1
}

phase_langfuse(){
  local NS=langfuse
  declare -A V=( [postgres-data-langfuse-postgresql-0]=langfuse-postgresql
                 [clickhouse-storage-volume-langfuse-clickhouse-0-0-0]=langfuse-clickhouse
                 [clickhouse-storage-volume-langfuse-keeper-0-0]=langfuse-keeper
                 [langfuse-redis]=langfuse-redis
                 [langfuse-s3-all-in-one-data]=langfuse-s3 )
  # Day 8b set the sign-in URL to the tailnet host with --set-string; keep it.
  LF_URL=$($K -n $NS get deploy langfuse-web -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="NEXTAUTH_URL")].value}')
  [[ -n $LF_URL ]] || { echo "could not read NEXTAUTH_URL from langfuse-web"; exit 1; }
  echo "$LF_URL" > "$BK/nextauth-url"
  for p in "${!V[@]}"; do retain $NS "$p"; done

  log "stop writers (web, worker)"
  scale_wait $NS deploy/langfuse-web 0; scale_wait $NS deploy/langfuse-worker 0
  wait_gone $NS langfuse-web; wait_gone $NS langfuse-worker

  log "verification snapshot + pg_dump"
  $K -n $NS exec langfuse-postgresql-0 -c postgresql -- sh -c 'pg_dump -U postgres -Fc "$POSTGRES_DB"' > "$BK/langfuse-postgres.dump"
  [[ -s $BK/langfuse-postgres.dump ]] || { echo "empty dump"; exit 1; }
  pg_counts > "$BK/pg-counts.before"
  ch_counts > "$BK/ch-counts.before"

  log "stop data services (the ClickHouse operator first, so it does not restart them)"
  scale_wait clickhouse-operator deploy/clickhouse-operator-controller-manager 0
  wait_gone clickhouse-operator clickhouse-operator-controller-manager
  scale_wait $NS sts/langfuse-clickhouse-0-0 0; scale_wait $NS sts/langfuse-keeper-0 0
  scale_wait $NS sts/langfuse-postgresql 0
  scale_wait $NS deploy/langfuse-redis 0; scale_wait $NS deploy/langfuse-s3-all-in-one 0
  for p in langfuse-clickhouse langfuse-keeper langfuse-postgresql langfuse-redis langfuse-s3; do wait_gone $NS $p; done

  for p in "${!V[@]}"; do copy_volume $NS "$p" "${V[$p]}"; done

  log "swap PVCs to the static PVs on gpu-node"
  for p in "${!V[@]}"; do $K -n $NS delete pvc "$p" --wait=true; done
  $K apply -f "$REPO/k8s/observability-move/10-langfuse-pvs.yaml"

  log "move cert-manager to gpu-node"
  helm upgrade cert-manager oci://quay.io/jetstack/charts/cert-manager --version v1.20.2 --force-conflicts -n cert-manager \
    -f "$REPO/k8s/day-07-cert-manager-values.yaml" --wait

  # Upgrade while everything is still at 0 replicas, so no pod ever starts with the old
  # obs-node selector against a volume that now lives on gpu-node. This also recreates the two
  # Deployment PVCs (redis, s3) from the chart; they bind to the pre-bound static PVs.
  log "helm upgrade langfuse (pins every pod and the ClickHouse CRs to gpu-node)"
  helm upgrade langfuse langfuse/langfuse --version 2.1.2 --force-conflicts -n $NS \
    -f "$REPO/k8s/day-07-langfuse-values.yaml" --set-string langfuse.nextauth.url="$LF_URL" --timeout 20m

  log "move the ClickHouse operator to gpu-node and start it (it brings up ClickHouse and Keeper on gpu-node)"
  helm upgrade clickhouse-operator oci://ghcr.io/clickhouse/clickhouse-operator-helm --version 0.0.5 --force-conflicts \
    -n clickhouse-operator -f "$REPO/k8s/day-07-clickhouse-operator-values.yaml" --wait
  scale_wait clickhouse-operator deploy/clickhouse-operator-controller-manager 1

  log "start data services, then Langfuse"
  scale_wait $NS sts/langfuse-postgresql 1
  scale_wait $NS deploy/langfuse-redis 1; scale_wait $NS deploy/langfuse-s3-all-in-one 1
  $K -n $NS rollout status sts/langfuse-postgresql --timeout=10m
  for s in langfuse-redis langfuse-s3-all-in-one; do $K -n $NS rollout status deploy/$s --timeout=10m; done
  for _ in $(seq 120); do
    $K -n $NS get pod langfuse-clickhouse-0-0-0 -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null | grep -q true && break; sleep 5; done
  scale_wait $NS deploy/langfuse-web 1; scale_wait $NS deploy/langfuse-worker 1
  for s in langfuse-web langfuse-worker; do $K -n $NS rollout status deploy/$s --timeout=15m; done
  for p in "${!V[@]}"; do
    $K -n $NS get pvc "$p" >/dev/null 2>&1 || { echo "PVC $p missing after upgrade, see docs (Troubleshooting)"; exit 1; }
    [[ $($K -n $NS get pvc "$p" -o jsonpath='{.spec.volumeName}') == obs-* ]] || { echo "PVC $p not on a static PV"; exit 1; }
  done
  [[ -z $($K -n $NS get pods -o wide --no-headers | grep -v -e obs-mover -e Terminating -e Completed | awk '$7!="d"') ]] || { echo "a langfuse pod is not on gpu-node"; exit 1; }

  log "verify history"
  pg_counts > "$BK/pg-counts.after"; ch_counts > "$BK/ch-counts.after"
  # Ingestion resumes as soon as web/worker start, so "after" may be higher, never lower.
  no_loss "$BK/pg-counts.before" "$BK/pg-counts.after" && no_loss "$BK/ch-counts.before" "$BK/ch-counts.after" \
    && log "no table lost rows" || { echo "ROWS MISSING, see $BK; run rollback.sh"; exit 1; }
  $K -n $NS get pods -o wide
}

pg_counts(){ # "table|rows" for every user table
  $K -n langfuse exec langfuse-postgresql-0 -c postgresql -- sh -c 'psql -U postgres -d "$POSTGRES_DB" -At -c "select format(\$q\$select %L, count(*) from %I.%I;\$q\$, schemaname||chr(46)||relname, schemaname, relname) from pg_stat_user_tables" | psql -U postgres -d "$POSTGRES_DB" -At' | sort
}
no_loss(){ # before after: every key in before has count <= after
  awk 'function key(l){sub(/[|\t][^|\t]*$/,"",l); return l} function val(l){sub(/.*[|\t]/,"",l); return l+0}
       NR==FNR{b[key($0)]=val($0); next} {a[key($0)]=val($0)}
       END{bad=0; for(k in b) if(!(k in a) || a[k] < b[k]){print "LOST: " k " before=" b[k] " after=" a[k]; bad=1} exit bad}' "$1" "$2"
}
ch_counts(){
  $K -n langfuse exec langfuse-clickhouse-0-0-0 -- clickhouse-client -q \
    "select database, table, sum(rows) from system.parts where active and database not in ('system','INFORMATION_SCHEMA','information_schema') group by 1,2 order by 1,2"
}

phase_monitoring(){
  local NS=monitoring
  declare -A V=( [prometheus-kps-prometheus-db-prometheus-kps-prometheus-0]=prometheus
                 [storage-tempo-0]=tempo [storage-loki-0]=loki )
  for p in "${!V[@]}"; do retain $NS "$p"; done

  log "stop Prometheus (via its CR), Tempo, and Loki"
  $K -n $NS patch prometheus kps-prometheus --type merge -p '{"spec":{"replicas":0}}'
  scale_wait $NS sts/tempo 0; scale_wait $NS sts/loki 0
  for p in prometheus-kps-prometheus tempo loki; do wait_gone $NS $p; done

  for p in "${!V[@]}"; do copy_volume $NS "$p" "${V[$p]}"; done

  log "swap PVCs to the static PVs on gpu-node"
  for p in "${!V[@]}"; do $K -n $NS delete pvc "$p" --wait=true; done
  $K apply -f "$REPO/k8s/observability-move/20-monitoring-pvs.yaml"

  # Upgrade while Prometheus, Tempo, and Loki are at 0, then start them, so no pod starts
  # with the old obs-node selector against a volume that now lives on gpu-node.
  log "helm upgrade kps, tempo, loki, otel-collector"
  helm upgrade kps prometheus-community/kube-prometheus-stack --version 91.5.3 --force-conflicts -n $NS \
    -f "$REPO/k8s/day-07-kube-prometheus-stack-values.yaml" --timeout 15m
  helm upgrade tempo grafana-community/tempo --version 3.0.0 --force-conflicts -n $NS -f "$REPO/k8s/day-07-tempo-values.yaml"
  helm upgrade loki grafana-community/loki --version 18.13.5 --force-conflicts -n $NS -f "$REPO/k8s/day-07-loki-values.yaml"
  helm upgrade otel-collector open-telemetry/opentelemetry-collector --version 0.173.1 --force-conflicts -n $NS \
    -f "$REPO/k8s/day-07-otel-collector-values.yaml" -f "$REPO/k8s/day-07-otel-collector-stage-c.yaml" --wait
  $K -n $NS patch prometheus kps-prometheus --type merge -p '{"spec":{"replicas":1}}'
  scale_wait $NS sts/tempo 1; scale_wait $NS sts/loki 1
  for _ in $(seq 60); do $K -n $NS get sts prometheus-kps-prometheus >/dev/null 2>&1 && break; sleep 5; done
  for s in prometheus-kps-prometheus tempo loki; do $K -n $NS rollout status sts/$s --timeout=10m; done
  for s in kps-grafana kps-operator kps-kube-state-metrics otel-collector; do $K -n $NS rollout status deploy/$s --timeout=10m; done
  [[ -z $($K -n $NS get pods -o wide --no-headers | grep -v -e obs-mover -e Terminating -e Completed | awk '$7!="d"') ]] || { echo "a monitoring pod is not on gpu-node"; exit 1; }
  for p in "${!V[@]}"; do
    [[ $($K -n $NS get pvc "$p" -o jsonpath='{.spec.volumeName}') == obs-* ]] || { echo "PVC $p not on a static PV"; exit 1; }
  done

  log "verify history: oldest Prometheus sample should be ~3 days old (retention 3d)"
  $K -n $NS exec prometheus-kps-prometheus-0 -c prometheus -- \
    wget -qO- 'http://localhost:9090/api/v1/query?query=prometheus_tsdb_lowest_timestamp_seconds' | tee "$BK/prom-lowest.json"; echo
  $K -n $NS get pods -o wide
}

helm_repos
case $PHASE in
  langfuse) phase_langfuse ;;
  monitoring) phase_monitoring ;;
  *) echo "unknown PHASE"; exit 1 ;;
esac
log "done. Backup and evidence: $BK. Old obs-node volumes are kept (Retain); see rollback.sh."
