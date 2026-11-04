#!/usr/bin/env bash
# Every CI gate in one script, so CI on GitHub and a laptop run the same checks.
#   bash scripts/sdlc/ci.sh
set -uo pipefail
cd "$(dirname "$0")/../.."
fail=0
step() { echo "::group::$1"; shift; if "$@"; then echo "PASS"; else echo "::error::FAILED: $*"; fail=1; fi; echo "::endgroup::"; }
for b in apps/*/build_manifest.py; do
  grep -q -- '--check' "$b" && step "manifest in sync: $b" python3 "$b" --check
done
step "ssi-langgraph tests" python3 -m pytest -q apps/ssi-langgraph/tests
[[ -d apps/m365-mcp/tests ]] && step "m365-mcp tests" python3 -m pytest -q apps/m365-mcp/tests
step "engineering-mcp tests" python3 apps/engineering-mcp/tests/test_server.py
[[ -d apps/control-layer/tests ]] && step "control-layer tests" python3 -m pytest -q apps/control-layer/tests
step "control-layer compiles" python3 -m py_compile apps/control-layer/server.py
step "sdlc smoke-test tests" python3 -m pytest -q scripts/sdlc/tests
step "forgejo manifests and workflows parse" python3 -c "import glob,yaml; [list(yaml.safe_load_all(open(f))) for f in glob.glob('k8s/forgejo/*.yaml')+glob.glob('.forgejo/workflows/*.yml')]"
step "forgejo scripts" bash -c 'for f in infra/forgejo/*.sh scripts/forgejo/*.sh; do bash -n "$f" || exit 1; done; python3 -m py_compile scripts/forgejo/forge.py'
step "render staging" bash -c 'python3 scripts/sdlc/render.py --env staging --sha ci >/dev/null'
step "render prod" bash -c 'python3 scripts/sdlc/render.py --env prod --sha ci >/dev/null'
exit $fail
