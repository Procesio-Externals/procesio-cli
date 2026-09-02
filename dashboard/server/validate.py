"""Live credential validation - the 'is it actually connected?' truth.

Presence (secret exists in Credential Manager) comes free from the registry. This
layer goes further: it runs a cheap, read-only probe and reports CONNECTED /
INVALID / UNKNOWN.

Probe resolution per capability:
  1. explicit `healthcheck:` in the manifest  -> run that action, success = connected
  2. else a conventional `auth-status` action  -> run it; its `ready` field decides
  3. else                                       -> UNKNOWN (no way to probe)

We only probe when every required secret is already present - a capability with
missing creds is already known-unconfigured, so we skip the call (no point proving
the obvious, and it keeps 'validate everything on load' fast). Probes run
concurrently and stream back as they finish.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterator

import registry

from . import runner

_MAX_WORKERS = 6
_CACHE_TTL = 20.0
_PROBE_TIMEOUT = 12.0  # a dead/unreachable system (e.g. VPN-gated) fails fast
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
# Single-flight: only one full sweep runs at a time. A second concurrent
# request (e.g. a reconnecting client) is served the current cache snapshot
# instead of storming the machine with a second wave of subprocesses.
_sweep_lock = threading.Lock()


def _index() -> dict[str, dict]:
    """kind:name -> registry entry, for tools and agents."""
    idx = {}
    for t in registry.list_tools():
        idx["tool:" + t["name"]] = t
    for a in registry.list_agents():
        idx["agent:" + a["name"]] = a
    return idx


def _probe_argv(entry: dict) -> list[str] | None:
    """The argv to run for this entry's probe, or None if it has none."""
    hc = entry.get("healthcheck")
    if hc:
        action = hc.get("action") or ""
        argv = [action] if action else []
        argv += runner.flags_from(hc.get("args") or {})
        return argv
    actions = {a["name"] for a in entry.get("actions", [])}
    if "auth-status" in actions:
        return ["auth-status"]
    return None


def _interpret(entry: dict, argv: list[str], result: dict) -> dict:
    """Map a probe run to {status, detail}."""
    using_authstatus = argv == ["auth-status"] and not entry.get("healthcheck")
    if result["ok"]:
        data = result.get("data")
        # auth-status tools report their own readiness; honor it.
        if using_authstatus and isinstance(data, dict) and "ready" in data and not data["ready"]:
            return {"status": "invalid",
                    "detail": "auth-status reports not ready: " + _short(data)}
        return {"status": "connected", "detail": _short(data) if isinstance(data, dict) else ""}
    err = result.get("error") or {}
    return {"status": "invalid", "detail": (err.get("message") or err.get("code") or "probe failed")[:300]}


def _short(data: dict) -> str:
    keep = {k: v for k, v in list(data.items())[:6]
            if isinstance(v, (str, int, float, bool)) and k not in ("error",)}
    return ", ".join(f"{k}={v}" for k, v in keep.items())[:300]


def probe(key: str, entry: dict, *, force: bool = False) -> dict:
    """Run (or serve from cache) the probe for one capability."""
    if not force:
        with _lock:
            hit = _cache.get(key)
        if hit and (time.time() - hit[0]) < _CACHE_TTL:
            return hit[1]

    if entry.get("error"):
        res = {"kind": key.split(":")[0], "name": entry["name"],
               "status": "unknown", "detail": "manifest error"}
    elif entry.get("missing_secrets"):
        res = {"kind": key.split(":")[0], "name": entry["name"], "status": "unknown",
               "detail": "credentials not set: " + ", ".join(entry["missing_secrets"])}
    else:
        argv = _probe_argv(entry)
        if argv is None:
            res = {"kind": key.split(":")[0], "name": entry["name"],
                   "status": "unknown", "detail": "no healthcheck or auth-status"}
        else:
            run = runner.run_tool(entry["name"], argv, timeout=_PROBE_TIMEOUT)
            verdict = _interpret(entry, argv, run)
            res = {"kind": key.split(":")[0], "name": entry["name"], **verdict}
    with _lock:
        _cache[key] = (time.time(), res)
    return res


def stream_all(req) -> Iterator[tuple[str, dict]]:
    """Probe every capability that CAN be probed, concurrently, yielding each
    result as it lands. Items with no probe or missing creds resolve instantly."""
    idx = _index()
    force = req.q("force") in ("1", "true", "yes")
    targets = list(idx.items())

    # Single-flight: if a sweep is already running, don't launch a second wave -
    # stream whatever the cache currently holds and return.
    if not _sweep_lock.acquire(blocking=False):
        for k, e in targets:
            with _lock:
                hit = _cache.get(k)
            yield ("result", hit[1] if hit else
                   {"kind": k.split(":")[0], "name": k.split(":", 1)[1],
                    "status": "checking", "detail": "another check in progress"})
        return
    try:
        with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
            futs = {pool.submit(probe, k, e, force=force): k for k, e in targets}
            from concurrent.futures import as_completed
            for fut in as_completed(futs):
                try:
                    yield ("result", fut.result())
                except Exception as e:  # noqa: BLE001
                    k = futs[fut]
                    yield ("result", {"kind": k.split(":")[0], "name": k.split(":", 1)[1],
                                      "status": "invalid", "detail": str(e)[:200]})
    finally:
        _sweep_lock.release()


def validate_one_route(req) -> dict:
    """POST {kind, name} -> fresh probe for a single capability (bypasses cache)."""
    kind = (req.body.get("kind") or "").strip()
    name = (req.body.get("name") or "").strip()
    key = f"{kind}:{name}"
    idx = _index()
    entry = idx.get(key)
    if entry is None:
        return (404, {"error": "unknown capability", "key": key})
    return probe(key, entry, force=True)
