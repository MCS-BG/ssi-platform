# Day 3 — Serving a local LLM on the GPU inside k3s

Yesterday I finished with a single-node k3s cluster that exposes nothing new to my network, encrypts its secrets at rest, runs lab workloads under the baseline Pod Security level, and can hand the NVIDIA GPU to a pod. Today's goal was to put that GPU to real work by serving a language model from inside the cluster.

By the end of the night I had Ollama running as a Kubernetes Deployment in `si-lab`, using the GPU, storing its models on the external drive, and answering requests at roughly 72 tokens per second. It is reachable only from inside the cluster, or from my terminal through `kubectl port-forward`. Nothing new is open on my home network.

## The lab at a glance

- **My terminal:** where I edit manifests and run `kubectl`. The Kubernetes API reaches it through an SSH tunnel on port 6443.
- **Lab host:** Ubuntu 26.04 running single-node k3s `v1.36.4+k3s1`, with secrets encryption on and Traefik disabled. The GPU is an NVIDIA laptop GPU with 4 GB of video memory, on driver 595.91.07 with CUDA 13.2. The NVIDIA Container Toolkit, the `nvidia` runtime class, and the NVIDIA device plugin were all set up on day 2.
- **External drive:** a USB drive formatted exFAT and mounted at `/mnt/ailab-data`. Model files go in `/mnt/ailab-data/ai-ops-homelab/ollama`. Container images stay on the internal NVMe drive.

Placeholders used below: `labuser` is the SSH user on the lab host, `<lab-lan-ip>` is its address on my home network, `labnode` is the Kubernetes node name, and `~/.kube/k3s-lab.yaml` is the kubeconfig on my terminal.

## Design decisions before deploying anything

**Ollama as the model server.** Ollama packages model downloads, GPU inference, and a simple HTTP API into one container: one image, one port, and an API that later pieces can call.

**A small model that fits the GPU.** The card has 4 GB of video memory, so I picked `llama3.2:3b`. A 3 billion parameter model in Ollama's default quantization fits with room to spare.

**Models on the external drive, through a PersistentVolume.** The `si-lab` namespace enforces the baseline Pod Security level, which rejects `hostPath` volumes written directly into a pod spec. A pod that references a PersistentVolumeClaim is allowed, though. So I created a static PersistentVolume that points at the folder on the drive, bound a claim to it, and had the pod use the claim. The policy stays intact.

**A custom storage class name.** k3s ships with the local-path provisioner as its default storage class. If my claim didn't name a class, that provisioner could grab it and create a brand-new empty folder on the internal drive. Setting `storageClassName: ailab-external` on both the volume and the claim, and naming the volume explicitly, makes sure they only bind to each other.

**Retain, not Delete.** The volume uses `persistentVolumeReclaimPolicy: Retain`. If I delete the claim, the model files on the drive stay where they are.

**Recreate, not a rolling update.** There is exactly one GPU. A rolling update starts the new pod before stopping the old one, and the new pod would sit in `Pending` waiting for a GPU that the old pod still holds. The `Recreate` strategy stops the old pod first, so a rollout never has two pods competing for one GPU.

**ClusterIP only.** The Service is type `ClusterIP`, so it has an address inside the cluster and nothing on the home network. When I want to call it from my terminal, I use `kubectl port-forward`, which rides on the same SSH tunnel as everything else.

**Keep the model warm.** `OLLAMA_KEEP_ALIVE=10m` keeps a model loaded in video memory for ten minutes after its last request. Without it, calls spaced a few minutes apart would each pay the cost of loading the model again.

## Step 1: Confirm the tunnel and the cluster

From my terminal, the tunnel runs in its own tab, just like on day 2:

```bash
ssh -N -L 6443:127.0.0.1:6443 labuser@<lab-lan-ip>
```

Then, in another tab:

```bash
export KUBECONFIG=~/.kube/k3s-lab.yaml
kubectl get nodes
```

`labnode` came back `Ready`, so the tunnel and the kubeconfig were both working.

## Step 2: Free the GPU

The device plugin advertises exactly one `nvidia.com/gpu` on this node. The `gpu-smoke` pod from day 2 was still around, so I removed it to make sure the slot was free. From my terminal:

```bash
kubectl -n si-lab delete pod gpu-smoke --ignore-not-found
```

## Step 3: Write the manifest

