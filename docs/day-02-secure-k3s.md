# Day 2: A secure single-node k3s cluster with a working GPU

Yesterday I hardened the lab host: automatic security updates, a deny-by-default firewall, fail2ban, and key-only SSH. Today's goal was to put Kubernetes on that host without undoing any of it, and to finish with a pod that can actually use the GPU.

By the end of the night I had a single-node k3s cluster that exposes nothing new to my network, keeps its secrets encrypted on disk, runs lab workloads under a restricted security policy, and hands the NVIDIA GPU to any pod that asks for it. I manage all of it from my laptop's terminal.

## The lab at a glance

- **Workstation:** my laptop, where I edit code and run `kubectl` and `helm`.
- **Lab host:** an Ubuntu laptop with an NVIDIA laptop GPU (4 GB of video memory). This runs k3s.
- **External drive:** a large USB drive on the lab host, used only for model weights and caches.

Placeholders used below: `labuser` is the SSH user on the lab host, `<lab-lan-ip>` is its address on my home network, and `labnode` is the Kubernetes node name.

## Design decisions before installing anything

**Single-node k3s.** k3s is a lightweight, fully conformant Kubernetes distribution that installs as one service. For a one-machine lab it gives me real Kubernetes objects (namespaces, policies, runtime classes, Helm charts) without the overhead of a full cluster.

**No new open ports.** The Kubernetes API listens on port 6443. I did not add a firewall rule for it. Instead, I reach it through an SSH tunnel, so the only way in is still the key-only SSH I set up on day 1.

**Locked-down admin file.** k3s writes an admin kubeconfig to `/etc/rancher/k3s/k3s.yaml`. I install with mode `600`, so only root on the lab host can read it.

**Secrets encrypted at rest.** Kubernetes Secrets are stored in the cluster datastore. The `--secrets-encryption` flag makes k3s encrypt them on disk.

**No ingress controller yet.** k3s ships with Traefik for inbound HTTP. Nothing in this lab should be reachable from outside yet, so I disabled it. I'll add ingress deliberately later if I need it.

**Cluster data on the internal SSD, models on the external drive.** The cluster datastore and container images stay on the internal NVMe drive. The external drive is USB and formatted exFAT, which is a poor fit for a database and for container storage, so it only holds large model files.

## Step 1: Install k3s on the lab host

On the lab host:

```bash
curl -sfL https://get.k3s.io | sh -s - \
  --write-kubeconfig-mode 600 \
  --secrets-encryption \
  --disable traefik
```

Verify it:

```bash
sudo systemctl is-active k3s
sudo k3s kubectl get nodes
sudo k3s kubectl get pods -A
```

I got `active`, the node showed `Ready` on `v1.36.4+k3s1`, and `kube-system` had exactly three pods running: CoreDNS, the local-path storage provisioner, and metrics-server. There was no Traefik pod, which confirms the flag worked.

## Step 2: Create namespaces with a security baseline

I created two namespaces. `si-lab` is for my own workloads. `gpu-system` is for GPU infrastructure, which needs more host access than normal apps.

On the lab host:

```bash
sudo k3s kubectl create namespace si-lab
sudo k3s kubectl create namespace gpu-system
sudo k3s kubectl label namespace si-lab \
  pod-security.kubernetes.io/enforce=baseline \
  pod-security.kubernetes.io/enforce-version=latest
```

The label turns on Kubernetes Pod Security Admission at the `baseline` level for `si-lab`. It rejects pods that ask for privileged mode, host networking, host folders mounted directly, and similar escalations. `gpu-system` is left without that label because the NVIDIA device plugin legitimately needs host access.

## Step 3: Manage the cluster from my own terminal

Instead of SSHing into the lab host for every command, I run `kubectl` locally and send it through an SSH tunnel.

**Open the tunnel.** In a terminal on the workstation, in its own tab:

```bash
ssh -N -L 6443:127.0.0.1:6443 labuser@<lab-lan-ip>
```

`-L` forwards port 6443 on my workstation to port 6443 on the lab host's loopback interface. `-N` means "don't open a shell." After the passphrase, the tab just sits there with no prompt. That looks frozen, but it's the tunnel doing its job. Adding `-v` shows `Local forwarding listening on 127.0.0.1 port 6443` if you want proof.

