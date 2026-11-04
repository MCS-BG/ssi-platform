#!/usr/bin/env bash
# Observability storage on the data lake, same pattern as infra/forgejo/storage-setup.sh.
# One ext4 image FILE on the exFAT drive, loop-mounted at /srv/observability by a systemd
# mount unit. Postgres, ClickHouse, Prometheus, and friends need Unix owners, modes, and
# fsync semantics that exFAT does not have; inside the image they get real ext4.
# Run on node gpu-node, ONLY after the operator approves. Idempotent.
#   sudo SIZE=50G bash infra/observability/storage-setup.sh
set -euo pipefail
SIZE=${SIZE:-50G}
IMG_DIR=/mnt/ailab-data/observability
IMG=$IMG_DIR/observability-store.ext4
MNT=/srv/observability
UNIT=srv-observability.mount
DIRS="langfuse-postgresql langfuse-clickhouse langfuse-keeper langfuse-redis langfuse-s3 prometheus tempo loki"

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
[[ $(hostname) == [Dd] ]] || { echo "run on node gpu-node"; exit 1; }
findmnt -no FSTYPE /mnt/ailab-data | grep -qx exfat || { echo "data lake not mounted"; exit 1; }

mkdir -p "$IMG_DIR" /mnt/ailab-data/backups/observability
if [[ ! -f "$IMG" ]]; then
  echo "Allocating $SIZE image (exFAT has no sparse files; this writes the full size)"
  fallocate -l "$SIZE" "$IMG" 2>/dev/null || truncate -s "$SIZE" "$IMG"
  mkfs.ext4 -q -F -L observability -m 1 -E nodiscard "$IMG"
fi

# Empty, immutable mount point: if the image is not mounted, pods fail instead of
# silently writing to the root disk.
if ! mountpoint -q "$MNT"; then
  mkdir -p "$MNT"
  chattr +i "$MNT" 2>/dev/null || true
fi

cat > /etc/systemd/system/$UNIT <<UNIT
[Unit]
Description=Observability ext4 store (loop image on the exFAT data lake)
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
systemctl enable --now $UNIT

# One directory per local PV (k8s/observability-move/*-pvs.yaml). root:root 0700 until the
# migration copies data in; tar -p then restores each volume's original owner and mode.
for d in $DIRS; do install -d -m 0700 -o 0 -g 0 "$MNT/$d"; done
findmnt "$MNT"; df -h "$MNT"; ls -ln "$MNT"
