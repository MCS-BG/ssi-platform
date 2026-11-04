#!/usr/bin/env bash
# Staging restore drill: deploy, publish a post, back up, wipe the namespace AND its data image,
# rebuild from scratch, restore from the backup, and check the post is back (HTTP 200).
#   sudo bash scripts/blog/restore-test.sh      (tears staging down at the end unless KEEP=1)
set -euo pipefail
cd "$(dirname "$0")/../.."
K="k3s kubectl"; NS=blog-staging; S=$K\ -n\ $NS
up() {
  ENV=staging bash infra/blog/storage-setup.sh >/dev/null
  $K apply -f k8s/blog/storageclass.yaml >/dev/null
  NS=$NS bash scripts/blog/secrets.sh >/dev/null
  $K apply -k k8s/blog/staging >/dev/null
  $S rollout status statefulset/blog-mysql --timeout=300s
  $S rollout status deployment/ghost --timeout=600s
}
pf() { $S port-forward svc/ghost 23680:2368 >/dev/null 2>&1 & PF=$!; sleep 5; }
wipe() {
  $K delete ns $NS --wait --timeout=180s
  $K delete pv blog-staging-mysql blog-staging-ghost-content blog-staging-backup --ignore-not-found
  ENV=staging bash infra/blog/storage-remove.sh
}
trap 'kill ${PF:-0} 2>/dev/null || true' EXIT
U=http://127.0.0.1:23680; O=http://localhost:2368; SLUG=restore-drill
export GHOST_EMAIL=owner@example.com
GHOST_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=\n'); export GHOST_PASSWORD

echo "== 1. deploy"; up; pf
python3 -c 'import json,os;print(json.dumps({"setup":[{"name":"Staging Owner","email":os.environ["GHOST_EMAIL"],"password":os.environ["GHOST_PASSWORD"],"blogTitle":"example"}]}))' |
  curl -sf -H "Origin: $O" -H 'Content-Type: application/json' --data-binary @- $U/ghost/api/admin/authentication/setup/ >/dev/null
GHOST_URL=$U GHOST_ORIGIN=$O bash scripts/blog/brand.sh
J=$(mktemp)
python3 -c 'import json,os;print(json.dumps({"username":os.environ["GHOST_EMAIL"],"password":os.environ["GHOST_PASSWORD"]}))' |
  curl -sf -c $J -H "Origin: $O" -H 'Content-Type: application/json' --data-binary @- $U/ghost/api/admin/session/ >/dev/null
curl -sf -b $J -H "Origin: $O" -H 'Content-Type: application/json' \
  -d '{"posts":[{"title":"Restore drill","slug":"'$SLUG'","status":"published","lexical":"{\"root\":{\"children\":[{\"children\":[{\"detail\":0,\"format\":0,\"mode\":\"normal\",\"style\":\"\",\"text\":\"This post must survive a full wipe.\",\"type\":\"extended-text\",\"version\":1}],\"direction\":\"ltr\",\"format\":\"\",\"indent\":0,\"type\":\"paragraph\",\"version\":1}],\"direction\":\"ltr\",\"format\":\"\",\"indent\":0,\"type\":\"root\",\"version\":1}}"}]}' \
  "$U/ghost/api/admin/posts/" >/dev/null; rm -f $J
sleep 2
before=$(curl -s -o /dev/null -w '%{http_code}' $U/$SLUG/); echo "post before wipe: HTTP $before"
kill $PF

echo "== 2. back up"
$S create job --from=cronjob/blog-backup blog-backup-drill >/dev/null
$S wait --for=condition=complete job/blog-backup-drill --timeout=300s
$S logs job/blog-backup-drill

echo "== 3. wipe namespace and data image"; wipe
ls /mnt/ailab-data/blog-staging 2>&1 | head -1 || true
echo "== 4. rebuild empty"; up; pf
empty=$(curl -s -o /dev/null -w '%{http_code}' $U/$SLUG/); echo "post after rebuild, before restore: HTTP $empty"
kill $PF

echo "== 5. restore"; NS=$NS bash scripts/blog/restore.sh; pf
after=$(curl -s -o /dev/null -w '%{http_code}' $U/$SLUG/)
body=$(curl -s $U/$SLUG/ | grep -c 'This post must survive a full wipe.' || true)
cover=$(curl -s $U/ | grep -c 'cover-2000x666-plain' || true)
echo "post after restore: HTTP $after, text found: $body, branding cover found: $cover"
kill $PF
[[ $before == 200 && $empty == 404 && $after == 200 && $body -ge 1 && $cover -ge 1 ]] && echo PASS || { echo FAIL; exit 1; }
[[ ${KEEP:-0} == 1 ]] || { echo "== 6. tear down"; wipe; rm -rf /mnt/ailab-data/backups/blog-staging; }
