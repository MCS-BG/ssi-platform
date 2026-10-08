# Day 5b: add more models (local Ollama + Azure cloud models in Open WebUI)

Files, all in `~/ssi-platform/models/` on the terminal:

- `day-05b-ollama-models.yaml`: ConfigMap `ollama-models` (the model list), ConfigMap `ollama-pull-script`, and Job `ollama-pull`
- `day-05b-open-webui-cloud-models.yaml`: ConfigMap `open-webui-cloud` plus the full v0.11.4 Open WebUI Deployment (theme mount kept) with four new env vars
- `litellm-gateway-design.md`: an optional design note, nothing to apply

Each command block is labelled with the machine it runs on. None of the command blocks contain `#` lines.

## What gets added

| Model (exact Ollama tag) | Role | Download (ollama.com) | VRAM loaded (est.) | License |
|---|---|---|---|---|
| `llama3.2:3b` (already there) | general chat, used by rag-worker | 2.0 GB | 2.6 GB (measured day 3) | Llama 3.2 Community |
| `nomic-embed-text:latest` (already there) | embeddings | 274 MB | < 1 GB | Apache-2.0 |
| `qwen2.5-coder:1.5b` | coding | 986 MB | ~1.3–1.6 GB | Apache-2.0 |
| `qwen3:4b` | reasoning / general (thinking) | 2.5 GB | ~3.0–3.5 GB (tight) | Apache-2.0 |
| `granite4.1:3b` | tool calling / JSON for MCP | 2.1 GB | ~2.5–3.0 GB | Apache-2.0 |

About 5.6 GB of new files land on the external drive. All three new models are Q4_K_M. The VRAM figures are the download size plus the KV cache for Ollama's default 4k context, so treat them as estimates and check them in step 4.

**How VRAM is shared.** Ollama keeps a model loaded for `OLLAMA_KEEP_ALIVE` (already `10m`) after its last request. `OLLAMA_MAX_LOADED_MODELS` defaults to 3 per GPU, but on a GPU a second model only loads alongside the first if both fit completely in VRAM. Otherwise Ollama queues the request, unloads the idle model and loads the new one. On 4 GB that means one chat model at a time, possibly with `nomic-embed-text` next to it. Switching models costs a reload from the USB drive, which takes a few seconds.

## 1. Tunnel and cluster check

On the terminal, in its own tab:

```bash
ssh -N -L 6443:127.0.0.1:6443 <lab-user>@192.0.2.71
```

On the terminal, in a second tab:

```bash
export KUBECONFIG=~/.kube/si-lab.yaml
kubectl get nodes
kubectl -n si-lab get deploy ollama open-webui
```

Expected: node `gpu-node` is `Ready`, and both Deployments show `1/1`.

## 2. Check disk space on the external drive

On the lab host (`ssh <lab-user>@192.0.2.71`):

```bash
df -h /mnt/ailab-data
du -sh /mnt/ailab-data/ai-ops-homelab/ollama
```

Expected: at least about 8 GB free on `/mnt/ailab-data`. That's 5.6 GB for the models plus some headroom. The `du` figure grows by about 5.6 GB after step 3.

## 3. Pull the models declaratively

On the terminal:

```bash
cd ~/ssi-platform/models
kubectl apply --dry-run=server -f day-05b-ollama-models.yaml
kubectl apply -f day-05b-ollama-models.yaml
kubectl -n si-lab get pods -l job-name=ollama-pull
```

Expected:

```text
configmap/ollama-models created (server dry run)
configmap/ollama-pull-script created (server dry run)
job.batch/ollama-pull created (server dry run)
configmap/ollama-models created
configmap/ollama-pull-script created
job.batch/ollama-pull created
```

There should be no PodSecurity warning, because the Job pod also meets `restricted`. Once the pod shows `Running` (`python:3.12-slim` is already cached from days 4 and 6), follow the logs.

On the terminal:

```bash
kubectl -n si-lab logs -f job/ollama-pull
```

Expected, trimmed:

```text
Ollama is up at http://ollama.si-lab.svc.cluster.local:11434, version ...
SKIP  llama3.2:3b (already installed; set SKIP_EXISTING=false to re-pull)
SKIP  nomic-embed-text:latest (already installed; set SKIP_EXISTING=false to re-pull)
PULL  qwen2.5-coder:1.5b
  qwen2.5-coder:1.5b: pulling ... 25% of 0.99 GB
  ...
  qwen2.5-coder:1.5b: success
OK    qwen2.5-coder:1.5b
PULL  qwen3:4b ... OK    qwen3:4b
PULL  granite4.1:3b ... OK    granite4.1:3b
=== Installed models (GET /api/tags + POST /api/show) ===
  granite4.1:3b   2.1 GB  3.4B Q4_K_M caps=completion,tools  [listed]
  qwen3:4b        2.5 GB  4.0B Q4_K_M caps=completion,tools,thinking  [listed]
  ...
RESULT: ALL 5 LISTED MODELS PRESENT
```

