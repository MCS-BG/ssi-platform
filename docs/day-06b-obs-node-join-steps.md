# Day 6b: Join the monitoring laptop as a CPU-only k3s agent

Goal: the monitoring laptop, already running Ubuntu, joins the lab cluster as a second node. It becomes a CPU-only **agent** (worker) named `obs-node`, labeled and tainted so that only the Day 7 observability workloads land on it. The lab host (`gpu-node`, 192.0.2.71) stays the only server (control plane) and keeps the GPU, the models and all existing `si-lab` workloads.

The security posture matches Day 1 and Day 2:

- key-only SSH, fail2ban and unattended upgrades on the monitoring node
- ufw on both machines with deny-by-default, opening only the k3s ports, and only between the two nodes
- the join token is copied from the server file to a root-only file on the monitoring node and never printed on screen or written in these notes
- the k3s version is pinned to the server's version, `v1.36.4+k3s1`

How to read these steps:

- **Terminal** = the terminal laptop (zsh, `kubectl` through the SSH tunnel with `KUBECONFIG=~/.kube/si-lab.yaml`).
- **Lab host** = an SSH session on the lab host (`ssh "$LAB"`).
- **monitoring node** = an SSH session on the monitoring node (`ssh "$OBS_NODE"`), or its local console for the first steps.
- Values in `<angle brackets>` are placeholders you fill in once.

Official references used:

- k3s requirements and inbound ports: https://docs.k3s.io/installation/requirements
- k3s agent flags (`--token-file`, `--node-label`, `--node-taint`, `--node-ip`, `--flannel-iface`): https://docs.k3s.io/cli/agent
- k3s tokens (server token = node-token, bootstrap tokens): https://docs.k3s.io/cli/token
- k3s config file and install script variables (`INSTALL_K3S_VERSION`): https://docs.k3s.io/installation/configuration
- Flannel options: https://docs.k3s.io/networking/basic-network-options
- Uninstall: https://docs.k3s.io/installation/uninstall
- monitoring node UEFI and Battery Limit: https://learn.microsoft.com/en-us/obs-node/manage-obs-node-uefi-settings and https://learn.microsoft.com/en-us/obs-node/battery-limit
- logind lid settings: https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html

## What you need before starting

- The monitoring node's Ubuntu username (for SSH) and the lab host's username.
- A network decision: Wi-Fi, or Ethernet through a USB-C adapter or a USB-C dock. The monitoring laptop has no built-in Ethernet port. Ethernet is better (see Pitfalls), but Wi-Fi works.
- A DHCP reservation for the monitoring node in your router, so its IP never changes. The node IP and the firewall rules below are tied to that IP.
- About 40 GB free on the monitoring node's Ubuntu root filesystem for images and Day 7 volumes.

## Step 1: Find the monitoring node's IP and interface

On the monitoring node console (or any shell on it):

monitoring node

```bash
ip -4 -br addr
hostname -I
ip route get 192.0.2.71
```

Expected output (your names and addresses will differ):

```text
lo               UNKNOWN        127.0.0.1/8
<wifi-iface>        UP             192.0.2.84/24
192.0.2.84
192.0.2.71 dev <wifi-iface> src 192.0.2.84 uid 1000
    cache
```

The `src` address in the last command is the monitoring node IP, and `dev` is the interface that reaches the lab host. A Wi-Fi interface usually starts with `wl`, a USB Ethernet adapter usually with `enx`. Write both down. If the address is not the reserved one yet, fix the DHCP reservation first and reconnect.

Set them once per session in the Terminal:

Terminal

```bash
export LAB=<lab-user>@192.0.2.71
export OBS_NODE=<obs-node-user>@<obs-node-ip>
```

Expected output: none.

## Step 2: SSH keys and Day 1 hardening on the monitoring node

First make sure SSH is installed and reachable. On the monitoring node console:

monitoring node

```bash
sudo apt update
sudo apt install -y openssh-server unattended-upgrades ufw fail2ban
sudo systemctl enable --now ssh fail2ban
systemctl is-active ssh fail2ban
```

