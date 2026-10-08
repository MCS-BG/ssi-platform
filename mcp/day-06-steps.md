# Day 6: MCP server in k3s, the terminal steps

Everything below runs from the terminal and uses only `kubectl`, plus the built-in `curl`, `wc` and `shasum`. Workloads and data stay in the cluster on the lab host. Keep the SSH tunnel open in its own tab, as on earlier days:
`ssh -N -L 6443:127.0.0.1:6443 <lab-user>@192.0.2.71`

What gets deployed in `si-lab` (one file, `day-06-mcp.yaml`):
- **`fo-mock`**: a Deployment and ClusterIP Service on 8080. It's a read-only mock of a Dynamics 365 FO OData v4 endpoint (`/data/<EntitySet>`, `/data/$metadata`) with **fake demo data** and no auth. Real FO OData needs Microsoft Entra ID OAuth 2.0. This mock is cluster-internal only, and a NetworkPolicy lets only `mcp-server` reach it.
- **`mcp-server`**: a Deployment and ClusterIP Service on 8000, at `/mcp`. It's built on the official MCP Python SDK 2.2.0 (FastMCP is now called `MCPServer`) and speaks Streamable HTTP. Its tools are `search_notes`, `fo_list_entities`, `fo_get_entity_metadata` and `fo_query`. A NetworkPolicy accepts connections from `si-lab` pods only.
- **`mcp-test`**: a one-shot Job that uses the MCP Python client to list the tools, call each one, and check the NetworkPolicies.
- All three pods pass the **restricted** Pod Security level (non-root UID 10001, no privilege escalation, all capabilities dropped, RuntimeDefault seccomp, read-only root filesystem, no service account token). The namespace still enforces baseline.
- Python libraries are pinned (`mcp==2.2.0`, `psycopg[binary]==3.3.6`, `requests==2.34.2`) and pip-installed by an init container at pod start, following the day 4 rag-worker pattern. This is temporary until the custom image on day 8. `fo-mock` uses the standard library only, so it installs nothing.

---

## Step 0: Check the starting point

```bash
# terminal
kubectl -n si-lab get pods
kubectl -n si-lab get networkpolicy
kubectl -n si-lab get secret pgvector-auth
```

Expected:
```text
NAME                          READY   STATUS    RESTARTS   AGE
ollama-768d64b4c8-wqpq6       1/1     Running   0          ...
open-webui-7c95f85c9f-9xbk9   1/1     Running   0          ...
pgvector-0                    1/1     Running   0          ...
rag-worker-5fd846c57b-hhc98   1/1     Running   0          ...
No resources found in si-lab namespace.
NAME            TYPE     DATA   AGE
pgvector-auth   Opaque   1      ...
```
Your pod hashes will differ. "No resources found" means no NetworkPolicies exist yet, so nothing you already run can be affected by a default-deny rule.

## Step 1: Write the manifest

Paste the **entire** contents of `day-06-mcp.yaml` between the two marker lines. The file is plain ASCII, contains no line that reads `EOF`, and has no zsh history-expansion sequences. It was checked by pasting it through an interactive zsh heredoc.

```bash
# terminal
mkdir -p ~/ssi-platform/k8s
cat > ~/ssi-platform/k8s/day-06-mcp.yaml <<'EOF'
(paste the full day-06-mcp.yaml here, from "# Day 6: MCP server ..." to the last "emptyDir: {}")
EOF
```

Check that the paste arrived intact:
```bash
# terminal
wc -c ~/ssi-platform/k8s/day-06-mcp.yaml
shasum -a 256 ~/ssi-platform/k8s/day-06-mcp.yaml
```

Expected:
```text
   44859 /Users/<you>/ssi-platform/k8s/day-06-mcp.yaml
a69b9d17c8b79d6ad267e7de5d910b5c0b0a04104150852154561df9a2bbfc9a  /Users/<you>/ssi-platform/k8s/day-06-mcp.yaml
```
If the hash differs, the paste was cut short or changed. Write the file again.

## Step 2: Dry run on the server (schema + Pod Security admission)

```bash
# terminal
kubectl apply --dry-run=server -f ~/ssi-platform/k8s/day-06-mcp.yaml
```

Expected: 10 lines, and no `Warning: would violate PodSecurity` lines.
```text
configmap/fo-mock-code created (server dry run)
configmap/mcp-server-code created (server dry run)
configmap/mcp-test-code created (server dry run)
deployment.apps/fo-mock created (server dry run)
service/fo-mock created (server dry run)
deployment.apps/mcp-server created (server dry run)
service/mcp-server created (server dry run)
networkpolicy.networking.k8s.io/fo-mock-allow-mcp-server created (server dry run)
networkpolicy.networking.k8s.io/mcp-server-allow-si-lab created (server dry run)
job.batch/mcp-test created (server dry run)
```

