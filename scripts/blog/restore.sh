#!/usr/bin/env bash
# Restore the blog from the nightly backup files on the data lake into a deployed (empty or
# damaged) blog. Works on any node that has the data lake and the image mounted, so the blog
# can be rebuilt on another device: storage-setup.sh, secrets.sh, apply -k, then this.
#   sudo NS=blog bash scripts/blog/restore.sh                    # latest backup
#   sudo NS=blog TS=20261011-0315 bash scripts/blog/restore.sh   # a specific one
set -euo pipefail
NS=${NS:?set NS=blog or NS=blog-staging}
case $NS in blog|blog-staging) ;; *) echo "NS must be blog or blog-staging"; exit 1 ;; esac
B=/mnt/ailab-data/backups/$NS; MNT=/srv/$NS
K="k3s kubectl -n $NS"
TS=${TS:-$(ls -1 "$B"/db/ghost-*.sql.gz | sed 's/.*ghost-\(.*\)\.sql\.gz/\1/' | sort | tail -1)}
DB=$B/db/ghost-$TS.sql.gz; CT=$B/content/content-$TS.tar.gz
[[ -f $DB && -f $CT ]] || { echo "missing $DB or $CT"; exit 1; }
mountpoint -q "$MNT" || { echo "$MNT not mounted (run infra/blog/storage-setup.sh)"; exit 1; }
echo "Restoring $NS from $TS"
$K rollout status statefulset/blog-mysql --timeout=300s
$K scale deployment/ghost --replicas=0
$K wait --for=delete pod -l app=ghost --timeout=120s || true
gunzip -c "$DB" | $K exec -i blog-mysql-0 -- sh -c 'mysql -u root -p"$MYSQL_ROOT_PASSWORD" ghost'
find "$MNT/ghost-content" -mindepth 1 -delete
tar -xzf "$CT" -C "$MNT/ghost-content"
chown -R 1000:1000 "$MNT/ghost-content"
$K scale deployment/ghost --replicas=1
$K rollout status deployment/ghost --timeout=600s
echo "Restored $NS from $TS"