Expected output: apt progress, then

```text
active
active
```

Copy your key from the Terminal and test it:

Terminal

```bash
ssh-copy-id "$OBS_NODE"
ssh "$OBS_NODE" 'hostname && whoami'
```

Expected output: `Number of key(s) added: 1`, then the monitoring node hostname and your Ubuntu username, without a password prompt on the second command.

Keep that SSH session working and apply the same key-only drop-in as Day 1. On the monitoring node (through `ssh "$OBS_NODE"`):

monitoring node

```bash
sudo dpkg-reconfigure -plow unattended-upgrades
sudo tee /etc/ssh/sshd_config.d/99-lab-hardening.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF
sudo sshd -t && sudo systemctl reload ssh
sudo fail2ban-client status sshd
```

Expected output: answer **Yes** in the unattended-upgrades dialog; `sshd -t` prints nothing; fail2ban shows `Status for the jail: sshd` with `Currently banned: 0`.

Then, from a **second** Terminal tab, confirm key login still works before closing the first session (the Day 1 two-window rule):

Terminal

```bash
ssh "$OBS_NODE" 'echo key-login-ok'
```

Expected output:

```text
key-login-ok
```

Hostnames must be unique in a k3s cluster. If the monitoring node happens to have the same hostname as the lab host, rename it (optional otherwise, since the node name is set explicitly later):

monitoring node

```bash
hostnamectl --static
sudo hostnamectl set-hostname obs-node
```

Expected output: the old hostname, then nothing.

## Step 3: Pre-checks on the cluster

Terminal

```bash
kubectl get nodes -o wide
kubectl get node gpu-node -o jsonpath='{.metadata.annotations.flannel\.alpha\.coreos\.com/public-ip}{"\n"}'
kubectl get ds -A
kubectl top nodes
```

Expected output:

- one node, `gpu-node`, `Ready`, `v1.36.4+k3s1`, INTERNAL-IP `192.0.2.71`
- the flannel public IP is `192.0.2.71` (flannel on the server uses the LAN interface, so VXLAN will work between the two machines)
- the DaemonSet list: note each one. Anything without a toleration for the new taint (for example the NVIDIA device plugin in `gpu-system`) will stay off the monitoring node, which is what we want.
- `kubectl top nodes` shows CPU and memory for `gpu-node`. If it errors, metrics-server is not working today; note that, it does not block the join.

Check the monitoring node's resources:

Terminal

```bash
ssh "$OBS_NODE" 'free -h && nproc && df -h / && lsb_release -ds'
```

Expected output (example for an 8 GB model):

```text
               total        used        free      shared  buff/cache   available
Mem:           7.6Gi       1.9Gi       4.1Gi       ...
Swap:          ...
8
Filesystem      Size  Used Avail Use% Mounted on
/dev/nvme0n1p5  120G   20G   94G  18% /
Ubuntu 26.04 LTS
```

Write down the total memory (8 GB or 16 GB). Day 7 sizing depends on it.

## Step 4: Laptop pitfalls to fix before joining

A node that sleeps, reboots into Windows or drops Wi-Fi goes `NotReady`, and its pods get evicted after about 5 minutes. Fix these first.

### 4a. Lid close and suspend

Tell logind to ignore the lid, and mask every sleep target so nothing (GNOME idle settings included) can suspend the machine. On the monitoring node:

monitoring node

