"""Deterministic DESIGNER-layer normalizer.

Regenerates an action's `customData.configuration[].settings[].value` (the DESIGNER layer the Process
Designer reads) from that action's RUNTIME `parameters[]` (the source of truth = what executes), for
the ONE class where the two layers are a clean, reversible mirror: a STRING setting value that may hold
a `<%N%>` placeholder. It substitutes each `<%N%>` for its bound variable GUID (with the attribute chain,
`varId.attrId...`), which is exactly what the designer expects and what the runtime placeholder maps to.
This permanently kills the "customData holds `<%N%>` instead of the variable GUID -> designer paints it
red" class of bug: hand-place an action however, then normalize, and a string designer value can no
longer drift from its runtime parameter.

SCOPE - deliberately STRING-ONLY. LIST/dict-shaped settings (process-inputs/outputs, map-parameters,
map-process-data, document-mapper, decisional-case, ai-decisional-case) are LEFT UNTOUCHED, because their
runtime<->designer relationship is NOT a clean mirror: the builder's build-from-spec transforms drop the
attribute chain on subprocess maps and emit the runtime shape for map-parameters, i.e. regenerating them
from live runtime CORRUPTS them (verified live: process-outputs `varId.attrId` -> `varId`). Those settings
also never carry the `<%N%>`-in-a-string bug (they store GUID-form refs), so skipping them loses nothing.
The flowlint CUSTOMDATA_PLACEHOLDER guard remains the backstop for any residual case.

REUSES `builder._config_value_from_param` (never re-implements it). Contract: mutate `flow` IN PLACE
(matches flowpatch's _load->mutate->_save model); return a diff report. Idempotent and a NO-OP on
already-compliant flows (a value with no `<%N%>` passes through byte-identical).
"""
from __future__ import annotations

import copy
import uuid

from tools.procesio.dto.process import builder as _b


def _index_settings(cfg_tree: list) -> dict:
    """{setting.id: setting}, recursing into list-valued settings (side-pannel nesting) - mirrors
    the builder's _apply_values_to_config index()."""
    byid: dict = {}

    def walk(settings):
        for s in settings or []:
            if isinstance(s, dict):
                if s.get("id"):
                    byid[s["id"]] = s
                if isinstance(s.get("value"), list):
                    walk(s["value"])
    for tab in cfg_tree or []:
        walk(tab.get("settings") or [])
    return byid


def rebuild_missing_designer_config(flow: dict, catalog: dict, only: set | None = None) -> dict:
    """Give every action that has NO `customData.configuration` the designer layer the builder
    would have written: the template's configuration tree, with each setting filled from the
    action's runtime parameters through the builder's own `_apply_values_to_config` (bespoke
    shapes - decisional cases, document / data-store mappers, subprocess maps - included).

    An action without a configuration is what a raw PUT leaves behind, and the designer cannot
    open a process that carries one. The runtime never reads this layer, so filling it changes
    nothing that executes. An action whose TEMPLATE has an empty configuration (Join) gets an
    empty list when the key is missing altogether, since the canvas engine maps over it; any
    action that already has one is left alone.

    `catalog` is a `builder.catalog_index()` (actionId -> template). `only` restricts the repair
    to these action ids or names. Mutates `flow` in place; returns
    {changed, repaired: [{id, name, template, settings}], skipped: [{id, name, why}]}."""
    report: dict = {"changed": False, "repaired": [], "skipped": []}
    wanted = {str(x).strip().lower() for x in (only or set())}
    for a in flow.get("actions") or []:
        name = a.get("actionName")
        if wanted and str(a.get("id")).lower() not in wanted and str(name or "").strip().lower() not in wanted:
            continue
        cd = a.get("customData")
        if not isinstance(cd, dict) or cd.get("configuration"):
            continue
        tpl = catalog.get(a.get("templateId"))
        if tpl is None:
            report["skipped"].append({"id": a.get("id"), "name": name, "why": "template_not_in_catalog",
                                      "templateId": a.get("templateId")})
            continue
        tree = copy.deepcopy(tpl.get("configuration") or [])
        if not tree:
            # A Join template has nothing to show, but the KEY must still exist: the canvas
            # engine maps over every node's configuration, and a missing one throws inside a
            # promise that never settles (the designer loads forever, no console error).
            if "configuration" not in cd:
                cd["configuration"] = []
                report["changed"] = True
                report["repaired"].append({"id": a.get("id"), "name": name, "template": tpl.get("name"),
                                           "settings": 0})
            continue
        params = [{"TabPropertyId": p.get("tabPropertyId"), "Value": p.get("value"),
                   "Variable": p.get("variable")} for p in a.get("parameters") or []]
        ctx = {"flow_id": flow.get("id"), "catalog": catalog, "new_id": lambda: str(uuid.uuid4())}
        _b._apply_values_to_config(tree, params, ctx, a.get("id"))
        cd["configuration"] = tree
        filled = len([p for p in params if p["TabPropertyId"] in _index_settings(tree)])
        report["changed"] = True
        report["repaired"].append({"id": a.get("id"), "name": name, "template": tpl.get("name"),
                                   "settings": filled})
    return report


