"""Self-documenting processes: every saved process says what it is for.

Three things are written with every create and every edit, and kept true across edits:

1. the PROCESS purpose - the flow's `description`;
2. each ACTION's purpose in this process - `customData.description` (the designer's Properties
   panel "Description" field, shown as the node's hover tooltip). The designer pre-fills it
   with the template's stock caption ("Generates a GUID value."), which says what the action
   type does in general and nothing about this process, so the stock caption counts as missing;
3. on a process with more than 3 actions besides Start and Stop, AREAS - canvas rectangles
   with a title and a one-sentence text that group the actions by what they do together
   (`canvasData.shapes`, see layout/areas.py).

Config: `description` (process), `actions[].description`, and
`groups: [{title, text, actions: [action ids]}]`.

Edit rules (desired state, so whatever the config omits is resolved against the LIVE flow):
- process description: the config wins; omitted keeps the live one.
- action description: the config wins; omitted keeps the live one ONLY while the action still
  does the same thing (same template, same parameters - compared GUID-free, because an edit
  re-mints node ids). An action that changed with no restated description is STALE.
- areas: `groups` rebuilds them; omitted reads membership off the live shapes (geometric) and
  re-fits them to the new layout. A new action in no area, or an area that lost an action
  (its text may name it), must be restated.

The builder stays permissive (`build` never raises for documentation); it records a report in
`ctx["_doc"]`, and the create/edit layer enforces it with `gate()` unless --allow-undocumented.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from tools.procesio.errors import DocumentationMissing, UsageError
from tools.procesio.layout import areas

_CAPTIONS = Path(__file__).resolve().parent.parent / "data" / "action_captions.json"
STRUCTURAL = {"start", "stop"}
THRESHOLD = 3                    # more than this many actions besides Start/Stop -> areas required
_GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_WS = re.compile(r"\s+")
# the platform stores a timestamp in its own format ("...00Z" comes back "...00.0000000Z")
_ISO = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})?")


@lru_cache(maxsize=1)
def stock_captions() -> dict:
    """{template name (lower): stock caption} for the built-in actions."""
    try:
        caps = json.loads(_CAPTIONS.read_text(encoding="utf-8")).get("captions", {})
    except (OSError, ValueError):
        caps = {}
    return {k.strip().lower(): v for k, v in caps.items()}


def _norm_text(s) -> str:
    return _WS.sub(" ", str(s or "")).strip().lower().rstrip(".")


def is_generic(description, template_name: str, action_name: str = "",
               extra_captions: dict | None = None) -> bool:
    """True when `description` says nothing about THIS process: empty, the template's stock
    caption, or just the action's / template's name."""
    d = _norm_text(description)
    if not d:
        return True
    t = (template_name or "").strip().lower()
    caps = [stock_captions().get(t), (extra_captions or {}).get(t)]
    return d in {_norm_text(c) for c in caps if c} | {_norm_text(template_name), _norm_text(action_name)}


def _g(d, *names, default=None):
    return areas._g(d, *names, default=default)


def fingerprint(action: dict, var_names: dict) -> str:
    """What an action DOES, comparable across an edit: template + parameters, with variable ids
    replaced by variable names and every other GUID blanked (node ids, case ids and port ids
    are re-minted on every edit)."""
    def norm(o):
        if isinstance(o, dict):
            return {str(k).lower(): norm(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0]).lower())
                    if str(k).lower() not in ("id",)}
        if isinstance(o, list):
            return [norm(x) for x in o]
        if isinstance(o, str):
            o = _ISO.sub(lambda m: m.group(1), o)
            return _GUID.sub(lambda m: "var:" + var_names[m.group(0).lower()]
                             if m.group(0).lower() in var_names else "#", o)
        if isinstance(o, bool) or o is None:
            return o
        if isinstance(o, (int, float)):
            return str(o)                 # 120 and "120" are the same setting
        return o

    rows = []
    for p in _g(action, "parameters", default=[]) or []:
        val = _g(p, "value")
        if val in (None, "", [], {}):
            continue
        rows.append([str(_g(p, "tabPropertyId") or "").lower(), norm(val),
                     sorted(json.dumps(norm(v), sort_keys=True)
                            for v in (_g(p, "variable", default=[]) or []))])
    rows.sort(key=lambda r: json.dumps(r, sort_keys=True))
    return json.dumps([str(_g(action, "templateId") or "").lower(), rows], sort_keys=True)


def _var_names(variables) -> dict:
    return {str(_g(v, "id") or "").lower(): str(_g(v, "name") or "") for v in variables or []
            if _g(v, "id")}


def _finding(code: str, detail: str, action: str | None = None, severity: str = "error") -> dict:
    f = {"code": code, "severity": severity, "detail": detail}
    if action is not None:
        f["action"] = action
    return f


def apply(config: dict, ctx: dict, nodes: dict, seq: list, dto_vars: list) -> dict:
    """Write the action descriptions onto the built nodes (`nodes` = {cid: action dto}) and
    return the documentation state used later by `canvas()` and `gate()`. Called by build()
    BEFORE layout (descriptions do not depend on positions)."""
    live = ctx.get("_live_flow") or None
    live_match: dict = ctx.get("existing_actions") or {}         # cid -> live action
    live_vars = _var_names((live or {}).get("variables") or (live or {}).get("Variables"))
    new_vars = _var_names(dto_vars)
    findings: list = []
    actions_report: list = []
    by_cfg = {(a.get("id") or f"a{i}"): a for i, a in enumerate(config.get("actions", []))}

    for cid in seq:
        node = nodes[cid]
        tpl = node.get("ActionTemplateName") or ""
        if tpl.strip().lower() in STRUCTURAL:
            continue
        name = node.get("ActionName") or tpl
        cfg = by_cfg.get(cid, {})
        explicit = str(cfg.get("description") or "").strip()
        la = live_match.get(cid)
        status, desc = "missing", ""
        if explicit:
            desc, status = explicit, "set"
        elif la is not None:
            prev = str((_g(la, "customData", default={}) or {}).get("description") or "").strip()
            same = fingerprint(la, live_vars) == fingerprint(node, new_vars)
            if prev and is_generic(prev, tpl, name, ctx.get("_captions")):
                desc = prev                   # kept as it was, reported as generic below
            elif prev:
                if same:
                    desc, status = prev, "kept"
                else:
                    desc, status = prev, "stale"
        if desc:
            node["CustomData"]["description"] = desc
        if status == "missing" or (desc and is_generic(desc, tpl, name, ctx.get("_captions"))):
            status = "missing" if not desc else "generic"
            findings.append(_finding(
                "ACTION_DESCRIPTION_MISSING" if status == "missing" else "ACTION_DESCRIPTION_GENERIC",
                f"action {cid!r} ({name}) has no purpose of its own: give it a `description` that says "
                f"what it does in THIS process" + ("" if status == "missing" else
                                                    " (the text is the template's stock caption or its name)"),
                cid))
        elif status == "stale":
            findings.append(_finding(
                "ACTION_DESCRIPTION_STALE",
                f"action {cid!r} ({name}) changed what it does (template or parameters) and its "
                f"description was not restated; the live one reads {desc!r}. Restate it - repeat it "
                f"word for word if the purpose is unchanged", cid))
        actions_report.append({"id": cid, "name": name, "template": tpl, "status": status,
                               "description": desc})

    # process purpose
    pdesc = str(config.get("description") or "").strip()
    pstatus = "set" if pdesc else "missing"
    if not pdesc and live:
        pdesc = str(_g(live, "description") or "").strip()
        pstatus = "kept" if pdesc else "missing"
    if not pdesc:
        findings.append(_finding("PROCESS_DESCRIPTION_MISSING",
                                 "the process has no purpose: set `description` to what it is for, "
                                 "who or what starts it, and what it produces"))
    count = len(actions_report)
    return {"process": {"status": pstatus, "description": pdesc}, "actions": actions_report,
            "action_count": count, "areas_required": count > THRESHOLD, "findings": findings}


def _config_groups(config: dict, nodes: dict, parent_cid: dict) -> list:
    out = []
    seen: dict = {}
    for gi, g in enumerate(config.get("groups") or []):
        title = str(g.get("title") or "").strip()
        if not title:
            raise UsageError(f"groups[{gi}] needs a `title` (the area's name on the canvas)")
        members = []
        for cid in g.get("actions") or []:
            if cid in ("start", "stop") or cid not in nodes:
                raise UsageError(f"groups[{gi}] ({title}) lists {cid!r}, which is not an action id "
                                 f"of this config (Start/Stop never belong to an area)")
            if parent_cid.get(cid):
                raise UsageError(f"groups[{gi}] ({title}) lists {cid!r}, which sits inside the For Each "
                                 f"{parent_cid[cid]!r}; list the container instead - its children go with it")
            if cid in seen:
                raise UsageError(f"action {cid!r} is in two areas ({seen[cid]!r} and {title!r}); an action "
                                 f"belongs to one area")
            seen[cid] = title
            members.append(cid)
        out.append({"title": title, "text": str(g.get("text") or "").strip(), "members": members,
                    "source": "config"})
    return out


def _live_groups(ctx: dict, live_to_cid: dict) -> tuple[list, list]:
    """Areas read off the live shapes, members mapped onto this config's ids. Returns
    (groups, lost) where lost = [(title, live action name)] for members no longer present."""
    live = ctx.get("_live_flow") or {}
    canvas = _g(live, "canvasData") or {}
    shapes = (canvas.get("shapes") if isinstance(canvas, dict) else None) or []
    acts = _g(live, "actions", default=[]) or []
    names = {_g(a, "id"): (_g(a, "actionName") or _g(a, "actionTemplateName") or "") for a in acts}
    out, lost = [], []
    for g in areas.groups_from_shapes(acts, shapes):
        members = []
        for lid in g["members"]:
            cid = live_to_cid.get(lid)
            if cid is None:
                lost.append((g["title"], names.get(lid, lid)))
            else:
                members.append(cid)
        out.append({"title": g["title"], "text": g["text"], "members": members, "source": "live",
                    "id": g["shape_ids"][0]})
    return out, lost


def canvas(config: dict, ctx: dict, state: dict, actions: list, id_of: dict, new_id) -> dict | None:
    """The flow's CanvasData after layout: area shapes fitted around their members' FINAL
    positions, a person's free notes (shapes holding no action) kept, viewport kept on edit.
    Adds the area findings to `state`. Returns None when there is nothing to store."""
    by_id = {a["Id"]: a for a in actions}
    cid_of_id = {v: k for k, v in id_of.items()}
    parent_cid = {cid: cid_of_id.get(by_id[id_of[cid]].get("ParentId"))
                  for cid in id_of if by_id.get(id_of[cid]) and by_id[id_of[cid]].get("ParentId")}
    nodes = {cid: by_id[iid] for cid, iid in id_of.items() if iid in by_id}
    # non-structural top-level cids, in flow order (findings read in the order of the canvas)
    top_level = [r["id"] for r in state["actions"] if not parent_cid.get(r["id"])]
    findings = state["findings"]

    live = ctx.get("_live_flow") or None
    live_canvas = _g(live, "canvasData") if live else None
    live_shapes = (live_canvas.get("shapes") if isinstance(live_canvas, dict) else None) or []
    live_acts = (_g(live, "actions", default=[]) or []) if live else []
    keep_notes = areas.free_shapes(live_acts, live_shapes) if live_shapes else []

    if config.get("groups") is not None:
        groups = _config_groups(config, nodes, parent_cid)
    elif live:
        live_to_cid = {_g(la, "id"): cid for cid, la in (ctx.get("existing_actions") or {}).items()}
        groups, lost = _live_groups(ctx, live_to_cid)
        for title, nm in lost:
            findings.append(_finding(
                "AREA_MEMBERS_CHANGED",
                f"area {title!r} lost the action {nm!r}; its text may still describe it. Restate "
                f"`groups` (repeat the text if it is still true)"))
        groups = [g for g in groups if g["members"]]
    else:
        groups = []

    grouped = {m for g in groups for m in g["members"]}
    if state["areas_required"]:
        if not groups:
            findings.append(_finding(
                "AREAS_MISSING",
                f"the process has {state['action_count']} actions besides Start and Stop (more than "
                f"{THRESHOLD}): add `groups` - areas on the canvas, each a title and one sentence on what "
                f"its actions do together"))
        else:
            for cid in top_level:
                if cid not in grouped:
                    findings.append(_finding(
                        "ACTION_UNGROUPED",
                        f"action {cid!r} ({nodes[cid].get('ActionName')}) sits in no area; add it to the "
                        f"`groups` entry it belongs to", cid))
    for g in groups:
        if not g["text"]:
            findings.append(_finding("AREA_TEXT_MISSING",
                                     f"area {g['title']!r} has no text: one sentence on what its actions "
                                     f"do together"))

    spec, keyed = [], []
    for gi, g in enumerate(groups):
        spec.append({"key": gi, "title": g["title"], "text": g["text"], "id": g.get("id")})
        keyed.append((gi, [id_of[c] for c in g["members"] if c in id_of]))
    boxes = areas.node_boxes(actions)
    rects = areas.fit(boxes, keyed, {s["key"]: (s["title"], s["text"]) for s in spec})
    for s in spec:
        r = (rects.get(s["key"]) or [None])[0]
        if r and areas.text_lines(s["text"], r[2] - r[0]) > areas.MAX_TEXT_LINES:
            findings.append(_finding("AREA_TEXT_LONG",
                                     f"area {s['title']!r}: its text wraps past {areas.MAX_TEXT_LINES} lines "
                                     f"at this width and spills over the actions; shorten it to one sentence",
                                     severity="warn"))
    shapes = keep_notes + areas.to_shapes(spec, rects, new_id)
    state["areas"] = [{"title": g["title"], "text": g["text"], "actions": g["members"],
                       "source": g["source"], "rectangles": len(rects.get(i) or [])}
                      for i, g in enumerate(groups)]
    if isinstance(live_canvas, dict):
        out = dict(live_canvas)
        out["shapes"] = shapes
        return out
    if not shapes:
        return None
    return {"x": 0, "y": 0, "zoom": 1, "shapes": shapes}


def summary(state: dict) -> dict:
    """The report returned to the caller (dry-run, create, edit)."""
    errors = [f for f in state.get("findings", []) if f.get("severity") == "error"]
    return {"documented": not errors, "process": state.get("process"),
            "actions": state.get("actions", []), "areas": state.get("areas", []),
            "findings": state.get("findings", [])}


def gate(ctx: dict) -> dict | None:
    """Refuse the save when the process does not document itself (unless --allow-undocumented).
    Returns the summary to attach to the result."""
    state = ctx.get("_doc")
    if not state or "findings" not in state:
        return None
    rep = summary(state)
    if not rep["documented"] and not ctx.get("_allow_undocumented"):
        errs = [f for f in rep["findings"] if f["severity"] == "error"]
        codes = sorted({f["code"] for f in errs})
        raise DocumentationMissing(
            f"refusing to save: the process does not document itself ({len(errs)} gap(s): "
            + ", ".join(codes) + "). Every process carries its purpose (`description`), every action "
            "its purpose in this process (`actions[].description`), and a process with more than "
            f"{THRESHOLD} actions besides Start/Stop carries `groups` (areas on the canvas). Fix the "
            "config, or pass --allow-undocumented to save it anyway.", rep)
    return rep