```bash
sudo mkdir -p /etc/systemd/logind.conf.d
sudo tee /etc/systemd/logind.conf.d/10-lab-lid.conf >/dev/null <<'EOF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
systemctl is-enabled sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Expected output: four `Created symlink ... → /dev/null` lines, then

```text
masked
masked
masked
masked
```

The logind change applies after the reboot in step 4c. (Restarting `systemd-logind` right now would also work, but it ends the graphical session on the monitoring node.)

### 4b. Go headless (recommended, saves roughly 1 GB of RAM)

The GNOME desktop uses around 1 to 1.5 GB of RAM that Day 7 needs, especially on an 8 GB model. Booting to text mode keeps the desktop installed; you can still start it by hand.

monitoring node

```bash
sudo systemctl set-default multi-user.target
systemctl get-default
```

Expected output:

```text
Created symlink '/etc/systemd/system/default.target' → '/usr/lib/systemd/system/multi-user.target'.
multi-user.target
```

To go back later: `sudo systemctl set-default graphical.target`.

### 4c. Make Ubuntu the default boot entry

Check GRUB and the UEFI boot order. On the monitoring node:

monitoring node

```bash
grep -E '^GRUB_(DEFAULT|TIMEOUT)=' /etc/default/grub
sudo efibootmgr
```

Expected output (entry numbers differ):

```text
GRUB_DEFAULT=0
GRUB_TIMEOUT=5
BootCurrent: 0003
BootOrder: 0003,0000,0001
Boot0000* Windows Boot Manager
Boot0003* ubuntu
```

What to fix:

- `GRUB_DEFAULT` should be `0` (Ubuntu is the first GRUB entry). If it is `saved` or something else, set it to 0 with `sudo sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=0/' /etc/default/grub` and run `sudo update-grub`.
- `BootOrder` should start with the `ubuntu` entry. If `Windows Boot Manager` is first, put Ubuntu first, using your entry numbers:

monitoring node

```bash
sudo efibootmgr -o 0003,0000
sudo efibootmgr | grep BootOrder
```

Expected output:

```text
BootOrder: 0003,0000
```

Also check in **monitoring node UEFI** (shut down, then hold Volume Up and press Power): under **Boot configuration**, Ubuntu first. Windows feature updates and monitoring node firmware updates can put Windows Boot Manager back in front, so re-check after any Windows session.

In **Windows** (once): turn off Fast Startup, because a hibernated Windows can leave the Wi-Fi card and the clock in a bad state for Ubuntu. In an administrator PowerShell run `powercfg /h off`.

Then reboot the monitoring node and confirm it comes back by itself in Ubuntu:

monitoring node

```bash
sudo reboot
```

Terminal

```bash
ssh "$OBS_NODE" 'systemctl get-default && systemctl is-enabled suspend.target && timedatectl show -p NTPSynchronized'
```

Expected output (after a minute or two):

```text
multi-user.target
masked
NTPSynchronized=yes
```

`NTPSynchronized=yes` matters: TLS to the k3s API fails if the clock is off, and dual boot with Windows can shift the hardware clock by your UTC offset. If it says `no`, run `sudo timedatectl set-ntp true` and check again.

### 4d. Battery and heat

The monitoring node will be plugged in around the clock. Many laptops have a **Battery Limit** setting that stops charging at 50%: in monitoring node UEFI, **Boot configuration > Advanced Options > Enable Battery Limit**. On some models this setting only works with the firmware update Microsoft shipped in 2024 (monitoring node UEFI 24.203.143.0), which arrives through Windows Update, so boot Windows occasionally for firmware. Leave the lid slightly open or the laptop on a hard obs-node; it vents better than closed on a desk mat.

### 4e. Wi-Fi vs Ethernet

- **Ethernet (USB-C adapter or USB-C dock): preferred.** Lower latency and no power-save drops. Flannel VXLAN and the kubelet traffic are chatty, and Wi-Fi dropouts show up as `NotReady` flaps. Use the `enx...` interface from step 1.
- **Wi-Fi: works if you do three things.** Make the connection system-wide with the password stored in the system file (so it connects at boot without anyone logging in), keep it on autoconnect, and turn Wi-Fi power saving off.

For Wi-Fi, on the monitoring node:

monitoring node

