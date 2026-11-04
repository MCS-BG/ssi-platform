#!/usr/bin/env bash
# Forgejo storage on the data lake drive, done safely (run on the lab host, ONLY after the operator
# approves the disk change). Idempotent.
#
# Why: /mnt/ailab-data is exFAT. exFAT has no Unix owners, modes, or symlinks, so Git repos
# (hooks need +x, packs need permissions) and PostgreSQL (refuses a data dir it cannot chmod
# 0700) must not live on it directly. Instead, one ext4 filesystem image FILE lives on the drive
# and is loop-mounted at /srv/forgejo. To exFAT it is a single large file; inside it, Forgejo and
# PostgreSQL get a real Linux filesystem with journaling.
#
#   sudo SIZE=200G bash infra/forgejo/storage-setup.sh
set -euo pipefail
SIZE=${SIZE:-200G}
IMG_DIR=/mnt/ailab-data/forgejo
IMG=$IMG_DIR/forgejo-store.ext4
MNT=/srv/forgejo
UNIT=srv-forgejo.mount

[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
findmnt -no FSTYPE /mnt/ailab-data | grep -qx exfat || { echo "data lake not mounted"; exit 1; }

mkdir -p "$IMG_DIR" /mnt/ailab-data/backups/forgejo
if [[ ! -f "$IMG" ]]; then
  echo "Allocating $SIZE image (exFAT has no sparse files; this writes the full size)"
  fallocate -l "$SIZE" "$IMG" 2>/dev/null || truncate -s "$SIZE" "$IMG"
  mkfs.ext4 -q -F -L forgejo -m 1 "$IMG"
fi

# Empty, immutable mount point: if the image is ever not mounted, nothing can write to the
# root disk by mistake (pods fail instead of silently using the wrong disk).
if ! mountpoint -q "$MNT"; then
  mkdir -p "$MNT"
  chattr +i "$MNT" 2>/dev/null || true
fi

cat > /etc/systemd/system/$UNIT <<UNIT
[Unit]
Description=Forgejo ext4 store (loop image on the exFAT data lake)
Requires=mnt-ailab\x2ddata.mount
After=mnt-ailab\x2ddata.mount
Before=k3s.service

[Mount]
What=$IMG
Where=$MNT
Type=ext4
Options=loop,noatime,errors=remount-ro

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now $UNIT

# Directories for the two local PersistentVolumes (k8s/forgejo/00-namespace-storage.yaml)
install -d -m 0750 -o 1000 -g 1000 $MNT/data        # Forgejo rootless runs as uid 1000
install -d -m 0700 -o 70   -g 70   $MNT/postgres    # postgres:alpine runs as uid 70
findmnt "$MNT"; df -h "$MNT"; ls -ln "$MNT"
