#!/usr/bin/env bash
# Smoke test a stage over the network only (no kubectl exec, no port-forward).
# Runs on the lab host (self-hosted runner): the node reaches Service ClusterIPs directly.
# Commit check uses get/watch only: `rollout status` for each Deployment, then every Ready,
# non-terminating pod of the CURRENT ReplicaSet must carry si.sdlc/git-sha=<sha>
# (scripts/sdlc/rollout_check.py). Old pods still in their grace period are ignored; other
# mismatches are retried for up to SMOKE_ROLLOUT_WAIT seconds (default 120) before failing.
#   scripts/sdlc/smoke.sh staging|prod [sha] [--read-only]   (--read-only: health + sha, no /ask)
set -euo pipefail
STAGE=${1:?staging|prod}; SHA=${2:-}; MODE=${3:-}
case "$STAGE" in staging) NS=si-staging ;; prod) NS=si-lab ;; *) exit 2 ;; esac
fail=0
url() { # service path
  local ip port
  ip=$(kubectl -n "$NS" get svc "$1" -o jsonpath='{.spec.clusterIP}')
  port=$(kubectl -n "$NS" get svc "$1" -o jsonpath='{.spec.ports[0].port}')
  echo "http://$ip:$port$2"
}
health() { # retry each /healthz so a pod mid-rollout doesn't fail the run
  for svc in m365-mcp control-layer ssi-langgraph; do
    code=000
    for _ in $(seq 1 "${SMOKE_HEALTH_TRIES:-12}"); do
      code=$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$(url "$svc" /healthz)" || true)
      [[ "$code" == 200 ]] && break
      sleep "${SMOKE_POLL:-5}"
    done
    [[ "$code" == 200 ]] && echo "PASS $svc /healthz" || { echo "FAIL $svc /healthz ($code)"; fail=1; }
  done
}
if [[ -n "$SHA" ]]; then
  HERE=$(cd "$(dirname "$0")" && pwd); TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
  WAIT=${SMOKE_ROLLOUT_WAIT:-120}
  for d in m365-mcp control-layer ssi-langgraph; do
    if ! kubectl -n "$NS" rollout status "deployment/$d" --timeout="${WAIT}s" >/dev/null; then
      echo "FAIL $d rollout not complete within ${WAIT}s"; fail=1; continue
    fi
    sel=$(kubectl -n "$NS" get deploy "$d" -o jsonpath='{.spec.selector.matchLabels}' \
      | python3 -c 'import json,sys; print(",".join(f"{k}={v}" for k,v in json.load(sys.stdin).items()))')
    deadline=$((SECONDS + WAIT)); passed=0
    while :; do
      kubectl -n "$NS" get deploy "$d" -o json > "$TMP/d.json"
      kubectl -n "$NS" get rs -l "$sel" -o json > "$TMP/rs.json"
      kubectl -n "$NS" get pods -l "$sel" -o json > "$TMP/p.json"
      if msg=$(python3 "$HERE/rollout_check.py" "$TMP/d.json" "$TMP/rs.json" "$TMP/p.json" "$SHA"); then
        passed=1; break
      fi
      (( SECONDS >= deadline )) && break
      sleep "${SMOKE_POLL:-5}"
    done
    if (( passed )); then echo "PASS $msg"; else echo "FAIL $msg (after ${WAIT}s)"; fail=1; fi
  done
fi
health  # after rollout checks, so new pods are serving
if [[ "$MODE" != "--read-only" ]]; then
  body='{"question":"Do I have meetings this week?"}'
  if out=$(curl -s -m 240 -H 'Content-Type: application/json' -d "$body" "$(url ssi-langgraph /ask)") \
     && python3 -c 'import json,sys; r=json.loads(sys.argv[1]); assert r.get("ok") is True and r.get("guard",{}).get("label")=="benign"; print(json.dumps({k:r.get(k) for k in ("engine","slots_used","answer")}))' "$out"; then
    echo "PASS /ask (Prompt Guard, agent, tools)"
  else
    echo "FAIL /ask: ${out:0:300}"; fail=1
  fi
fi
exit $fail
