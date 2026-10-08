# Agent lab

This is a design lab for Sovereign Super Intelligence. It does not install the control layer. It does not apply a manifest, pull a model, train, or delete anything.

The control layer is its own small service in namespace `si-lab`, beside Open WebUI. It is not a process inside Ollama, and it is not a plugin inside the model. Open WebUI stays human chat. It does not run the agent loop.

The rule for the loop is the same as the rest of the system. The model proposes, the control layer permits, MCP performs, RAG only supplies evidence.

## The lab at a glance

- **Terminal:** `kubectl` through the SSH tunnel that is already open, with the existing `KUBECONFIG`. This lab does not open a new tunnel.
- **Cluster:** k3s, two nodes. The lab host is the control plane and the only GPU node. Its node name is `gpu-node`. The GPU has 4 GB. The monitoring node has no GPU and is tainted for observability (`ailab/role=observability:NoSchedule`).
- **Local model slot:** `llama3.2:3b` via Ollama on the lab host. Embeddings stay `nomic-embed-text`. This lab does not swap the slot and does not full-fine-tune.
- **What is live:** Open WebUI, Prompt Guard (fail closed), the RAG worker, the document store (`pgvector`), the MCP server and its sample tools, Grafana, Langfuse, and the Tailscale private ingresses. kubectl is not one of those ingresses.
- **What is not deployed:** the control layer, and the customer-tools slot for financial reports. This lab does not deploy either one.
- **Images:** this lab does not check image digests and does not treat any tag as verified. Part B leaves the image unset on purpose.

## Part A: what is already live

Part A is read-only. Compare the screen with the notes under each command. Do not apply, delete, scale, or exec anything except the single `ollama list` below.

Two nodes should be Ready. The control-plane row is the lab host, node `gpu-node`. The other row is the monitoring node. Do not copy addresses, and do not use `-o wide`.

Terminal
```bash
kubectl get nodes
```

The monitoring node should show the taint key `ailab/role`. Node `gpu-node` should not. Leave the monitoring node's printed name out of any note you keep.

Terminal
```bash
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,TAINTS:.spec.taints[*].key'
```

Namespace `si-lab` should already have Deployments `ollama`, `open-webui`, `prompt-guard`, `rag-worker`, and `mcp-server`, and a StatefulSet `pgvector`. `fo-mock` may also be there. It is the sample backend from `k8s/day-06-mcp.yaml`, not a customer database. There should be no Deployment named `control-layer`.

Terminal
```bash
kubectl -n si-lab get deploy,sts,svc
```

A missing control layer is the expected result. `NotFound` means this lab is still a design.

Terminal
```bash
kubectl -n si-lab get deploy control-layer
```

The model slot should list `llama3.2:3b` and `nomic-embed-text`. This command does not pull, delete, or change keep-alive. Nothing in the list is a fine-tune.

Terminal
```bash
kubectl -n si-lab exec deploy/ollama -- ollama list
```

Three private ingresses should already exist, from `k8s/day-08b-tailscale-ingress.yaml`: `open-webui` in `si-lab`, `grafana` in `monitoring` (Service `kps-grafana`), and `langfuse` in `langfuse` (Service `langfuse-web`). The class is `tailscale`. They are tailnet names, not a public front door. There should be no Funnel annotation. Do not add one.

Terminal
```bash
kubectl get ingress -A
```

Prompt Guard and MCP only accept pods in `si-lab`. The policies are `prompt-guard-allow-si-lab` in `k8s/day-07-prompt-guard.yaml` and `mcp-server-allow-si-lab` in `k8s/day-06-mcp.yaml`. A control layer placed in another namespace would be refused by those policies. That is one reason it belongs beside Open WebUI, in `si-lab`.

Terminal
```bash
kubectl -n si-lab get networkpolicy prompt-guard-allow-si-lab mcp-server-allow-si-lab
```

## Part B: the shape of the service

Part B is not an install. There is no file under `k8s/` for this service. The outline below is not a manifest to save and apply. The image is unset. No tag is chosen here. Do not invent one, and do not claim a pin.

The object is a Deployment `control-layer` and a ClusterIP Service of the same name, both in `si-lab`, one replica. It is not a sidecar of `ollama`, and it is not an Ingress. Open WebUI keeps the human chat ingress from `k8s/day-08b-tailscale-ingress.yaml`. This service is not a fourth published UI.

It is scheduled only onto node `gpu-node`, with `kubernetes.io/hostname: gpu-node`. It does not tolerate `ailab/role=observability`. The monitoring node is for Grafana, Langfuse, and the collector, not for the loop. It does not request `nvidia.com/gpu`. The 4 GB card stays with Ollama. It does not mount the model volume from `k8s/day-03/ollama.yaml`, and it does not automount a service account token. It calls Services. It does not administer the cluster.

