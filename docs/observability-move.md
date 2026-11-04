# Moving Langfuse and the monitoring stack from obs-node to gpu-node

Everything the obs-node runs for observability moves to node `gpu-node` (the GPU laptop), with its data on the
data lake drive. Only the two per-node DaemonSets, `node-exporter` and `otel-agent`, stay on the
obs-node for as long as it is in the cluster.

| Phase | Moves | Stateful volumes |
|---|---|---|
| 1, Langfuse | Langfuse web and worker, Postgres, Valkey (Redis), SeaweedFS (S3), ClickHouse and Keeper, cert-manager, the ClickHouse operator | 5 |
| 2, monitoring | Prometheus and its operator, Grafana, kube-state-metrics, Tempo, Loki, the OpenTelemetry Collector | 3 |

## Storage

`/mnt/ailab-data` is exFAT, which has no Unix owners, modes, or symlinks, so Postgres,
ClickHouse, and Prometheus cannot use it directly. As with Forgejo, one ext4 **image file**
(`/mnt/ailab-data/observability/observability-store.ext4`, 50 GB) is loop-mounted at
`/srv/observability` by the systemd unit `srv-observability.mount`, with `nodiscard`
(TRIM inside the image cannot punch holes in a file on exFAT). The mount point is immutable
while unmounted, so if the image is missing, pods fail instead of writing to the root disk.

Each volume becomes a static local PV (`k8s/observability-move/10-langfuse-pvs.yaml`,
`20-monitoring-pvs.yaml`) pinned to `gpu-node`, with reclaim policy `Retain`. Each PV is pre-bound
(`claimRef`) to the PVC name the chart or StatefulSet already uses and keeps
`storageClassName: local-path`, so no immutable `volumeClaimTemplate` has to change.

| PV | PVC | Size | Live data (2026-10-11) |
|---|---|---|---|
| obs-langfuse-postgresql | langfuse/postgres-data-langfuse-postgresql-0 | 5Gi | 70 MB |
| obs-langfuse-clickhouse | langfuse/clickhouse-storage-volume-langfuse-clickhouse-0-0-0 | 10Gi | 69 MB |
| obs-langfuse-keeper | langfuse/clickhouse-storage-volume-langfuse-keeper-0-0 | 2Gi | not measured |
| obs-langfuse-redis | langfuse/langfuse-redis | 1Gi | not measured |
| obs-langfuse-s3 | langfuse/langfuse-s3-all-in-one-data | 5Gi | under 1 MB |
| obs-prometheus | monitoring/prometheus-kps-prometheus-db-prometheus-kps-prometheus-0 | 8Gi | capped at 3 GB (retention 3d) |
| obs-tempo | monitoring/storage-tempo-0 | 5Gi | 48h retention |
| obs-loki | monitoring/storage-loki-0 | 5Gi | 48h retention |

That is 41Gi of claims in a 50 GB image. Prometheus keeps 3 days (`retention: 3d`,
`retentionSize: 3GB`), not 30; raising retention later is a values change plus a larger image.

## Placement

The Day 7 values files now pin every pod to `gpu-node` with `nodeSelector: kubernetes.io/hostname: gpu-node`,
and the obs-node tolerations are removed. Server-side dry runs show only placement changes.

## Memory on gpu-node (measured 2026-10-11, 8:31 PM CT)

| | Now on gpu-node | Moving | After |
|---|---|---|---|
| Memory requests | 7,354 Mi | 4,264 Mi | about 11,600 Mi of 15,194 Mi allocatable (76%) |
| Memory in use | 4,194 Mi | about 3,600 Mi | about 7,800 Mi, leaving about 7 GiB free |
| Memory limits | 20,266 Mi | 11,616 Mi | about 31,900 Mi (210%, overcommitted) |

The requests fit, and actual use leaves about 7 GiB free. Limits are overcommitted, which is
normal, but if several pods spike at once the kernel kills the biggest. A RAM upgrade removes
that risk. The requests and limits are unchanged from Day 7, since they already match the
measured use (for example Prometheus uses 824 Mi against a 1 Gi limit).

## Migration (after the operator approves)

Each phase takes Langfuse or monitoring down for a few minutes. Traces and metrics sent while
it is down are queued by the OpenTelemetry Collector (up to 200 batches) and then dropped.

What `migrate.sh` does for each phase:
1. Sets the old obs-node PVs to `Retain`, so deleting their PVCs keeps the data as the rollback copy.
2. Phase 1 only: stops Langfuse web and worker, saves `pg_dump -Fc` of the Langfuse database,
   and records row counts for every Postgres and ClickHouse table.
