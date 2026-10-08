"""SSI private front door: path-route /control and /mcp/* with Bearer auth.

Lab gateway for the SSI Connector defaults:
  GET  /healthz                 local probe (no auth)
  *    /control/*               → control-layer (strip /control prefix)
  POST /mcp/business            → mcp-server /mcp
  POST /mcp/engineering         → engineering-mcp /mcp

Auth: Authorization: Bearer <token> from SSI_GATEWAY_TOKEN (K8s Secret).
Enterprise would replace this shared secret with Entra/OIDC at the edge.
Stdlib only. Fail closed if the token is unset.
"""
from __future__ import annotations

import http.client
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

PORT = int(os.environ.get("PORT", "8080"))
TOKEN = os.environ.get("SSI_GATEWAY_TOKEN", "").strip()
CONTROL_BASE = os.environ.get(
    "CONTROL_BASE", "http://control-layer.si-lab.svc.cluster.local:8080"
).rstrip("/")
BUSINESS_MCP_URL = os.environ.get(
    "BUSINESS_MCP_URL", "http://mcp-server.si-lab.svc.cluster.local:8000/mcp"
)
ENGINEERING_MCP_URL = os.environ.get(
    "ENGINEERING_MCP_URL", "http://engineering-mcp.si-lab.svc.cluster.local:8000/mcp"
)
# Host headers that match mcp-server TransportSecuritySettings allowlist.
BUSINESS_MCP_HOST = os.environ.get("BUSINESS_MCP_HOST", "mcp-server:8000")
ENGINEERING_MCP_HOST = os.environ.get("ENGINEERING_MCP_HOST", "engineering-mcp:8000")
HTTP_TIMEOUT = float(os.environ.get("HTTP_TIMEOUT", "120"))

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


def _split_base(url: str) -> tuple[str, int, bool, str]:
    parts = urlsplit(url)
    scheme = parts.scheme or "http"
    host = parts.hostname or "127.0.0.1"
    port = parts.port or (443 if scheme == "https" else 80)
    path = parts.path or "/"
    return host, port, scheme == "https", path


def proxy_request(
    method: str,
    target_url: str,
    *,
    body: bytes,
    in_headers: dict[str, str],
    override_host: str | None = None,
) -> tuple[int, list[tuple[str, str]], bytes]:
    host, port, use_tls, base_path = _split_base(target_url)
    parts = urlsplit(target_url)
    # Preserve query from the caller's path if target_url has none; caller passes full URL.
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"

    headers: dict[str, str] = {}
    for k, v in in_headers.items():
        lk = k.lower()
        if lk in HOP_BY_HOP or lk == "authorization":
            # Do not forward the edge Bearer token to ClusterIP backends.
            continue
        headers[k] = v
    headers["Host"] = override_host or f"{host}:{port}"
    headers["Connection"] = "close"
    if body and "Content-Length" not in headers and "content-length" not in {
        k.lower() for k in headers
    }:
        headers["Content-Length"] = str(len(body))

    conn: http.client.HTTPConnection
    if use_tls:
        conn = http.client.HTTPSConnection(host, port, timeout=HTTP_TIMEOUT)
    else:
        conn = http.client.HTTPConnection(host, port, timeout=HTTP_TIMEOUT)
    try:
        conn.request(method, path, body=body or None, headers=headers)
        resp = conn.getresponse()
        out_body = resp.read()
        out_headers = [
            (k, v)
            for k, v in resp.getheaders()
            if k.lower() not in HOP_BY_HOP
        ]
        return resp.status, out_headers, out_body
    finally:
        conn.close()


def join_control(rest: str, query: str) -> str:
    path = rest if rest.startswith("/") else f"/{rest}"
    if path == "":
        path = "/"
    url = f"{CONTROL_BASE}{path}"
    if query:
        url = f"{url}?{query}"
    return url


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _unauthorized(self) -> None:
        self._send(401, b'{"error":"unauthorized"}\n')

    def _forbidden_config(self) -> None:
        self._send(503, b'{"error":"gateway token not configured"}\n')

    def _check_auth(self) -> bool:
        if not TOKEN:
            self._forbidden_config()
            return False
        auth = self.headers.get("Authorization", "")
        if auth != f"Bearer {TOKEN}":
            self._unauthorized()
            return False
        return True

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length) if length else b""

    def _route(self) -> None:
        parts = urlsplit(self.path)
        path = parts.path or "/"
        query = parts.query or ""

        if self.command == "GET" and path == "/healthz":
            self._send(200, b"ok\n", "text/plain; charset=utf-8")
            return

        if not self._check_auth():
            return

        method = self.command
        body = self._read_body()
        in_headers = {k: v for k, v in self.headers.items()}

        try:
            if path == "/control" or path.startswith("/control/"):
                rest = path[len("/control") :] or "/"
                target = join_control(rest, query)
                status, out_headers, out_body = proxy_request(
                    method, target, body=body, in_headers=in_headers
                )
            elif path == "/mcp/business" or path.startswith("/mcp/business/"):
                target = BUSINESS_MCP_URL
                if query:
                    target = f"{target}?{query}"
                status, out_headers, out_body = proxy_request(
                    method,
                    target,
                    body=body,
                    in_headers=in_headers,
                    override_host=BUSINESS_MCP_HOST,
                )
            elif path == "/mcp/engineering" or path.startswith("/mcp/engineering/"):
                target = ENGINEERING_MCP_URL
                if query:
                    target = f"{target}?{query}"
                status, out_headers, out_body = proxy_request(
                    method,
                    target,
                    body=body,
                    in_headers=in_headers,
                    override_host=ENGINEERING_MCP_HOST,
                )
            else:
                self._send(404, b'{"error":"not found"}\n')
                return
        except (TimeoutError, socket.timeout) as e:
            self._send(504, f'{{"error":"upstream timeout: {e}"}}\n'.encode())
            return
        except OSError as e:
            self._send(502, f'{{"error":"upstream unreachable: {e}"}}\n'.encode())
            return
        except Exception as e:  # noqa: BLE001
            self._send(502, f'{{"error":"proxy error: {e}"}}\n'.encode())
            return

        self.send_response(status)
        for k, v in out_headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(out_body)))
        self.end_headers()
        if out_body:
            self.wfile.write(out_body)

    def do_GET(self) -> None:  # noqa: N802
        self._route()

    def do_POST(self) -> None:  # noqa: N802
        self._route()

    def do_PUT(self) -> None:  # noqa: N802
        self._route()

    def do_DELETE(self) -> None:  # noqa: N802
        self._route()

    def do_PATCH(self) -> None:  # noqa: N802
        self._route()

    def do_HEAD(self) -> None:  # noqa: N802
        self._route()


def main() -> None:
    if not TOKEN:
        print("WARNING: SSI_GATEWAY_TOKEN unset; authenticated routes return 503", flush=True)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(
        f"ssi-gateway on 0.0.0.0:{PORT} control={CONTROL_BASE} "
        f"business={BUSINESS_MCP_URL} engineering={ENGINEERING_MCP_URL}",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