On the terminal:

```bash
kubectl -n si-lab wait --for=condition=complete job/ollama-pull --timeout=90m
```

Expected: `job.batch/ollama-pull condition met`.

To change the list later, edit `models.txt` in the YAML, then run the commands below. Jobs are immutable, so the old one has to go first.

On the terminal:

```bash
kubectl -n si-lab delete job ollama-pull --ignore-not-found
kubectl apply -f day-05b-ollama-models.yaml
```

## 4. Verify through the Ollama API, the GPU, and tool calling

On the terminal, in a third tab:

```bash
kubectl -n si-lab port-forward svc/ollama 11435:11434
```

On the terminal, in the second tab:

```bash
curl -s http://127.0.0.1:11435/api/tags | grep -o '"name":"[^"]*"'
curl -s http://127.0.0.1:11435/api/generate -d '{"model":"qwen2.5-coder:1.5b","prompt":"Python one-liner to reverse a string","stream":false}' | grep -o '"response":"[^"]*"'
kubectl -n si-lab exec deploy/ollama -- ollama ps
```

Expected: five names, including `qwen2.5-coder:1.5b`, `qwen3:4b` and `granite4.1:3b`. Then a short code answer. Then an `ollama ps` row showing `100% GPU`.

Repeat the `generate` line with `qwen3:4b`, then run `ollama ps` again. If it shows a CPU/GPU split, the model plus context doesn't fit in 4 GB. Don't raise the context for that model, or use `qwen3:1.7b` (1.4 GB) instead.

Tool-calling check, which is the reason for `granite4.1:3b`.

On the terminal:

```bash
curl -s http://127.0.0.1:11435/api/chat -d '{"model":"granite4.1:3b","stream":false,"messages":[{"role":"user","content":"What is the weather in Chicago?"}],"tools":[{"type":"function","function":{"name":"get_weather","description":"Get current weather for a city","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}}]}' | grep -o '"tool_calls".\{0,160\}'
```

Expected: something like `"tool_calls":[{"id":"...","function":{"index":0,"name":"get_weather","arguments":{"city":"Chicago"}}}]`.

Optional: Ollama already defaults to sharing VRAM as described at the top. If you want an explicit cap of chat plus embeddings, run the command below. It restarts the Ollama pod. Because the image is `ollama/ollama:latest`, a restart may also pull a newer Ollama. Add the same env line to `~/ssi-platform/k8s/day-03/ollama.yaml` so the file matches the cluster.

On the terminal:

```bash
kubectl -n si-lab set env deploy/ollama OLLAMA_MAX_LOADED_MODELS=2
kubectl -n si-lab rollout status deploy/ollama
```

## 5. The new local models in Open WebUI

No config change is needed. Open WebUI lists whatever `OLLAMA_BASE_URL` serves.

On the terminal:

```bash
kubectl -n si-lab port-forward svc/open-webui 3000:8080
```

Open `http://127.0.0.1:3000` (type `http://` explicitly, as on day 5) and open the model dropdown. Expected: `qwen2.5-coder:1.5b`, `qwen3:4b` and `granite4.1:3b` appear next to `llama3.2:3b`.

Tip for MCP tools with small models: Open WebUI's per-model `num_ctx` control pre-fills 2048, and its docs warn that too small a context causes blank replies with Native function calling. Use at least 4096 and keep it modest on this GPU.

## 6. Azure: create the key Secret without it touching shell history

In the Azure portal, open your Azure OpenAI or Foundry resource, go to **Keys and Endpoint**, and note the resource name, one key, and the **deployment names** of the models you deployed. Open WebUI needs deployment names, not model family names.

On the terminal (zsh), replacing `YOUR-RESOURCE` and `YOUR-DEPLOYMENT` in the two `curl` lines:

```bash
read -s "AZ_KEY?Azure OpenAI key: "
echo
curl -s -o /dev/null -w 'api-key header: %{http_code}\n' https://YOUR-RESOURCE.openai.azure.com/openai/v1/models -H "api-key: $AZ_KEY"
curl -s https://YOUR-RESOURCE.openai.azure.com/openai/v1/chat/completions -H "api-key: $AZ_KEY" -H "Content-Type: application/json" -d '{"model":"YOUR-DEPLOYMENT","messages":[{"role":"user","content":"Say hi"}]}' | grep -o '"content":"[^"]*"'
printf '%s' "$AZ_KEY" | kubectl -n si-lab create secret generic open-webui-cloud-keys --from-file=AZURE_OPENAI_API_KEY=/dev/stdin
unset AZ_KEY
kubectl -n si-lab get secret open-webui-cloud-keys
```

