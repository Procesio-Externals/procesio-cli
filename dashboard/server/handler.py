"""HTTP request handler: routing, token gate, JSON + SSE + static serving.

Stdlib only. Domain logic lives in inventory/validate/setup/llmtest; this module
just parses the request, enforces the loopback token on /api/*, dispatches, and
serializes the response. Route handlers are imported lazily inside each branch so
the server boots even while later-milestone modules are still being added.
"""
from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import security

WEB_DIR = Path(__file__).resolve().parents[1] / "web"

_CTYPES = {".html": "text/html; charset=utf-8",
           ".js": "application/javascript; charset=utf-8",
           ".css": "text/css; charset=utf-8",
           ".svg": "image/svg+xml", ".ico": "image/x-icon"}


class Req:
    """Minimal parsed-request view passed to route handlers."""
    def __init__(self, method: str, path: str, query: dict, body: dict | None):
        self.method = method
        self.path = path
        self.query = query
        self.body = body or {}

    def q(self, name: str, default=None):
        v = self.query.get(name)
        return v[0] if isinstance(v, list) and v else default


class Handler(BaseHTTPRequestHandler):
    server_version = "AATDashboard/0.1"
    protocol_version = "HTTP/1.1"

    # ---- low-level response helpers -------------------------------------
    def _send_json(self, obj, status: int = 200):
        payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_bytes(self, data: bytes, ctype: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")  # local tool - always fresh
        self.end_headers()
        self.wfile.write(data)

    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

    def _sse_send(self, event: str, data: dict):
        chunk = f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"
        self.wfile.write(chunk.encode("utf-8"))
        self.wfile.flush()

    # ---- auth -----------------------------------------------------------
    def _authed(self, query: dict) -> bool:
        tok = self.headers.get("X-Dashboard-Token")
        if not tok:
            q = query.get("token")
            tok = q[0] if isinstance(q, list) and q else None
        return security.token_ok(tok)

    # ---- static ---------------------------------------------------------
    def _serve_static(self, path: str):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR.resolve() not in target.parents and target != WEB_DIR.resolve():
            self._send_json({"error": "forbidden"}, 403)
            return
        if not target.is_file():
            self._send_json({"error": "not found", "path": path}, 404)
            return
        ctype = _CTYPES.get(target.suffix, "application/octet-stream")
        self._send_bytes(target.read_bytes(), ctype)

    # ---- dispatch -------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not path.startswith("/api/"):
            return self._serve_static(path)
        if not self._authed(query):
            return self._send_json({"error": "unauthorized"}, 401)
        if path == "/api/validate/all":
            return self._route_sse(Req("GET", path, query, None))
        return self._route(Req("GET", path, query, None))

    def do_POST(self):
        parsed = urlparse(self.path)
        path, query = parsed.path, parse_qs(parsed.query)
        if not self._authed(query):
            return self._send_json({"error": "unauthorized"}, 401)
        body = self._read_body()
        return self._route(Req("POST", path, query, body))

    def _read_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return None
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None

    def _route(self, req: Req):
        try:
            from . import routes
            fn = routes.resolve(req.method, req.path)
            if fn is None:
                return self._send_json({"error": "no such route",
                                        "path": req.path}, 404)
            result = fn(req)
            if isinstance(result, tuple):
                status, obj = result
                return self._send_json(obj, status)
            return self._send_json(result)
        except Exception as e:  # noqa: BLE001 - surface as JSON, never 500-crash
            return self._send_json(
                {"error": "handler_exception", "message": str(e),
                 "trace": traceback.format_exc().splitlines()[-6:]}, 500)

    def _route_sse(self, req: Req):
        try:
            from . import validate
            self._sse_open()
            for event, data in validate.stream_all(req):
                self._sse_send(event, data)
            self._sse_send("done", {"ok": True})
        except BrokenPipeError:
            pass
        except Exception as e:  # noqa: BLE001
            try:
                self._sse_send("error", {"message": str(e)})
            except Exception:
                pass

    def log_message(self, fmt, *args):
        # Quiet by default; the launcher prints a startup banner instead.
        pass
