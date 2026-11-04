# Day 17 proposal: gateway route `/control-lg` for the LangGraph agent

**Status: proposal, not applied.** Nothing in `apps/ssi-gateway/` or `k8s/day-11-ssi-gateway.yaml` changes on Day 17. Apply this only when you want the LangGraph agent reachable through the private gateway (the SSI Connector, or another IDE on the home network) instead of a port-forward.

The route mirrors `/control`: same Bearer token, same proxy function, the `/control-lg` prefix is stripped, and the edge token is not forwarded to the backend. `/control` keeps pointing at the control layer, so both engines can be called side by side.

| Through the gateway | Reaches |
| --- | --- |
| `/control/*` | `control-layer:8080` (unchanged) |
| `/control-lg/*` | `ssi-langgraph:8080` (new): `/control-lg/ask`, `/control-lg/healthz`, `/control-lg/v1/chat/completions` ... |

## Change to `apps/ssi-gateway/server.py`

```diff
--- a/apps/ssi-gateway/server.py
+++ b/apps/ssi-gateway/server.py
@@ -34,6 +34,10 @@
 BUSINESS_MCP_HOST = os.environ.get("BUSINESS_MCP_HOST", "mcp-server:8000")
 ENGINEERING_MCP_HOST = os.environ.get("ENGINEERING_MCP_HOST", "engineering-mcp:8000")
 HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "120"))
+# Day 17 (proposal): the LangGraph agent next to the control layer.
+LANGGRAPH_BASE = os.environ.get(
+    "LANGGRAPH_BASE", "http://ssi-langgraph.si-lab.svc.cluster.local:8080"
+).rstrip("/")
 
 HOP_BY_HOP = {
     "connection",
@@ -172,6 +176,12 @@
                 status, out_headers, out_body = proxy_request(
                     method, target, body=body, in_headers=in_headers
                 )
+            elif path == "/control-lg" or path.startswith("/control-lg/"):
+                rest = path[len("/control-lg") :] or "/"
+                target = f"{LANGGRAPH_BASE}{rest}" + (f"?{query}" if query else "")
+                status, out_headers, out_body = proxy_request(
+                    method, target, body=body, in_headers=in_headers
+                )
             elif path == "/mcp/business" or path.startswith("/mcp/business/"):
                 target = BUSINESS_MCP_URL
                 if query:
```

Also add `*    /control-lg/*  → ssi-langgraph (strip /control-lg prefix)` to the route list in the module docstring.

## To apply it later

1. Make the change above in `apps/ssi-gateway/server.py`.
2. Mirror the file into the `ssi-gateway-code` ConfigMap in `k8s/day-11-ssi-gateway.yaml` (the lab runs the gateway from that ConfigMap), and add the env entry `LANGGRAPH_BASE=http://ssi-langgraph.si-lab.svc.cluster.local:8080` to the gateway container.
3. No NetworkPolicy change is needed: `ssi-langgraph-allow-si-lab` (Day 17) already admits every pod in `si-lab`, the gateway included.
4. Apply `k8s/day-11-ssi-gateway.yaml` and restart the gateway.
5. In the SSI Connector, set `ssi.controlPath` to `/control-lg` to point it at the LangGraph agent (back to `/control` for the control layer).

## Tested on the box

A scratch copy of the gateway with this change, in front of the LangGraph agent and the control layer (both running locally against stubs): `/control-lg/healthz` answered `ok` with the token and `401` without it, `/control-lg/v1/models` and `/control-lg/ask` reached the LangGraph agent (`"engine": "langgraph"`), and `/control/ask` still reached the control layer.