**Copy the kubeconfig.** Because the admin file is root-only, I made a temporary copy on the lab host that my user can read:

```bash
sudo cp /etc/rancher/k3s/k3s.yaml ~/k3s-lab.yaml
sudo chown labuser:labuser ~/k3s-lab.yaml
chmod 600 ~/k3s-lab.yaml
```

Then, from the workstation terminal:

```bash
mkdir -p ~/.kube
scp labuser@<lab-lan-ip>:~/k3s-lab.yaml ~/.kube/k3s-lab.yaml
chmod 600 ~/.kube/k3s-lab.yaml
ssh labuser@<lab-lan-ip> 'rm ~/k3s-lab.yaml'
```

The last line removes the temporary copy, since it's a full admin credential.

The kubeconfig points at `https://127.0.0.1:6443`. That's the lab host's own loopback address, and it's also exactly where the tunnel listens on my workstation, so no edits are needed.

**Install the tools and connect.** I installed `kubectl` with Homebrew (`brew install kubectl`), then:

```bash
export KUBECONFIG=~/.kube/k3s-lab.yaml
echo 'export KUBECONFIG=~/.kube/k3s-lab.yaml' >> ~/.zshrc
kubectl get nodes
kubectl get ns
```

The node came back `Ready`, and both new namespaces were listed. My `kubectl` is 1.37 against a 1.36 cluster, which is within Kubernetes' supported skew of one minor version.

## Step 4: Smoke-test the cluster

A throwaway pod proves that scheduling works, that images pull, that the baseline policy admits normal pods, and that cluster DNS resolves:

```bash
kubectl -n si-lab run smoke --image=busybox:1.36 --restart=Never -- \
  sh -c 'echo hello-from-si-lab; nslookup kubernetes.default.svc.cluster.local'
kubectl -n si-lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/smoke --timeout=90s
kubectl -n si-lab logs smoke
kubectl -n si-lab delete pod smoke
```

The logs printed `hello-from-si-lab` and resolved the Kubernetes API service to `10.43.0.1` through CoreDNS at `10.43.0.10`.

My first attempt used the short name `kubernetes.default` and failed with `NXDOMAIN`. That's a busybox quirk, not a cluster problem: its `nslookup` doesn't apply the search domains the way other tools do. Using the fully qualified name fixed it.

## Step 5: Make the GPU available to Kubernetes

Getting a GPU into a pod takes a chain of four pieces: the NVIDIA driver on the host, the NVIDIA Container Toolkit so the container runtime can expose the GPU, a Kubernetes runtime class that uses it, and the NVIDIA device plugin so the scheduler knows the GPU exists.

**Check the driver.** On the lab host:

```bash
nvidia-smi
lspci | grep -i nvidia
ubuntu-drivers devices
```

The driver was already installed and working: an NVIDIA laptop GPU on driver 595.91.07, reporting CUDA 13.2, which is also the version Ubuntu recommends for this card.

**Install the NVIDIA Container Toolkit.** On the lab host:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
```

**Restart k3s so it detects the NVIDIA runtime.** k3s looks for the NVIDIA runtime at startup and adds it to its containerd configuration on its own:

```bash
sudo systemctl restart k3s
sudo grep -ril nvidia /var/lib/rancher/k3s/agent/etc/containerd/
```

The `grep` found the NVIDIA entries in `config.toml`. From the workstation terminal, `kubectl get runtimeclass` listed an `nvidia` runtime class.

**Install the NVIDIA device plugin with Helm.** From the workstation terminal (after `brew install helm`):

```bash
helm repo add nvdp https://nvidia.github.io/k8s-device-plugin
helm repo update
helm upgrade -i nvdp nvdp/nvidia-device-plugin \
  --namespace gpu-system \
  --set runtimeClassName=nvidia
