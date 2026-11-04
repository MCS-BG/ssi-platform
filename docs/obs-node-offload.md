# obs-node offload: everything back on gpu-node

## Live inventory (2026-10-12, 1:34 PM CT)

All app and stateful workloads already run on `gpu-node` since the observability move (PR #10). Their data lives in ext4 images on the data lake (`/mnt/ailab-data/observability/observability-store.ext4` and `/mnt/ailab-data/forgejo/forgejo-store.ext4`), with backups under `/mnt/ailab-data/backups`.

What is still scheduled on `obs-node`:

| Namespace | Pod | Owner | Requests | Limits | Actual | Volumes |
|---|---|---|---|---|---|---|
| monitoring-host | kps-prometheus-node-exporter | DaemonSet | 10m CPU, 24Mi | 64Mi | 1m, 11Mi | hostPath /proc, /sys, / |
| monitoring-host | otel-agent-agent | DaemonSet | 20m CPU, 48Mi | 192Mi | 8m, 40Mi | hostPath /var/log/pods |

No PVCs are bound on the obs-node. Eight old `local-path` PVs pointing at the obs-node are `Released` leftovers from before the move. This change does not touch them; deleting them needs separate approval.

## Capacity on gpu-node

- RAM: 14 GiB total, about 8.0 GiB used, 6.1 GiB available. Requests are 11.6 GiB (76% of allocatable).
- CPU: 16 cores, about 0.5 core used, 3.8 cores requested (23%).
- Disk: root 101 GB free; data lake 4.0 TB free.

The DaemonSets already run one copy on `gpu-node`, so the offload removes the obs-node copies and adds nothing to `gpu-node`. Net change on `gpu-node`: 0 MiB. Nothing needs to wait for the RAM upgrade.

## What changes

- `k8s/day-07-otel-agent-values.yaml`: drop the `ailab/role` toleration.
- `k8s/day-07-kube-prometheus-stack-values.yaml`: node-exporter gets node affinity `ailab/role DoesNotExist`.
- `scripts/obs-node-offload/offload.sh`: backs up node YAML, Helm values, and the pod list to `/mnt/ailab-data/backups/obs-node-offload/<stamp>`, upgrades both releases, waits for the obs-node to empty, then cordons it. The node stays joined.
- `scripts/obs-node-offload/rollback.sh <backup dir>`: uncordons the obs-node and restores the saved Helm values.

With node-exporter off the obs-node, the obs-node target from PR #11 (`<obs-node-ip>:9100`) goes away, so the Ansible apply for that PR is no longer needed.

## Run (on gpu-node, after approval)

```
git pull
sudo DRY_RUN=1 bash scripts/obs-node-offload/offload.sh   # prints every step, changes nothing
sudo bash scripts/obs-node-offload/offload.sh
k3s kubectl get pods -A -o wide --field-selector spec.nodeName=obs-node   # expect none
```

Rollback: `sudo bash scripts/obs-node-offload/rollback.sh /mnt/ailab-data/backups/obs-node-offload/<stamp>`
