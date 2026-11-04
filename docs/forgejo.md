# Self-hosted Forgejo (replacing GitHub)

Forgejo runs on the lab k3s cluster in namespace `forgejo`, with its own PostgreSQL, reachable
only over the tailnet. It carries the same SDLC as GitHub today: issues and a Kanban board,
pull requests with CI, staging on merge, an owner-only Prod promotion, releases, and rollback.

Status: **designed, not deployed.** Everything here passed a server-side dry-run. Deploying
needs the operator's approval of the storage change, the admin username, and a GitHub read token.

## Architecture

```mermaid
flowchart LR
  subgraph tailnet[Tailnet only]
    the operator[the operator's Mac and browser]
  end
  the operator -->|HTTPS git.<tailnet>.ts.net| TSI[Tailscale ingress proxy]
  the operator -->|SSH git-ssh.<tailnet>.ts.net:22| TSS[Tailscale LoadBalancer proxy]
  subgraph k3s[k3s, node gpu-node]
    subgraph ns[namespace forgejo]
      FJ[Forgejo 15.0.9<br/>rootless, uid 1000]
      PG[(PostgreSQL 17<br/>uid 70)]
      BK[Nightly CronJobs<br/>pg_dump and forgejo dump]
    end
    STG[si-staging]
    PROD[si-lab]
  end
  TSI -->|3000| FJ
  TSS -->|2222| FJ
  FJ --> PG
  BK --> PG
  subgraph host[Lab host]
    EXT[(ext4 image, loop-mounted<br/>/srv/forgejo)]
    LAKE[(exFAT data lake<br/>/mnt/ailab-data)]
    RS[forgejo-runner<br/>si-lab-staging-runner<br/>user fjrunner-staging]
    RP[forgejo-runner<br/>si-lab-runner<br/>user fjrunner]
  end
  FJ --- EXT
  PG --- EXT
  EXT -.image file on.-> LAKE
  BK -->|dumps| LAKE
  RS -->|sa forgejo-staging-deployer| STG
  RP -->|sa forgejo-deployer| PROD
  RS & RP -->|poll jobs over the tailnet| TSI
```

## Versions (pinned, checked 2026-10-10 at the official source)