I keep each day's manifests in the repo. From my terminal, I created `~/ssi-platform/k8s/day-03/ollama.yaml` with four objects: the PersistentVolume, the PersistentVolumeClaim, the Deployment, and the Service.

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: ollama-models-pv
spec:
  capacity:
    storage: 200Gi
  accessModes: ["ReadWriteOnce"]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ailab-external
  hostPath:
    path: /mnt/ailab-data/ai-ops-homelab/ollama
    type: Directory
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: ollama-models
  namespace: si-lab
spec:
  accessModes: ["ReadWriteOnce"]
  storageClassName: ailab-external
  volumeName: ollama-models-pv
  resources:
    requests:
      storage: 200Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ollama
  namespace: si-lab
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels: {app: ollama}
  template:
    metadata:
      labels: {app: ollama}
    spec:
      runtimeClassName: nvidia
      containers:
      - name: ollama
        image: ollama/ollama:latest
        ports:
        - containerPort: 11434
        env:
        - {name: OLLAMA_HOST, value: "0.0.0.0:11434"}
        - {name: OLLAMA_MODELS, value: "/models"}
        - {name: OLLAMA_KEEP_ALIVE, value: "10m"}
        resources:
          requests: {cpu: "1", memory: 4Gi}
          limits: {memory: 8Gi, nvidia.com/gpu: 1}
        volumeMounts:
        - {name: models, mountPath: /models}
        readinessProbe:
          httpGet: {path: /, port: 11434}
          initialDelaySeconds: 5
          periodSeconds: 10
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: ollama-models
---
apiVersion: v1
kind: Service
metadata:
  name: ollama
  namespace: si-lab
spec:
  type: ClusterIP
  selector: {app: ollama}
  ports:
  - {port: 11434, targetPort: 11434}
```

A few details worth calling out. `type: Directory` on the volume means Kubernetes refuses to start the pod if the folder is missing, instead of quietly creating an empty one on the internal drive when the USB drive isn't mounted. `runtimeClassName: nvidia` and the `nvidia.com/gpu: 1` limit are the same two pieces the day 2 smoke test used. `OLLAMA_MODELS=/models` points Ollama at the mounted claim, and `OLLAMA_HOST=0.0.0.0:11434` makes it listen on the pod's network interface rather than only on its own loopback address. The readiness probe keeps the Service from sending traffic until the API actually answers.

## Step 4: Apply it and wait for the pod

From my terminal:

```bash
kubectl apply -f ~/ssi-platform/k8s/day-03/ollama.yaml
kubectl -n si-lab get pvc ollama-models
kubectl -n si-lab get pods -w
```

The claim showed `Bound`, which confirmed it had attached to my volume and not to a new local-path folder. The pod took a few minutes to start the first time, because the Ollama image is several gigabytes and has to be pulled onto the internal drive. Once it showed `1/1 Running`, the readiness probe was passing and the API was up.

## Step 5: Pull the model onto the external drive

From my terminal:

```bash
kubectl -n si-lab exec deploy/ollama -- ollama pull llama3.2:3b
```

`exec deploy/ollama` picks the Deployment's pod for me, so I don't have to look up the generated pod name.

To confirm the files landed on the external drive and not inside the container, I checked on the lab host:

```bash
du -sh /mnt/ailab-data/ai-ops-homelab/ollama
```

It reported `1.9G`. The model survives pod restarts, image updates, and even deleting the Deployment.

## Step 6: Run a prompt and check it's on the GPU

From my terminal:

```bash
kubectl -n si-lab exec deploy/ollama -- ollama run llama3.2:3b "In two sentences, what is Kubernetes?"
kubectl -n si-lab exec deploy/ollama -- ollama ps
```

The first command loads the model into video memory and prints the answer. The second lists what's loaded. Mine showed:

```text
NAME           ID              SIZE      PROCESSOR    CONTEXT    UNTIL
llama3.2:3b    a80c4f17acd5    2.6 GB    100% GPU     4096       8 minutes from now
```

`PROCESSOR` is the column that matters, and `100% GPU` is the proof. A split between CPU and GPU would mean the model didn't fit in video memory, and CPU only would mean the pod isn't getting the GPU at all, which usually points back at the runtime class or the device plugin. `SIZE` is 2.6 GB, which covers the weights plus the cache for the 4096-token context window, and it fits within the 4 GB card. `UNTIL` is the keep-alive timer: `OLLAMA_KEEP_ALIVE=10m` keeps the model loaded for ten minutes after the last request, and a couple of minutes had passed since my prompt.

For a second opinion, `nvidia-smi` on the lab host should list an `ollama` process holding video memory.

## Step 7: Call the API from my terminal

The Service has no address on my home network, so I forward a local port to it. From my terminal, in a second tab:

```bash
kubectl -n si-lab port-forward svc/ollama 11435:11434
```

I used local port 11435 on purpose. A native Ollama install on my laptop would already be listening on 11434, and I wanted it to be obvious which one I was talking to.

Then, in another tab:

```bash
curl http://127.0.0.1:11435/api/generate \
  -d '{"model":"llama3.2:3b","prompt":"Say hello from the lab.","stream":false}'