Expected: `api-key header: 200`, then a `"content":"Hi..."` line, then `secret/open-webui-cloud-keys created`, and the Secret listed with `DATA 1`.

`read -s` doesn't echo the key. History only records the literal `$AZ_KEY`. `printf` is a zsh builtin, so the key never appears in any process's arguments.

## 7. Point Open WebUI at Azure

In `day-05b-open-webui-cloud-models.yaml`, replace `CHANGE-ME-resource` with your resource name and the `CHANGE-ME-deployment-*` entries with your deployment names. Keep `/openai/v1` at the end of the URL with no trailing slash. A Foundry `https://<name>.services.ai.azure.com/openai/v1` URL also works.

On the terminal:

```bash
grep -n 'CHANGE-ME' day-05b-open-webui-cloud-models.yaml
kubectl apply --dry-run=server -f day-05b-open-webui-cloud-models.yaml
kubectl apply -f day-05b-open-webui-cloud-models.yaml
kubectl -n si-lab rollout status deploy/open-webui
```

Expected: `grep` prints nothing. Both applies show `configmap/open-webui-cloud created` and `deployment.apps/open-webui configured`. You'll see the same `would violate PodSecurity "restricted:latest"` warning as on day 5. It's only a warning, because the namespace enforces baseline. Then `deployment "open-webui" successfully rolled out`.

**The UI will still show no Azure models at this point.** That's expected. `OPENAI_API_BASE_URLS`, `OPENAI_API_KEYS` and `OPENAI_API_CONFIGS` are PersistentConfig ("ConfigVar") settings. On its first start on day 5, Open WebUI copied the defaults (`https://api.openai.com/v1` with an empty key) into its database, and database values win over env vars from then on. Pick one of the two options in step 8.

## 8. Load the new connection into Open WebUI's database

### Option A (recommended): re-seed only the three OpenAI rows from env

This keeps the Secret as the source of truth. It backs up the database, deletes only `openai.api_base_urls`, `openai.api_keys` and `openai.api_configs`, and restarts the pod. At startup, Open WebUI re-inserts missing keys from env. Every other setting stays as it is, including the day 6 MCP tool-server connection.

On the terminal:

```bash
kubectl -n si-lab exec -i deploy/open-webui -- python3 - <<'EOF'
import sqlite3
db = "/app/backend/data/webui.db"
con = sqlite3.connect(db)
bak = sqlite3.connect(db + ".bak-day05b")
con.backup(bak)
bak.close()
print("backup:", db + ".bak-day05b")
rows = [r[0] for r in con.execute("SELECT key FROM config WHERE key LIKE 'openai.api_%' ORDER BY key")]
print("deleting:", rows)
con.execute("DELETE FROM config WHERE key LIKE 'openai.api_%'")
con.commit()
con.close()
EOF
kubectl -n si-lab rollout restart deploy/open-webui
kubectl -n si-lab rollout status deploy/open-webui
kubectl -n si-lab logs deploy/open-webui | grep -i 'seeded'
```

Expected: `deleting: ['openai.api_base_urls', 'openai.api_configs', 'openai.api_keys']`, then `successfully rolled out`, then `Seeded 3 new config defaults`.

Check what's stored now. The key is shown as a length only.

On the terminal:

```bash
kubectl -n si-lab exec -i deploy/open-webui -- python3 - <<'EOF'
import sqlite3, json
con = sqlite3.connect("/app/backend/data/webui.db")
for k in ("openai.api_base_urls", "openai.api_keys", "openai.api_configs"):
    row = con.execute("SELECT value FROM config WHERE key=?", (k,)).fetchone()
    v = json.loads(row[0]) if row else None
    if k == "openai.api_keys" and v:
        v = ["<%d chars>" % len(x) for x in v]
    print(k, "=", v)
EOF
```

Expected: your `.../openai/v1` URL, `['<NN chars>']` with a non-zero length, and the JSON config with your deployment names.

### Option B (no database edit): the Admin UI

Go to **Settings > Admin > Connections**. Under the OpenAI API connections, edit the existing `https://api.openai.com/v1` entry:

