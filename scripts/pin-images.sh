#!/usr/bin/env bash
# Pin the image lines in k8s/day-08*.yaml to the tags GitHub Actions built.
#
# For each app, the tag is the short (7-character) SHA of the newest commit that touched
# apps/<app>/ or its workflow files, because that is the commit whose push built the image
# (docker/metadata-action type=sha). Before editing anything, the script checks anonymously
# that ghcr.io serves that tag, which also proves the package is public.
#
# Usage (from anywhere inside the repo):  scripts/pin-images.sh <github-owner>
# Works with the macOS bash 3.2, BSD sed and curl.
set -euo pipefail

owner="${1:?usage: scripts/pin-images.sh <github-owner>}"
owner="$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')"
cd "$(git rev-parse --show-toplevel)"

accept='application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.docker.distribution.manifest.v2+json'
failed=0

for app in rag-worker mcp-server prompt-guard; do
  sha="$(git log -1 --format=%H -- "apps/$app" ".github/workflows/build-$app.yml" ".github/workflows/_build-image.yml")"
  if [ -z "$sha" ]; then
    echo "$app: no commit touches apps/$app yet" >&2
    failed=1
    continue
  fi
  tag="${sha:0:7}"
  image="ghcr.io/$owner/$app:$tag"

  token="$(curl -s "https://ghcr.io/token?scope=repository:$owner/$app:pull" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')"
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer ${token:-none}" -H "Accept: $accept" "https://ghcr.io/v2/$owner/$app/manifests/$tag")"
  if [ "$code" != "200" ]; then
    echo "$app: $image is not pullable anonymously (HTTP $code). Is the build finished and the package public?" >&2
    failed=1
    continue
  fi

  for f in k8s/day-08*.yaml; do
    if grep -q "ghcr.io/[^/]*/$app:" "$f"; then
      sed -i.bak -E "s#ghcr\.io/[^/]+/$app:[A-Za-z0-9._-]+#$image#g" "$f"
      rm -f "$f.bak"
    fi
  done
  echo "$app: pinned to $image"
done

exit "$failed"
