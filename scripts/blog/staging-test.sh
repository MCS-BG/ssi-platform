#!/usr/bin/env bash
# Deploy the blog to blog-staging, smoke-test over port-forward, and (unless KEEP=1) tear down.
#   sudo bash scripts/blog/staging-test.sh
set -euo pipefail
cd "$(dirname "$0")/../.."
K="k3s kubectl"
ENV=staging bash infra/blog/storage-setup.sh >/dev/null
$K apply -f k8s/blog/storageclass.yaml
NS=blog-staging bash scripts/blog/secrets.sh >/dev/null
$K apply -k k8s/blog/staging
$K -n blog-staging rollout status statefulset/blog-mysql --timeout=300s
$K -n blog-staging rollout status deployment/ghost --timeout=600s
$K -n blog-staging port-forward svc/ghost 23680:2368 >/tmp/blog-pf.log 2>&1 & PF=$!
trap 'kill $PF 2>/dev/null || true' EXIT
sleep 5
home=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:23680/)
admin=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:23680/ghost/api/admin/site/)
echo "home=$home admin-api=$admin"
# Staging only: create a throwaway owner (generated, never printed) and apply the branding.
export GHOST_URL=http://127.0.0.1:23680 GHOST_ORIGIN=http://localhost:2368 GHOST_EMAIL=owner@example.com
GHOST_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=\n'); export GHOST_PASSWORD
python3 -c 'import json,os;print(json.dumps({"setup":[{"name":"Staging Owner","email":os.environ["GHOST_EMAIL"],"password":os.environ["GHOST_PASSWORD"],"blogTitle":"example"}]}))' |
  curl -sf -H "Origin: $GHOST_ORIGIN" -H 'Content-Type: application/json' --data-binary @- "$GHOST_URL/ghost/api/admin/authentication/setup/" >/dev/null
bash scripts/blog/brand.sh
page=$(curl -s http://127.0.0.1:23680/)
brand=FAIL; echo "$page" | grep -q '#2F5BFF' && echo "$page" | grep -q 'family=Inter' && echo "$page" | grep -q 'Sora' && brand=PASS
echo "branding=$brand"
$K -n blog-staging create job --from=cronjob/blog-backup blog-backup-test
$K -n blog-staging wait --for=condition=complete job/blog-backup-test --timeout=300s
$K -n blog-staging logs job/blog-backup-test
[ "$home" = 200 ] && [ "$admin" = 200 ] && [ "$brand" = PASS ] || { echo FAIL; exit 1; }
echo PASS
if [ "${KEEP:-0}" != 1 ]; then
  $K delete ns blog-staging --wait
  $K delete pv blog-staging-mysql blog-staging-ghost-content blog-staging-backup --ignore-not-found
  ENV=staging bash infra/blog/storage-remove.sh
  rm -rf /mnt/ailab-data/backups/blog-staging
fi
