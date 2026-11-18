"""What each action did when the tool last documented it - so a later change made by hand in the
designer, which leaves the description behind, can be seen.

The designer rebuilds customData and canvasData from fixed keys on every save, so nothing can be
remembered inside the process itself. Instead every save the tool makes records, per action id,
the GUID-free fingerprint of what the action does (selfdoc.fingerprint) and its description at
that moment, in this installation's user data (never in the framework, never in the process):

    <user data>/state/procesio/doc-baselines/<process id>.json

`findings(flow)` then reports ACTION_CHANGED_SINCE_DOCUMENTED for an action whose behaviour
differs from the record while its description is still the recorded one: someone changed what
it does and not what it says. It sees only changes made after a save by the tool on this machine;
without a record it reports nothing (it never guesses). Best effort: a failure to read or write
the record never fails the save it follows.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.procesio.dto.process.selfdoc import fingerprint
from tools.procesio.layout import areas

_g = areas._g
_STRUCTURAL = {"start", "stop"}


def _dir() -> Path:
    from tools._lib import userdata
    return Path(userdata.state_dir("procesio")) / "doc-baselines"


def _flow(obj):
    if isinstance(obj, dict) and isinstance(obj.get("flow"), dict):
        return obj["flow"]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        return _flow(obj["result"])
    return obj


def _var_names(flow: dict) -> dict:
    return {str(_g(v, "id") or "").lower(): str(_g(v, "name") or "")
            for v in (_g(flow, "variables", default=[]) or []) if _g(v, "id")}


def snapshot(flow: dict) -> dict:
    flow = _flow(flow)
    names = _var_names(flow)
    acts = {}
    for a in _g(flow, "actions", default=[]) or []:
        if str(_g(a, "actionTemplateName") or "").strip().lower() in _STRUCTURAL:
            continue
        cd = _g(a, "customData", default={}) or {}
        acts[str(_g(a, "id"))] = {"name": _g(a, "actionName"), "fingerprint": fingerprint(a, names),
                                  "description": str(cd.get("description") or "").strip()}
    return {"process_id": _g(flow, "id"), "description": str(_g(flow, "description") or "").strip(),
            "recorded_on": datetime.now(timezone.utc).isoformat(timespec="seconds"), "actions": acts}


def record(flow: dict) -> None:
    """Remember the flow as the tool just saved it. Never raises."""
    try:
        snap = snapshot(flow)
        if not snap["process_id"]:
            return
        d = _dir()
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{snap['process_id']}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                                                      encoding="utf-8", newline="\n")
    except Exception:  # noqa: BLE001 - the save already happened; the record is best effort
        pass


def load(process_id) -> dict | None:
    try:
        p = _dir() / f"{process_id}.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def findings(flow: dict, base: dict | None = None) -> list[dict]:
    """ACTION_CHANGED_SINCE_DOCUMENTED for every action that does something else than when the
    tool last documented it, while its description did not move."""
    flow = _flow(flow)
    base = base if base is not None else load(_g(flow, "id"))
    if not base:
        return []
    names = _var_names(flow)
    out = []
    for a in _g(flow, "actions", default=[]) or []:
        rec = (base.get("actions") or {}).get(str(_g(a, "id")))
        if not rec:
            continue
        cd = _g(a, "customData", default={}) or {}
        desc = str(cd.get("description") or "").strip()
        if fingerprint(a, names) != rec["fingerprint"] and desc == rec["description"]:
            out.append({"code": "ACTION_CHANGED_SINCE_DOCUMENTED", "severity": "error",
                        "action": _g(a, "actionName"),
                        "detail": f"what this action does changed after it was last documented "
                                  f"({base.get('recorded_on')}), and its description did not: "
                                  f"restate it (process-edit, or node-* --doc)"})
    return out