- URL: `https://<resource>.openai.azure.com/openai/v1`
- Key: paste the key
- Under Advanced, Provider: `Azure OpenAI`
- API Version: `v1`. The dialog requires a value, but v0.11.4 ignores it for `/openai/v1` URLs.
- Prefix ID: `azure`
- Model IDs: your deployment names

Then Save. With this option, the Secret and env vars only act as the seed for a rebuild.

## 9. Verify in the browser

Restart the port-forward (the `Recreate` rollout killed it).

On the terminal:

```bash
kubectl -n si-lab port-forward svc/open-webui 3000:8080
```

At `http://127.0.0.1:3000`:

- **Settings > Admin > Connections** shows the Azure URL.
- The model dropdown lists `azure.<deployment>` entries next to the Ollama models.
- Sending "Say hi" to an Azure model returns an answer.

Optional, to avoid paying for chat titles and follow-up suggestions: in **Settings > Admin > Interface**, under Tasks, set the task model to a local one such as `llama3.2:3b`.

## Rollback

**Remove one local model.** Take it out of `models.txt` and re-apply the ConfigMap so the list stays the source of truth. Then, with the step 4 port-forward running, run the commands below. `delete` returns HTTP 200 when it works and 404 if the model isn't installed.

On the terminal:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE http://127.0.0.1:11435/api/delete -d '{"model":"qwen3:4b"}'
kubectl -n si-lab exec deploy/ollama -- ollama list
```

To delete everything that isn't listed in one go, change `PRUNE` to `"true"` in the Job, delete the Job and apply again. PRUNE is skipped if any pull failed.

**Remove the pull machinery.** The model files stay on the drive.

On the terminal:

```bash
kubectl -n si-lab delete job ollama-pull --ignore-not-found
kubectl -n si-lab delete configmap ollama-models ollama-pull-script
```

**Quick Azure rollback.** Toggle the Azure connection off in **Settings > Admin > Connections**.

**Full Azure rollback.** This restores the day 5 Deployment and the day 5 default OpenAI rows, and removes the Secret and ConfigMap.

On the terminal:

```bash
kubectl apply -f ~/ssi-platform/k8s/day-05-open-webui-theme.yaml
kubectl -n si-lab rollout status deploy/open-webui
kubectl -n si-lab exec -i deploy/open-webui -- python3 - <<'EOF'
import sqlite3
con = sqlite3.connect("/app/backend/data/webui.db")
con.execute("DELETE FROM config WHERE key LIKE 'openai.api_%'")
con.commit()
print("openai rows cleared")
EOF
kubectl -n si-lab rollout restart deploy/open-webui
kubectl -n si-lab delete configmap open-webui-cloud
kubectl -n si-lab delete secret open-webui-cloud-keys
```

The backup `/app/backend/data/webui.db.bak-day05b` from step 8A is the last resort. Restoring it also rolls back any chats made after the backup.

## Top 3 failures

1. **Azure models never appear, or the pod won't start.**
   - Pod in `CreateContainerConfigError`: run `kubectl -n si-lab describe pod -l app=open-webui`. `secret "open-webui-cloud-keys" not found` means step 6 was skipped. `configmap "open-webui-cloud" not found` means the file wasn't applied.
   - Pod runs but no Azure models: the ConfigVar database rows are still the day 5 ones, so do step 8. Don't reach for `RESET_CONFIG_ON_START=true`, because it wipes every saved setting, including the MCP tool server. Don't reach for `ENABLE_PERSISTENT_CONFIG=false` either, because Admin UI changes would stop persisting.
2. **Azure errors when chatting.**
   - `401`: wrong key, or a key from a different resource. Repeat the step 6 `curl` check.
   - `404` / `DeploymentNotFound`: `model_ids` must be deployment names, and the URL must end in `/openai/v1`.
   - Timeouts: check the pod has outbound DNS/HTTPS by running `kubectl -n si-lab logs deploy/open-webui | grep -i azure`.
3. **Ollama pull or VRAM problems.**
   - `ERROR pull model manifest: file does not exist` in the Job logs: a tag typo. Check it on ollama.com/library.
   - `Ollama not reachable`: the Ollama pod is down. If it's stuck in `ContainerCreating`, the USB drive isn't mounted, because the PV uses `type: Directory`.
   - `no space left on device`: the external drive is full.
   - `ollama ps` shows a CPU/GPU split: the model plus context exceeds 4 GB. Stay at 4B or below, keep 4k context, and remember that 7B 4-bit models (about 4.7 GB) won't fit.
   - The first request after switching models is slow while the model reloads. rag-worker and mcp-server embeds can time out once, as noted on day 6. Just retry.

## Optional: AWS (Amazon Bedrock)

AWS documents two OpenAI-compatible Bedrock endpoints that take a **Bedrock API key as a Bearer token**, so no proxy is needed for chat:

- `https://bedrock-runtime.<region>.amazonaws.com/openai/v1` (recommended by AWS; IAM `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream`)
- `https://bedrock-mantle.<region>.api.aws/v1` (IAM `bedrock-mantle:CreateInference`)

