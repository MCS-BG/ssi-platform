#!/usr/bin/env bash
# Create the blog's Secrets on the lab host. Generated values are never printed or saved.
# Re-running keeps existing Secrets.
#   sudo NS=blog-staging bash scripts/blog/secrets.sh          # staging: DB only
#   sudo NS=blog bash scripts/blog/secrets.sh                   # prod: DB, then asks for the tunnel token
set -euo pipefail
NS=${NS:?set NS=blog or NS=blog-staging}
K="k3s kubectl -n $NS"
gen() { openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-32; }
k3s kubectl get ns "$NS" >/dev/null 2>&1 || k3s kubectl create ns "$NS"
if ! $K get secret blog-mysql >/dev/null 2>&1; then
  $K create secret generic blog-mysql --from-literal=root-password="$(gen)" --from-literal=password="$(gen)"
fi
if [ "$NS" = blog ] && ! $K get secret blog-cloudflared >/dev/null 2>&1; then
  read -rsp "Paste the Cloudflare tunnel token (input hidden): " T; echo
  [ -n "$T" ] || { echo "empty token" >&2; exit 1; }
  $K create secret generic blog-cloudflared --from-literal=token="$T"; unset T
fi
$K get secret
