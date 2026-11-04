#!/usr/bin/env bash
# Install one Forgejo Actions runner on the lab host as its own non-root user and systemd
# service, mirroring the GitHub runners (staging names say staging; Prod names are neutral).
#   staging: user fjrunner-staging, runner si-lab-staging-runner, label si-lab-staging,
#            ServiceAccount si-staging/forgejo-staging-deployer
#   Prod:    user fjrunner, runner si-lab-runner, label si-lab,
#            ServiceAccount si-lab/forgejo-deployer
# The runner registration token (Forgejo: Site administration > Actions > Runners > Create new
# runner, or repo Settings > Actions > Runners) is read from stdin, never from argv or files.
#   printf '%s' "$TOKEN" | sudo bash scripts/forgejo/runner-setup.sh staging
#   printf '%s' "$TOKEN" | sudo bash scripts/forgejo/runner-setup.sh prod
set -euo pipefail
STAGE=${1:?staging|prod}
VERSION=${RUNNER_VERSION:-13.2.0}   # https://code.forgejo.org/forgejo/runner/releases (v13.2.0, 2026-09-18)
INSTANCE=${FORGEJO_URL:-https://git.<tailnet>.ts.net}
case "$STAGE" in
  staging) U=fjrunner-staging; NAME=si-lab-staging-runner; LABEL=si-lab-staging; NS=si-staging; SA=forgejo-staging-deployer ;;
  prod)    U=fjrunner;         NAME=si-lab-runner;         LABEL=si-lab;         NS=si-lab;     SA=forgejo-deployer ;;
  *) exit 2 ;;
esac
[[ $EUID -eq 0 ]] || { echo "run with sudo"; exit 1; }
read -r TOKEN
id "$U" >/dev/null 2>&1 || useradd --create-home --shell /bin/bash "$U"
chmod 700 "/home/$U"
H=/home/$U

# Binary (checksum-verified)
BIN=/usr/local/bin/forgejo-runner-$VERSION
if [[ ! -x $BIN ]]; then
  base=https://code.forgejo.org/forgejo/runner/releases/download/v$VERSION
  curl -fsSL -o /tmp/fr "$base/forgejo-runner-$VERSION-linux-amd64"
  curl -fsSL -o /tmp/fr.sha256 "$base/forgejo-runner-$VERSION-linux-amd64.sha256"
  echo "$(cut -d' ' -f1 /tmp/fr.sha256)  /tmp/fr" | sha256sum -c -
  install -m 0755 /tmp/fr "$BIN"; rm -f /tmp/fr /tmp/fr.sha256
fi

# Kubeconfig for this stage's ServiceAccount (mode 600, owner $U)
T=$(k3s kubectl -n "$NS" get secret "$SA-token" -o jsonpath='{.data.token}' | base64 -d)
CA=$(k3s kubectl -n "$NS" get secret "$SA-token" -o jsonpath='{.data.ca\.crt}')
install -d -o "$U" -g "$U" -m 700 "$H/.kube"
umask 077
printf 'apiVersion: v1\nkind: Config\nclusters:\n- name: lab\n  cluster: {server: "https://127.0.0.1:6443", certificate-authority-data: %s}\nusers:\n- name: %s\n  user: {token: %s}\ncontexts:\n- name: sdlc\n  context: {cluster: lab, user: %s, namespace: %s}\ncurrent-context: sdlc\n' \
  "$CA" "$SA" "$T" "$SA" "$NS" > /tmp/kc.$$; unset T
install -o "$U" -g "$U" -m 600 /tmp/kc.$$ "$H/.kube/config"; rm -f /tmp/kc.$$

# Register (host executor: jobs run as $U on the lab host, like the GitHub runners)
install -d -o "$U" -g "$U" -m 700 "$H/runner"
if [[ ! -f $H/runner/.runner ]]; then
  sudo -u "$U" env RT="$TOKEN" sh -c "cd $H/runner && $BIN register --no-interactive \
    --instance '$INSTANCE' --token \"\$RT\" --name '$NAME' --labels '$LABEL:host'"
fi
unset TOKEN
sudo -u "$U" sh -c "cd $H/runner && $BIN generate-config > config.yml"
# Set runner.envs to exactly KUBECONFIG (drops the sample entries generate-config writes)
python3 - "$H/runner/config.yml" "$H/.kube/config" <<'PY'
import sys, yaml
path, kc = sys.argv[1:3]
cfg = yaml.safe_load(open(path))
cfg.setdefault("runner", {})["envs"] = {"KUBECONFIG": kc}
yaml.safe_dump(cfg, open(path, "w"), sort_keys=False)
PY
chown "$U:$U" "$H/runner/config.yml"; chmod 600 "$H/runner/config.yml"

cat > /etc/systemd/system/forgejo-runner-$NAME.service <<UNIT
[Unit]
Description=Forgejo Actions runner $NAME
After=network-online.target
Wants=network-online.target

[Service]
User=$U
WorkingDirectory=$H/runner
ExecStart=$BIN daemon --config $H/runner/config.yml
Restart=on-failure
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$H
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now "forgejo-runner-$NAME.service"
systemctl is-active "forgejo-runner-$NAME.service"