CANVAS_SHAPES = frozenset({"square", "circle", "diamond", "area"})


def designer_render_problems(flow: dict) -> list[dict]:
    """The nodes of a flow the designer cannot draw, before it is saved: no
    `customData.configuration` key, or a `customData.type` outside CANVAS_SHAPES. Either makes the
    canvas engine throw inside a promise that never settles, so the designer and every instance
    view load forever with no error. Reads the live (camelCase) and builder (PascalCase) shapes."""
    if not isinstance(flow, dict):
        return []
    flow = flow.get("flow") if isinstance(flow.get("flow"), dict) else flow
    out = []
    for a in flow.get("actions") or flow.get("Actions") or []:
        if not isinstance(a, dict):
            continue
        cd = a.get("customData", a.get("CustomData"))
        name = a.get("actionName") or a.get("ActionName")
        aid = a.get("id") or a.get("Id")
        if not isinstance(cd, dict):
            out.append({"id": aid, "name": name, "why": "no customData"})
            continue
        if "configuration" not in cd:
            out.append({"id": aid, "name": name, "why": "no configuration key"})
        if cd.get("type") not in CANVAS_SHAPES:
            out.append({"id": aid, "name": name, "why": f"unknown shape {cd.get('type')!r}"})
    return out


_SHAPE_KEYS = (("type", "shape"), ("inputPorts", "inputPorts"), ("outputPorts", "outputPorts"))


def align_node_shapes(flow: dict, catalog: dict) -> dict:
    """Set each node's canvas shape and port counts (`customData.type`, `inputPorts`,
    `outputPorts`) to its template's, where they differ.

    The canvas engine draws four shapes (square, circle, diamond, area). A node stored with any
    other type (a hand-built Decisional saved as "rhombus") makes the engine's addNode fail inside
    a promise that never settles: the designer and every instance view of the process load
    forever, with no error in the console. Wrong port counts do the same quieter damage (a Join
    with one input cannot take its second line). A designer-built node always matches its
    template on all three, so the template is the reference. Mutates `flow` in place; returns
    {changed, aligned: [{id, name, fields: {key: [old, new]}}]}."""
    report: dict = {"changed": False, "aligned": []}
    for a in flow.get("actions") or []:
        cd = a.get("customData")
        tpl = catalog.get(a.get("templateId"))
        if not isinstance(cd, dict) or tpl is None:
            continue
        fields = {}
        for key, tkey in _SHAPE_KEYS:
            want = tpl.get(tkey)
            if key == "type":
                want = want or "square"
            if want is not None and cd.get(key) != want:
                fields[key] = [cd.get(key), want]
                cd[key] = want
        if fields:
            report["changed"] = True
            report["aligned"].append({"id": a.get("id"), "name": a.get("actionName"), "fields": fields})
    return report


def normalize_designer_layer(flow: dict) -> dict:
    """Regenerate STRING designer setting values from their runtime parameters, in place. Returns a
    report {changed: bool, actions: [{id,name,settings:[{id,type,label}]}], warnings: [...]}."""
    report: dict = {"changed": False, "actions": [], "warnings": []}
    for a in flow.get("actions") or []:
        cfg_tree = (a.get("customData") or {}).get("configuration") or []
        byid = _index_settings(cfg_tree)
        changed_settings: list = []
        for p in a.get("parameters") or []:
            s = byid.get(p.get("tabPropertyId"))
            if s is None:
                # a runtime param with no designer setting to mirror into - a malformed/hand-built
                # node smell. Never clobber; surface it so a human looks.
                if p.get("value") not in (None, "", [], {}):
                    report["warnings"].append({"action": a.get("actionName"),
                                               "param": p.get("tabPropertyId"), "why": "param_without_setting"})
                continue
            # STRING-ONLY: only a string designer value can hold the <%N%> bug and is a clean mirror of
            # its runtime param. Anything list/dict-shaped is left exactly as-is (see module doc).
            if not isinstance(s.get("value"), str):
                continue
            new = _b._config_value_from_param(p.get("value"), p.get("variable"))
            if new != s.get("value"):
                s["value"] = new
                changed_settings.append({"id": s.get("id"), "type": s.get("type"), "label": s.get("label")})
        if changed_settings:
            report["changed"] = True
            report["actions"].append({"id": a.get("id"), "name": a.get("actionName"), "settings": changed_settings})
    return report