## Step 3: Apply and watch the pods

```bash
# terminal
kubectl apply -f ~/ssi-platform/k8s/day-06-mcp.yaml
kubectl -n si-lab get pods -l 'app in (fo-mock,mcp-server,mcp-test)' -w
```

Expected: the same 10 objects as `created`, then something like the following. Press Ctrl+C once `mcp-test` shows `Completed`.
```text
NAME                          READY   STATUS            RESTARTS   AGE
fo-mock-xxxxxxxxxx-xxxxx      0/1     Running           0          3s
mcp-server-xxxxxxxxxx-xxxxx   0/1     Init:0/1          0          3s
mcp-test-xxxxx                0/1     Init:0/1          0          3s
fo-mock-xxxxxxxxxx-xxxxx      1/1     Running           0          8s
mcp-server-xxxxxxxxxx-xxxxx   0/1     PodInitializing   0          25s
mcp-server-xxxxxxxxxx-xxxxx   1/1     Running           0          32s
mcp-test-xxxxx                0/1     Completed         0          50s
```
`Init:0/1` is pip installing the pinned libraries, usually 10 to 60 seconds. `python:3.12-slim` is already on the node from day 4. If `mcp-test` starts before `mcp-server` is ready, it prints `waiting for ... retrying in 5s` and waits up to 5 minutes, so that's fine.

## Step 4: Read the test results

```bash
# terminal
kubectl -n si-lab logs job/mcp-test -c test
```

Expected:
```text
=== connecting to http://mcp-server.si-lab.svc.cluster.local:8000/mcp (mode=auto)
tools: fo_get_entity_metadata, fo_list_entities, fo_query, search_notes

--- search_notes: 'What GPU is in the lab host and how much VRAM does it have?'
  0.260  day-03-model-serving.md  `PROCESSOR` is the column that matters, and `100% GPU` is the proof. A...
  0.261  day-02-secure-k3s.md  One real constraint shapes what comes next. This GPU has 4 GB of memor...
  0.281  day-02-secure-k3s.md  # Day 2: A secure single-node k3s cluster with a working GPU Yesterday...

--- fo_list_entities
  CustomersV3, ReleasedProductsV2, SalesOrderHeadersV2, VendorsV2

--- fo_get_entity_metadata: CustomersV3
  keys: ['dataAreaId', 'CustomerAccount']  fields: 17

--- fo_query: CustomersV3 where CustomerGroupId eq '30'
  matched=2 returned=2
   {'CustomerAccount': 'DEMO-C0001', 'OrganizationName': 'Lakeside Bike Shop (demo)', 'AddressCity': 'Chicago'}
   {'CustomerAccount': 'DEMO-C0002', 'OrganizationName': 'Prairie Outfitters (demo)', 'AddressCity': 'Milwaukee'}

--- fo_query: SalesOrderHeadersV2 backorders for DEMO-C0001
   {'SalesOrderNumber': 'DEMO-SO-0001', 'RequestedShippingDate': '2026-10-05T12:00:00Z', 'OrderTotalAmount': 1780.0}
   {'SalesOrderNumber': 'DEMO-SO-0004', 'RequestedShippingDate': '2026-10-12T12:00:00Z', 'OrderTotalAmount': 3400.0}

--- fo_query with an unsupported filter (expect a clean tool error)
  is_error = True | Error executing tool fo_query: OData error 400: The mock only supports $filter clauses like Field eq 'value' joined by 'and'. Could not parse: CreditLimit gt 10

=== connecting to http://mcp-server.si-lab.svc.cluster.local:8000/mcp (mode=legacy)
tools: fo_get_entity_metadata, fo_list_entities, fo_query, search_notes
  fo_query VendorsV2 over the legacy handshake: returned=1

=== NetworkPolicy checks (direct TCP from this test pod)
  fo-mock  fo-mock.si-lab.svc.cluster.local:8080: blocked as expected (ConnectionRefusedError)
  pgvector pgvector.si-lab.svc.cluster.local:5432: reachable (expected unless the optional pgvector policy is applied)

ALL MCP CHECKS PASSED
```
Notes:
- `search_notes` uses the same embedding model, `search_query:` prefix and `<=>` SQL as day 4's `ask.py`. With the `chunks` table unchanged since day 4 (32 chunks from days 1 to 3), the three hits and distances should match day 4's `ask.py` output for the same question. If you've re-ingested since then, the sources can differ.
- `mode=auto` is the MCP 2026-07-28 protocol negotiation. `mode=legacy` is the older initialize handshake that clients like Open WebUI still use. Both have to work.
- `blocked as expected` proves k3s' built-in network policy controller (kube-router) is enforcing the fo-mock policy. `TimeoutError` instead of `ConnectionRefusedError` is equally fine: it depends on whether the packet is rejected or dropped. If it says `REACHABLE`, see failure 3 below.

