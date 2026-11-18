"""The documentation contract for every action that changes a LIVE process outside process-edit.

process-create / process-edit keep a process documented through its config (selfdoc.py). The
surgical writers (node-insert, node-delete, node-set-param, node-set-query, node-replace-text,
node-add-binding, node-bind-var, node-set-error-port, sql-convert, variable-*) change one thing
in place, and used to leave the documentation behind: an inserted action had no purpose and no
area, a changed one kept a description of what it used to do, a deleted one stayed named in its
area's text. Each of them now declares what it changed, and this module asks for exactly the
documentation that change can make untrue, through one argument:

    --doc '{"action": "<purpose>" | true,
            "area":   {"title": "<area>", "text": "<one sentence>"} | true,
            "process": "<purpose>" | true}'

A string (or an area object) states the new text; `true` confirms that the current one is still
right after this change. What each change requires:

    behaviour  (the action now does something else: set-param, set-query, replace-text,
                add-binding, bind-var, sql-convert)
               action, its area (when it is in one), process
    insert     action (a string: a new action has no purpose yet), area (an existing area's
               title to join, or a new title + text; only when the process has areas or will
               have more than 3 actions besides Start/Stop), process
    delete     the area it leaves (when other actions stay in it; an area left empty is removed),
               process
    process    process only (node-set-error-port: the action is the same, the run is not)
    contract   process, when the variable is an input or an output (variable-*)

Missing documentation stops the save with `documentation_missing` and lists what to pass;
`--allow-undocumented` saves anyway. A dry run reports instead of stopping. The area shapes are
re-fitted after every such change (rebuild), so an inserted action sits inside its area and a
deleted one leaves it.
"""
from __future__ import annotations

import argparse
import json
import uuid

from tools.procesio.dto.process.selfdoc import THRESHOLD, is_generic
from tools.procesio.errors import DocumentationMissing, UsageError
from tools.procesio.layout import areas

_g = areas._g
KINDS = ("behaviour", "insert", "delete", "process", "contract")
_STRUCTURAL = {"start", "stop"}


def add_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--doc", help=(
        "documentation this change needs, as JSON: {\"action\": \"<purpose>\"|true, "
        "\"area\": {\"title\": \"...\", \"text\": \"...\"}|true, \"process\": \"<purpose>\"|true}; "
        "a text replaces, true confirms the current one is still right. The error lists "
        "what this change requires"))
    p.add_argument("--doc-file", dest="doc_file", help="path to a UTF-8 JSON file for --doc")
    p.add_argument("--allow-undocumented", dest="allow_undocumented", action="store_true",
                   help="save even when the documentation this change needs is missing; the gaps "
                        "come back under `documentation`")


def parse(args) -> dict:
    raw = None
    if getattr(args, "doc_file", None):
        with open(args.doc_file, encoding="utf-8") as f:
            raw = f.read()
    elif getattr(args, "doc", None):
        raw = args.doc
    if raw is None:
        return {}
    try:
        doc = json.loads(raw)
    except ValueError as e:
        raise UsageError(f"--doc must be valid JSON: {e}") from e
    if not isinstance(doc, dict):
        raise UsageError("--doc must be a JSON object with any of: action, area, process")
    unknown = set(doc) - {"action", "area", "process"}
    if unknown:
        raise UsageError(f"--doc has unknown keys {sorted(unknown)}; use action, area, process")
    return doc


def _acts(flow: dict) -> list:
    return [a for a in (_g(flow, "actions", default=[]) or []) if isinstance(a, dict)]


def _by_id(flow: dict, aid) -> dict | None:
    return next((a for a in _acts(flow) if _g(a, "id") == aid), None)


def _shapes(flow: dict) -> list:
    cv = _g(flow, "canvasData")
    return (cv.get("shapes") if isinstance(cv, dict) else None) or []


def _nonstructural(flow: dict) -> int:
    return sum(1 for a in _acts(flow)
               if str(_g(a, "actionTemplateName") or "").strip().lower() not in _STRUCTURAL)


def _cd(action: dict) -> dict:
    key = next((k for k in action if k.lower() == "customdata"), "customData")
    action.setdefault(key, {})
    return action[key]


def _need(code: str, key: str, detail: str) -> dict:
    return {"code": code, "severity": "error", "doc_key": key, "detail": detail}


