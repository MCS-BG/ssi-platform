# Design option (not deployed): LiteLLM proxy as the single model gateway in `si-lab`

Status: design note only. Nothing in day 5b depends on it. It's a candidate for when the MCP/agent layer grows (day 6 and later) and for day 7 observability with Langfuse.

## Idea

Put one OpenAI-compatible endpoint in front of every model:

```text
Open WebUI ─┐
mcp-server ─┼──> litellm (ClusterIP :4000, /v1/chat/completions, /v1/embeddings, /v1/models)
rag-worker ─┘        ├── ollama.si-lab.svc:11434   (llama3.2:3b, qwen3:4b, granite4.1:3b, qwen2.5-coder:1.5b, nomic-embed-text)
                     ├── Azure OpenAI / Foundry     (your deployments)
                     └── Amazon Bedrock             (SigV4 with IAM credentials, or a Bedrock API key)
                     └── callbacks -> Langfuse      (day 7: traces, tokens, cost, latency per model and caller)
```

Open WebUI would then have a single OpenAI connection (`http://litellm.si-lab.svc.cluster.local:4000/v1`) with a LiteLLM *virtual key*, instead of one connection per cloud. Per the Open WebUI docs, its **Provider = LiteLLM** setting only changes how requests to Open WebUI's own Anthropic Messages endpoint are handled. Normal chat doesn't change.

## Sketch of `config.yaml` (illustrative, check against the LiteLLM docs before use)

```yaml
model_list:
  - model_name: local-llama3.2-3b
    litellm_params:
      model: ollama_chat/llama3.2:3b
      api_base: http://ollama.si-lab.svc.cluster.local:11434
  - model_name: local-granite4.1-3b
    litellm_params:
      model: ollama_chat/granite4.1:3b
      api_base: http://ollama.si-lab.svc.cluster.local:11434
  - model_name: azure-chat
    litellm_params:
      model: azure/<your-deployment-name>
      api_base: https://<resource>.openai.azure.com
      api_key: os.environ/AZURE_API_KEY
      api_version: "<a GA api-version from Microsoft Learn>"
  - model_name: bedrock-chat
    litellm_params:
      model: bedrock/<bedrock-model-id>
      aws_region_name: us-east-1
litellm_settings:
  success_callback: ["langfuse"]      # day 7; needs LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST
  drop_params: true
general_settings:
  master_key: os.environ/LITELLM_MASTER_KEY
```

Kubernetes shape: Deployment `litellm` (image from `ghcr.io/berriai/litellm`, pinned to a release tag), a ConfigMap for `config.yaml`, a Secret for provider keys and the master key, a ClusterIP Service on 4000, and a NetworkPolicy allowing ingress only from `app in (open-webui, mcp-server, rag-worker)`. It can run under restricted Pod Security. Virtual keys, budgets and spend tracking need a Postgres, which could be a second database in the existing pgvector StatefulSet.

## Pros

- **One endpoint, one auth model.** Clients stop caring whether a model is local or in Azure or AWS. Swapping `azure-chat` from one deployment to another, or failing over to Bedrock, becomes a config change, not a change to every client.
- **Bedrock without long-lived bearer keys.** LiteLLM can call Bedrock with SigV4 and IAM credentials, which avoids pasting Bedrock API keys into Open WebUI. AWS recommends long-term Bedrock API keys only for exploration, and short-term keys last at most 12 hours.
- **Observability in one place (day 7).** A single Langfuse callback captures every call from Open WebUI, mcp-server and rag-worker, with tokens, latency and cost. Without the gateway, each client needs its own instrumentation.
- **Guardrails for agents.** Per-key rate limits, budgets, model allowlists, retries, fallbacks and timeouts are useful once MCP tools can start calling models in loops.
- **Open WebUI's config pain goes away.** The OpenAI connection ConfigVars are set once. Adding or removing models is then a LiteLLM config change plus a restart, not an Open WebUI database reseed.

## Cons

- **Another hop and another failure point** in front of every model, including local Ollama. If LiteLLM is down, everything is down unless clients keep a direct Ollama fallback. Open WebUI can keep its direct `OLLAMA_BASE_URL` as that fallback.
- **Feature lag and translation risk.** Ollama-native features (`/api/pull`, `keep_alive`, `think`, `num_ctx`, model management in Open WebUI) and new Azure or Bedrock parameters only work if LiteLLM maps them. rag-worker and mcp-server currently call Ollama's native `/api/embed` and `/api/generate`, so they would need changes to use `/v1/embeddings` and `/v1/chat/completions`.
- **More to run on a 16 GB laptop.** Another Python service, about a few hundred MB of RAM, and Postgres if you want keys and spend tracking. Also another image to pin and patch.
- **Secret concentration.** The gateway holds every provider credential, so it needs the tightest NetworkPolicy and RBAC in the namespace.
- **Licensing and editions.** The core is open source, but some admin and enterprise features are commercial. Check which features you need.

## Recommendation

Not needed for day 5b. With two backends (Ollama plus Azure) and one client that cares (Open WebUI), direct connections are simpler. Revisit at day 7 if Langfuse tracing across all clients, Bedrock via IAM, or per-agent budgets become requirements. At that point, run LiteLLM alongside the direct connections first, then move clients over one at a time.

## References

- LiteLLM proxy config: https://docs.litellm.ai/docs/proxy/configs
- LiteLLM deploy / images: https://docs.litellm.ai/docs/proxy/deploy
- LiteLLM providers: https://docs.litellm.ai/docs/providers/ollama, https://docs.litellm.ai/docs/providers/azure/, https://docs.litellm.ai/docs/providers/bedrock
- LiteLLM + Langfuse: https://docs.litellm.ai/docs/observability/langfuse_integration
- Open WebUI LiteLLM connection and Provider setting: https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible
- Bedrock API key types: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html
