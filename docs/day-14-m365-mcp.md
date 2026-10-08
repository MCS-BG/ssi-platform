# Day 14: Microsoft 365 productivity MCP (`m365-mcp`)

Goal: add a real productivity MCP slot to SSI. `m365-mcp` reads one person's Microsoft 365 data (mail, calendar, OneDrive) through Microsoft Graph, signed in as that person with delegated OAuth. It sits behind the control layer like the business and engineering slots, with Prompt Guard in front and fail-closed behaviour everywhere.

Everything is read-only. No Copilot seat. The account is a **personal Microsoft account** (Outlook.com / Live / Hotmail), and the app registration allows any Entra ID tenant plus personal accounts, so the authority is `common`.

How to read these steps:

- Every code block has a label above it: **Terminal** (the laptop) or **Browser**.
- Each block holds one command. Quotes are zsh-safe.
- `kubectl` needs `KUBECONFIG=~/.kube/si-lab.yaml` and the SSH tunnel to the API (Day 2 / Day 8).

## What is new

| Object | Role |
| --- | --- |
| `apps/m365-mcp/server.py` | MCP server (official MCP Python SDK, `MCPServer`), Streamable HTTP on `:8000` at `/mcp`. |
| `apps/m365-mcp/login.py` | One-time device-code sign-in. Writes the MSAL token cache to a file outside the repo and prints the `kubectl` command for the Secret. |
| `k8s/day-14-m365-mcp.yaml` | ConfigMap (code) + Deployment + Service + NetworkPolicy in `si-lab`. No Secret: you create it after signing in. |
| `charts/ssi/templates/m365-mcp.yaml` | Same workload for Helm mode (`m365Mcp.*` values). |
| `.github/workflows/build-m365-mcp.yml` | Builds `ghcr.io/<owner>/m365-mcp` on push to `main` (Helm mode image). |
| `control-layer` | New `productivity` slot: `M365_MCP_URL` (default `http://m365-mcp.si-lab.svc.cluster.local:8000/mcp`) and `M365_MCP_HOST`. |

### Tools

| Tool | Graph call | Notes |
| --- | --- | --- |
| `m365_whoami` | `GET /me` | Display name, sign-in name, id. Use it as the smoke test. |
| `m365_list_mail` | `GET /me/mailFolders/{folder}/messages` | Newest first, `top` 1-25, optional `unread_only`. |
| `m365_get_mail` | `GET /me/messages/{id}` | Headers + body preview. No attachments, no full HTML body. |
| `m365_list_events` | `GET /me/calendarView` | Now through the next `days` (1-31), times in `M365_TIMEZONE`. |
| `m365_list_onedrive` | `GET /me/drive/root/children` or `/root:/{path}:/children` | Folder listing. |
| `m365_search_onedrive` | `GET /me/drive/root/search(q=...)` | Works on personal OneDrive. |

SharePoint sites and Teams are left out on purpose: they do not exist for personal Microsoft accounts.

### Guardrails

- Prompt Guard classifies every user-supplied string argument before a tool runs (same contract as `mcp-server`). Prompt Guard down = refused (`PROMPT_GUARD_FAIL_OPEN=false`).
- Mail subjects and previews are classified on the way out. A message that looks like an injection attempt is withheld (`[withheld by Prompt Guard ...]`), because email is the easiest indirect prompt-injection channel there is.
- Only the control layer may reach `m365-mcp` (NetworkPolicy `m365-mcp-allow-control-layer`). `kubectl port-forward` still works for debugging.
- Optional `expected_account` in the Secret: the server refuses a token cache for any other account.

## How the sign-in works

