# Ansible: rebuild the lab nodes

Step 1 of the supported rebuild path (step 2 is OpenTofu in `infra/terraform/envs/lab-k3s`). Ansible turns a bare Ubuntu machine into a k3s node with the exact versions the lab runs today. OpenTofu then deploys everything that runs on the cluster.

| Role | Hosts | What it owns |
| --- | --- | --- |
| `common` | all nodes | base packages, time zone, unattended upgrades, key-only SSH drop-in, fail2ban, ufw (k3s ports only between the two node IPs), external data drive mount |
| `nvidia` | `gpu_nodes` (lab host) | NVIDIA driver check (595.91.07), NVIDIA Container Toolkit 1.20.1-1 from NVIDIA's apt repo |
| `k3s_server` | `k3s_server` (lab host) | k3s v1.36.4+k3s1, `/etc/rancher/k3s/config.yaml` with the node-ip pin, secrets encryption, Traefik off, NVIDIA runtime check |
| `k3s_agent` | `k3s_agent` (agent node) | k3s v1.36.4+k3s1 agent, join token file, server URL + node-ip pin, observability label and taint |

Pins live in `group_vars/all.yml`. Per-node IPs, labels, firewall peers and mounts live in `host_vars/`.

## The node-ip pin (why this exists)

DHCP moved the lab host from 192.0.2.71 to 192.0.2.93. k3s on the lab host still advertises .71 until it restarts, and the agent node's config and firewall still point at .71, so the agent node is `NotReady`. The fix:

1. On the router, add a DHCP reservation for each node's MAC (lab host 192.0.2.93, agent node 192.0.2.94).
2. Run this playbook. It writes `node-ip` into both k3s configs, points the agent at the new server URL, opens the firewall for the new IP and removes the stale .71 rules.
3. The handlers restart k3s and k3s-agent once (never in `--check` mode).

## Run it from the terminal

Prerequisites: `brew install ansible` (ships the `community.general` and `ansible.posix` collections; `ansible-galaxy collection install -r requirements.yml` if you use ansible-core alone), key-based SSH to the lab host, and sudo on both nodes (your password is asked once per run).

Tell SSH who you are on the nodes once, in `~/.ssh/config` on the terminal (not in this repo). Replace `<ssh-user>`:

```text
Host d
  User <ssh-user>
Host 192.0.2.94
  User <ssh-user>
  ProxyJump d
```

Terminal

```bash
cd ~/ssi-platform/infra/ansible
```

Terminal

```bash
cp inventory.example.ini inventory.ini
```

Check the syntax:

Terminal

```bash
ansible-playbook playbooks/site.yml --syntax-check
```

Dry run. sudo on the nodes needs your password, so Ansible asks once:

Terminal

```bash
ansible-playbook playbooks/site.yml --check --diff --ask-become-pass
```

Apply (only when the dry run shows what you expect):

Terminal

```bash
ansible-playbook playbooks/site.yml --diff --ask-become-pass
```

One node only:

Terminal

```bash
ansible-playbook playbooks/site.yml --check --diff --ask-become-pass --limit d
```

## What the dry run should show today

- Lab host: `changed` only for `/etc/rancher/k3s/config.yaml` (new file: the node-ip pin). Everything else `ok`.
- Agent node: `changed` for `/etc/rancher/k3s/config.yaml` (server URL .71 -> .93) and the firewall rules for the new lab host IP, plus deleting the .71 rules. If the agent node is unreachable it shows `UNREACHABLE`; fix the network first.
- After one real run, a second `--check` should report `changed=0`.

## Secrets

None are stored here. The join token is read from the server at run time (`no_log`) and written to a root-only file on the agent only when that file is missing. Do not put a become password in a file; use `--ask-become-pass`.
