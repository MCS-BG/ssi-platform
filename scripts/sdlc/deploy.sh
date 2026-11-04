#!/usr/bin/env bash
# Deploy one release to a stage with the runner's scoped kubeconfig (sdlc-staging-deployer for staging, sdlc-deployer for Prod).
#   scripts/sdlc/deploy.sh staging <sha> [--dry-run]
#   scripts/sdlc/deploy.sh prod    <sha> [--dry-run]
set -euo pipefail
STAGE=${1:?staging|prod}; SHA=${2:?git sha}; DRY=${3:-}
case "$STAGE" in staging) NS=si-staging ;; prod) NS=si-lab ;; *) echo "bad stage"; exit 2 ;; esac
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=$(mktemp); trap 'rm -f "$OUT"' EXIT
python3 "$HERE/render.py" --env "$STAGE" --sha "$SHA" > "$OUT"
echo "Rendered $(grep -c '^kind:' "$OUT") objects for $STAGE ($NS) at ${SHA:0:12}"
if [[ "$DRY" == "--dry-run" ]]; then
  kubectl apply --dry-run=server -f "$OUT"
  exit 0
fi
kubectl apply -f "$OUT"
for d in $(python3 "$HERE/render.py" --env "$STAGE" --list-deployments); do
  kubectl -n "$NS" rollout status "deployment/$d" --timeout=420s
done
echo "Deployed ${SHA:0:12} to $NS"
