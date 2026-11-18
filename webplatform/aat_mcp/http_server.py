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
Metrics: if AAT_METRICS_PORT is set, a second listener on that port serves Prometheus text at
      /metrics, without authentication and with nothing else on it (metrics.py). Unset or 0 = off.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402  (runtime metrics on their own port; off unless AAT_METRICS_PORT is set)
import server  # noqa: E402  (reuse handle/TOOLS/dispatch)
import turn_token as turn_token_reader  # noqa: E402

PATH = "/mcp"
_MCP_TOOL_NAMES = frozenset(t["name"] for t in server.TOOLS)  # the only values of the mcp_tool label


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

            # Who this request runs as. Never from the JSON-RPC body / model output; bound for
            # this request only, so the tool subprocess runs as that user.
            #
            # A PROCESIO turn carries X-AAT-Turn-Token (the worker writes it into that turn's
            # opencode config). Its payload names the workspace and user, and it is the only
            # identity used then - X-AAT-User / X-AAT-Workspace are ignored, so a header cannot
            # contradict the token. The payload is read, not verified (only Web-Api holds the
            # key): it scopes user data locally, while credentials stay Web-Api's decision.
            #
            # Without a token (local driver, dashboard) the older X-AAT-User header still works.
            turn_token = (self.headers.get(turn_token_reader.HEADER) or "").strip() or None
            claims = turn_token_reader.read(turn_token)
            if turn_token and claims is None:
                # Malformed or expired: run without it rather than as someone. Tools that need
                # no credential still work; the rest report "could not be resolved".
                self.log_message("ignoring an unreadable or expired turn token")
                turn_token = None
            if claims is not None:
                uid, ws = claims["user"], claims["workspace"]
            else:
                uid, ws = self.headers.get("X-AAT-User") or None, None
            _utok = server.bridge.set_user(uid)
            _wtok = server.bridge.set_workspace(ws)
            _ttok = server.bridge.set_turn_token(turn_token)
            # Same rule for the managed-turn flag: it comes from the CALLER's config (the worker sets
            # it on every turn it drives), never from the JSON-RPC body, so the model cannot clear it
            # to unlock a competing orchestration loop.
            managed = (self.headers.get("X-AAT-Managed-Turn") or "").strip().lower() in ("1", "true", "yes")
            _mtok = server.bridge.set_managed_turn(managed)
            try:
                batch = msg if isinstance(msg, list) else [msg]
                responses = []
                is_initialize = False
                for m in batch:
                    if not isinstance(m, dict):
                        continue
                    if m.get("method") == "initialize":
                        is_initialize = True
                    # Legacy era only: modern Streamable HTTP requires the Mcp-Method / Mcp-Name
                    # header rules, which this transport does not implement.
                    with metrics.mcp_request(m, _MCP_TOOL_NAMES) as seen:
                        resp = seen.response = server.handle(m, modern=False)
                    if resp is not None:
                        responses.append(resp)
            finally:
                server.bridge.reset_managed_turn(_mtok)
                server.bridge.reset_turn_token(_ttok)
                server.bridge.reset_workspace(_wtok)
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
    # After the port is bound, and in the background: the health probe answers at once, and the
    # first tool call does not start the registry scan itself.
    server.bridge.warm_registry()
    # Never fatal: a metrics port that cannot be opened is logged. The label scan waits for the
    # warm-up above and reuses its result instead of scanning again.
    if metrics.start_listener(a.host) is not None:
        server.bridge.warm_metric_labels()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