```bash
nmcli -f NAME,DEVICE,TYPE connection show --active
WIFI_CONN='<connection-name-from-the-list>'
sudo nmcli connection modify "$WIFI_CONN" connection.permissions '' connection.autoconnect yes 802-11-wireless.powersave 2 802-11-wireless-security.psk-flags 0
sudo nmcli connection up "$WIFI_CONN"
nmcli -f connection.permissions,connection.autoconnect,802-11-wireless.powersave connection show "$WIFI_CONN"
```

Expected output: the active connection list, `Connection successfully activated`, then

```text
connection.permissions:                 --
connection.autoconnect:                 yes
802-11-wireless.powersave:              2 (disable)
```

If the Wi-Fi password was stored in your user keyring, `nmcli connection up` asks for it once; after that it lives in `/etc/NetworkManager/system-connections/` (root-only).

Whichever you choose, the IP must match the DHCP reservation, because it goes into the k3s config and the firewall rules. If you switch between Wi-Fi and Ethernet later, the node IP and the interface change: update `/etc/rancher/k3s/config.yaml` and the ufw rules on both machines.

## Step 5: Firewall rules on both nodes

k3s needs these between the nodes (from the k3s requirements page):

| Port | Protocol | Direction | Why |
|---|---|---|---|
| 6443 | TCP | agent → server | Kubernetes API and the agent's supervisor connection |
| 8472 | UDP | both ways | Flannel VXLAN (pod-to-pod traffic across nodes). Never expose it beyond the nodes. |
| 10250 | TCP | both ways | kubelet (metrics-server and Prometheus scrape it) |
| 9100 | TCP | monitoring node → lab host | node-exporter on the lab host, scraped by Prometheus on the monitoring node (Day 7) |

The k3s docs also say to allow the pod network `10.42.0.0/16` and the service network `10.43.0.0/16` when ufw is on. Pods reaching their own node's IP (for example Prometheus scraping the monitoring node's own kubelet) arrive with a pod source address, so without these rules they are dropped.

Set the monitoring node IP in the lab host session, then add the rules. On the lab host (`ssh "$LAB"`):

Lab host

```bash
OBS_NODE_IP='<obs-node-ip>'
sudo ufw allow from "${OBS_NODE_IP:?set OBS_NODE_IP first}" to any port 6443 proto tcp comment 'k3s api from obs-node'
sudo ufw allow from "$OBS_NODE_IP" to any port 8472 proto udp comment 'flannel vxlan from obs-node'
sudo ufw allow from "$OBS_NODE_IP" to any port 10250 proto tcp comment 'kubelet from obs-node'
sudo ufw allow from "$OBS_NODE_IP" to any port 9100 proto tcp comment 'node-exporter from obs-node'
sudo ufw allow from 10.42.0.0/16 to any comment 'k3s pods'
sudo ufw allow from 10.43.0.0/16 to any comment 'k3s services'
sudo ufw status numbered
```

Expected output: `Rule added` for each line (or `Skipping adding existing rule` for the last two if Day 2 already added them), then a list that contains:

```text
     To                         Action      From
     --                         ------      ----
[ 1] OpenSSH                    ALLOW IN    Anywhere
[ 2] 6443/tcp                   ALLOW IN    <obs-node-ip>               # k3s api from obs-node
[ 3] 8472/udp                   ALLOW IN    <obs-node-ip>               # flannel vxlan from obs-node
[ 4] 10250/tcp                  ALLOW IN    <obs-node-ip>               # kubelet from obs-node
[ 5] 9100/tcp                   ALLOW IN    <obs-node-ip>               # node-exporter from obs-node
[ 6] Anywhere                   ALLOW IN    10.42.0.0/16               # k3s pods
[ 7] Anywhere                   ALLOW IN    10.43.0.0/16               # k3s services
```

Port 6443 stays closed to everything except the monitoring node. Your Terminal still reaches the API only through the SSH tunnel, as on Day 2.

On the monitoring node (`ssh "$OBS_NODE"`), deny by default, allow SSH, and allow only the lab host to reach VXLAN and the kubelet:

