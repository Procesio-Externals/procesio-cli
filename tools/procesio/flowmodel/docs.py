"""Read a process's DOCUMENTED INTENT, and say where it is missing.

A self-documenting process carries three things (see dto/process/selfdoc.py for how create and
edit write them):

- the process purpose: the flow's `description`;
- each action's purpose in this process: `customData.description`. The designer pre-fills it
  with the template's stock caption, which describes the action TYPE, not this use of it, so a
  stock caption counts as missing;
- on a process with more than 3 actions besides Start and Stop, AREAS: canvas rectangles
  (`canvasData.shapes`) with a title and a text, grouping the actions by what they do together.
  Membership is geometric (layout/areas.py).

`read(flow)` returns that intent as data - the first thing to read when analysing a process or a
workspace you do not know, before reading parameters. `findings(flow)` lists the gaps. Pure;
works on the live camelCase flow and the PascalCase DTO / export alike.
"""
from __future__ import annotations

from tools.procesio.dto.process.selfdoc import THRESHOLD, is_generic
from tools.procesio.layout import areas

_g = areas._g
STRUCTURAL = {"start", "stop"}


def _template(a: dict) -> str:
    return str(_g(a, "actionTemplateName") or _g(a, "actionName") or "")


def _name(a: dict) -> str:
    return str(_g(a, "actionName") or _template(a) or _g(a, "id") or "?")


def _flow(obj: dict) -> dict:
    if isinstance(obj, dict) and isinstance(obj.get("flow"), dict):
        return obj["flow"]
    if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
        return _flow(obj["result"])
    return obj


def read(flow: dict, captions: dict | None = None) -> dict:
    """{title, id, purpose, actions: [{id, name, template, purpose, documented, area}],
    areas: [{title, text, actions: [names]}], notes: [free canvas notes], coverage, findings,
    documented}. `captions` ({template lower: caption}) adds live stock captions to the bundled
    ones (custom / connector actions)."""
    flow = _flow(flow)
    acts = [a for a in (_g(flow, "actions", default=[]) or []) if isinstance(a, dict)]
    canvas = _g(flow, "canvasData") or {}
    shapes = (canvas.get("shapes") if isinstance(canvas, dict) else None) or []
    groups = areas.groups_from_shapes(acts, shapes)
    top = areas.top_level_of(acts)
    by_id = {_g(a, "id"): a for a in acts}
    area_of = {}
    for g in groups:
        for m in g["members"]:
            area_of[m] = g["title"]

    rows, findings = [], []
    for a in acts:
        tpl = _template(a)
        if tpl.strip().lower() in STRUCTURAL:
            continue
        aid = _g(a, "id")
        desc = str((_g(a, "customData", default={}) or {}).get("description") or "").strip()
        generic = is_generic(desc, tpl, _name(a), captions)
        area = area_of.get(top.get(aid, aid))
        rows.append({"id": aid, "name": _name(a), "template": tpl,
                     "purpose": desc, "documented": not generic, "area": area,
                     "inside": _name(by_id[top[aid]]) if top.get(aid) not in (aid, None) else None})
        if not desc:
            findings.append({"code": "ACTION_DESCRIPTION_MISSING", "severity": "error",
                             "action": _name(a),
                             "detail": "no description: say what this action does in this process"})
        elif generic:
            findings.append({"code": "ACTION_DESCRIPTION_GENERIC", "severity": "error",
                             "action": _name(a),
                             "detail": f"the description is the template's stock caption or its name "
                                       f"({desc!r}); say what it does in THIS process"})

    purpose = str(_g(flow, "description") or "").strip()
    if not purpose:
        findings.insert(0, {"code": "PROCESS_DESCRIPTION_MISSING", "severity": "error",
                            "detail": "the process has no description: what it is for, what starts "
                                      "it and what it produces"})
    if len(rows) > THRESHOLD:
        if not groups:
            findings.append({"code": "AREAS_MISSING", "severity": "error",
                             "detail": f"{len(rows)} actions besides Start/Stop and no areas on the "
                                       f"canvas: group them into titled areas with a short text"})
        else:
            for r in rows:
                if r["inside"] is None and not r["area"]:
                    findings.append({"code": "ACTION_UNGROUPED", "severity": "error",
                                     "action": r["name"], "detail": "sits in no area on the canvas"})
    for g in groups:
        if not g["text"]:
            findings.append({"code": "AREA_TEXT_MISSING", "severity": "warn", "area": g["title"],
                             "detail": "the area has a title but no text saying what its actions do"})

    names = {_g(a, "id"): _name(a) for a in acts}
    notes = [{"title": _g(s, "title", default=""), "text": _g(s, "text", default="")}
             for s in areas.free_shapes(acts, shapes)]
    errors = [f for f in findings if f["severity"] == "error"]
    return {
        "id": _g(flow, "id"), "title": _g(flow, "title"), "purpose": purpose,
        "areas": [{"title": g["title"], "text": g["text"],
                   "actions": [names.get(m, m) for m in g["members"]]} for g in groups],
        "actions": rows, "notes": notes,
        "coverage": {"actions": len(rows),
                     "described": sum(1 for r in rows if r["documented"]),
                     "grouped": sum(1 for r in rows if r["area"] or r["inside"]),
                     "areas_required": len(rows) > THRESHOLD},
        "documented": not errors, "findings": findings,
    }


def findings(flow: dict, captions: dict | None = None) -> list[dict]:
    return read(flow, captions)["findings"]


def render_markdown(doc: dict) -> str:
    """The documented intent as a short markdown block (flow-digest prepends it)."""
    lines = []
    if doc.get("purpose"):
        lines.append(f"**Purpose:** {doc['purpose']}")
    else:
        lines.append("**Purpose:** _(undocumented)_")
    if doc.get("areas"):
        lines += ["", "## Areas", ""]
        for a in doc["areas"]:
            lines.append(f"- **{a['title']}** - {a['text'] or '_(no text)_'} "
                         f"({', '.join(a['actions'])})")
    gaps = [f for f in doc.get("findings", []) if f["severity"] == "error"]
    if gaps:
        lines += ["", f"_Documentation gaps: {len(gaps)} "
                      f"({', '.join(sorted({f['code'] for f in gaps}))})_"]
    return "\n".join(lines)
