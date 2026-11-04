#!/usr/bin/env bash
# Blog storage on the data lake (stateless rule: no app data under /var/lib/rancher).
# Same pattern as infra/observability/storage-setup.sh: one ext4 image FILE on the exFAT data
# lake, loop-mounted (nodiscard) by a systemd mount unit that starts before k3s. MySQL and Ghost
# need Unix owners and modes that exFAT lacks; inside the image they get real ext4. To move the
# blog to another machine, copy the image file (or restore from backups) and run this script.
# Run on node gpu-node. Idempotent.
#   sudo bash infra/blog/storage-setup.sh                         # prod:    /srv/blog, 10G
#   sudo ENV=staging SIZE=2G bash infra/blog/storage-setup.sh     # staging: /srv/blog-staging
set -euo pipefail
ENV=${ENV:-prod}
case $ENV in
  prod)    NAME=blog;         SIZE=${SIZE:-10G} ;;
  staging) NAME=blog-staging; SIZE=${SIZE:-2G} ;;
  *) echo "ENV must be prod or staging"; exit 1 ;;
esac
IMG_DIR=/mnt/ailab-data/$NAME
IMG=$IMG_DIR/$NAME-store.ext4
MNT=/srv/$NAME
UNIT=$(systemd-escape -p --suffix=mount "$MNT")
BACKUPS=/mnt/ailab-data/backups/$NAME

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
[[ $(hostname) == [Dd] ]] || { echo "run on node gpu-node"; exit 1; }
findmnt -no FSTYPE /mnt/ailab-data | grep -qx exfat || { echo "data lake not mounted"; exit 1; }

mkdir -p "$IMG_DIR" "$BACKUPS"
if [[ ! -f "$IMG" ]]; then
  echo "Allocating $SIZE image (exFAT has no sparse files; this writes the full size)"
  fallocate -l "$SIZE" "$IMG" 2>/dev/null || truncate -s "$SIZE" "$IMG"
  mkfs.ext4 -q -F -L "${NAME:0:16}" -m 1 -E nodiscard "$IMG"
fi
if ! mountpoint -q "$MNT"; then
  mkdir -p "$MNT"
  chattr +i "$MNT" 2>/dev/null || true   # unmounted = immutable, so pods fail instead of writing to the root disk
fi
cat > /etc/systemd/system/$UNIT <<UNIT
[Unit]
Description=Blog ($ENV) ext4 store (loop image on the exFAT data lake)
Requires=mnt-ailab\x2ddata.mount
After=mnt-ailab\x2ddata.mount
Before=k3s.service

[Mount]
What=$IMG
Where=$MNT
Type=ext4
# nodiscard: TRIM inside the image would punch holes in a file on exFAT, which it cannot do.
Options=loop,noatime,nodiscard,errors=remount-ro

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now "$UNIT"
install -d -m 0750 -o 1000 -g 1000 "$MNT/ghost-content"   # Ghost runs as uid 1000
install -d -m 0700 -o 999 -g 999 "$MNT/mysql"             # MySQL runs as uid 999
findmnt "$MNT"; df -h "$MNT"; ls -ln "$MNT"