monitoring node

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow from 192.0.2.71 to any port 8472 proto udp comment 'flannel vxlan from lab host'
sudo ufw allow from 192.0.2.71 to any port 10250 proto tcp comment 'kubelet from lab host'
sudo ufw allow from 10.42.0.0/16 to any comment 'k3s pods'
sudo ufw allow from 10.43.0.0/16 to any comment 'k3s services'
sudo ufw --force enable
sudo ufw status numbered
```

Expected output: `Default incoming policy changed to 'deny'`, `Rule added` lines, `Firewall is active and enabled on system startup`, then:

```text
Status: active

     To                         Action      From
     --                         ------      ----
[ 1] OpenSSH                    ALLOW IN    Anywhere
[ 2] 8472/udp                   ALLOW IN    192.0.2.71               # flannel vxlan from lab host
[ 3] 10250/tcp                  ALLOW IN    192.0.2.71               # kubelet from lab host
[ 4] Anywhere                   ALLOW IN    10.42.0.0/16               # k3s pods
[ 5] Anywhere                   ALLOW IN    10.43.0.0/16               # k3s services
```

(plus the `(v6)` duplicates of the OpenSSH rule).

Quick reachability test from the monitoring node to the API port:

monitoring node

```bash
curl -sk -o /dev/null -w '%{http_code}\n' https://192.0.2.71:6443/ping
```

Expected output:

```text
200
```

Anything else (a timeout, `000`) means the lab host firewall rule or the IP is wrong. Fix that before continuing.

## Step 6: Move the join token without printing it

The agent authenticates with the cluster token. It lives in `/var/lib/rancher/k3s/server/node-token` on the lab host (root-only, same value as `/var/lib/rancher/k3s/server/token`). It is effectively a cluster-admin credential, so it never appears on screen, in shell history or in these notes. It travels as: root file on the lab host, then a temporary user file (mode 600), then an SSH pipe, then a temporary user file on the monitoring node, then a root-only file.

On the lab host, copy it to a private temporary file:

Lab host

```bash
(umask 077 && sudo cat /var/lib/rancher/k3s/server/node-token > ~/.k3s-join-token)
ls -l ~/.k3s-join-token
grep -c '^K10' ~/.k3s-join-token
```

Expected output:

```text
-rw------- 1 <lab-user> <lab-user> 1xx <date> /home/<lab-user>/.k3s-join-token
1
```

`1` confirms it is the secure `K10<ca-hash>::...` format, which also lets the agent verify the server's CA.

Relay it from the Terminal through a pipe (nothing is printed or stored on the terminal laptop), then remove the lab host copy in the same command:

Terminal

```bash
ssh "$LAB" 'cat ~/.k3s-join-token && rm -f ~/.k3s-join-token' | ssh "$OBS_NODE" 'umask 077 && cat > ~/.k3s-join-token'
ssh "$LAB" 'ls ~/.k3s-join-token 2>&1 | head -1'
```

Expected output: nothing from the first command, then `ls: cannot access '/home/<lab-user>/.k3s-join-token': No such file or directory`.

On the monitoring node, move it to a root-only file and delete the temporary copy:

monitoring node

```bash
grep -c '^K10' ~/.k3s-join-token
sudo install -D -m 600 -o root -g root ~/.k3s-join-token /etc/rancher/k3s/join-token
rm -f ~/.k3s-join-token
sudo ls -l /etc/rancher/k3s/join-token
```

Expected output:

```text
1
-rw------- 1 root root 1xx <date> /etc/rancher/k3s/join-token
```

Safer alternative: instead of the permanent server token, give the monitoring node a short-lived, agent-only bootstrap token. On the lab host run `(umask 077 && sudo k3s token create --ttl 1h --description obs-node-join > ~/.k3s-join-token)` in place of the `sudo cat` line above; everything else is identical. It expires after an hour. Per the k3s token docs and release notes, an agent that joined with it keeps working across restarts, but if you ever delete the `obs-node` Node object you need a fresh token to rejoin.

## Step 7: Write the agent config (label, taint, IP, interface)

Labels and taints set through `node-label` / `node-taint` are only applied when the node **registers**, so they go in the config file before the first start. Here the label marks the node's role and the taint keeps every pod off the monitoring node unless it explicitly tolerates it.

Why the taint is needed here, not just nice to have: the existing `si-lab` workloads have no node pinning. `rag-worker` mounts a hostPath volume on `/mnt/ailab-data` that only exists on the lab host, and `mcp-server`/`fo-mock` would happily reschedule onto the monitoring node after a restart. With the taint, only the Day 7 observability pods (which carry the matching toleration) land on it.

On the monitoring node, set the IP and interface from step 1, then write the file:

monitoring node

```bash
OBS_NODE_IP='<obs-node-ip>'
OBS_NODE_IFACE='<interface-from-step-1>'
sudo tee /etc/rancher/k3s/config.yaml >/dev/null <<EOF
server: "https://192.0.2.71:6443"
token-file: "/etc/rancher/k3s/join-token"
node-name: "obs-node"
node-ip: "${OBS_NODE_IP:?set OBS_NODE_IP first}"
flannel-iface: "${OBS_NODE_IFACE:?set OBS_NODE_IFACE first}"
node-label:
  - "ailab/role=observability"
