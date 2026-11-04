#!/usr/bin/env python3
"""Small Forgejo API helper for the .forgejo workflows (stdlib only).

  forge.py status-set <sha> <context> <state> <description>
  forge.py status-ok  <sha> <context>          exit 1 unless the commit has <context>=success
  forge.py cards      <sha> <stage-label> [--close]   label (and close) the PR's 'Card: #N' issues
  forge.py release    <tag> <sha> <prev-tag|->         create a release with notes from git log

Env: FORGEJO_URL (or GITHUB_SERVER_URL), GITHUB_REPOSITORY, FORGEJO_TOKEN (the job token).
Replaces GitHub-only pieces: Projects board sync becomes stage/* labels (Forgejo's project
boards have no API), and generated release notes become a git-log summary.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request

URL = (os.environ.get("FORGEJO_URL") or os.environ["GITHUB_SERVER_URL"]).rstrip("/")
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["FORGEJO_TOKEN"]


def api(method: str, path: str, body=None):
    req = urllib.request.Request(f"{URL}/api/v1/repos/{REPO}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"token {TOKEN}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def main(argv: list[str]) -> int:
    cmd = argv[0]
    if cmd == "status-set":
        sha, ctx, state, desc = argv[1:5]
        api("POST", f"/statuses/{sha}", {"context": ctx, "state": state, "description": desc})
        return 0
    if cmd == "status-ok":
        sha, ctx = argv[1:3]
        st = api("GET", f"/commits/{sha}/status")
        ok = any(s.get("context") == ctx and s.get("status", s.get("state")) == "success"
                 for s in st.get("statuses", []))
        print(f"{ctx} on {sha[:12]}: {'success' if ok else 'missing'}")
        return 0 if ok else 1
    if cmd == "cards":
        sha, label = argv[1:3]
        try:
            body = api("GET", f"/commits/{sha}/pull").get("body") or ""
        except Exception:
            print("no PR for this commit"); return 0
        for n in sorted({int(x) for x in re.findall(r"(?im)^\s*card:\s*#(\d+)", body)}):
            cur = [l["name"] for l in api("GET", f"/issues/{n}/labels")]
            api("PUT", f"/issues/{n}/labels", {"labels": [l for l in cur if not l.startswith("stage/")] + [label]})
            if "--close" in argv:
                api("PATCH", f"/issues/{n}", {"state": "closed"})
            print(f"#{n} -> {label}")
        return 0
    if cmd == "release":
        tag, sha, prev = argv[1:4]
        rng = f"{prev}..{sha}" if prev != "-" else sha
        log = subprocess.run(["git", "log", "--no-merges", "--format=- %s (%h)", rng],
                             capture_output=True, text=True, check=True).stdout
        r = api("POST", "/releases", {"tag_name": tag, "target_commitish": sha, "name": f"SI release {tag}",
                                      "body": f"## Changes\n{log or '- (no new commits)'}\n"})
        print(r.get("html_url", ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
