# ssi-platform

Sovereign Super Intelligence is a home lab for running and operating local AI on Kubernetes, built one day at a time. The point of the system is that a business keeps control of its own model, data, tools, and the loop that is allowed to call them.

It uses k3s, a local model on a small GPU, RAG that only supplies evidence, a chat UI that is not the agent loop, an MCP server for tools, observability, and prompt-injection guardrails that fail closed. The same patterns are practised here before they are used on AKS and EKS.

## Current architecture

![SSI control layer: one agent loop, Prompt Guard in front, Microsoft 365, business and engineering MCP slots behind it](diagrams/si-control-layer-real-world.png)

One control-layer loop owns every tool call. Prompt Guard sits in front and fails closed, and each MCP slot (Microsoft 365 productivity, business or engineering) is reached only through that loop, never directly from another slot. From Day 15 the loop also remembers each conversation in Postgres, so a follow-up question can build on earlier answers from any slot. A text version is in [docs/si-control-layer-real-world-readable.md](docs/si-control-layer-real-world-readable.md).

## The three machines

| Name in the docs | Role |
| --- | --- |
| terminal | The laptop everything is driven from: `kubectl`, `helm`, `git`, `gh`, browser. Not part of the cluster. |
| lab host | k3s server with the NVIDIA GPU. Runs Ollama, pgvector, Open WebUI, the MCP server, Prompt Guard. Kubernetes node name `gpu-node`. |
| monitoring node | CPU-only k3s agent (joined on Day 6b). Runs Prometheus, Grafana, Loki, Tempo, the OpenTelemetry Collector and Langfuse. Node name `obs-node`. |

The terminal reaches the Kubernetes API through an SSH tunnel to the lab host and uses
`KUBECONFIG=~/.kube/k3s-lab.yaml`. From Day 8b the tunnel can run over Tailscale.

## Day by day

| Day | Write-up | Step file |
| --- | --- | --- |
| 1 | Host hardening | [docs/day-01-host-hardening.md](docs/day-01-host-hardening.md) |
| 2 | Secure single-node k3s with the GPU | [docs/day-02-secure-k3s.md](docs/day-02-secure-k3s.md) |
| 3 | Ollama on the GPU | [docs/day-03-model-serving.md](docs/day-03-model-serving.md) |
| 4 | RAG with pgvector | [docs/day-04-rag.md](docs/day-04-rag.md) |
| 5 | Open WebUI (5b: more models) | [docs/day-05-open-webui.md](docs/day-05-open-webui.md), [models/add-models-steps.md](models/add-models-steps.md) |
| 6 | MCP server: notes search and a mock FO OData service | [docs/day-06-mcp-server.md](docs/day-06-mcp-server.md), [mcp/day-06-steps.md](mcp/day-06-steps.md) |
| 6b | Second node for monitoring | [docs/day-06b-second-node.md](docs/day-06b-second-node.md), [docs/day-06b-obs-node-join-steps.md](docs/day-06b-obs-node-join-steps.md) |
| 7 | Observability, Langfuse and Prompt Guard | [docs/day-07-observability.md](docs/day-07-observability.md), [docs/day-07-observability-steps.md](docs/day-07-observability-steps.md) |
| 8a | Git repo, GitHub Actions image builds, GHCR images | [docs/day-08a-steps.md](docs/day-08a-steps.md) |
| 8b | Prompt Guard in the MCP server and Open WebUI, Langfuse generations, Tailscale | [docs/day-08b-steps.md](docs/day-08b-steps.md) |
| 9 | How models learn (teaching notes) | [docs/day-09-how-models-learn.md](docs/day-09-how-models-learn.md) |
| 10 | Control layer bridge, engineering MCP, and the IDE connection | [docs/day-10-control-layer-bridge-steps.md](docs/day-10-control-layer-bridge-steps.md), [docs/day-10-vscode-mcp.md](docs/day-10-vscode-mcp.md) |
| 11 | Private SSI gateway for `/control` and `/mcp` | [docs/day-11-ssi-gateway.md](docs/day-11-ssi-gateway.md) |
| 12 | SSI on AKS | [docs/day-12-ssi-on-aks.md](docs/day-12-ssi-on-aks.md) |
| 13 | Reproducible SSI on any cloud: Ansible for the nodes, OpenTofu for the cluster and apps | [docs/day-13-iac-full-stack.md](docs/day-13-iac-full-stack.md) |
| 14 | Microsoft 365 productivity MCP: Graph mail, calendar and OneDrive behind the control layer, with a one-time device-code sign-in | [docs/day-14-m365-mcp.md](docs/day-14-m365-mcp.md) |
| 15 | Conversation memory: the control layer stores each turn in Postgres and recalls it for follow-up questions across every MCP slot | [docs/day-15-conversation-memory.md](docs/day-15-conversation-memory.md) |
| 16 | Real cross-system answers: the engineering MCP reads real GitHub data (read-only, fine-grained token), the model chooses the tools (validated, keyword fallback), optional OpenAI-compatible backend for a bigger model | [docs/day-16-real-cross-system-answers.md](docs/day-16-real-cross-system-answers.md) |
| 17 | The SSI agent as a LangGraph graph: same MCP slots, Prompt Guard, memory and model backend as the control layer, runs next to it, adds an OpenAI-compatible endpoint | [docs/day-17-langgraph-steps.md](docs/day-17-langgraph-steps.md) |

