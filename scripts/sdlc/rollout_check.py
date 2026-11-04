#!/usr/bin/env python3
"""Decide whether a Deployment runs exactly one commit (used by smoke.sh, read-only).

  kubectl get deploy D -o json > d.json; kubectl get rs -l SEL -o json > rs.json
  kubectl get pods -l SEL -o json > p.json
  python3 scripts/sdlc/rollout_check.py d.json rs.json p.json <sha>

Counts only pods that belong to the Deployment's CURRENT ReplicaSet (same revision), are not
terminating (no metadata.deletionTimestamp), and are Ready. Pods from the old ReplicaSet that
are still shutting down during their grace period are ignored, which is the bug in #4.
Exit 0 = pass, 1 = not yet (smoke.sh retries), with a one-line reason on stdout.
"""
from __future__ import annotations

import json
import sys

ANN = "si.sdlc/git-sha"
REV = "deployment.kubernetes.io/revision"


def ready(pod: dict) -> bool:
    return any(c.get("type") == "Ready" and c.get("status") == "True"
               for c in pod.get("status", {}).get("conditions", []))


def check(deploy: dict, rs_list: dict, pods: dict, sha: str) -> tuple[bool, str]:
    name = deploy["metadata"]["name"]
    tmpl = deploy["spec"]["template"].get("metadata", {}).get("annotations", {}).get(ANN, "")
    want = int(deploy["spec"].get("replicas", 1))
    rev = deploy["metadata"].get("annotations", {}).get(REV)
    uid = deploy["metadata"].get("uid")
    current = [rs for rs in rs_list.get("items", [])
               if rs["metadata"].get("annotations", {}).get(REV) == rev
               and any(o.get("uid") == uid for o in rs["metadata"].get("ownerReferences", []))]
    if tmpl != sha:
        return False, f"{name} template={tmpl[:12] or '-'} want={sha[:12]}"
    if len(current) != 1:
        return False, f"{name} current ReplicaSet for revision {rev} not found"
    rs_uid = current[0]["metadata"]["uid"]
    live, terminating, other = [], 0, 0
    for p in pods.get("items", []):
        if p["metadata"].get("deletionTimestamp"):
            terminating += 1
            continue
        if not any(o.get("uid") == rs_uid for o in p["metadata"].get("ownerReferences", [])):
            other += 1
            continue
        if ready(p):
            live.append(p["metadata"].get("annotations", {}).get(ANN, ""))
    shas = sorted(set(live))
    note = f"(ignored {terminating} terminating, {other} from old ReplicaSets)"
    if shas == [sha] and len(live) >= want:
        return True, f"{name} runs {sha[:12]} ({len(live)}/{want} ready) {note}"
    return False, f"{name} ready pods={[s[:12] or '-' for s in shas]} {len(live)}/{want} {note}"


def main() -> int:
    d, rs, p = (json.load(open(f)) for f in sys.argv[1:4])
    ok, msg = check(d, rs, p, sys.argv[4])
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