3. Stops the stateful pods (and the ClickHouse operator, so it does not restart them, or the
   Prometheus CR, so the Prometheus operator does not).
4. Copies each volume with a short-lived, read-only mover pod on the obs-node (tar over the
   Kubernetes API, since `gpu-node` has no SSH to the obs-node), preserving owners and modes, and checks
   the file counts.
5. Deletes the old PVCs, creates the static PVs, runs `helm upgrade` with the values in this
   branch while the pods are still stopped, then starts them on `gpu-node`.
6. Checks that every PVC is on an `obs-*` PV, every pod is on `gpu-node`, and (phase 1) no table lost
   rows, or (phase 2) the oldest Prometheus sample is still about 3 days old.

Postgres moves by a stopped-volume copy (same `postgres:18` image on both sides), which keeps
the database exactly as it was. The dump is a verified backup for a manual restore, not the
primary path, because restoring a dump into a fresh database means Langfuse would first run
its migrations on an empty schema.

### Steps

On `gpu-node`, in the repo:

```bash
git pull
sudo SIZE=50G bash infra/observability/storage-setup.sh
findmnt /srv/observability            # loop device, ext4, nodiscard
sudo PHASE=langfuse bash scripts/observability-move/migrate.sh
```

Note the backup folder it prints. Open Langfuse at the tailnet address and check that old
traces are there. Then:

```bash
sudo PHASE=monitoring bash scripts/observability-move/migrate.sh
```

Open Grafana and check that the Prometheus dashboards show the last 3 days and that Tempo and
Loki return recent data.

## Rollback

The original volumes stay on the obs-node (PVs in `Released` state, policy `Retain`).
`rollback.sh` deletes the PVCs on `gpu-node` (the data on `gpu-node` stays), re-opens the obs-node PVs for the
same PVC names, and runs `helm upgrade` with the values from the commit before the merge.
Roll back monitoring before Langfuse. Data written on `gpu-node` after the move is not copied back.

```bash
REF=$(git rev-parse <merge-commit>^1)
sudo PHASE=monitoring BK=<backup folder> REF=$REF bash scripts/observability-move/rollback.sh
sudo PHASE=langfuse   BK=<backup folder> REF=$REF bash scripts/observability-move/rollback.sh
```

## What happened on 2026-10-11 (CT)

the operator approved PR #10 at 8:40 PM. It was merged as `72cedb2` and run from a clone at
`/home/<lab-user>/ssi-platform-run` on `gpu-node`. `gpu-node` has no GitHub login, so the clone came from a git
bundle copied from the agent box. Both phases succeeded with no rollback. The old obs-node volumes
are kept (8 PVs, `Released`, `Retain`).

| Time | Step | Result |
|---|---|---|
| 8:42 to 8:51 PM | `sudo SIZE=50G bash infra/observability/storage-setup.sh` | `/srv/observability` on `/dev/loop35`, ext4, 49 GB |
| 8:51 to 8:59 PM | `sudo PHASE=langfuse bash scripts/observability-move/migrate.sh` | Moved. The script stopped at its final pod check (issue 2), so the row counts were checked by hand |
| 8:59 to 9:04 PM | `sudo PHASE=monitoring bash scripts/observability-move/migrate.sh` | Copies done, then `helm upgrade kps` failed (issue 3). The four upgrades were re-run with `--force-conflicts` and the remaining steps finished by hand |
| 9:31 PM | the operator raised the inotify limits on `gpu-node` | Fixed node-exporter crashing on `gpu-node` (see Troubleshooting) |

Backup folders on the data lake:
- `/mnt/ailab-data/backups/observability/20261011-205151-langfuse`: `pg_dump` (329 KB), row
  counts before and after, file counts, the sign-in URL, and `old-pvs.txt`.
- `/mnt/ailab-data/backups/observability/20261011-205948-monitoring`: file counts and `old-pvs.txt`.

### Evidence

Langfuse:
- Volumes copied with matching file counts: ClickHouse 686 MB (3,961 files), Keeper 553 MB,
  Postgres 70 MB, Redis, and S3.
- All 7 Langfuse pods, cert-manager (3 pods), and the ClickHouse operator are Running and Ready
  on `gpu-node`. All 5 PVCs are bound to `obs-langfuse-*`.
- All 75 Postgres tables have the same row counts as before. ClickHouse is the same too:
  `events_core` 289, `events_full` 289, `schema_migrations` 98.
