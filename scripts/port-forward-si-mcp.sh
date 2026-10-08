#!/usr/bin/env bash
# LAB DEBUG ONLY: Forward SI lab MCP services to localhost for Cursor / VS Code.
# Developer product path: apps/ssi-vscode-connector + docs/ssi-vscode-connector.md
# (remote SSI base URL on Tailscale / Private Link — not this script).
# Requires: KUBECONFIG set, API tunnel up, namespace si-lab.
set -euo pipefail

export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/si-lab.yaml}"
NS=si-lab
PIDS=()

cleanup() {
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

kubectl -n "$NS" port-forward svc/mcp-server 18001:8000 &
PIDS+=($!)
kubectl -n "$NS" port-forward svc/engineering-mcp 18002:8000 &
PIDS+=($!)

echo "si-business   -> http://127.0.0.1:18001/mcp  (mcp-server)"
echo "si-engineering -> http://127.0.0.1:18002/mcp  (engineering-mcp)"
echo "Leave this terminal open. Ctrl-C stops both forwards."
wait