It may call only these cluster addresses, which already exist:

- The model, at `http://ollama.si-lab.svc.cluster.local:11434`, slot `llama3.2:3b`. That call is the proposal. The service does not load a second model and does not full-fine-tune.
- Prompt Guard, at `http://prompt-guard.si-lab.svc.cluster.local:8080/classify`, before a tool runs. The guard stays fail closed. This outline does not set a new threshold and does not restate the one already in the live manifests.
- MCP, at `http://mcp-server.si-lab.svc.cluster.local:8000`. MCP performs. The sample tools are `search_notes`, `fo_list_entities`, `fo_get_entity_metadata`, and `fo_query`. That set is a stand-in.

RAG is evidence only. `rag-worker` (see `k8s/day-08a-rag-worker.yaml` and `k8s/day-04-rag-worker.yaml`) is not a Service the loop can dial, and this lab does not turn it into one. The document store is `pgvector` (`k8s/day-04-pgvector.yaml`). The control layer does not get `pgvector-auth` and does not open Postgres. Evidence enters through MCP `search_notes`, which already reads that store. Retrieved text is evidence in the prompt. It does not update weights.

The loop stops on a budget. Two limits live on this service: max tool calls, and max tokens. This lab does not pick the numbers. When either limit is hit, the loop stops and says which limit stopped it. It does not make one more call.

It fails closed. If Prompt Guard does not answer, the loop stops and does not call MCP or the model again. If MCP does not answer, the loop stops and does not pretend the tool returned data. There is no fail-open switch in this design.

The trace hop, in words: one loop is one trace. Inside it, each hop is a span. The guard check is a span. The model call is a span, with model `llama3.2:3b` and the token counts Ollama already returns. The tool call is a span, with the tool name and the fact of a result, not a copy of a secret. Those spans leave the pod as OTLP HTTP to the collector already running for this cluster, `http://otel-collector.monitoring.svc.cluster.local:4318`, the same destination `mcp-server` uses in `k8s/day-08b-mcp-server.yaml`. The collector forwards traces to Langfuse. You read the loop in Langfuse. Grafana stays the operations view. It does not choose tools or call the model. The collector's auth header already exists as a Secret in the monitoring namespace. This lab does not create a key, print a key, or put one in the outline.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: control-layer
  namespace: si-lab
spec:
  replicas: 1
  selector:
    matchLabels:
      app: control-layer
  template:
    metadata:
      labels:
        app: control-layer
    spec:
      nodeSelector:
        kubernetes.io/hostname: gpu-node
      automountServiceAccountToken: false
      containers:
        - name: control-layer
          image: UNSET
          env:
            - name: OLLAMA_URL
              value: http://ollama.si-lab.svc.cluster.local:11434
            - name: MODEL
              value: llama3.2:3b
            - name: PROMPT_GUARD_URL
              value: http://prompt-guard.si-lab.svc.cluster.local:8080/classify
            - name: MCP_URL
              value: http://mcp-server.si-lab.svc.cluster.local:8000
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: http://otel-collector.monitoring.svc.cluster.local:4318
            - name: MAX_TOOL_CALLS
              value: UNSET
            - name: MAX_TOKENS
              value: UNSET
---
apiVersion: v1
kind: Service
metadata:
  name: control-layer
  namespace: si-lab
spec:
  type: ClusterIP
  selector:
    app: control-layer
  ports:
    - name: http
      port: 8080
```

`image: UNSET` is not a repository and not a tag. `MAX_TOOL_CALLS` and `MAX_TOKENS` are unset for the same reason. Filling them in and applying this text is outside this lab.

### What it is allowed to do

- Ask `llama3.2:3b` for the next step.
- Ask Prompt Guard to classify before a tool runs.
- Ask the MCP server to run one sample tool, then read that result and call the model again.
- Stop when the tool-call budget or the token budget is spent.
- Emit the spans described above so Langfuse can show the hop.

### What it must refuse

- Running the loop inside Open WebUI, or inside the Ollama container.
- A tool call when Prompt Guard is down, or when MCP is down.
- Any tool that is not one of the four sample tools. The financial-reports slot is not deployed. This service does not add it.
- A direct connection to `pgvector`, or any write to model weights, including a full fine-tune.
- A GPU request, a toleration for the monitoring node, or a public ingress, including Tailscale Funnel.
- A call that continues after max tool calls or max tokens.
- A closed model off the lab as the default path. That path sends data off the lab, and it is not this service.

## What this lab deliberately does not do

It does not `kubectl apply`. It does not create the Deployment, the Service, or a Secret. It does not pull or delete a model. It does not train. It does not change Prompt Guard. It does not point Open WebUI at this service. It does not add an ingress. It does not touch GitHub, Notion, or OneDrive.