## How it grew

The diagrams below are kept as a record of each stage. The current design is the one at the top of this page.

- [After Day 5](diagrams/history/homelab-architecture.svg): one GPU node running Ollama, RAG on pgvector, and Open WebUI.
- [After Day 6](diagrams/history/homelab-architecture-day06.svg): an MCP server added with notes search and a mock business service.
- [After Day 6b](diagrams/history/homelab-architecture-day06b.svg): a second node joined for monitoring.
- [After Day 7](diagrams/history/homelab-architecture-day07.svg): observability and Prompt Guard in place.
- [After Day 8](diagrams/history/homelab-architecture-day08.svg): private Tailscale access, Prompt Guard on the request path, and images from GHCR.

## Layout

| Path | Contents |
| --- | --- |
| `apps/<name>/` | Source and Dockerfile for each image built by GitHub Actions: `rag-worker`, `mcp-server`, `prompt-guard`, `control-layer`, `engineering-mcp`, `ssi-gateway`, `m365-mcp`, `ssi-langgraph` (Day 17, built from the repository root). |
| `apps/ssi-vscode-connector/` | **Sovereign Super Intelligence (SSI)** VS Code / Cursor connector. Developers set a private-network base URL and run SSI: Connect. See [`docs/ssi-vscode-connector.md`](docs/ssi-vscode-connector.md). Port-forward (`scripts/port-forward-si-mcp.sh`) is lab debug only. |
| `ide/` | MCP config examples: remote connector placeholders (`ssi-connector.mcp.json.example`) and localhost debug copies. |
| `.github/workflows/` | One workflow per image plus the shared `_build-image.yml`. Images go to `ghcr.io/<owner>/<name>:<short-sha>`. |
| `k8s/` | Every manifest and Helm values file, named `day-NN-*.yaml` after the day that introduced it. |
| `openwebui/` | The Open WebUI Prompt Guard filter function (Day 8b). |
| `scripts/pin-images.sh` | Pins the image tags in `k8s/day-08*.yaml` to the commits that built them. |
| `staged/day-08b/` | Day 8b code changes. Day 8b step 2 moves them into `apps/` so they build in their own commit, and the folder is gone after that. |
| `rag/`, `mcp/`, `prompt-guard/` | The Day 4, 6 and 7 originals, kept as history. `apps/` is the current source. |
| `models/`, `research/`, `diagrams/`, `screenshots/` | Day 5b model notes, background research, the current architecture diagram (earlier stages in `diagrams/history/`), redacted screenshots. |

## How to use it

Follow the step files in order. Each step says which machine it runs on (terminal, lab host or
monitoring node), gives the command, and shows the expected output. Secrets are never stored in the
repo. They are created with `openssl rand` or read with `read -rs` straight into Kubernetes Secrets.

## License

MIT. See [LICENSE](LICENSE).