1. A **public client** app is registered in Microsoft Entra for **any Entra ID tenant + personal Microsoft accounts**, so the MSAL authority is `common`. It has no client secret and no redirect URI (device code does not need one); "Allow public client flows" is on, which enables the device code flow.
2. `login.py` asks Microsoft for a device code. You open `https://www.microsoft.com/link` (the URL it prints) in any browser, type the short code, sign in with the personal account, approve the **Microsoft Authenticator** prompt (Microsoft enforces MFA if the account has two-step verification), and consent to the four read-only permissions.
3. MSAL receives an access token and a **refresh token** (it adds `offline_access`, `openid` and `profile` itself). `login.py` writes the serialized MSAL token cache to `~/.ssi/m365-token-cache.json` with mode `0600`, refuses to write inside a git work tree, and prints the `kubectl` command.
4. The Secret `m365-mcp-auth` holds `client_id`, `token_cache.json` and (optionally) `expected_account`. It is mounted read-only into the pod. Nothing is ever in git. The pod runs as non-root UID/GID `10001`, so the Deployment sets `fsGroup: 10001` and mounts the Secret with mode `0440`; with a root-owned `0400` mount the server cannot read its own token cache (fixed in `9a47bc4`).
5. At runtime MSAL refreshes access tokens silently from the cache (`acquire_token_silent`). Rotated refresh tokens stay in memory. When the Secret changes, the server reloads the cache by itself.
6. No Secret, wrong account, or a revoked/expired sign-in: the pod stays Ready (`/healthz` is `ok`) and every tool answers with a clear error that says how to sign in again. `GET /authz` shows non-secret status (client id set, cache present, number of accounts).

A refresh token for a personal account lasts about 90 days and is extended each time it is used, but a password change, "sign out everywhere", or removing the app's consent at `https://account.live.com/consent/Manage` ends it. If a tool says the sign-in expired, repeat steps 2 and 3 below.

| Setting | Where | Value |
| --- | --- | --- |
| `AZURE_CLIENT_ID` | Secret key `client_id` | Application (client) ID |
| `M365_EXPECTED_ACCOUNT` | Secret key `expected_account` | your personal Microsoft account (optional, recommended) |
| `MSAL_TOKEN_CACHE` | env | `/var/run/secrets/m365/token_cache.json` (Secret key `token_cache.json`) |
| `MSAL_REFRESH_TOKEN` | env (optional) | alternative to the cache file; not used in the lab |
| `MSAL_AUTHORITY` | env | `https://login.microsoftonline.com/common` |
| `M365_SCOPES` | env | `User.Read Mail.Read Calendars.Read Files.Read` |

## Step 1: Register the app in Microsoft Entra (once)

Browser

```text
https://entra.microsoft.com  ->  sign in with your personal Microsoft account
```

If the admin center says the account has no directory, create a free one first (the free Azure account sign-up creates a "Default Directory"). It is only a home for the app registration; who can sign in is set below.

1. **Identity > Applications > App registrations > New registration.**
2. Name: `SSI M365 MCP`.
3. Supported account types: **Any Entra ID tenant + personal Microsoft accounts**.
4. Redirect URI: leave empty (device code does not need one). Select **Register**.
5. On **Overview**, copy the **Application (client) ID**. It is not a secret, but keep it out of the repo anyway.
6. **Authentication > Settings tab > Allow public client flows: Yes > Save.** (Older portals put it under **Advanced settings**.) Either way, **Manifest** then shows `"isFallbackPublicClient": true`; setting that in the manifest and saving does the same thing. Do not add a platform or redirect URI: device code does not need one.
7. **API permissions > Add a permission > Microsoft Graph > Delegated permissions**: `User.Read` (already there), `Mail.Read`, `Calendars.Read`, `Files.Read`, `offline_access`. Select **Add permissions**. There is no admin consent for personal accounts; you consent at sign-in.
8. Do **not** create a client secret or certificate. This is a public client.

A new registration can take a few minutes to reach the consumer sign-in endpoint. If step 2 fails with `AADSTS700016` (application not found), wait five minutes and retry.

## Step 2: Sign in once (device code + Authenticator)

Terminal