node-taint:
  - "ailab/role=observability:NoSchedule"
EOF
sudo chmod 600 /etc/rancher/k3s/config.yaml
sudo cat /etc/rancher/k3s/config.yaml
```

Expected output: the file with your real IP and interface (and no token in it, only the path):

```text
server: "https://192.0.2.71:6443"
token-file: "/etc/rancher/k3s/join-token"
node-name: "obs-node"
node-ip: "<obs-node-ip>"
flannel-iface: "<interface>"
node-label:
  - "ailab/role=observability"
node-taint:
  - "ailab/role=observability:NoSchedule"
```

## Step 8: Install the k3s agent, pinned to the server version

`sh -s - agent` tells the install script to set up the `k3s-agent` service; the server URL and token file come from the config file, so no secret is passed on the command line or stored in the service environment file.

monitoring node

```bash
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='v1.36.4+k3s1' sh -s - agent
systemctl is-active k3s-agent
```

Expected output (abridged):

```text
[INFO]  Using v1.36.4+k3s1 as release
[INFO]  Downloading hash https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/sha256sum-amd64.txt
[INFO]  Downloading binary https://github.com/k3s-io/k3s/releases/download/v1.36.4+k3s1/k3s
[INFO]  Verifying binary download
[INFO]  Installing k3s to /usr/local/bin/k3s
...
[INFO]  systemd: Enabling k3s-agent unit
[INFO]  systemd: Starting k3s-agent
active
```

If it is not `active` after a minute, look at the log:

monitoring node

```bash
sudo journalctl -u k3s-agent --since '-5 min' --no-pager | tail -n 30
```

Typical messages and fixes:

- `connection refused` / `i/o timeout` to `192.0.2.71:6443`: the lab host ufw rule or the IP (step 5).
- `token CA hash does not match`: the token file is wrong or truncated; redo step 6.
- `x509: certificate has expired or is not yet valid`: the clock (step 4c).
- `duplicate hostname` / node password rejected: another node registered with the name `obs-node` before. Run `kubectl delete node obs-node` in the Terminal, then `sudo systemctl restart k3s-agent`.

## Step 9: Verify the node, its label and its taint

Terminal

```bash
kubectl get nodes -o wide
kubectl get node obs-node -L ailab/role
kubectl get node obs-node -o jsonpath='{.spec.taints}{"\n"}'
```

Expected output:

```text
NAME      STATUS   ROLES           AGE   VERSION        INTERNAL-IP    EXTERNAL-IP   OS-IMAGE           KERNEL-VERSION   CONTAINER-RUNTIME
d         Ready    control-plane   6d    v1.36.4+k3s1   192.0.2.71   <none>        Ubuntu 26.04 LTS   ...              containerd://...
obs-node   Ready    <none>          1m    v1.36.4+k3s1   <obs-node-ip>   <none>        Ubuntu ...         ...              containerd://...