def apply(before: dict, after: dict, change: dict, doc: dict, *, allow: bool = False,
          enforce: bool = True) -> dict:
    """Check `doc` against what `change` ({kind, node, variable?}) needs, write the texts onto
    `after` (action description, process description, area texts) and re-fit its area shapes.
    Raises DocumentationMissing when something required is missing, unless `allow` or not
    `enforce` (a dry run); returns the report for the result either way."""
    kind = change.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unknown documentation change kind {kind!r}")
    doc = doc or {}
    findings: list = []
    node_id = change.get("node")
    shapes = _shapes(before)
    before_acts, after_acts = _acts(before), _acts(after)
    old_area = areas.area_of(before_acts, shapes, node_id) if node_id else None
    titles = {g["title"]: g for g in areas.groups_from_shapes(before_acts, shapes)} if shapes else {}
    add, remove, texts, new_areas = {}, set(), {}, {}
    report: dict = {"change": kind, "required": []}

    # -- the action ---------------------------------------------------------------------------
    if kind in ("behaviour", "insert"):
        report["required"].append("action")
        node = _by_id(after, node_id) or {}
        tpl = str(_g(node, "actionTemplateName") or "")
        name = str(_g(node, "actionName") or tpl)
        current = str(_cd(node).get("description") or "").strip() if node else ""
        val = doc.get("action")
        if isinstance(val, str) and val.strip():
            if is_generic(val, tpl, name):
                findings.append(_need("ACTION_DESCRIPTION_GENERIC", "action",
                                      f"{name}: the text is the template's stock caption or its name; "
                                      f"say what this action does in this process"))
            elif node:
                _cd(node)["description"] = val.strip()
        elif val is True and kind == "behaviour" and current and not is_generic(current, tpl, name):
            pass                                      # confirmed as still right
        else:
            findings.append(_need(
                "ACTION_DESCRIPTION_REQUIRED", "action",
                f"{name}: " + ("a new action needs its purpose in this process"
                               if kind == "insert" else
                               f"this change alters what the action does; restate its purpose, or pass "
                               f"true if {current!r} is still right" if current else
                               "it has no purpose of its own; give it one")))

    # -- its area -----------------------------------------------------------------------------
    if kind == "behaviour" and old_area:
        report["required"].append("area")
        val = doc.get("area")
        if val is True:
            pass
        elif isinstance(val, dict) and str(val.get("text") or "").strip():
            if val.get("title") and val["title"] != old_area:
                findings.append(_need("AREA_MISMATCH", "area",
                                      f"the action sits in {old_area!r}, not {val['title']!r}; "
                                      f"move it with process-edit groups"))
            else:
                texts[old_area] = val["text"]
        else:
            findings.append(_need("AREA_REVIEW_REQUIRED", "area",
                                  f"the action is in area {old_area!r} "
                                  f"({titles[old_area]['text']!r}); restate its text "
                                  f"({{\"text\": ...}}) or pass true if it still holds"))
    if kind == "insert":
        will_have = _nonstructural(after)
        if titles or will_have > THRESHOLD:
            report["required"].append("area")
            val = doc.get("area")
            title = str(val.get("title") or "").strip() if isinstance(val, dict) else ""
            if not title:
                findings.append(_need(
                    "AREA_REQUIRED", "area",
                    "the new action needs an area: {\"title\": \"<existing area>\"} to join one "
                    f"({', '.join(map(repr, titles)) or 'none yet'}), or a new title with a \"text\""))
            else:
                add[node_id] = title
                text = str(val.get("text") or "").strip()
                if title in titles:
                    if text:
                        texts[title] = text
                elif text:
                    new_areas[title] = text
                else:
                    findings.append(_need("AREA_TEXT_REQUIRED", "area",
                                          f"{title!r} is a new area; give it a \"text\""))
    if kind == "delete" and old_area:
        remove.add(node_id)
        left = [m for m in titles[old_area]["members"] if m != node_id]
        if left:
            report["required"].append("area")
            val = doc.get("area")
            if val is True:
                pass
            elif isinstance(val, dict) and str(val.get("text") or "").strip():
                texts[old_area] = val["text"]
            else:
                findings.append(_need("AREA_REVIEW_REQUIRED", "area",
                                      f"the action leaves area {old_area!r} "
                                      f"({titles[old_area]['text']!r}), whose text may still describe "
                                      f"it; restate the text or pass true"))
        else:
            report["area_removed"] = old_area

    # -- the process --------------------------------------------------------------------------
    var = change.get("variable") or {}
    needs_process = kind in ("behaviour", "insert", "delete", "process") or (
        kind == "contract" and int(_g(var, "type", default=0) or 0) in (10, 30))
    if needs_process:
        report["required"].append("process")
        current = str(_g(after, "description") or "").strip()
        val = doc.get("process")
        if isinstance(val, str) and val.strip():
            key = next((k for k in after if k.lower() == "description"), "description")
            after[key] = val.strip()
        elif val is True and current:
            pass
        else:
            findings.append(_need(
                "PROCESS_REVIEW_REQUIRED", "process",
                "this change alters what the process does; restate its purpose, or pass true if "
                f"{current!r} is still right" if current else
                "the process has no purpose yet; give it one"))

    # -- the area shapes follow the change ----------------------------------------------------
    if titles or add:
        cv_key = next((k for k in after if k.lower() == "canvasdata"), "canvasData")
        canvas = after.get(cv_key) if isinstance(after.get(cv_key), dict) else {"x": 0, "y": 0, "zoom": 1}
        canvas = dict(canvas)
        canvas["shapes"] = areas.rebuild(before_acts, after_acts, shapes, lambda: str(uuid.uuid4()),
                                         add=add, remove=remove, texts=texts, new_areas=new_areas)
        after[cv_key] = canvas
        report["areas"] = [g["title"] for g in areas.groups_from_shapes(after_acts, canvas["shapes"])]

    report["findings"] = findings
    report["documented"] = not findings
    if findings and enforce and not allow:
        keys = sorted({f["doc_key"] for f in findings})
        raise DocumentationMissing(
            "refusing to save: this change needs documentation that was not given ("
            + ", ".join(f["code"] for f in findings) + "). Pass --doc with "
            + ", ".join(keys) + " - a text replaces, true confirms the current one - or "
            "--allow-undocumented to save anyway.", report)
    return report