```

The response, trimmed (I replaced the long `context` token array with `...`):

```json
{
  "model": "llama3.2:3b",
  "response": "Hello from the lab! (In a robotic, lab-coat-clad tone) *beep boop* I'm ready to assist with your queries. What can I help you with today?",
  "done": true,
  "done_reason": "stop",
  "context": [...],
  "total_duration": 614793630,
  "load_duration": 2667991,
  "prompt_eval_count": 31,
  "eval_count": 41,
  "eval_duration": 565892000
}
```

The durations are in nanoseconds. `eval_count` is 41 tokens generated in an `eval_duration` of about 0.57 seconds, which works out to roughly 72 tokens per second. `load_duration` is under 3 milliseconds because the model was already in video memory from the previous step, which is the keep-alive setting doing its job. That speed is consistent with GPU inference. I'd expect a 3B model on this laptop's CPU to be far slower.

## What tripped me up

- **Running commands in the wrong window.** I ran `kubectl get nodes` and the tunnel command in a window that was already SSH'd into the lab host. Plain `kubectl` there gave `permission denied` on `/etc/rancher/k3s/k3s.yaml`, because that file is root-only by design. On the lab host, the right command is `sudo k3s kubectl`. The tunnel command, run from the lab host to itself, failed with `Permission denied (publickey)`, which is actually good news: it proves password login is off. The lesson is to check the prompt before every command.
- **`bind [127.0.0.1]:6443: Address already in use`.** This means a tunnel from earlier is still running. There's nothing to fix, just run `kubectl`. If the old tunnel is stuck and not forwarding anything, from my terminal:

  ```bash
  lsof -ti tcp:6443 | xargs kill
  ```

  Then start the tunnel again.
- **The single GPU slot.** The node has one GPU, and the old `gpu-smoke` pod had to go before Ollama could claim it. The same rule applies to any future GPU workload: only one pod at a time can hold it.

## Where the lab stands

- Ollama running as a Deployment in `si-lab` under the baseline Pod Security level, with the GPU assigned through the `nvidia` runtime class
- `llama3.2:3b` stored on the external drive through a static PersistentVolume with a Retain policy
- A ClusterIP Service that other workloads in the cluster can call at `ollama.si-lab.svc.cluster.local:11434`
- Access from my terminal through `kubectl port-forward` only, with nothing new exposed on the home network
- Roughly 72 tokens per second on a 4 GB laptop GPU

It's small, but it's the same shape as a production endpoint: a model server behind an internal Service, with weights on persistent storage and hardware requested through Kubernetes.

## Next: Day 4

Day 4 is putting something useful on top of this endpoint. The first steps are toward retrieval-augmented generation: an embedding model and a small vector store, both in `si-lab`. Alongside that, I want an MCP server that calls Ollama, so tools and agents can use the local model. The longer-term direction is lab integrations in the style of Dynamics 365 Finance & Operations and SQL workloads, using lab data only and never production.

## How this maps to Azure (AKS)

- **The GPU.** On AKS, this becomes a GPU node pool, for example an NC-series VM size. The NVIDIA device plugin or the NVIDIA GPU Operator makes `nvidia.com/gpu` schedulable, and the pod spec requests it the same way.
- **Model storage.** The static hostPath volume is replaced by a PersistentVolumeClaim backed by Azure Disk or Azure Files through their CSI drivers. The Retain reclaim policy and the idea of keeping weights off the container image carry over unchanged.
- **Internal-only access.** A ClusterIP Service works the same on AKS. When something outside the cluster needs to call the model, the options are an internal load balancer or a private ingress, not a public endpoint.
- **Images and secrets.** Images would come from Azure Container Registry instead of a public registry, and any API keys or connection strings would live in Azure Key Vault.
- **Bigger models.** The 4 GB card is the main limit here. Models that don't fit locally are what I'll run on AKS GPU nodes.

## AWS delta

On EKS, the matching pieces are a GPU node group (g4dn or g5 instances), PersistentVolumeClaims backed by the EBS or EFS CSI drivers, an internal Network Load Balancer for access from outside the cluster, ECR for images, and AWS Secrets Manager for secrets.