Model IDs use Bedrock names, for example `openai.gpt-oss-120b` from the AWS examples. Check which models are available in your Region.

To add Bedrock as the second connection:

1. Create the Secret the same way as step 6: `read -s "BR_KEY?Bedrock API key: "`, then `printf '%s' "$BR_KEY" | kubectl -n si-lab create secret generic open-webui-bedrock-key --from-file=BEDROCK_API_KEY=/dev/stdin`, then `unset BR_KEY`.
2. In the Deployment, add this env entry **above** `OPENAI_API_KEYS`:

   ```yaml
   - name: BEDROCK_API_KEY
     valueFrom:
       secretKeyRef: {name: open-webui-bedrock-key, key: BEDROCK_API_KEY}
   ```

   Then change `OPENAI_API_KEYS` to `"$(AZURE_OPENAI_API_KEY);$(BEDROCK_API_KEY)"`.
3. In the ConfigMap, set `OPENAI_API_BASE_URLS` to `"https://<res>.openai.azure.com/openai/v1;https://bedrock-runtime.us-east-1.amazonaws.com/openai/v1"`, and add `"1": {"enable": true, "connection_type": "external", "prefix_id": "bedrock", "model_ids": ["openai.gpt-oss-120b"]}` to `OPENAI_API_CONFIGS`. Don't set the Azure flag on connection 1. The static `model_ids` list means Open WebUI never calls Bedrock's `/models`.
4. Apply the file, then repeat step 8 (option A), or add the connection in the Admin UI.

Caveat: AWS recommends long-term Bedrock API keys only for exploration, and short-term keys expire within 12 hours. For anything lasting, put a proxy that signs with IAM credentials in front instead: LiteLLM (see `litellm-gateway-design.md`) or AWS's Bedrock Access Gateway (https://github.com/aws-samples/bedrock-access-gateway).

## Optional: LiteLLM as a single gateway

See `litellm-gateway-design.md`. It's a design option only: one endpoint for Ollama, Azure and Bedrock, useful later for the MCP/agent layer and for day 7 Langfuse tracing. It isn't needed for day 5b.

## Sources (checked 2026-09-25)

- Open WebUI env reference (ConfigVar/PersistentConfig, `OPENAI_API_BASE_URLS`, `OPENAI_API_KEYS`, `OPENAI_API_CONFIGS`, `ENABLE_PERSISTENT_CONFIG`, `RESET_CONFIG_ON_START`): https://docs.openwebui.com/reference/env-configuration
- Open WebUI OpenAI-compatible providers (Azure tab with the two URL formats, Bedrock options, LiteLLM, the Provider setting): https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-openai-compatible
- Open WebUI Azure OpenAI with Entra ID (keyless, for later): https://docs.openwebui.com/tutorials/integrations/llm-providers/azure-openai/
- Open WebUI v0.11.4 source, tag `v0.11.4` = `8bd8b4f`: `backend/open_webui/config.py`, `models/config.py` (`seed_defaults` only inserts missing keys) and `routers/openai.py` (the `/openai/v1` handling)
- Microsoft Learn, Azure OpenAI v1 API: https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle
- Ollama API: pull https://docs.ollama.com/api/pull, delete https://docs.ollama.com/api/delete, tags https://docs.ollama.com/api/tags, ps https://docs.ollama.com/api/ps, show https://github.com/ollama/ollama/blob/main/docs/api.md
- Ollama FAQ (`OLLAMA_KEEP_ALIVE`, `OLLAMA_MAX_LOADED_MODELS` default 3 per GPU, `OLLAMA_NUM_PARALLEL`, `ollama ps`): https://docs.ollama.com/faq
- Ollama context length (4k default under 24 GiB VRAM): https://docs.ollama.com/context-length
- Model tags and sizes: https://ollama.com/library/qwen2.5-coder/tags, https://ollama.com/library/qwen3/tags, https://ollama.com/library/granite4.1/tags, https://ollama.com/library/llama3.2, https://ollama.com/library/nomic-embed-text
- AWS Bedrock endpoints: https://docs.aws.amazon.com/bedrock/latest/userguide/endpoints.html
- AWS Bedrock Chat Completions: https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions-mantle.html
- AWS Bedrock API keys: https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html