| Component | Version | Source |
|---|---|---|
| Helm chart | `oci://code.forgejo.org/forgejo-helm/forgejo` **17.2.0** (released 2026-10-05) | https://code.forgejo.org/forgejo-helm/forgejo-helm/releases |
| Forgejo | **15.0.9** (the chart's appVersion; rootless image) | https://code.forgejo.org/forgejo/forgejo/releases |
| forgejo-runner | **13.2.0** (2026-09-18), checksum-verified on install | https://code.forgejo.org/forgejo/runner/releases |
| PostgreSQL | `postgres:17.11-alpine` | Docker Hub official image |

The chart no longer bundles PostgreSQL, so `k8s/forgejo/10-postgres.yaml` runs a dedicated one.

## Storage

The data lake `/mnt/ailab-data` (4.5 TB, about 4 TB free, on node `gpu-node`) is **exFAT**: it has no
Unix owners, modes, or symlinks, and it is mounted `uid=1000,umask=022`. Git (executable hooks,
file modes) and PostgreSQL (requires a `0700` data directory it owns) must not live on it
directly.

**Recommended: an ext4 image file on the data lake, loop-mounted at `/srv/forgejo`**
(`infra/forgejo/storage-setup.sh`).

- One file, `/mnt/ailab-data/forgejo/forgejo-store.ext4` (200 GB by default; exFAT has no sparse
  files, so the full size is written up front), formatted ext4 and mounted by the systemd unit
  `srv-forgejo.mount`, which requires the data lake mount and starts before k3s.
- `/srv/forgejo` is an immutable empty directory when not mounted, so pods fail instead of
  silently writing to the root disk.
- Two static local PersistentVolumes, pinned to node `gpu-node`: `/srv/forgejo/data` (Forgejo, uid
  1000) and `/srv/forgejo/postgres` (PostgreSQL, uid 70). Reclaim policy `Retain`.
- Trade-off: a loop image on exFAT adds one layer. ext4 journaling inside the image protects
  consistency, but exFAT itself has no journal, so an unclean power-off can still damage the
  image. The nightly dumps (below) are the safety net, and a UPS is advisable.

Alternatives the operator can pick instead:

| Option | Pros | Cons |
|---|---|---|
| A. ext4 image on the data lake (recommended) | No repartitioning; data on the big drive | One extra layer; exFAT has no journal |
| B. Shrink the exFAT partition and add an ext4 partition | Native ext4, best integrity | exFAT cannot be shrunk in place: back up 0.5 TB, repartition, restore; downtime |
| C. local-path on the NVMe root disk (113 GB free) | Simplest, fastest | Not on the data lake; shares the OS disk |

## Access (tailnet only)

- Web: `https://git.<tailnet>.ts.net` through the Tailscale ingress (class `tailscale`,
  hostname `git`), like Grafana and Open WebUI today.
- SSH clone: `ssh://git@git-ssh.<tailnet>.ts.net/MCS-BG/ssi-platform.git`. The SSH Service is
  a `LoadBalancer` with `loadBalancerClass: tailscale`, so the operator gives it its own tailnet
  machine, `git-ssh`. A tailnet machine can serve only one proxy, so web and SSH have separate
  hostnames.
- No LAN NodePort, no public exposure. Registration is disabled and sign-in is required to view
  anything.

## Security

- NetworkPolicies (`k8s/forgejo/20-networkpolicies.yaml`): default-deny ingress; Forgejo ports
  3000 and 2222 only from the Tailscale proxies; PostgreSQL only from Forgejo and the backup
  jobs; Forgejo egress limited to DNS, PostgreSQL, and HTTPS to public addresses (for GitHub
  migration and webhooks), never to cluster or LAN ranges.
- Pods run non-root with all capabilities dropped, no privilege escalation, RuntimeDefault
  seccomp, a read-only root filesystem for Forgejo, and no ServiceAccount tokens mounted.
- Resource limits on every container. Recreate strategy, so two Forgejo pods never share the
  repository volume.
- Migrations may fetch only from GitHub (`ALLOWED_DOMAINS`), never from local networks.

### Secrets

No secret is in git. On the lab host, `scripts/forgejo/secrets.sh` generates and creates:

- `forgejo-db` (key `password`) for PostgreSQL, the backup job, and Forgejo;
- `forgejo-admin` (keys `username`, `password`). The initial admin password is written once to
  `/root/forgejo-admin-initial-password` (root-only); Forgejo forces a change at first sign-in.

```bash
sudo ADMIN_USER=<admin name the operator picks> bash scripts/forgejo/secrets.sh
```

## Forgejo Actions

Two `forgejo-runner` services on the lab host mirror the GitHub runners (staging names say
staging; Prod names are neutral):

| | Staging | Prod |
|---|---|---|
| Runner | `si-lab-staging-runner`, label `si-lab-staging` (host executor) | `si-lab-runner`, label `si-lab` (host executor) |
| Linux user (no sudo, home 700) | `fjrunner-staging` | `fjrunner` |
| systemd service | `forgejo-runner-si-lab-staging-runner` | `forgejo-runner-si-lab-runner` |
| Kubernetes account | `si-staging/forgejo-staging-deployer` | `si-lab/forgejo-deployer` |
| Role (reused, unchanged) | `sdlc-staging-deployer` | `sdlc-deployer` |
| Jobs | CI, CD Staging | Promote to Prod, Rollback Prod |

Accounts: `k8s/forgejo/40-runner-accounts.yaml`. Install: `scripts/forgejo/runner-setup.sh`.

### Workflows ported to `.forgejo/workflows`

Forgejo reads `.forgejo/workflows` and ignores `.github/workflows` when both exist; GitHub
ignores `.forgejo`. So both sets can live in the repo during the move.

| GitHub | Forgejo | Change |
|---|---|---|
| `ci.yml` on `ubuntu-latest` | `ci.yml` on `si-lab-staging` | No GitHub-hosted runners; runs in a per-run venv on the staging runner |
| `cd-staging.yml` (calls CI) | `cd-staging.yml` | CI steps inlined; sets commit status `si/staging=success` after the smoke test |
| `promote-prod.yml` | `promote-prod.yml` | Gate reads the `si/staging` commit status instead of the Actions runs API; release via the Forgejo API with notes from `git log` |
| `rollback.yml` | `rollback.yml` | Same |
| `project-sync.yml` and `board.py` | `scripts/forgejo/forge.py cards` | See below |

What does not port:

- **GitHub Projects board sync.** Forgejo has repository project boards (Kanban columns) but no
  API to move cards. Replace it with a Forgejo project board named "SSI Delivery" with the same
  columns, driven by the `stage/in-review`, `stage/staging`, and `stage/prod` labels that the
  workflows set. Card moves on the board are manual.
- **Environments and deployment history.** Forgejo has none; the run log, commit statuses, and
  releases record each deployment.
- **Generated release notes.** Built from `git log` between tags instead.
- **Reusable workflows (`workflow_call`) and `GITHUB_STEP_SUMMARY`.** Inlined or dropped.
- **PR template location.** Copy `.github/pull_request_template.md` and the issue templates to
  `.forgejo/` at cutover (Forgejo also reads `.github/`, so this is optional).

## Migration

MCS-BG repositories on GitHub (from `gh repo list`, 2026-10-10):

| Repo | Visibility | Size |
|---|---|---|
| ssi-platform | private | 39.5 MB |
| ssi-platform | public | 25.7 MB |
| d365fo.tools | private | 20.5 MB |
| Kubernetes-Webserver | public | 0.3 MB |
| finops-intelligence | private | 0.2 MB |
| cybertex | private | 77 KB |
| two-rivers-advisory | private | 58 KB |
| atxweb | private | 30 KB |
| texupport | private | 25 KB |
| bbdevdata | private | 13 KB |
| XppProjects, PyProjects, NewRepo-09-15-2022 | private | 3 KB each |
| d365-timer-etl | public | empty |
| bbdtest, blackbeardtech, topguninc, DataFactories | private | empty |

`scripts/forgejo/migrate.sh` uses Forgejo's built-in GitHub migrator (`POST /api/v1/repos/migrate`,
service `github`): git data, issues, pull requests, labels, milestones, releases, wiki, and LFS.
Actions secrets, branch settings, webhooks, and the GitHub Projects board are not migrated.

