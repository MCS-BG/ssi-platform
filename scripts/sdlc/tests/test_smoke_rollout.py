"""Offline tests for the smoke test's commit check (#4): no cluster, no network.

Unit tests drive rollout_check.check(); the harness runs smoke.sh itself with a fake
kubectl and curl on PATH, replaying the live failure (old pods still terminating).
Run:  python3 -m pytest -q scripts/sdlc/tests
"""
from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys

import pytest

SDLC = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SDLC))
import rollout_check as rc  # noqa: E402

NEW, OLD = "6a4b05bcefc0" + "0" * 28, "aa1cccf" + "0" * 33


def deploy(sha=NEW, rev="2", replicas=1):
    return {"metadata": {"name": "control-layer", "uid": "d1", "annotations": {rc.REV: rev}},
            "spec": {"replicas": replicas,
                     "template": {"metadata": {"annotations": {rc.ANN: sha}}}}}


def rs(uid, rev):
    return {"metadata": {"uid": uid, "annotations": {rc.REV: rev}, "ownerReferences": [{"uid": "d1"}]}}


RS = {"items": [rs("rs-old", "1"), rs("rs-new", "2")]}


def pod(owner, sha, ready=True, terminating=False):
    meta = {"ownerReferences": [{"uid": owner}], "annotations": {rc.ANN: sha} if sha else {}}
    if terminating:
        meta["deletionTimestamp"] = "2026-10-10T19:40:00Z"
    return {"metadata": meta,
            "status": {"phase": "Running",
                       "conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


def test_live_case_terminating_old_pod_without_stamp_is_ignored():
    """Prod on 2026-10-10: the old pod (no stamp) was still terminating next to the new one."""
    ok, msg = rc.check(deploy(), RS, {"items": [pod("rs-new", NEW), pod("rs-old", "", terminating=True)]}, NEW)
    assert ok, msg
    assert "ignored 1 terminating" in msg


def test_live_case_staging_terminating_old_commit_is_ignored():
    ok, _ = rc.check(deploy(), RS, {"items": [pod("rs-new", NEW), pod("rs-old", OLD, terminating=True)]}, NEW)
    assert ok


def test_old_replicaset_pod_not_terminating_is_not_counted_and_new_missing_fails():
    ok, msg = rc.check(deploy(), RS, {"items": [pod("rs-old", OLD)]}, NEW)
    assert not ok and "0/1" in msg


def test_unready_new_pod_fails():
    assert not rc.check(deploy(), RS, {"items": [pod("rs-new", NEW, ready=False)]}, NEW)[0]


def test_template_mismatch_fails():
    ok, msg = rc.check(deploy(sha=OLD), RS, {"items": [pod("rs-new", OLD)]}, NEW)
    assert not ok and "template=" in msg


def test_wrong_stamp_on_current_pod_fails():
    assert not rc.check(deploy(), RS, {"items": [pod("rs-new", OLD)]}, NEW)[0]


def test_needs_all_replicas():
    assert not rc.check(deploy(replicas=2), RS, {"items": [pod("rs-new", NEW)]}, NEW)[0]
    assert rc.check(deploy(replicas=2), RS, {"items": [pod("rs-new", NEW)] * 2}, NEW)[0]


def test_missing_current_replicaset_fails():
    assert not rc.check(deploy(rev="3"), RS, {"items": [pod("rs-new", NEW)]}, NEW)[0]


# ---- harness: smoke.sh with a fake kubectl and curl ------------------------------------------

FAKE_KUBECTL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
a = sys.argv[1:]; st = pathlib.Path(os.environ["FAKE_STATE"])
if "rollout" in a: sys.exit(0)
if "svc" in a: print("10.0.0.1" if "clusterIP" in " ".join(a) else "8080", end=""); sys.exit(0)
if "jsonpath={.spec.selector.matchLabels}" in a or "{.spec.selector.matchLabels}" in a:
    print('{"app":"x"}', end=""); sys.exit(0)
kind = a[a.index("get") + 1]
if kind == "deploy": print((st / "deploy.json").read_text()); sys.exit(0)
if kind == "rs": print((st / "rs.json").read_text()); sys.exit(0)
if kind == "pods":
    n = int((st / "calls").read_text() or 0) if (st / "calls").exists() else 0
    (st / "calls").write_text(str(n + 1))
    seq = json.loads((st / "pods.json").read_text())
    print(json.dumps(seq[min(n, len(seq) - 1)])); sys.exit(0)
sys.exit(3)
'''


@pytest.fixture
def fakebin(tmp_path):
    b = tmp_path / "bin"; b.mkdir()
    (b / "kubectl").write_text(FAKE_KUBECTL)
    (b / "curl").write_text("#!/bin/sh\nprintf 200\n")
    for f in ("kubectl", "curl"):
        (b / f).chmod((b / f).stat().st_mode | stat.S_IEXEC)
    (tmp_path / "deploy.json").write_text(json.dumps(deploy()))
    (tmp_path / "rs.json").write_text(json.dumps(RS))
    return tmp_path


def run_smoke(state, pods_seq, wait="6"):
    (state / "pods.json").write_text(json.dumps(pods_seq))
    env = {**os.environ, "PATH": f"{state / 'bin'}:{os.environ['PATH']}", "FAKE_STATE": str(state),
           "SMOKE_ROLLOUT_WAIT": wait, "SMOKE_POLL": "1"}
    return subprocess.run(["bash", str(SDLC / "smoke.sh"), "prod", NEW, "--read-only"],
                          env=env, capture_output=True, text=True, timeout=60)


def test_harness_live_case_passes(fakebin):
    seq = [{"items": [pod("rs-new", NEW), pod("rs-old", "", terminating=True)]}]
    r = run_smoke(fakebin, seq)
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.count("PASS control-layer runs") == 3  # fake serves the same deploy for all 3


def test_harness_waits_for_old_pod_then_passes(fakebin):
    seq = [{"items": [pod("rs-new", NEW, ready=False), pod("rs-old", OLD)]},
           {"items": [pod("rs-new", NEW), pod("rs-old", OLD, terminating=True)]}]
    r = run_smoke(fakebin, seq)
    assert r.returncode == 0, r.stdout + r.stderr


def test_harness_fails_after_bounded_wait(fakebin):
    r = run_smoke(fakebin, [{"items": [pod("rs-old", OLD)]}], wait="2")
    assert r.returncode == 1 and "FAIL" in r.stdout and "after 2s" in r.stdout
