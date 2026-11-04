#!/usr/bin/env python3
"""Move SSI Delivery cards (Project v2) for a PR or a deployed commit.

Cards are the issues a PR names with "Card: #N" (the PR template line) or with a closing
keyword. Env: PR or SHA, STATUS (a Status option name), CLOSE=true to close the issue
(done at Prod), GH_TOKEN (repo token), PROJECT_TOKEN (optional, project scope).
Every move also sets a stage/* label with GH_TOKEN, so the flow stays visible in the repo
even before PROJECT_TOKEN exists.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

REPO = os.environ["GITHUB_REPOSITORY"]
OWNER = REPO.split("/")[0]
PROJECT_TITLE = os.environ.get("PROJECT_TITLE", "SSI Delivery")
STATUS = os.environ.get("STATUS", "In Review")
STAGE_LABELS = {"In Review": "stage/in-review", "Staging": "stage/staging", "Done (Prod)": "stage/prod"}


def call(method: str, url: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        url if url.startswith("http") else f"https://api.github.com{url}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def gql(token: str, query: str, **variables):
    out = call("POST", "/graphql", token, {"query": query, "variables": variables})
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]


def pr_numbers(tok: str) -> list[int]:
    if os.environ.get("PR"):
        return [int(os.environ["PR"])]
    sha = os.environ.get("SHA", "")
    return [p["number"] for p in call("GET", f"/repos/{REPO}/commits/{sha}/pulls", tok)] if sha else []


def cards(tok: str, pr: int) -> set[int]:
    body = call("GET", f"/repos/{REPO}/pulls/{pr}", tok).get("body") or ""
    found = {int(n) for n in re.findall(r"(?im)^\s*card:\s*#(\d+)", body)}
    found |= {int(n) for n in re.findall(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", body)}
    return found


def move_on_board(ptok: str, issue: int) -> None:
    q = """query($o:String!){user(login:$o){projectsV2(first:50){nodes{id title
      field(name:"Status"){... on ProjectV2SingleSelectField{id options{id name}}}}}}}"""
    proj = next((p for p in gql(ptok, q, o=OWNER)["user"]["projectsV2"]["nodes"]
                 if p["title"] == PROJECT_TITLE), None)
    if not proj:
        print(f"::warning::Project '{PROJECT_TITLE}' not found")
        return
    opt = next((o["id"] for o in proj["field"]["options"] if o["name"] == STATUS), None)
    if not opt:
        print(f"::warning::Status option '{STATUS}' not found")
        return
    owner, name = REPO.split("/")
    node = gql(ptok, "query($o:String!,$n:String!,$i:Int!){repository(owner:$o,name:$n){issue(number:$i){id}}}",
               o=owner, n=name, i=issue)["repository"]["issue"]["id"]
    item = gql(ptok, "mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}",
               p=proj["id"], c=node)["addProjectV2ItemById"]["item"]["id"]
    gql(ptok, """mutation($p:ID!,$i:ID!,$f:ID!,$v:String!){updateProjectV2ItemFieldValue(input:{
        projectId:$p,itemId:$i,fieldId:$f,value:{singleSelectOptionId:$v}}){projectV2Item{id}}}""",
        p=proj["id"], i=item, f=proj["field"]["id"], v=opt)
    print(f"#{issue} -> {STATUS} on {PROJECT_TITLE}")


def main() -> int:
    tok, ptok = os.environ["GH_TOKEN"], os.environ.get("PROJECT_TOKEN", "")
    issues = sorted({i for pr in pr_numbers(tok) for i in cards(tok, pr)})
    if not issues:
        print("No linked cards (add 'Card: #N' to the PR body).")
        return 0
    for i in issues:
        label = STAGE_LABELS.get(STATUS)
        if label:
            cur = [l["name"] for l in call("GET", f"/repos/{REPO}/issues/{i}", tok)["labels"]]
            keep = [l for l in cur if not l.startswith("stage/")] + [label]
            call("PUT", f"/repos/{REPO}/issues/{i}/labels", tok, {"labels": keep})
        if ptok:
            move_on_board(ptok, i)
        else:
            print(f"::notice::PROJECT_TOKEN not set: labelled #{i} {label}, board not moved")
        if os.environ.get("CLOSE") == "true":
            call("PATCH", f"/repos/{REPO}/issues/{i}", tok, {"state": "closed", "state_reason": "completed"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
