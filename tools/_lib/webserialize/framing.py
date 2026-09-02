"""Wire framing for the broker protocol: one JSON object per UTF-8 line.

Ops (proto v1) — see server.py for semantics:
  {"op": "ping"} | {"op": "status"} | {"op": "stop"}
  {"op": "run", "action": "...", "argv": [...]}
  {"op": "web-steps", "session": "...", "steps": [...], "url": ..., "headless": true}
Responses: {"ok": true, "result": {...}} or
           {"ok": false, "error": {code,message,details}, "exit_code": N}.
"""
from __future__ import annotations

import json

# A request/response can carry a full tool result (chat dumps); cap high.
MAX_LINE_BYTES = 8 * 1024 * 1024


def encode(obj: dict) -> bytes:
    return (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes | str) -> dict:
    if isinstance(line, bytes):
        line = line.decode("utf-8", errors="replace")
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError("protocol message must be a JSON object")
    return obj


def recv_line(sock, *, max_bytes: int = MAX_LINE_BYTES) -> bytes:
    """Read from ``sock`` until ``\\n`` (or EOF). Honors the socket timeout."""
    chunks: list[bytes] = []
    total = 0
    while True:
        b = sock.recv(65536)
        if not b:
            break
        chunks.append(b)
        total += len(b)
        if b"\n" in b:
            break
        if total > max_bytes:
            raise ValueError(f"protocol line exceeds {max_bytes} bytes")
    return b"".join(chunks)