NAME      STATUS   ROLES    AGE   VERSION        ROLE
obs-node   Ready    <none>   1m    v1.36.4+k3s1   observability

[{"effect":"NoSchedule","key":"ailab/role","value":"observability"}]
```

The ROLES column for `gpu-node` may read differently depending on the k3s build; what matters is both nodes `Ready`, the same version, and the monitoring node INTERNAL-IP equal to the reserved address.

Check that nothing from `si-lab` moved and that only node agents run on the monitoring node:

Terminal

```bash
kubectl get pods -A -o wide --field-selector spec.nodeName=obs-node
kubectl -n si-lab get pods -o wide
```

Expected output: on `obs-node`, at most DaemonSet pods that tolerate all taints (often none yet; Day 7 adds node-exporter); every `si-lab` pod still on `gpu-node`.

## Step 10: Test cross-node networking with a throwaway pod

This pod tolerates the taint and targets the monitoring node, then resolves a name through CoreDNS, which runs on `gpu-node`. Success proves the Flannel VXLAN path works in both directions.

Terminal

```bash
kubectl -n default run obs-node-net-test --image=busybox:1.37 --restart=Never --rm -i --overrides='{"spec":{"nodeSelector":{"ailab/role":"observability"},"tolerations":[{"key":"ailab/role","operator":"Equal","value":"observability","effect":"NoSchedule"}]}}' -- nslookup kubernetes.default.svc.cluster.local
```

Expected output:

```text
Server:         10.43.0.10
Address:        10.43.0.10:53

Name:   kubernetes.default.svc.cluster.local
Address: 10.43.0.1

pod "obs-node-net-test" deleted
```

A timeout here, with the node `Ready`, almost always means UDP 8472 is blocked on one side or `flannel-iface` points at the wrong interface.

Finally, check metrics-server can reach the monitoring node kubelet (port 10250 from the lab host):

Terminal

```bash
kubectl top nodes
```

Expected output: both `gpu-node` and `obs-node` with CPU and memory numbers (the monitoring node can take a minute to show up).

## Rollback

Remove the monitoring node from the cluster cleanly:

Terminal

```bash
kubectl drain obs-node --ignore-daemonsets --delete-emptydir-data
kubectl delete node obs-node
```

monitoring node

```bash
sudo /usr/local/bin/k3s-agent-uninstall.sh
sudo rm -f /etc/rancher/k3s/join-token /etc/rancher/k3s/config.yaml
```

Lab host

```bash
sudo ufw status numbered
```

Then delete the four `from <obs-node-ip>` rules by number with `sudo ufw delete <n>` (highest number first).

Expected output: `node/obs-node drained`, `node "obs-node" deleted`, the uninstall script's cleanup messages, and a ufw list without the monitoring node rules.

## Pitfalls summary

- **Suspend or lid close** takes the node `NotReady` and its pods are evicted after about 5 minutes. Step 4a.
- **Rebooting into Windows** after an update. Keep Ubuntu first in GRUB, efibootmgr and monitoring node UEFI, turn off Fast Startup, and re-check after Windows or firmware updates. Step 4c.
- **Clock skew after dual boot** breaks TLS. Keep NTP on. Step 4c.
- **Wi-Fi power saving and per-user Wi-Fi connections** make the node flap or stay offline until someone logs in. Step 4e. Ethernet through a USB-C adapter or dock avoids both.
- **IP changes** break the node IP, Flannel and the firewall rules. Use a DHCP reservation.
- **Labels and taints only apply at registration.** To change them later, use `kubectl label` / `kubectl taint`, or delete the node and let it re-register.
- **No taint = surprise scheduling.** Without it, `rag-worker` could move to the monitoring node and fail on the missing `/mnt/ailab-data` hostPath.
- **Desktop RAM.** The GNOME session eats memory Day 7 needs. Step 4b.
