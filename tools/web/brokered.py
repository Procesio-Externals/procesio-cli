"""Routing of the web tool's generic browser actions (run / get-text /
screenshot) through the serializing broker that OWNS the target session.

Why: brokers exist so exactly one process drives a tool's web session at a
time (tools/_lib/webserialize). But `web run --session whatsapp ...` used to
open the profile DIRECTLY — an ad-hoc debugging command could race the
whatsapp broker's warm browser and invalidate the session. So when the target
session is broker-owned (registry: whatsapp/ryver/fgo/mirro), the web CLI
translates the action into a step list and submits it to that broker's
``web-steps`` op instead; the broker executes it serialized, on its warm
browser. Unowned sessions (e.g. 'google') keep the direct behavior.

Escape hatches: ``--direct``, the owning tool's ``<PREFIX>_DIRECT`` env, or
``--channel`` (not carried by the op — a channel run stays in-process).
Inside a broker's own worker the owning tool's ``<PREFIX>_SERVICE_WORKER``
env disables routing automatically, so a worker executing web steps can never
recurse into itself.
"""
from __future__ import annotations

from tools._lib.webserialize import client as ws_client
from tools._lib.webserialize import registry as ws_registry
from tools._lib.webserialize.config import BrokerConfig

_TAG_KEYS = ("via", "service_queue_wait_ms", "service_fallback")


def eligible(parsed, *, driver_factory, allow_service: bool) -> BrokerConfig | None:
    """The owning broker config when this invocation should route, else None."""
    if not allow_service or driver_factory is not None:
        return None
    if getattr(parsed, "direct", False):
        return None
    if getattr(parsed, "channel", None):
        return None
    session = getattr(parsed, "session", None)
    if not session:
        return None
    cfg = ws_registry.owner_of_session(session)
    if cfg is None or not ws_client.enabled(cfg):
        return None
    return cfg


def route(cfg: BrokerConfig, action: str, parsed, *, dispatch_direct) -> dict:
    steps, url, reshape = _translate(action, parsed)
    result = ws_client.web_steps(
        cfg, parsed.session, steps, url=url,
        headless=not getattr(parsed, "headed", False),
        dispatch_direct=dispatch_direct,
    )
    if not isinstance(result, dict) or result.get("via") == "direct-fallback":
        return result  # fallback already ran the real handler; final shape
    return reshape(result)


def _tags(src: dict, dst: dict) -> dict:
    for k in _TAG_KEYS:
        if k in src:
            dst.setdefault(k, src[k])
    return dst


def _translate(action: str, parsed):
    """(steps, url, reshape) for one of the three generic browser actions."""
    if action == "run":
        from tools.web.handlers.browse import _load_steps
        return _load_steps(parsed), parsed.url, lambda r: r

    if action == "get-text":
        steps: list[dict] = []
        if parsed.wait:
            steps.append({"do": "wait_for", "selector": parsed.wait})
        step: dict = {"do": "extract_text", "name": "text"}
        if parsed.selector:
            step["selector"] = parsed.selector
        steps.append(step)

        def reshape(r: dict) -> dict:
            return _tags(r, {
                "session": parsed.session, "url": parsed.url,
                "selector": parsed.selector,
                "text": (r.get("results") or {}).get("text", ""),
                "final_url": r.get("final_url"),
                "diagnostics": r.get("diagnostics", {}),
            })

        return steps, parsed.url, reshape

    if action == "screenshot":
        steps = []
        if parsed.wait:
            steps.append({"do": "wait_for", "selector": parsed.wait})
        steps.append({"do": "screenshot", "path": parsed.out,
                      "full_page": not parsed.viewport_only})

        def reshape(r: dict) -> dict:
            return _tags(r, {
                "session": parsed.session, "url": parsed.url,
                "path": parsed.out,
                "final_url": r.get("final_url"),
                "diagnostics": r.get("diagnostics", {}),
            })

        return steps, parsed.url, reshape

    raise ValueError(f"no broker translation for web action {action!r}")
