# Reflection AI Beam: what it would take to run it in SSI

Status on 2026-10-06: Beam was announced on 2026-10-05. The **weights are not released yet** (no Hugging Face repository as of 2026-10-06). Reflection says the weights, model card and technical report ship "later this month" under Apache 2.0. Everything below marked **ESTIMATE** is our arithmetic, not a Reflection number. Redo it when the model card ships.

The lab keeps running **Llama 3.2 3B** (open-weight, Meta license) on Ollama day to day. Beam is a demo or paying-client option on rented cloud GPUs, switched on with `model_backend = "vllm"` and switched off when the session ends.

## Official numbers (Reflection)

Source: [Introducing Beam: Reflection's 501B open-weight model](https://reflection.ai/blog/introducing-beam), 2026-10-05.

| Item | Official value |
| --- | --- |
| Architecture | Sparse Mixture-of-Experts, fine-grained routed experts, interleaved local and global attention |
| Parameters | 501B total, 23B active per token |
| Layers | 52 |
| Context | Effective context extended to 1M tokens in midtraining; RL rollouts used up to 256K |
| Modality | Text only |
| Focus | Coding, reasoning, agentic and tool-calling work |
| Reasoning control | A reasoning effort parameter (shorter vs longer reasoning) |
| Pretraining | 23.8T tokens, under four weeks on 6,144 GB300 NVL72 GPUs |
| RL | 100M+ rollouts on 10.5K GB300 GPUs over four weeks |
| License | Apache 2.0 **planned** for the weights release |
| Availability | Waitlist / early access today; weights "later this month" |
| Benchmarks (selected, vendor-reported) | SWE-bench Verified 80.9, Terminal Bench v2.1 80.1, SWE Bench Pro v1 65.5, GPQA Diamond 90.5, MCP Atlas 78.7 |
| Efficiency claim | Comparable to GLM-5.2 on advanced reasoning with 3-4x less inference compute (their FLOPs approximation excludes prefill and serving overhead) |

Not published by Reflection yet: serving hardware, memory requirements, released precision (BF16 / FP8), supported quantizations, expert count and experts per token, vLLM or SGLang support, prices.

Third-party reporting (useful, not authoritative):

- [Kingy AI launch analysis](https://kingy.ai/news/reflection-beam-501b-open-weight-ai-guide/): hosted beta API model id `Beam-501B-A23B`, 262,144-token combined context on the beta API, OpenAI-compatible base URL, raw weight math (16-bit about 1,002 GB, 8-bit about 501 GB, 4-bit about 250.5 GB).
- [The Frontier](https://www.thefrontier.dev/articles/reflection-beam-501b-open-weight-model): confirms no weights, model card or hardware requirements yet; no independent benchmark exists.
- [Metir AI benchmark summary](https://www.metirai.com/blog/reflection-ai-beam-501b-open-weight-moe-model-benchmarks-2026): benchmark recap of the same vendor table.

## Sizing (ESTIMATES)

MoE detail that matters: only 23B parameters do work per token, so **compute** per token is small, but **all 501B weights must sit in GPU memory**. Size by total parameters.

Weights alone:

| Precision | Bytes per param | Weights (ESTIMATE) |
| --- | --- | --- |
| BF16 | 2 | about 1.0 TB |
| FP8 | about 1 | about 500 GB |
| 4-bit (AWQ / GPTQ / NVFP4) | about 0.5 plus scales | about 250-280 GB |

Add KV cache, activations and engine overhead. KV cache grows with context length times concurrent requests; the 1M context is not something to serve on one node.

| Precision | GPUs (ESTIMATE) | Fit | Notes |
| --- | --- | --- | --- |
| FP8 | 1x 8xH100 80 GB (640 GB) | At a squeeze | About 500 GB weights leaves roughly 100 GB for KV and overhead. Short contexts (for example 32K), low concurrency. Good enough for a demo. |
| FP8 | 1x 8xH200 141 GB (about 1.1 TB) | Comfortable | Recommended single-node target. Room for long contexts and a few concurrent users. |
| 4-bit | 4xH100 (320 GB) or 2xH200 (282 GB) | Tight | Cheapest option. Expect some quality loss; test on your own tasks first. Only if a 4-bit checkpoint or recipe is published. |
| BF16 | 8xH200 (about 1.1 TB) | Very tight | Weights nearly fill memory. |
| BF16 | 8xB200 (about 1.5 TB) | Comfortable | Full precision on one node. |

Serving engine: **vLLM** (what OpenTofu deploys here, `vllm/vllm-openai`) or **SGLang**, both OpenAI-compatible. One node, tensor parallel across 8 GPUs (`vllm_tensor_parallel_size = 8`) plus expert parallel (`vllm_enable_expert_parallel = true`) for the MoE layers. Use the engine version named in Reflection's model card once it ships; Day 13 pins `vllm/vllm-openai:v0.31.0` as a placeholder that may need bumping.

Other resources (ESTIMATES):

- Disk: 1-2 TB of fast local NVMe for the checkpoint (BF16 download about 1 TB, plus room for an FP8 copy and engine cache). Download time on first start dominates; keep the weights on a persistent volume (`vllm_weights_size`) or a node-local NVMe path (`vllm_weights_host_path`) so restarts do not re-download.
- Host RAM: at least as much as the weights you load (500 GB+ for FP8). The 8-GPU SKUs below ship with roughly 2 TB; check the SKU page.
- Shared memory: `/dev/shm` of 16-64 GB for tensor-parallel workers (`vllm_shm_size`).
- Networking: keep it on **one node** so tensor parallel runs over NVLink/NVSwitch. Multi-node serving needs InfiniBand (Azure), EFA (AWS) or GPUDirect-TCPX/TCPXO (GCP) and is out of scope for SSI demos.

## Cloud SKUs

All three envs ship the GPU pool **off** (`enable_gpu_pool = false`) with an 8xH100 SKU as the default. Swap the SKU variable for H200 or B200 when you need the headroom.

| Cloud | 8xH100 80 GB (default) | 8xH200 141 GB | 8xB200 | Variable |
| --- | --- | --- | --- | --- |
| Azure (AKS) | `Standard_ND96isr_H100_v5` | `Standard_ND96isr_H200_v5` | check current ND-series B200/GB200 offers in your region | `gpu_pool_vm_size` |
| AWS (EKS) | `p5.48xlarge` | `p5e.48xlarge` / `p5en.48xlarge` | `p6-b200.48xlarge` | `gpu_instance_type` |
| GCP (GKE) | `a3-highgpu-8g` (`nvidia-h100-80gb`) | `a3-ultragpu-8g` (`nvidia-h200-141gb`) | `a4-highgpu-8g` (`nvidia-b200`) | `gpu_machine_type` + `gpu_accelerator_type` |

Quota: every one of these needs a GPU quota increase (Azure: ND H100/H200 v5 family vCPUs; AWS: "Running On-Demand P instances" vCPUs, 192 per p5 node; GCP: `NVIDIA_H100_GPUS` / H200 / B200 per region, plus A3/A4 machine availability in the zone). Many accounts start at zero. Ask days before a demo, or use capacity reservations / Capacity Blocks / DWS calendar mode.

Cost: these are among the most expensive instances on each cloud. **Check current on-demand pricing** on the provider's pricing page for your region before you start; no prices are quoted here because they change and differ by region and commitment.

## How to run Beam in SSI (when the weights ship)

1. Request GPU quota on the target cloud.
2. Put a Hugging Face token in `secrets.auto.tfvars` as `hf_token` (git-ignored) if the repository is gated.
3. In the env's `terraform.tfvars`: `enable_gpu_pool = true`, `model_backend = "vllm"`, `vllm_model_id = "<repo id from the model card>"`, `vllm_quantization = "fp8"` (or `"none"` if the checkpoint is already FP8), `vllm_max_model_len = 32768`, `vllm_weights_size = "1500Gi"`.
4. `tofu plan`, read it, `tofu apply`.
5. Wait for the vllm pod's `/health` (first start downloads the weights).
6. Run the demo. Then set `enable_gpu_pool = false` and `model_backend = "ollama"` and apply again, or `tofu destroy` the whole env.

Known gap: the SSI control layer currently calls the Ollama API (`/api/generate`). OpenTofu points it at the vLLM Service and sets `MODEL_API=openai`, but `apps/control-layer/server.py` still needs a small OpenAI-compatible (`/v1/chat/completions`) branch before Beam answers through the control layer. Open WebUI and the SSI Connector can talk to vLLM's OpenAI endpoint directly in the meantime.
