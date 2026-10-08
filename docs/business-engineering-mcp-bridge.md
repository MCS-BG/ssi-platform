# Business and engineering MCP bridge

This is a design lab for one shared control loop across a business MCP slot and an engineering MCP slot. It does not install a new service. It does not apply a manifest, pull a model, train, or delete anything.

The need is one conversation that can use business tools and engineering tools in the same turn. Business context and engineering context stay on separate MCP servers. They meet only inside the control layer. Open WebUI stays human chat. It does not run the agent loop.

The rule is the same as the rest of Sovereign Super Intelligence. The model proposes, the control layer permits, MCP performs, RAG only supplies evidence.

## The lab at a glance

- **Terminal:** `kubectl` through the SSH tunnel that is already open, with the existing `KUBECONFIG`. This lab does not open a new tunnel.
- **Cluster:** k3s, two nodes. The lab host is the control plane and the only GPU node. The monitoring node has no GPU.
- **Local model slot:** `llama3.2:3b` via Ollama on the lab host. Embeddings stay `nomic-embed-text`.
- **What is live:** Open WebUI, Prompt Guard (fail closed), the RAG worker, the document store, the business MCP server and its sample tools, Grafana, Langfuse, and the Tailscale private ingresses.
- **What is not deployed:** the control layer, and the engineering MCP slot. This lab does not deploy either one.

## How one loop serves both contexts

Open WebUI is where a person asks. Prompt Guard sits in front of that chat. The control layer is the only thing allowed to run the agent loop. That loop may call the business MCP slot, the engineering MCP slot, or both, in either order, and stop on a budget.

Prompt Guard also sits in front of both MCP paths. If the guard is down, the call stops. No request continues past a guard that cannot answer.

Cross-share is not a sync between two agents. It is one agent with two tool sets. When the loop needs a work item, it calls engineering tools. When it needs an account or an invoice line, it calls business tools. When both are needed, it calls both in the same loop. Langfuse shows which slot each hop used. Grafana stays the operations view. It does not choose tools or call the model.

RAG and the document store stay the context layer. They supply evidence into the prompt. They do not update weights. Shared evidence that both sides should read can live in that store. Permissions stay on each MCP.

## Business MCP slot (live)

The live MCP server holds the business slot. The sample tools are:

- `search_notes`
- `fo_list_entities`
- `fo_get_entity_metadata`
- `fo_query`

That set is sample business data over MCP. The next dataset on this same slot is financial reports in Postgres. That customer-tools path is not deployed.

## Engineering MCP slot (design)

The engineering slot is not deployed. The design is a second MCP server on the same tool layer, behind the same Prompt Guard and the same control-layer budget. GitHub issues and PRs are the first tools. Azure DevOps work items come later on the same slot.

## Part A: what is already live

Part A is read-only. Compare the screen with the notes under each command. Do not apply, delete, scale, or exec anything except the single `ollama list` below.

Two nodes should be Ready. The control-plane row is the lab host. The other row is the monitoring node. Do not copy addresses, and do not use `-o wide`.

Terminal
```bash
kubectl get nodes
```

Namespace `si-lab` should already have Deployments `ollama`, `open-webui`, `prompt-guard`, `rag-worker`, and `mcp-server`, and a StatefulSet `pgvector`. There should be no Deployment named `control-layer`, and no engineering MCP Deployment.

Terminal
```bash
kubectl -n si-lab get deploy,sts,svc
```

A missing control layer and a missing engineering MCP are the expected result.

Terminal
```bash
kubectl -n si-lab get deploy control-layer
```

Terminal
```bash
kubectl -n si-lab get deploy engineering-mcp
```

The model slot should list `llama3.2:3b` and `nomic-embed-text`. This command does not pull, delete, or change keep-alive.

Terminal
```bash
kubectl -n si-lab exec deploy/ollama -- ollama list
```

## Part B: the shape of the engineering MCP service

