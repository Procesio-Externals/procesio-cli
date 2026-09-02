"""aat-mcp over HTTP (MCP Streamable-HTTP transport) - for containers / k8s, where
opencode connects as a *remote* MCP client. Reuses server.handle() so stdio and HTTP
share ONE dispatch + the same reversibility gate.

Endpoint: a single path (default /mcp). Client POSTs a JSON-RPC message (or a batch);
the server replies with application/json. Notifications (no id) get 202 Accepted. On
`initialize` the server issues an Mcp-Session-Id header (not enforced - single local
tenant). GET returns 405 (no server-initiated stream is needed for these tools).

Run:  python webplatform/aat_mcp/http_server.py --host 0.0.0.0 --port 8901 [--token X]
Auth: if --token or AAT_MCP_HTTP_TOKEN is set, requests must send
      `Authorization: Bearer <token>` (use for any non-loopback bind).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402  (reuse handle/TOOLS/dispatch)

PATH = "/mcp"


def _make_handler(token: str | None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # quiet; logs to stderr only if needed
            sys.stderr.write("[aat-mcp-http] " + (fmt % args) + "\n")

        def _authed(self) -> bool:
            if not token:
                return True
            got = self.headers.get("Authorization", "")
            return got == f"Bearer {token}"

        def _send(self, code: int, body: bytes | None, ctype: str = "application/json",
                  extra: dict | None = None):
            self.send_response(code)
            if body is not None:
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
            else:
                self.send_header("Content-Length", "0")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if body is not None:
                self.wfile.write(body)

        def do_GET(self):
            # Health probe convenience + MCP: no server-initiated SSE stream offered.
            if self.path.rstrip("/") in ("", "/health", "/healthz"):
                self._send(200, json.dumps({"ok": True, "server": server.SERVER_INFO,
                                            "tools": [t["name"] for t in server.TOOLS]}
                                           ).encode())
                return
            self._send(405, json.dumps({"error": "GET not supported; POST JSON-RPC to "
                                        + PATH}).encode())

        def do_POST(self):
            if self.path.rstrip("/") != PATH.rstrip("/"):
                self._send(404, json.dumps({"error": f"unknown path; use {PATH}"}).encode())
                return
            if not self._authed():
                self._send(401, json.dumps({"error": "unauthorized"}).encode())
                return
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                msg = json.loads(raw.decode("utf-8")) if raw else None
            except ValueError:
                self._send(400, json.dumps(
                    {"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32700, "message": "parse error"}}).encode())
                return

            # Server-established user (multi-user platform). The auth gateway sets
            # X-AAT-User; it is NEVER taken from the JSON-RPC body / model output. Bound
            # for this request only, so the tool subprocess runs as that user.
            uid = self.headers.get("X-AAT-User") or None
            _utok = server.bridge.set_user(uid)
            try:
                batch = msg if isinstance(msg, list) else [msg]
                responses = []
                is_initialize = False
                for m in batch:
                    if not isinstance(m, dict):
                        continue
                    if m.get("method") == "initialize":
                        is_initialize = True
                    resp = server.handle(m)
                    if resp is not None:
                        responses.append(resp)
            finally:
                server.bridge.reset_user(_utok)

            if not responses:
                self._send(202, None)  # only notifications
                return
            out = responses if isinstance(msg, list) else responses[0]
            extra = {"Mcp-Session-Id": uuid.uuid4().hex} if is_initialize else None
            self._send(200, json.dumps(out, ensure_ascii=False).encode(), extra=extra)

    return Handler


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--token", default=os.environ.get("AAT_MCP_HTTP_TOKEN", ""))
    a = ap.parse_args()
    httpd = ThreadingHTTPServer((a.host, a.port), _make_handler(a.token or None))
    sys.stderr.write(f"[aat-mcp-http] listening on http://{a.host}:{a.port}{PATH} "
                     f"(auth: {'on' if a.token else 'off'})\n")
    sys.stderr.flush()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
