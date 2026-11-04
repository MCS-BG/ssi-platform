#!/usr/bin/env bash
# Apply example branding to a running Ghost through the Admin API (session login).
# Needs a reachable Ghost URL (port-forward for staging, https://blog.example.com for prod) and
# the owner's email and password in env vars (never on the command line or in git).
#   GHOST_URL=http://127.0.0.1:23680 GHOST_EMAIL=... GHOST_PASSWORD=... bash scripts/blog/brand.sh
# Sets: accent #2F5BFF, logo (Si tile + wordmark lockup, never the tile alone), icon/favicon,
# cover, title/description, and code injection for Sora SemiBold headings, Inter body, and
# JetBrains Mono code.
set -euo pipefail
U=${GHOST_URL:?}; : "${GHOST_EMAIL:?}" "${GHOST_PASSWORD:?}"
D=$(cd "$(dirname "$0")/../../assets/blog-brand" && pwd)
J=$(mktemp); trap 'rm -f "$J"' EXIT
H=(-H "Origin: ${GHOST_ORIGIN:-$U}")  # must equal Ghost's configured url
python3 -c 'import json,os;print(json.dumps({"username":os.environ["GHOST_EMAIL"],"password":os.environ["GHOST_PASSWORD"]}))' |
  curl -sS --fail-with-body -o /dev/null -c "$J" "${H[@]}" -H 'Content-Type: application/json' --data-binary @- "$U/ghost/api/admin/session/"
up() { curl -sS --fail-with-body -b "$J" "${H[@]}" -F "file=@$D/$1" -F purpose="$2" -F ref="$1" "$U/ghost/api/admin/images/upload/" |
  python3 -c 'import sys,json;print(json.load(sys.stdin)["images"][0]["url"])'; }
LOGO=$(up example-si-tile-lockup-light.png image)
ICON=$(up example-si-tile-icon-512.png icon)
# Text-free cover from the example brand assets (the site description is the single headline). Copy it from
# /workspace/example-blog-brand/ into assets/blog-brand/ when delivered.
[ -f "$D/example-blog-cover-2000x666-plain.png" ] || { echo "missing $D/example-blog-cover-2000x666-plain.png (copy it from the example brand assets)" >&2; exit 1; }
COVER=$(up example-blog-cover-2000x666-plain.png image)
LOGO="$LOGO" ICON="$ICON" COVER="$COVER" python3 - > "$J.body" <<'PY'
import json,os
css = """<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&family=Sora:wght@600&display=swap" rel="stylesheet">
<style>
:root{--example-blue:#2F5BFF;--example-ink:#0E1116;--example-slate:#2B3445;--example-gray:#5A6270;--example-paper:#FAF9F6;--example-line:#E6E2D8;
--font-sans:'Inter',system-ui,sans-serif;--gh-font-body:'Inter',system-ui,sans-serif;--gh-font-heading:'Sora',sans-serif;--font-mono:'JetBrains Mono',ui-monospace,monospace}
body{font-family:'Inter',system-ui,sans-serif;background:var(--example-paper);color:var(--example-ink)}
h1,h2,h3,h4,h5,h6,.gh-head-logo,.gh-article-title,.gh-card-title,.site-title{font-family:'Sora',sans-serif!important;font-weight:600!important}
code,pre,kbd,samp{font-family:'JetBrains Mono',ui-monospace,monospace!important}
hr,.gh-card,.gh-head{border-color:var(--example-line)}
</style>"""
s = [("accent_color","#2F5BFF"),("logo",os.environ["LOGO"]),("icon",os.environ["ICON"]),
     ("cover_image",os.environ["COVER"]),("title","example"),
     ("description","adapt adopt advance. Private super intelligence you own."),
     ("codeinjection_head",css)]
print(json.dumps({"settings":[{"key":k,"value":v} for k,v in s]}))
PY
curl -sS --fail-with-body -b "$J" "${H[@]}" -X PUT -H 'Content-Type: application/json' --data-binary @"$J.body" \
  "$U/ghost/api/admin/settings/" | python3 -c 'import sys,json;d={s["key"]:s["value"] for s in json.load(sys.stdin)["settings"]};print("accent",d["accent_color"],"logo",bool(d["logo"]),"icon",bool(d["icon"]),"cover",bool(d["cover_image"]))'
rm -f "$J.body"
