#!/usr/bin/env bash
# Unmount and DELETE a blog image (used by the staging restore test). Backups are kept.
#   sudo ENV=staging bash infra/blog/storage-remove.sh
# Prod needs CONFIRM=delete-blog-prod as well.
set -euo pipefail
ENV=${ENV:?set ENV=staging or ENV=prod}
case $ENV in staging) NAME=blog-staging ;; prod) NAME=blog; [[ ${CONFIRM:-} == delete-blog-prod ]] || { echo "refusing"; exit 1; } ;; *) exit 1 ;; esac
MNT=/srv/$NAME; UNIT=$(systemd-escape -p --suffix=mount "$MNT")
systemctl disable --now "$UNIT" 2>/dev/null || true
rm -f "/etc/systemd/system/$UNIT"; systemctl daemon-reload
rm -f "/mnt/ailab-data/$NAME/$NAME-store.ext4"; rmdir "/mnt/ailab-data/$NAME" 2>/dev/null || true
echo "removed $NAME image; backups kept in /mnt/ailab-data/backups/$NAME"
