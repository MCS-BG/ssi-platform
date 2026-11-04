"""The Day 17 manifest matches the sources and mirrors the control layer's settings and policies."""
from __future__ import annotations

import pathlib
import subprocess
import sys

import yaml

APP = pathlib.Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
MANIFEST = REPO / "k8s" / "day-17-ssi-langgraph.yaml"


def docs(path: pathlib.Path) -> list[dict]:
    return [d for d in yaml.safe_load_all(path.read_text()) if d]


def by_kind_name(items: list[dict]) -> dict[tuple[str, str], dict]:
    return {(d["kind"], d["metadata"]["name"]): d for d in items}


def test_manifest_is_generated_from_the_current_sources():
    run = subprocess.run([sys.executable, str(APP / "build_manifest.py"), "--check"], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout


def test_configmap_carries_the_exact_sources():
    cm = by_kind_name(docs(MANIFEST))[("ConfigMap", "ssi-langgraph-code")]
    assert cm["data"]["control_layer.py"] == (REPO / "apps" / "control-layer" / "server.py").read_text()
    for name in ("cl_bridge.py", "graph.py", "server.py"):
        assert cm["data"][name] == (APP / name).read_text(), name


def test_init_container_installs_the_pinned_requirements():
    dep = by_kind_name(docs(MANIFEST))[("Deployment", "ssi-langgraph")]
    cmd = dep["spec"]["template"]["spec"]["initContainers"][0]["command"]
    pins = [ln for ln in (APP / "requirements.txt").read_text().splitlines() if ln and not ln.startswith("#")]
    assert "--no-deps" in cmd and cmd[-len(pins):] == pins
    assert "langgraph==1.2.14" in pins and "langchain-core==1.6.7" in pins and "psycopg==3.3.6" in pins
    assert all("==" in p for p in pins)


def test_same_settings_as_the_day16_control_layer():
    mine = by_kind_name(docs(MANIFEST))[("Deployment", "ssi-langgraph")]
    theirs = by_kind_name(docs(REPO / "k8s" / "day-16-control-layer.yaml"))[("Deployment", "control-layer")]
    env = lambda d: {e["name"]: e for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}  # noqa: E731
    mine_env, their_env = env(mine), env(theirs)
    for name, entry in their_env.items():
        assert mine_env.get(name) == entry, name
    assert mine_env["LANGSMITH_TRACING"]["value"] == "false"


def test_network_policies_mirror_the_control_layer():
    items = by_kind_name(docs(MANIFEST))
    own = items[("NetworkPolicy", "ssi-langgraph-allow-si-lab")]["spec"]
    assert own["podSelector"] == {"matchLabels": {"app": "ssi-langgraph"}}
    assert own["ingress"] == [{"from": [{"podSelector": {}}], "ports": [{"protocol": "TCP", "port": 8080}]}]
    pg = items[("NetworkPolicy", "pgvector-allow-ssi-langgraph")]["spec"]
    assert pg["podSelector"] == {"matchLabels": {"app": "pgvector"}}
    assert pg["ingress"][0]["from"] == [{"podSelector": {"matchLabels": {"app": "ssi-langgraph"}}}]
    m365 = items[("NetworkPolicy", "m365-mcp-allow-ssi-langgraph")]["spec"]
    assert m365["podSelector"] == {"matchLabels": {"app": "m365-mcp"}}
    assert m365["ingress"][0]["ports"] == [{"protocol": "TCP", "port": 8000}]
    svc = items[("Service", "ssi-langgraph")]["spec"]
    assert svc["type"] == "ClusterIP"


def test_only_new_object_names():
    existing = set()
    for path in (REPO / "k8s").glob("day-1[0-6]*.yaml"):
        existing |= set(by_kind_name(docs(path)))
    assert not set(by_kind_name(docs(MANIFEST))) & existing


def test_no_secret_values_in_the_manifest():
    for d in docs(MANIFEST):
        if d["kind"] == "Deployment":
            for c in d["spec"]["template"]["spec"]["containers"]:
                for e in c["env"]:
                    if e["name"].endswith(("_KEY", "PASSWORD", "_TOKEN", "_SECRET")):
                        assert "value" not in e and "secretKeyRef" in e["valueFrom"], e["name"]
