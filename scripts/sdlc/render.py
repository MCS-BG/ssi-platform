#!/usr/bin/env python3
"""Render the SI release manifests for one stage (the SDLC deploy step).

  python3 scripts/sdlc/render.py --env staging --sha <git sha> > /tmp/release.yaml
  python3 scripts/sdlc/render.py --env prod    --sha <git sha> > /tmp/release.yaml

Prod (si-lab) applies the generated lab manifests as they are in git, plus one pod-template
annotation (si.sdlc/git-sha) so every release is traceable and always rolls out.

Staging (si-staging) runs the same code with these differences:
  * namespace si-staging on every object;
  * m365-mcp is the staging copy (m365-mcp.si-staging.svc), started WITHOUT the
    m365-mcp-auth Secret, so Outlook tools answer "Not signed in" (no personal data in staging);
  * Ollama and Prompt Guard stay shared from si-lab by service DNS (no extra GPU/CPU model);
  * engineering-mcp and mcp-server point at si-lab by FQDN (their si-lab ingress policies keep
    staging out, so those tools return errors in staging, which the grounding layer reports);
  * pgvector-auth is absent, so conversation memory is off in staging;
  * the control-layer Service from k8s/day-10-control-layer.yaml is added.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
RELEASE = [  # (file, kinds to take or None for all, stages)
    ("k8s/day-06-netpol-pgvector.yaml", None, {"prod"}),
    ("k8s/day-10-control-layer.yaml", {"Service"}, {"staging"}),
    ("k8s/day-14-m365-mcp.yaml", None, {"prod", "staging"}),
    ("k8s/day-16-control-layer.yaml", None, {"prod", "staging"}),
    ("k8s/day-17-ssi-langgraph.yaml", None, {"prod", "staging"}),
]
NS = {"prod": "si-lab", "staging": "si-staging"}
STAGING_ENV_REWRITES = {
    "m365-mcp.si-lab.svc": "m365-mcp.si-staging.svc",
    "http://engineering-mcp:8000": "http://engineering-mcp.si-lab.svc.cluster.local:8000",
    "http://mcp-server:8000": "http://mcp-server.si-lab.svc.cluster.local:8000",
}
DEPLOYMENTS = ("m365-mcp", "control-layer", "ssi-langgraph")


def docs_for(stage: str) -> list[dict]:
    out = []
    for rel, kinds, stages in RELEASE:
        if stage not in stages:
            continue
        for doc in yaml.safe_load_all((REPO / rel).read_text()):
            if doc and (kinds is None or doc.get("kind") in kinds):
                out.append(doc)
    return out


def rewrite_env(pod_spec: dict) -> None:
    for c in pod_spec.get("containers", []) + pod_spec.get("initContainers", []):
        for env in c.get("env", []):
            val = env.get("value")
            if isinstance(val, str):
                for old, new in STAGING_ENV_REWRITES.items():
                    val = val.replace(old, new)
                env["value"] = val


def render(stage: str, sha: str) -> list[dict]:
    docs = docs_for(stage)
    for doc in docs:
        meta = doc.setdefault("metadata", {})
        if stage == "staging":
            meta["namespace"] = NS[stage]
        elif meta.get("namespace") != NS["prod"]:
            raise SystemExit(f"refusing: {doc['kind']}/{meta.get('name')} is not in si-lab")
        meta.setdefault("labels", {})["si.sdlc/managed"] = "true"
        if doc.get("kind") == "Deployment":
            tmpl = doc["spec"]["template"]
            tmpl.setdefault("metadata", {}).setdefault("annotations", {})["si.sdlc/git-sha"] = sha
            if stage == "staging":
                rewrite_env(tmpl["spec"])
    return docs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", choices=sorted(NS), required=True)
    ap.add_argument("--sha", default="local")
    ap.add_argument("--list-deployments", action="store_true")
    a = ap.parse_args()
    if a.list_deployments:
        print(" ".join(DEPLOYMENTS))
        return 0
    yaml.safe_dump_all(render(a.env, a.sha), sys.stdout, sort_keys=False, width=10_000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
