# Day 8: Private access, Prompt Guard in the path, images from GitHub

Day 8 makes the lab reachable without the home router, puts Prompt Guard in the request path, and stops building images by hand. The chat, Grafana, and Langfuse stay on the tailnet. Nothing is published to the public internet.

The sample MCP tools (`search_notes` and the `fo_*` mock) are still a stand-in. They are what the next piece replaces: a financial-report dataset, with Power BI as the chart layer on the same numbers.

## The lab at a glance

- **Terminal:** where I run `kubectl` through an SSH tunnel to the k3s API. That tunnel now rides Tailscale. The three UIs no longer need a port-forward from this machine.
- **Phone:** on the same tailnet. Open WebUI, Grafana, and Langfuse open in the phone browser over cellular, with no home Wi-Fi and no public DNS.
- **Lab host:** node `gpu-node`, the GPU control plane. Ollama, pgvector, `rag-worker`, Open WebUI, `mcp-server`, and Prompt Guard stay here. New today: the Tailscale Kubernetes operator, in namespace `tailscale`, and three private Ingress proxies.
- **Monitoring node:** node `obs-node`, still holding Prometheus, Grafana, Langfuse, Loki, and Tempo. Tailscale is installed on the machine itself so the operator and the node can reach each other.
- **Cluster:** both nodes run k3s `v1.36.4+k3s1`. There is no Funnel and no public ingress.

## What is live

The app namespace is `si-lab` (Sovereign Super Intelligence lab). Service DNS uses that name, for example `http://prompt-guard.si-lab.svc.cluster.local:8080/classify`.

Tailscale is on the terminal, the phone, the lab host, and the monitoring node. Key expiry is off on the two nodes only, so a lab machine does not drop off the tailnet while I am away. The phone and the terminal still expire on Tailscale's normal schedule.

The Tailscale Kubernetes operator (Helm chart 1.102.4) publishes three private HTTPS names: `webui`, `grafana`, and `langfuse` on tailnet `<tailnet>.ts.net`. `kubectl` still uses the SSH tunnel to the API. The three UIs do not need that tunnel, and they stay up if the terminal is closed, as long as both lab machines are on and the phone's Tailscale is connected.

GitHub repo `MCS-BG/ssi-platform` is public. GitHub Actions builds `rag-worker`, `mcp-server`, and `prompt-guard` and pushes them to GHCR. The cluster runs those images pinned to the commit that built them, not `latest`. The Prompt Guard model stays on its volume. It is not in the public image. The three packages are public so the cluster can pull them with no registry login. A public package cannot be made private again. They contain the lab code and open-source packages only.

Prompt Guard checks each new user message in Open WebUI. The filter is global, threshold 0.5, fail closed, and pointed at `http://prompt-guard.si-lab.svc.cluster.local:8080/classify`. `mcp-server` checks tool arguments and retrieved notes before Ollama is called. If Prompt Guard cannot be reached, the call is refused.

Langfuse's sign-in URL is the tailnet host (`langfuse.nextauth.url`), so a login started on the phone stays on the phone instead of bouncing to localhost.

## How a request moves

1. The terminal or the phone reaches Open WebUI only through Tailscale.
2. The Open WebUI filter sends the newest user message to Prompt Guard. At or above 0.5 it blocks the turn.
3. If the model calls a tool, `mcp-server` classifies the string arguments first. A bad query never reaches Ollama, pgvector, or the sample customer tools.
4. After `search_notes`, each retrieved chunk is classified. A flagged chunk is withheld. The rest of the results still come back.
5. If Prompt Guard cannot be reached, the call is refused.
6. Langfuse records the question as one `rag-ask` trace (embed, search, generate) and records each guard check as a guardrail. Grafana Tempo can filter on `prompt_guard.blocked = true`.

The diagram adds the `tailscale` namespace on the lab host (the operator and one proxy per Ingress), the phone on the same tailnet, Prompt Guard on the request path from the Open WebUI filter and from `mcp-server`, and the three images pulled from GHCR, pinned to a commit SHA. The black lines are the private tailnet.

![ssi-platform architecture after Day 8](../diagrams/history/homelab-architecture-day08.svg)

## What I checked

Both nodes were Ready on k3s `v1.36.4+k3s1` before the image swap. The embedding model `nomic-embed-text` was pinned in Ollama (`keep_alive` of forever) so the first search after a quiet spell does not wait for a load.

The Open WebUI filter is saved and global. A plain question, "what GPU is in the lab host", got a refusal from `llama3.2:3b` itself: "I can't provide information about the hardware of other users' systems." That is the small model, not the guard. The guard's own block text is different. The injection check in chat completed successfully. A guard block shows as "Blocked by Prompt Guard"; a plain model refusal is not that.

## What did not change

The lab host is still the GPU control plane. The monitoring node still holds the observability stack. Day 4, Day 6, and Day 7 deployment files are not the files to re-apply. They would put the old start-up back. Day-to-day changes use the Day 8 manifests.

Dynamics 365 is not connected. The `fo_*` tools are a fake finance API so the guard had something to sit in front of. The same cluster, the same retrieval path, and the same request path are meant to work with any dataset and any MCP, not one product.

## What tripped me up

A leftover Microsoft Edge apt source on the lab host returned 404 and stopped `apt` before Tailscale could install. Disabling that one list was enough. The real Edge source was left alone.

On the terminal, zsh treats an unquoted pair of square brackets as a file glob. A `kubectl` custom-columns check that included `containers[0]` failed with "no matches found" until that argument was single-quoted.

The GPU question looked like a guard block and was not one. A 3B model refusing to talk about "someone else's hardware" is a different failure from Prompt Guard. I only trust a block when the reply is the guard's own message, or when the Open WebUI log shows the filter fired.

## How this maps to Azure (AKS)

Tailscale here is a private network in front of the UIs. On Azure that job is private endpoints, or a VPN gateway, in front of AKS. None of those open the service to the internet.

GHCR plus GitHub Actions is Azure Container Registry with a pipeline that builds on each commit and deploys the digest, not a floating tag.

Prompt Guard in the request path is the same idea as [Prompt Shields in Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection): the check runs before the model and before the data tools. Fail closed matters there too. If the safety call cannot be reached, the request should not proceed.

## AWS delta

On AWS the private path is PrivateLink, or Client VPN, in front of EKS. The registry is Amazon ECR, fed by CodeBuild or by GitHub Actions. For the guard, [Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-prompt-attack.html) has a prompt attack filter. As noted on Day 7, that filter does not evaluate tool results, which is exactly where an indirect injection through retrieved notes would come from. The lab checks those chunks itself, before they reach Ollama.

## What's next

The cluster does not become Power BI. Power BI is the chart tool. The lab holds the numbers and answers questions about them.

1. Load one extract, a spreadsheet of periods and line items, into Postgres on the cluster.
2. Replace the `fo_*` mock with MCP tools that read that table: list periods, get line items, compare two periods.
3. Ingest the matching written reports into the document store so a question can use both the table and the narrative.
4. Point Power BI Desktop at that same Postgres database and build the visuals there. The chat and the charts then share one set of numbers.

A `.pbix` file is not generated inside the cluster. Power BI Desktop is where the report is designed.