The migration needs a GitHub token that can read the repos. Use a fine-grained token with
read-only Contents, Issues, Pull requests, and Metadata on the MCS-BG repos (or the bot box's
`gh` token, read-only use). Forgejo does not store the token for one-time migrations.

### Cutover runbook

1. **Deploy Forgejo** (below) and sign in as the admin; create organisation `MCS-BG`.
2. **Trial migration**: migrate `ssi-platform` into a scratch name, check issues, PRs,
   labels, and releases, then delete it.
3. **Runners**: apply `k8s/forgejo/40-runner-accounts.yaml`, then install the staging runner.
   Keep the Prod runner off until step 7, so only GitHub can deploy Prod until then.
4. **Freeze GitHub**: announce, merge or close open PRs, stop creating issues.
5. **Final migration**: run `migrate.sh` for every repo. Copy secrets by hand
   (Settings > Actions > Secrets); there is no `PROJECT_TOKEN` equivalent to copy.
6. **Switch remotes** on every working copy (Mac, data lake copy, bot box):
   `git remote set-url origin ssh://git@git-ssh.<tailnet>.ts.net/MCS-BG/<repo>.git`.
7. **Switch CI/CD**: stop and disable the GitHub runner services
   (`actions.runner.MCS-BG-ssi-platform.si-lab-runner` and `...si-lab-staging-runner`), then
   install the Forgejo Prod runner. Run one card through the Forgejo flow end to end.
8. **Archive GitHub**: set each repo to archived (read-only) after a week without issues; keep it
   as an off-site copy, or add a Forgejo push mirror to GitHub for the repos to keep mirrored.

## Backups

Two CronJobs (`k8s/forgejo/30-backups.yaml`) write to `/mnt/ailab-data/backups/forgejo` on the
data lake (exFAT is fine for archive files) and keep 14 days:

- 02:15 Central: `pg_dump` to `pg/forgejo-YYYYMMDD-HHMM.sql.gz`;
- 02:45 Central: `forgejo dump` (repositories, LFS, attachments, config; database skipped since
  it is dumped separately) to `dump/forgejo-dump-YYYYMMDD-HHMM.tar.gz`.

Both run as uid 1000, the owner of the exFAT mount. Restore: recreate the volumes, `psql < dump`,
unpack the Forgejo dump into `/srv/forgejo/data`, then start Forgejo.

## Deploy (after the operator's approval)

```bash
# On the lab host, in the data lake checkout at this PR's merge commit
sudo SIZE=200G bash infra/forgejo/storage-setup.sh               # 1. storage (disk change)
sudo k3s kubectl apply -f k8s/forgejo/00-namespace-storage.yaml   # 2. namespace, PVs, PVCs
sudo ADMIN_USER=<name> bash scripts/forgejo/secrets.sh            # 3. Secrets (generated)
sudo k3s kubectl apply -f k8s/forgejo/10-postgres.yaml \
                       -f k8s/forgejo/20-networkpolicies.yaml      # 4. PostgreSQL, policies
sudo k3s kubectl -n forgejo rollout status statefulset/forgejo-postgres
helm upgrade --install forgejo oci://code.forgejo.org/forgejo-helm/forgejo \
  --version 17.2.0 -n forgejo -f k8s/forgejo/forgejo-values.yaml \
  --kubeconfig /etc/rancher/k3s/k3s.yaml                          # 5. Forgejo (helm needs installing)
sudo k3s kubectl -n forgejo rollout status deploy/forgejo
sudo k3s kubectl apply -f k8s/forgejo/30-backups.yaml             # 6. backups
sudo k3s kubectl -n forgejo create job --from=cronjob/forgejo-pg-dump pg-dump-first   # 7. test backups
sudo k3s kubectl -n forgejo create job --from=cronjob/forgejo-dump dump-first
```

Then open `https://git.<tailnet>.ts.net`, sign in with the admin name and the initial password
(`sudo cat /root/forgejo-admin-initial-password`), set a new password, enable 2FA, delete the
password file, and continue with the cutover runbook.

Remove (keeps data): `helm uninstall forgejo -n forgejo`, then
`sudo k3s kubectl delete ns forgejo`; the PVs are `Retain` and the image file stays on the drive.