```

Helm reported the release as deployed, but no pod appeared. The chart only schedules onto nodes that are labeled as having an NVIDIA GPU. Normally a node-labeling add-on sets that label, and I don't run one, so I added it myself:

```bash
kubectl label node labnode nvidia.com/gpu.present=true
kubectl -n gpu-system get pods -w
kubectl get node labnode -o jsonpath='{.status.allocatable.nvidia\.com/gpu}{"\n"}'
```

The plugin pod started, and the node reported `1` allocatable GPU.

## Step 6: Run a GPU pod

The final test is a pod in the restricted `si-lab` namespace that requests the GPU and runs `nvidia-smi`:

```bash
cat <<'EOF2' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: gpu-smoke
  namespace: si-lab
spec:
  restartPolicy: Never
  runtimeClassName: nvidia
  containers:
  - name: cuda
    image: nvidia/cuda:12.4.1-base-ubuntu22.04
    command: ["nvidia-smi"]
    resources:
      limits:
        nvidia.com/gpu: 1
EOF2
kubectl -n si-lab wait --for=jsonpath='{.status.phase}'=Succeeded pod/gpu-smoke --timeout=180s
kubectl -n si-lab logs gpu-smoke
kubectl -n si-lab delete pod gpu-smoke
```

The logs showed the same `nvidia-smi` table as the host, with the NVIDIA laptop GPU and 4096 MiB of memory. The pod ran under the baseline policy without any special privileges. A CUDA 12.4 image works on a CUDA 13.2 driver because newer drivers support containers built for older CUDA versions.

## What tripped me up

- **Running the tunnel on the wrong machine.** The tunnel command goes in a terminal on the workstation. I ran it from inside an SSH session on the lab host at first, which just connects the lab host to itself.
- **`Address already in use` on port 6443.** An earlier tunnel was still running. `lsof -nP -iTCP:6443 -sTCP:LISTEN` showed an `ssh` process holding the port, which meant I already had a working tunnel.
- **`permission denied` from plain `kubectl` on the lab host.** That's the mode-600 kubeconfig working as intended. On the lab host, use `sudo k3s kubectl`. Everywhere else, use the tunnel.
- **The device plugin installed but no pod ran.** The chart waits for a GPU node label. Adding `nvidia.com/gpu.present=true` fixed it.
- **busybox `nslookup` and short names.** Use the fully qualified service name in smoke tests.

## Where the lab stands

- Single-node k3s with no API port exposed to the network, secrets encrypted at rest, and no ingress
- Cluster managed from my workstation terminal through an SSH tunnel
- `si-lab` running under the baseline Pod Security level, and `gpu-system` holding the GPU infrastructure
- The GPU schedulable from Kubernetes with `nvidia.com/gpu: 1`

One real constraint shapes what comes next. This GPU has 4 GB of memory, which comfortably fits small quantized models in the 1 to 4 billion parameter range, plus embedding models for retrieval. That's plenty for learning model serving, MCP servers, and RAG pipelines. Larger models belong on cloud GPUs.

## Next: Day 3

Day 3 is serving a real model: Ollama as an internal-only service in `si-lab`, with a small model stored on the external drive. The baseline policy blocks pods from mounting host folders directly, so the drive will be attached through a PersistentVolume and PersistentVolumeClaim instead, which keeps the policy intact.

## How this maps to Azure (AKS)

- **SSH tunnel instead of an open API port.** On AKS, the equivalent is a private cluster, or API server authorized IP ranges, with access through a jump box, Azure Bastion, or `az aks command invoke`.
- **k3s secrets encryption.** On AKS, that's etcd encryption with a customer-managed key in Azure Key Vault (KMS).
- **Pod Security Admission.** It's the same Kubernetes feature and the same namespace labels on AKS. Azure Policy for AKS can enforce it across clusters.
- **GPU setup.** AKS GPU node pools handle the NVIDIA driver on the node image. You still decide how the device plugin is managed, either AKS-managed or the NVIDIA GPU Operator.
- **Model storage.** The PersistentVolume pattern from day 3 carries over directly, with Azure Disk or Azure Files in place of the external drive.

## AWS delta

On EKS, the matching pieces are a private API endpoint, envelope encryption of Secrets with AWS KMS, the EKS-optimized accelerated AMI (which comes with the NVIDIA driver and container toolkit), and the same NVIDIA device plugin or GPU Operator. Pod Security Admission works the same way.