- `https://langfuse.<tailnet>.ts.net` returned 200 on `/api/public/health`, `/api/public/ready`,
  and `/auth/sign-in`, with version 4.38.0. All 51 traces from Sep 26 to Oct 10 are still there.

Monitoring:
- Volumes copied: Prometheus 1.3 GB, Loki 90 MB, and Tempo 2.2 MB. All 7 pods run on `gpu-node`, and all
  3 PVCs are bound to `obs-*`.
- The oldest Prometheus sample was 3.1 days old. A query for 70 hours ago returned data.
- Grafana `/api/health` reported database ok. Tempo returned traces from before the move, and
  Loki returned logs from 24 hours earlier.
- Memory on `gpu-node` afterward: 8,392 Mi (55%) right after the move, and 8,998 Mi (59%) at 9:40 PM.

### Issues and fixes

1. **The obs-node's node-exporter could not be scraped from `gpu-node`.** The obs-node firewall only
   allowed the lab host's flannel and kubelet ports. `infra/ansible/host_vars/obs-node.yml` now
   allows TCP 9100 from `gpu-node`, mirroring the opposite rule in `host_vars/gpu-node.yml`.
2. **The script's nodiscard check failed on a correct mount.** ext4 does not list `nodiscard` in
   `findmnt` output because it is the default. The check now asserts that `discard` is absent.
3. **The script's "every pod is on gpu-node" check gave false failures.** It counted the finished mover
   pods and old pods that were still terminating. Those are now excluded.
4. **Helm 4 refused `helm upgrade kps`.** Helm 4 applies server-side, so it refused to take back
   Prometheus's `.spec.replicas`, which the script had changed with `kubectl patch`. Every
   `helm upgrade` in `migrate.sh` and `rollback.sh` now uses `--force-conflicts`.
5. **Two smaller notes:**
   - Files in the backup folders, including the `pg_dump`, are readable by any user on `gpu-node`,
     because exFAT has no permissions.
   - `langfuse-web` restarted 4 times at startup while it waited for ClickHouse, and Loki
     restarted once at startup. Both have been stable since.

## Cleanup (after about a week)

When both phases have run cleanly, delete the old obs-node PVs (`kubectl get pv | grep Released`)
and their folders under `/var/lib/rancher/k3s/storage` on the obs-node. Both are separate,
approved changes. The `ailab/role=observability` label and taint can then come off the obs-node.

## Troubleshooting

- **`helm upgrade` fails with "conflict ... .spec.replicas":** add `--force-conflicts`. The scripts
  already do this.
- **A Langfuse Deployment PVC is missing after the upgrade:** `helm upgrade` recreates objects
  that were deleted. If `langfuse-redis` or `langfuse-s3-all-in-one-data` is missing, re-run the
  same `helm upgrade` line from the script.
- **A pod is Pending with "volume node affinity conflict":** it still has the old obs-node
  selector. Delete the pod so it is recreated from the updated template.
- **node-exporter on `gpu-node` keeps restarting with "too many open files":** this is the inotify
  limit, not file descriptors. The Ubuntu default of 128 inotify instances per user ran out on
  `gpu-node` (629 restarts in 15 days). the operator applied a fix by hand on 2026-10-11 at 9:31 PM CT, and
  Ansible now manages the same file on both nodes (`sysctl_inotify` in `group_vars/all.yml`):

  ```bash
  printf 'fs.inotify.max_user_instances=1024\nfs.inotify.max_user_watches=524288\n' | sudo tee /etc/sysctl.d/99-inotify.conf
  sudo sysctl --system
  sysctl fs.inotify.max_user_instances fs.inotify.max_user_watches
  ```

## Applying the follow-up (firewall and inotify)

From the terminal with the Ansible inventory (`infra/ansible`, see its README), check first:

```bash
cd infra/ansible
ansible-playbook playbooks/site.yml --syntax-check
ansible-playbook playbooks/site.yml --check --diff --ask-become-pass --limit obs-node
ansible-playbook playbooks/site.yml --check --diff --ask-become-pass --limit d
```

Expect on obs-node: one new ufw rule (9100/tcp from <lab-lan-ip>) and the new
`/etc/sysctl.d/99-inotify.conf`. Expect on gpu-node: no changes, since the file is already live. Then
apply obs-node only:

```bash
ansible-playbook playbooks/site.yml --diff --ask-become-pass --limit obs-node
```

Verify with Prometheus: `up{instance="<obs-node-ip>:9100"}` should be 1 within a minute.