```bash
python3 -m venv ~/.venvs/m365-login
```

Terminal

```bash
~/.venvs/m365-login/bin/pip install msal==1.39.0
```

Terminal

```bash
~/.venvs/m365-login/bin/python ~/ssi-platform/apps/m365-mcp/login.py --client-id 'PASTE-CLIENT-ID' --expected-account 'PASTE-YOUR-PERSONAL-ACCOUNT'
```

It prints something like `To sign in, use a web browser to open the page https://www.microsoft.com/link and enter the code ABCD1234 to authenticate.` Open the page on any device, enter the code, sign in with the personal account, approve the number-match prompt in Microsoft Authenticator, and accept the permissions. The script then prints `Signed in as ...`, the granted scopes, and the `kubectl` commands for step 3.

## Step 3: Create the Secret

Terminal

```bash
kubectl -n si-lab create secret generic m365-mcp-auth --from-literal=client_id='PASTE-CLIENT-ID' --from-literal=expected_account='PASTE-YOUR-PERSONAL-ACCOUNT' --from-file=token_cache.json="$HOME/.ssi/m365-token-cache.json" --dry-run=client -o yaml | kubectl apply -f -
```

Terminal

```bash
kubectl -n si-lab rollout restart deployment/m365-mcp
```

The restart is needed once so the pod picks up `client_id` and `expected_account` from the Secret (they are env vars). Later token cache updates are picked up without a restart.

Terminal

```bash
rm -P ~/.ssi/m365-token-cache.json
```

## Step 4: Deploy

Lab (manifests, code in a ConfigMap, pinned packages installed by an initContainer):

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-14-m365-mcp.yaml
```

Terminal

```bash
kubectl apply -f ~/ssi-platform/k8s/day-10-control-layer.yaml
```

Terminal

```bash
kubectl -n si-lab rollout status deployment/m365-mcp --timeout=180s
```

Helm mode uses the image from `build-m365-mcp.yml` (`images.m365Mcp`, `m365Mcp.enabled`). A package's first push to GHCR is private; make it public the same way as Day 8a step 6 if the cluster pulls anonymously. OpenTofu: `enable_m365_mcp = true` (default `false`).

## Step 5: Smoke test

Terminal

```bash
kubectl -n si-lab port-forward svc/m365-mcp 18000:8000
```

In a second terminal:

Terminal

```bash
curl -s -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' http://127.0.0.1:18000/mcp -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"m365_whoami","arguments":{}}}'
```

Before step 3 the expected answer is `"isError":true` with `Not signed in to Microsoft 365 ...`. After step 3 it returns your display name and sign-in name.

Through the control layer (the real path):

Terminal

```bash
kubectl -n si-lab exec deploy/control-layer -- python -c "import json,urllib.request as u;r=u.Request('http://127.0.0.1:8080/ask',data=json.dumps({'question':'What is on my calendar this week?'}).encode(),headers={'Content-Type':'application/json'});print(u.urlopen(r,timeout=120).read().decode()[:1500])"
```

The answer lists `"slot": "productivity"` and `"name": "m365_list_events"` in `tool_calls`.

## Control layer wiring

- `M365_MCP_URL` / `M365_MCP_HOST` (Helm: `controlLayer.m365McpUrl`, `controlLayer.m365McpHost`).
- The tool catalog gains `productivity.m365_*` entries, so the model-driven loop can call them as `TOOL productivity.m365_list_mail {"top":3}`.
- The planner adds productivity steps for questions about mail, inbox, calendar, meetings or OneDrive.
- A productivity tool error (for example "not signed in") becomes an error result in the answer instead of stopping the loop. Prompt Guard refusals still stop it.

## Later

- Write scopes (`Mail.Send`, `Calendars.ReadWrite`) only with an explicit approval step in the control layer.
- A `/mcp/productivity` route on `ssi-gateway` if the IDE connector should see these tools.