Optionally, look at the server side:
```bash
# terminal
kubectl -n si-lab logs deploy/mcp-server --tail=5
```
Expected: lines like `Uvicorn running on http://0.0.0.0:8000` and `"POST /mcp HTTP/1.1" 200 OK`. Kubelet health checks also show up as `"GET /healthz HTTP/1.1" 200 OK`.

## Step 5: Confirm the new pods would pass "restricted" (changes nothing)

```bash
# terminal
kubectl label --dry-run=server --overwrite ns si-lab pod-security.kubernetes.io/enforce=restricted
```

Expected (it's a dry run, so the label is **not** changed):
```text
Warning: existing pods in namespace "si-lab" violate the new PodSecurity enforce level "restricted:latest"
Warning: ollama-768d64b4c8-wqpq6 (and 2 other pods): allowPrivilegeEscalation != false, unrestricted capabilities, runAsNonRoot != true, seccompProfile
Warning: open-webui-7c95f85c9f-9xbk9: unrestricted capabilities, runAsNonRoot != true
namespace/si-lab labeled (server dry run)
```
The exact grouping can differ. The point is that the pods counted are only the day 3 to 5 ones (ollama, pgvector-0, rag-worker, open-webui). `fo-mock`, `mcp-server` and `mcp-test` never appear.

## Step 6 (optional, recommended): Let only mcp-server and rag-worker reach pgvector

This is low risk. On day 5, Open WebUI kept its default Chroma vector store and doesn't use pgvector. `kubectl exec` into `pgvector-0` and any `kubectl port-forward` keep working, because neither passes through pod networking. First confirm Open WebUI has no Postgres settings:

```bash
# terminal
kubectl -n si-lab get deploy open-webui -o jsonpath='{.spec.template.spec.containers[0].env[*].name}'; echo
```
Expected, with no `VECTOR_DB`, `PGVECTOR_DB_URL` or `DATABASE_URL`:
```text
OLLAMA_BASE_URL RAG_EMBEDDING_ENGINE RAG_EMBEDDING_MODEL ANONYMIZED_TELEMETRY DO_NOT_TRACK SCARF_NO_ANALYTICS WEBUI_SECRET_KEY
```

Write and apply the policy:
```bash
# terminal
cat > ~/ssi-platform/k8s/day-06-netpol-pgvector.yaml <<'EOF'
# OPTIONAL (day 6): only mcp-server and rag-worker may connect to pgvector.
# kubectl exec into pgvector-0 and kubectl port-forward are not affected.
# Roll back with: kubectl -n si-lab delete networkpolicy pgvector-allow-clients
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: pgvector-allow-clients
  namespace: si-lab
spec:
  podSelector:
    matchLabels:
      app: pgvector
  policyTypes: ["Ingress"]
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: mcp-server
        - podSelector:
            matchLabels:
              app: rag-worker
      ports:
        - protocol: TCP
          port: 5432
EOF
kubectl apply -f ~/ssi-platform/k8s/day-06-netpol-pgvector.yaml
```
Expected: `networkpolicy.networking.k8s.io/pgvector-allow-clients created`

Prove both allowed clients still work and the test pod is now blocked:
```bash
# terminal
kubectl -n si-lab delete job mcp-test
kubectl apply -f ~/ssi-platform/k8s/day-06-mcp.yaml
kubectl -n si-lab wait --for=condition=complete job/mcp-test --timeout=300s
kubectl -n si-lab logs job/mcp-test -c test | tail -4
kubectl -n si-lab exec deploy/rag-worker -- python ask.py "What GPU is in the lab host and how much VRAM does it have?"
```
Expected: `job.batch "mcp-test" deleted`, then `job.batch/mcp-test created` among 9 `unchanged` lines, then `job.batch/mcp-test condition met`, then:
```text
  fo-mock  fo-mock.si-lab.svc.cluster.local:8080: blocked as expected (ConnectionRefusedError)
  pgvector pgvector.si-lab.svc.cluster.local:5432: blocked (ConnectionRefusedError) - the optional pgvector policy is active

ALL MCP CHECKS PASSED
```
The day 4 answer ("...NVIDIA laptop GPU... 4 GB of video memory", with sources) comes back from rag-worker. "ALL MCP CHECKS PASSED" includes `search_notes`, which shows that mcp-server still reaches pgvector.
Roll back at any time with `kubectl -n si-lab delete networkpolicy pgvector-allow-clients`.

## Step 7 (optional): Call the server from the terminal with curl

In a **second tab** (leave it running):
```bash
# terminal
kubectl -n si-lab port-forward svc/mcp-server 8000:8000
```
Expected: `Forwarding from 127.0.0.1:8000 -> 8000` and `Forwarding from [::1]:8000 -> 8000`

In a **third tab**:
```bash
# terminal
curl -s -X POST http://127.0.0.1:8000/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fo_query","arguments":{"entity":"VendorsV2","select":"VendorAccountNumber,VendorOrganizationName","top":2}}}'; echo
```
Expected: one JSON-RPC line containing `"isError":false` and `"structuredContent":{"source":"fo-mock (fake demo data)","entity_set":"VendorsV2","matched":3,"returned":2,"records":[{"VendorAccountNumber":"DEMO-V0001",...`. The port-forward enters the pod's own network namespace, so the NetworkPolicy doesn't apply to it.

## Step 8 (optional): Add the tools to Open WebUI

Open WebUI supports MCP natively (Streamable HTTP) from v0.6.31, and the `main` image from day 5 is newer. **No `mcpo` proxy is needed.** `mcpo` is only for stdio or SSE servers ([docs](https://docs.openwebui.com/features/extensibility/mcp)).
1. Open Open WebUI at `http://127.0.0.1:3000` through the day 5 port-forward (`kubectl -n si-lab port-forward svc/open-webui 3000:8080`).
2. Go to **Settings > Admin > Integrations**. Under **External Tool Servers**, click **+ Add Connection**.
3. Set **Type** to **MCP (Streamable HTTP)** (not OpenAPI), **URL** to `http://mcp-server.si-lab.svc.cluster.local:8000/mcp`, and **Auth** to **None**. Save.
4. In a chat, choose **+ > Integrations > Tools** and enable the server.
Expected: the four tools appear. `llama3.2:3b` is a small model, and Open WebUI's docs warn that weak models may ignore tools or pass wrong arguments. That's a model limit, not a broken connection. Ask very direct questions, such as "Use fo_query to list VendorsV2".

## Step 9 (optional): Use it from Cursor on the Mac

Keep the step 7 port-forward running and add this to `~/.cursor/mcp.json`. It's client config only, with no code or data on the Mac:
```json
{
  "mcpServers": {
    "ssi-platform": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```
Expected: Cursor's MCP settings show `ssi-platform` with 4 tools. The server only accepts the `Host` names it knows: `127.0.0.1`, `localhost`, and the `mcp-server` Service names. Any other name gets `421 Invalid Host header`.

## Clean up (if needed)

```bash
# terminal
kubectl delete -f ~/ssi-platform/k8s/day-06-mcp.yaml
kubectl delete -f ~/ssi-platform/k8s/day-06-netpol-pgvector.yaml --ignore-not-found
```

---

## Top 3 likely failures

**1. `mcp-server` (or `mcp-test`) stuck at `Init:Error` / `Init:CrashLoopBackOff`.** The `deps` init container couldn't pip-install from PyPI, usually because DNS or outbound internet from the pod failed.
```bash
# terminal
kubectl -n si-lab logs deploy/mcp-server -c deps
```
You'll see something like `ERROR: Could not find a version that satisfies the requirement mcp==2.2.0` or `Failed to establish a new connection`. The rag-worker from day 4 depends on PyPI the same way, so check whether it still restarts cleanly (`kubectl -n si-lab rollout restart deploy/rag-worker`). Once the network is fine, run `kubectl -n si-lab rollout restart deploy/mcp-server`. Day 8's custom image removes this runtime dependency.

**2. The test fails at `search_notes`.** The error names the backend:
- `password authentication failed for user "rag"`: the `pgvector-auth` Secret or its `POSTGRES_PASSWORD` key doesn't match. Check with `kubectl -n si-lab describe secret pgvector-auth`, which shows key names and sizes but not the value. You should see `POSTGRES_PASSWORD:  48 bytes`.
- `search_notes returned no rows`, or `relation "chunks" does not exist`: re-run the day 4 ingest with `kubectl -n si-lab exec deploy/rag-worker -- python ingest.py`.
- `ReadTimeout` from Ollama: the first embed after a model swap on the 4 GB GPU can be slow. Re-run the Job (see failure 3).

**3. Re-running or editing: `The Job "mcp-test" is invalid: spec.template: ... field is immutable`.** A Job's pod template can't be changed in place, and a finished Job doesn't re-run on `apply`. Delete it, then apply again:
```bash
# terminal
kubectl -n si-lab delete job mcp-test
kubectl apply -f ~/ssi-platform/k8s/day-06-mcp.yaml
```
Related: if the NetworkPolicy check prints `REACHABLE`, the embedded network policy controller isn't active. Check that k3s wasn't started with `--disable-network-policy`. Day 2 didn't use that flag.
