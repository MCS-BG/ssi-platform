#!/usr/bin/env bash
# Create Forgejo's Secrets on the lab host from generated values. Nothing is printed or saved
# except the admin password, which goes to a root-only file for the operator to read once and then
# store in his password manager. Re-running keeps existing Secrets.
#   sudo ADMIN_USER=<name the operator chooses> bash scripts/forgejo/secrets.sh
set -euo pipefail
ADMIN_USER=${ADMIN_USER:?set ADMIN_USER (the operator chooses the admin username)}
K="k3s kubectl -n forgejo"
gen() { openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-32; }
if ! $K get secret forgejo-db >/dev/null 2>&1; then
  $K create secret generic forgejo-db --from-literal=password="$(gen)"
fi
if ! $K get secret forgejo-admin >/dev/null 2>&1; then
  umask 077; P=$(gen)
  $K create secret generic forgejo-admin --from-literal=username="$ADMIN_USER" --from-literal=password="$P"
  printf '%s\n' "$P" > /root/forgejo-admin-initial-password; unset P
  echo "Admin '$ADMIN_USER' created. Initial password: sudo cat /root/forgejo-admin-initial-password"
  echo "(Forgejo forces a change at first sign-in; delete the file afterwards.)"
fi
$K get secret forgejo-db forgejo-admin
