#!/usr/bin/env bash
# Migrate MCS-BG repos from GitHub into Forgejo with the built-in GitHub migrator
# (git data, issues, pull requests, labels, milestones, releases, wiki, LFS).
# Tokens are read from files you pass by path (mode 600), never from argv:
#   FORGEJO_TOKEN_FILE  Forgejo token of the admin (scope write:repository, write:organization)
#   GITHUB_TOKEN_FILE   GitHub token with READ access to the repos (fine-grained: Contents,
#                       Issues, Pull requests, Metadata: read-only)
# Forgejo does not keep the GitHub token for one-time (non-mirror) migrations.
#   FORGEJO_URL=https://git.<tailnet>.ts.net OWNER=MCS-BG \
#   FORGEJO_TOKEN_FILE=~/.fj GITHUB_TOKEN_FILE=~/.ghro bash scripts/forgejo/migrate.sh ssi-platform [repo...]
set -euo pipefail
FORGEJO_URL=${FORGEJO_URL:-https://git.<tailnet>.ts.net}
OWNER=${OWNER:-MCS-BG}
FT=$(<"${FORGEJO_TOKEN_FILE:?}"); GT=$(<"${GITHUB_TOKEN_FILE:?}")
for repo in "$@"; do
  private=$(curl -fsS -H "Authorization: Bearer $GT" "https://api.github.com/repos/$OWNER/$repo" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["private"]).lower())')
  body=$(GT="$GT" python3 - "$OWNER" "$repo" "$private" <<'PY'
import json, os, sys
owner, repo, private = sys.argv[1:4]
print(json.dumps({
  "service": "github", "clone_addr": f"https://github.com/{owner}/{repo}.git",
  "auth_token": os.environ["GT"], "repo_owner": owner, "repo_name": repo,
  "private": private == "true", "mirror": False,
  "issues": True, "pull_requests": True, "labels": True, "milestones": True,
  "releases": True, "wiki": True, "lfs": True,
  "description": f"Migrated from github.com/{owner}/{repo}"}))
PY
)
  echo "== $OWNER/$repo (private=$private)"
  curl -fsS -X POST "$FORGEJO_URL/api/v1/repos/migrate" \
    -H "Authorization: token $FT" -H 'Content-Type: application/json' --data-binary @- <<<"$body" \
    | python3 -c 'import json,sys; r=json.load(sys.stdin); print("migrated:", r["html_url"])'
done
