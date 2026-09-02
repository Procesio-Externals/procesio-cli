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
