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
Logs: stderr. One access line per request, except an answered GET /health. One `[aat-mcp] call`
      line per tool or agent call and one `[aat-mcp] refused` line per refusal (bridge.py), each
      naming the turn by the X-AAT-Message-Id header of the request.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import metrics  # noqa: E402  (runtime metrics on their own port; off unless AAT_METRICS_PORT is set)
import runtime_log  # noqa: E402  (the one writer of log lines)
import server  # noqa: E402  (reuse handle/TOOLS/dispatch)
import turn_token as turn_token_reader  # noqa: E402

PATH = "/mcp"
HEALTH_PATH = "/health"  # what the liveness and readiness probes ask for
_MCP_TOOL_NAMES = frozenset(t["name"] for t in server.TOOLS)  # the only values of the mcp_tool label


def _log(text: str, *, fields: dict | None = None, level: str = runtime_log.INFO,
         exception: str | None = None) -> None:
    runtime_log.write("aat-mcp-http", text, level=level, fields=fields, exception=exception)


class _Server(ThreadingHTTPServer):
    """The HTTP server, with one change: a request that ends in an exception is one log line.

    The base class prints the traceback as it is, over many lines. A log store reads each line as
    an entry of its own, and in the JSON format none of them would be JSON."""

    def handle_error(self, request, client_address):
        kind, error, _ = sys.exc_info()
        name = getattr(kind, "__name__", "Exception")
        _log(f"request from {client_address[0] if client_address else '?'} ended in {name}",
             level=runtime_log.ERROR, fields={"ExceptionType": name},
             exception="".join(traceback.format_exception(kind, error, error.__traceback__))
             if error is not None else None)


def _log_uncaught(source: str):
    """A hook for an exception nobody caught, on the main thread or on another one: one line."""
    def hook(*args):
        # sys.excepthook passes (type, value, traceback); threading.excepthook passes one object.
        kind, error, trace = args if len(args) == 3 else (args[0].exc_type, args[0].exc_value,
                                                          args[0].exc_traceback)
        name = getattr(kind, "__name__", "Exception")
        runtime_log.write(source, f"uncaught {name}", level=runtime_log.ERROR,
                          fields={"ExceptionType": name},
                          exception="".join(traceback.format_exception(kind, error, trace)))
    return hook


def _asked_for(message) -> tuple:
    """What one JSON-RPC message asks for, as the access line may show it: the method, and for a
    tool call the MCP tool, then the tool or agent and the action it names. Names only - cut and
    put on one line like every name on a log line - and never another argument: `args`, a search
    text or a payload can hold what the user wrote."""
    if not isinstance(message, dict):
        return ("?",)
    method = server.bridge._field(message.get("method")) or "?"
    if method != "tools/call":
        return (method,)
    params = message.get("params") if isinstance(message.get("params"), dict) else {}
    arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
    tool = params.get("name")
    out = [method, tool if isinstance(tool, str) and tool in _MCP_TOOL_NAMES else "other"]
    target = (server.bridge._field(arguments.get("tool")) or server.bridge._field(arguments.get("agent"))
              or server.bridge._field(arguments.get("name")))
    action = server.bridge._field(arguments.get("action"))
    if target or action:
        out.append(target or "-")
    if action:
        out.append(action)
    return tuple(out)


def _make_handler(token: str | None):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # every line of this handler goes through here
            _log(fmt % args)

        def log_error(self, fmt, *args):  # what the base class says about a request it refused
            _log(fmt % args, level=runtime_log.WARNING)

        def log_request(self, code="-", size="-"):
            # A health probe that was answered is the one access line that says nothing, and
            # it arrives every few seconds: left in, it buries the lines about real calls.
            # A probe that was not answered with 200 is still written.
            if self.command == "GET" and code == 200 and self.path.rstrip("/") == HEALTH_PATH:
                return
            status = getattr(code, "value", code)  # http.HTTPStatus or a plain number
            text = f'"{self.requestline}" {status} {size}'
            fields = {"RequestMethod": self.command, "RequestPath": self.path,
                      "StatusCode": status if isinstance(status, int) else None}
            # What the request was for, when it got as far as being read: without it every line
            # of a turn is the same `POST /mcp 200`.
            asked = getattr(self, "_asked", None)
            if asked is not None:
                calls, named, started = asked
                seconds = time.perf_counter() - started
                text += f" {seconds:.3f}s msg={named or '-'}"
                for call in calls:
                    text += " | " + " ".join(server.bridge._log_name(part) for part in call)
                first = calls[0] if calls else ()
                fields.update(
                    MessageId=named, Seconds=round(seconds, 3),
                    McpMethod=first[0] if first else None,
                    McpTool=first[1] if len(first) > 1 else None,
                    Tool=first[2] if len(first) > 2 else None,
                    Action=first[3] if len(first) > 3 else None,
                    McpCalls=[" ".join(call) for call in calls] if len(calls) > 1 else None)
            _log(text, fields=fields,
                 level=runtime_log.INFO if isinstance(status, int) and status < 500 else runtime_log.WARNING)

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
            self._asked = None  # a connection serves many requests: nothing is carried over
            # Health probe convenience + MCP: no server-initiated SSE stream offered.
            if self.path.rstrip("/") in ("", "/health", "/healthz"):
                self._send(200, json.dumps({"ok": True, "server": server.SERVER_INFO,
                                            "tools": [t["name"] for t in server.TOOLS]}
                                           ).encode())
                return
            self._send(405, json.dumps({"error": "GET not supported; POST JSON-RPC to "
                                        + PATH}).encode())

        def do_POST(self):
            started = time.perf_counter()
            self._asked = None  # a connection serves many requests: nothing is carried over
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
                self.log_error("ignoring an unreadable or expired turn token")
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
            # The turn's message id, also from the caller's config and never from the JSON-RPC
            # body. It only names the turn on the log lines of this request; a value that is not
            # a plain id is dropped. The turn token's payload holds the same id, so a turn whose
            # config could not carry the header, or carried one that is not a plain id, is still
            # named. The header is checked before it is preferred: an unusable header that won
            # over a usable token would leave the turn's lines without a name.
            named = server.bridge.first_message_id(
                (self.headers.get(server.bridge.MESSAGE_ID_HEADER) or "").strip(),
                claims["message"] if claims is not None else None)
            _itok = server.bridge.set_message_id(named)
            try:
                batch = msg if isinstance(msg, list) else [msg]
                # For the access line, written when the answer is sent.
                self._asked = ([_asked_for(m) for m in batch], named, started)
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
                server.bridge.reset_message_id(_itok)
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
    # Before anything can fail: what nobody catches is written as one line, in the chosen format.
    sys.excepthook = _log_uncaught("aat-mcp-http")
    threading.excepthook = _log_uncaught("aat-mcp-http")
    httpd = _Server((a.host, a.port), _make_handler(a.token or None))
    _log(f"listening on http://{a.host}:{a.port}{PATH} (auth: {'on' if a.token else 'off'})",
         fields={"Host": a.host, "Port": a.port, "Auth": bool(a.token)})
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