Part B is not an install. There is no file under `k8s/` for this service. The outline below is not a manifest to save and apply. The image is unset. Budgets stay UNSET. Do not invent a tag, and do not claim a pin.

The object is a Deployment `engineering-mcp` and a ClusterIP Service of the same name, both in `si-lab`, one replica. It is not a sidecar of `mcp-server`, and it is not an Ingress. It is the second MCP slot on the tool layer.

It is scheduled only onto the lab host. It does not tolerate the observability taint. It does not request a GPU. It does not automount a service account token. It holds sample engineering data: repos, PRs, and issues in JSON on a volume, or in Postgres beside the document store. That data is sample. It is not a live GitHub or Azure DevOps tenant.

Sample tools on this slot, in words:

- list repos
- list open PRs for a repo
- get a PR
- list issues for a repo
- get an issue

Azure DevOps work-item tools are the later addition on this same slot. They are not in this outline.

It may be reached only from pods in `si-lab`, the same NetworkPolicy shape as the live business MCP. Prompt Guard stays in front of every tool call. The control layer is the only loop allowed to dial either MCP. Evidence from RAG still enters through `search_notes` on the business slot, or as retrieved text the control layer already holds. This service does not update weights.

The loop stops on a budget. Max tool calls and max tokens stay UNSET here. When either limit is hit, the loop stops and says which limit stopped it.

It fails closed. If Prompt Guard does not answer, the loop stops and does not call either MCP. If engineering MCP does not answer, the loop stops and does not pretend the tool returned data.

The trace hop, in words: one loop is one trace. Each guard check is a span. Each model call is a span. Each business tool call is a span. Each engineering tool call is a span. Those spans leave as OTLP HTTP to the collector already running for this cluster. You read both slots in Langfuse.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: engineering-mcp
  namespace: si-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: engineering-mcp
  template:
    metadata:
      labels:
        app: engineering-mcp
    spec:
      automountServiceAccountToken: false
      containers:
        - name: engineering-mcp
          image: UNSET
          env:
            - name: MCP_TRANSPORT
              value: streamable-http
            - name: SAMPLE_DATA
              value: /data/engineering-sample.json
            - name: MAX_TOOL_CALLS
              value: UNSET
            - name: MAX_TOKENS
              value: UNSET
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: http://otel-collector.monitoring.svc.cluster.local:4318
          volumeMounts:
            - name: sample-data
              mountPath: /data
              readOnly: true
      volumes:
        - name: sample-data
          configMap:
            name: engineering-mcp-sample
---
apiVersion: v1
kind: Service
metadata:
  name: engineering-mcp
  namespace: si-lab
spec:
  selector:
    app: engineering-mcp
  ports:
    - name: http
      port: 8000
      targetPort: 8000
```

Sample data shape (JSON on the volume, or the same rows in Postgres). Not live GitHub. Not live Azure DevOps.

```json
{
  "repos": [
    {"name": "invoice-service", "default_branch": "main"},
    {"name": "billing-ui", "default_branch": "main"}
  ],
  "pull_requests": [
    {"repo": "invoice-service", "number": 42, "title": "fix tax rounding", "state": "open"},
    {"repo": "billing-ui", "number": 7, "title": "Show credit memo", "state": "open"}
  ],
  "issues": [
    {"repo": "invoice-service", "number": 18, "title": "Missing company filter", "state": "open"}
  ]
}
```

## What a shared-loop question looks like

One chat, one control loop, two slots:

> What open PRs touch the invoice service, and what customer account owns that invoice line in the business tools?

The control layer calls engineering MCP for the PRs, then business MCP for the account (or the reverse). Prompt Guard sits in front of both. Langfuse shows both hops. The answer comes back in the same conversation.

## What this lab does not do

It does not deploy the control layer. It does not deploy `engineering-mcp`. It does not connect a live GitHub App, a live Azure DevOps org, or a live business tenant. It does not set budget numbers. It does not change Prompt Guard. It does not claim the 3B model is the system. The system is the guarded loop with both MCP slots attached.
