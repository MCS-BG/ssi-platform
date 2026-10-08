# Day 1 — Host hardening before Kubernetes

*Series: AI Ops Homelab · Project: `ssi-platform` · Activity: `day-01-host-hardening`*

*Azure-first learning path. Local lab first; the same ideas promote to AKS later. Names and IPs below are placeholders.*

## Why harden before you install k3s

A single-node k3s box on a laptop is still a network service: SSH, later an API server, later model endpoints. Security bolted on after "hello world" usually means open NodePorts, password SSH, and a world-readable kubeconfig.

This post is the host baseline applied on an Ubuntu laptop **before** any cluster install: automatic security updates, firewall, fail2ban, and SSH key-only access from a Mac. Kubernetes is day 2 — not day 1.

## Lab roles

| Machine | Role |
| --- | --- |
| Mac (daily driver) | IDE, GitHub, SSH client, tunnels to the lab |
| Ubuntu laptop (GPU host) | Future k3s node — the only machine that will run the cluster |
| Optional thin client | Spare; not in this path |

**Wording note:** "On the lab host" means run commands as the Ubuntu user on that machine. That is usually a terminal after `ssh labuser@<lab-lan-ip>` — not sitting at the laptop keyboard. Use the keyboard only if remote SSH breaks.

## What we installed

```bash
sudo apt update
sudo apt install -y unattended-upgrades ufw fail2ban openssh-server
sudo dpkg-reconfigure -plow unattended-upgrades   # choose Yes
```

If `apt` complains about a broken third-party repo (for example a stale Microsoft `.sources` file), finish the security packages first. Fix `/etc/apt/sources.list.d/` later.

## Firewall (UFW)

Allow SSH **before** enabling the firewall.

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw --force enable
sudo ufw status verbose
```

You want: Status **active**, default deny incoming / allow outgoing, and `22/tcp (OpenSSH) ALLOW IN`.

Typo trap: `sudo allow OpenSSH` fails. It must be `sudo ufw allow OpenSSH`.

## fail2ban

```bash
sudo systemctl enable --now fail2ban
sudo systemctl status fail2ban --no-pager
sudo fail2ban-client status sshd
```

The `sshd` jail should be present. Zero bans on a fresh home lab is normal.

## SSH keys: Mac → lab host (without locking yourself out)

### Create the key on the Mac

```bash
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "lab-client"
```

### Confirm reachability

On Ubuntu: `ip -4 addr` (note the LAN address).  
On Mac: `ping <lab-lan-ip>`.

### Install the public key and test

```bash
ssh-copy-id labuser@<lab-lan-ip>
ssh labuser@<lab-lan-ip>
```

Use the **Ubuntu** username on the right of `@`. Your Mac account name is only who you are locally.

### The two-window rule

1. Keep the first successful key SSH session **open**.
2. Open a **second** terminal and `ssh` again with the key.
3. Only when the second session works, disable password authentication.
4. If something goes wrong, the open session (or the Ubuntu local console) is recovery — dual-boot Windows does not fix Ubuntu SSH.

If a terminal SSH session freezes: pause, then type `~.` (tilde then period), or quit `ssh` / Terminal from Activity Monitor. A frozen client is usually not a bricked lab.

## Disable password SSH (drop-in config)

Ubuntu's main `sshd_config` often has `#PasswordAuthentication yes`. Commented means "default," and the default is still **yes**. Prefer a drop-in:

```bash
sudo cp /etc/ssh/sshd_config /etc/ssh/sshd_config.bak

sudo tee /etc/ssh/sshd_config.d/99-lab-hardening.conf >/dev/null <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
EOF

sudo sshd -t && sudo systemctl reload ssh
cat /etc/ssh/sshd_config.d/99-lab-hardening.conf
```

Keep an existing SSH session open. From a **new** terminal:

```bash
ssh labuser@<lab-lan-ip>
```

Optional proof that passwords are rejected:

```bash
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no labuser@<lab-lan-ip>
```

That should fail closed.

Avoid multiline `sed` edits pasted from chat — line wraps produce `unterminated 's' command` and change nothing.

## Day 1 checklist

- [ ] unattended-upgrades enabled
- [ ] UFW active; OpenSSH allowed; default deny incoming
- [ ] fail2ban running; sshd jail on
- [ ] Ed25519 key from Mac; `ssh-copy-id` succeeded
- [ ] Second key login verified before closing the first session
- [ ] `99-lab-hardening.conf` sets `PasswordAuthentication no`
- [ ] New SSH login still works after `systemctl reload ssh`

## What day 1 does *not* include

- No Kubernetes, no GPU operator, no public model ports
- No exposure of the home lab to Copilot Studio / Cowork (enterprise tools stay behind Azure + Entra later)
- Full apt cleanup and pending upgrades can wait until SSH is solid

## If this were cloud (short delta)

| Home lab host | Azure (AKS path later) | AWS (interview delta) |
| --- | --- | --- |
| UFW on the laptop | NSG / Azure Firewall + private API | Security groups + private API |
| fail2ban on SSH | Prefer no public SSH; Bastion / Private Link | SSM Session Manager or bastion |
| SSH tunnel to services | Private endpoints + Entra | PrivateLink + IAM |
| Local kubeconfig over SSH | AAD-integrated AKS + least privilege | EKS + IAM authenticator |

Same idea: shrink the attack surface before workloads exist.

## Next: day 2 (`day-02-secure-k3s`)

1. Optional: fix broken apt sources, `apt upgrade`, reboot, re-check SSH
2. Install k3s with `--write-kubeconfig-mode 600`, `--secrets-encryption`, and Traefik disabled until needed
3. Use kubectl from the Mac over an SSH tunnel — do not open `6443` in UFW to the world
4. Create `si-lab` / `gpu-system` namespaces; enforce pod-security baseline on `si-lab`
5. Only then: NVIDIA toolkit for k3s' containerd, device plugin, smoke pod, ClusterIP + port-forward

---

**Publish tips:** paste into Medium; add a cover image; do not attach raw terminal screenshots that show real usernames, LAN IPs, MAC addresses, or key fingerprints.
