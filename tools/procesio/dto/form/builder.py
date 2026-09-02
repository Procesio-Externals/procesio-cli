"""Form template builder — PURE config -> FormTemplateDto.

A form's layout lives in `Data.elements` (plaintext control tree). PROVEN LIVE
(2026-06-24): the runtime renders from `elements` — the encrypted `Data.code`
blob is NOT required (a form with code="" and modified elements rendered the
modified elements). So forms are fully buildable server-side.

Approach (template-merge): for each control in config, clone a captured golden
element of that type (dto/form/elements/<type>.json) so every config field stays
valid, assign fresh ids, and override the semantic configs (label, name, required,
placeholder, options, default, submit, ...). theme/messages/dataModel/variables
come from a captured Data shell.

API (verified live):
  - Create: POST /api/FormTemplate (FormTemplateDto) -> {id} ; client supplies Id
  - Get:    GET  /api/FormTemplate/{id}
  - Edit:   PUT  /api/FormTemplate
  - Publish/state: Status=1 (PUBLISHED) + State=true on the body, or PATCH /api/FormTemplate/{id}?state=
  - Render: create a CustomUrl, open forms.procesio.app/{tinyUrl}
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from tools.procesio.dto.framework import Component
from tools.procesio.errors import UsageError

DIR = Path(__file__).resolve().parent
_ELEMENTS = DIR / "elements"

_FORM_TYPE = {"usertask": 0, "general": 1}

# config convenience key -> the element config `key` it sets
_OVERRIDE_KEYS = {
    "label", "placeholder", "tooltip", "info-text", "infoText", "defaultValue",
    "required", "readonly", "visible", "rows", "mode", "multiple", "searchable",
    "clearable", "regex", "submit", "disabledIfFormIsInvalid", "variation", "hasNow",
    "description", "src", "url", "alt", "title", "width", "height", "linkUrl",
    "maxFileSize", "canAdd", "canRemove", "addText", "min", "max", "outlined",
    # task / assignment (section, tabs, table, approval controls)
    "assignee", "assigneeReplacement", "approver", "approverReplacement",
}

# control event -> (config key holding the events, the event object `type`).
# VERIFIED 2026-06-25 against ui-builder source: trigger.ts TriggerKey enum (config keys),
# FieldEvents.component.vue (EventType<->key pairing), and the EventType enum in
# model/config/events/index.ts. (Fixed: open/close=SIDE_PANEL_*, step*=STEPPER_*,
# message*=CHAT_*, approvalsubmit=*_APPROVE_OR_REJECT.)
_EVENT_KEY = {
    "click": "onClickEvents", "input": "onInputEvents", "change": "onInputEvents",
    "focus": "onFocusEvents", "blur": "onBlurEvents", "hover": "onHoverEvents",
    "ready": "onReadyEvents",
    "open": "onOpenEvents", "close": "onCloseEvents",
    "tabchange": "onTabChangeEvents", "rowadded": "onTableRowAddedEvents",
    "rowdeleted": "onTableRowDeletedEvents", "paginated": "onPaginationChangedEvents",
    "stepchange": "onStepChangeEvents", "nextstep": "onNextStepEvents",
    "previousstep": "onPreviousStepEvents",
    "beforeapprove": "onBeforeApproveEvents", "afterapprove": "onAfterApproveEvents",
    "beforereject": "onBeforeRejectEvents", "afterreject": "onAfterRejectEvents",
    "beforeapprovalsubmit": "onBeforeApprovalSubmitEvents",
    "afterapprovalsubmit": "onAfterApprovalSubmitEvents",
    "messagesfetch": "onMessagesFetchEvents", "messagesent": "onMessageSentEvents",
}
_EVENT_TYPE = {
    "click": "CLICK", "input": "INPUT", "change": "INPUT", "focus": "FOCUS",
    "blur": "BLUR", "hover": "HOVER", "ready": "READY",
    "open": "SIDE_PANEL_OPEN", "close": "SIDE_PANEL_CLOSE", "tabchange": "TAB_CHANGE",
    "rowadded": "TABLE_ROW_ADDED", "rowdeleted": "TABLE_ROW_DELETED",
    "paginated": "TABLE_PAGINATED",
    "stepchange": "STEPPER_STEP_CHANGE", "nextstep": "STEPPER_NEXT_STEP",
    "previousstep": "STEPPER_PREVIOUS_STEP",
    "beforeapprove": "BEFORE_APPROVE", "afterapprove": "AFTER_APPROVE",
    "beforereject": "BEFORE_REJECT", "afterreject": "AFTER_REJECT",
    "beforeapprovalsubmit": "BEFORE_APPROVE_OR_REJECT",
    "afterapprovalsubmit": "AFTER_APPROVE_OR_REJECT",
    "messagesfetch": "CHAT_MESSAGES_FETCH", "messagesent": "CHAT_MESSAGE_SENT",
}
_KEY_ALIASES = {"infoText": "info-text", "default": "defaultValue"}


def _new_id(ctx) -> str:
    return (ctx.get("new_id") or (lambda: str(uuid.uuid4())))()


@lru_cache(maxsize=None)
def _golden(kind: str) -> dict:
    path = _ELEMENTS / f"{kind}.json"
    if not path.exists():
        avail = sorted(p.stem for p in _ELEMENTS.glob("*.json"))
        raise UsageError(f"unknown form control type {kind!r}; available: {avail}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _shell() -> dict:
    return json.loads((DIR / "data_shell.json").read_text(encoding="utf-8"))


def control_types() -> list[str]:
    return sorted(p.stem for p in _ELEMENTS.glob("*.json"))


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "", (s or "").title().replace(" ", "")) or "field"


def _options(raw):
    """Normalize options to [{name, value}]."""
    out = []
    for o in raw or []:
        if isinstance(o, dict):
            out.append({"name": o.get("name", o.get("label", o.get("value"))),
                        "value": o.get("value", o.get("name"))})
        else:
            out.append({"name": str(o), "value": str(o)})
    return out


def _set_config(configs: list, key: str, value, ctx) -> None:
    for c in configs:
        if c.get("key") == key:
            c["value"] = value
            return


@lru_cache(maxsize=1)
def _style_groups() -> list:
    """Resolved theme groups (label, types, {cssVariable: {label,type}}) from the shell.
    Used for per-element styling: the runtime applies an element's `style` config (a
    CSSProperty[] of ENABLED overrides) on top of the theme."""
    groups = []
    for g in _shell().get("theme") or []:
        props = {p["cssVariable"]: {"label": p.get("label", ""), "type": p.get("type")}
                 for p in g.get("properties") or [] if p.get("cssVariable")}
        groups.append((g.get("label"), set(g.get("types") or []), props))
    return groups


# Element alignment feature: three flex properties on container elements, each keyed by
# an element-scope SUFFIX. The 18 real vars are --fd/--jc/--ai × these 6 suffixes:
#   --fd-<suffix>  flex-direction   ("Inner direction")
#   --jc-<suffix>  justify-content  ("Inner main axis")
#   --ai-<suffix>  align-items      ("Inner cross axis")
# Element type -> its alignment suffix (ui-builder theme.ts registrations).
_ALIGNMENT_SUFFIX = {
    "section": "section", "list": "list-item", "columns": "column",
    "stepper": "step", "tabs": "tab", "side-panel": "side-panel",
}


def _alignment_props(el_type: str) -> dict:
    """The flex-alignment style vars a container element accepts. Additive to the golden
    theme groups so alignment is usable before the golden is refreshed from the launched
    form-theme.ts; when the golden ships them natively the golden's definition wins (it
    carries the proper dropdown type + option list). Values pass through (standard CSS,
    e.g. flex-direction row|column, justify-content flex-start|center|space-between,
    align-items flex-start|center|stretch)."""
    suffix = _ALIGNMENT_SUFFIX.get(el_type)
    if not suffix:
        return {}
    return {
        f"--fd-{suffix}": {"label": "Inner direction", "type": None},
        f"--jc-{suffix}": {"label": "Inner main axis", "type": None},
        f"--ai-{suffix}": {"label": "Inner cross axis", "type": None},
    }


def _style_props_for(el_type: str):
    """cssVariable -> {label,type} stylable on this element type, or None. Mirrors the
    frontend getCssGroupByElementType: the FIRST theme group whose `types` include the
    type (so e.g. select uses the Input group), plus the alignment vars for container
    types. Golden definitions win over the additive alignment fallback."""
    for _label, types, props in _style_groups():
        if el_type in types:
            extra = _alignment_props(el_type)
            return {**extra, **props} if extra else props
    return None


def _apply_element_style(spec: dict, el_type: str, configs: list, ctx) -> None:
    """Set the element's `style` config from spec['style'] = {cssVariable: value} (or a
    list of {cssVariable,value[,enabled]}). Stored as CSSProperty[] with enabled:true; the
    runtime applies only enabled props. Unknown vars fail loud (no silent drop)."""
    raw = spec.get("style")
    if not raw:
        return
    props = _style_props_for(el_type)
    if props is None:
        raise UsageError(f"form control {el_type!r} has no stylable properties")
    pairs = raw.items() if isinstance(raw, dict) else (
        (d.get("cssVariable"), d.get("value")) for d in raw)
    items = []
    for cssvar, value in pairs:
        meta = props.get(cssvar)
        if not meta:
            raise UsageError(f"{el_type}: unknown style variable {cssvar!r}; "
                             f"valid: {sorted(props)}")
        items.append({"label": meta["label"], "value": str(value),
                      "cssVariable": cssvar, "type": meta["type"], "enabled": True})
    _set_config(configs, "style", items, ctx)


_FIELDS_NS = "11223344-5566-7788-99aa-aabbccddeeff"  # platform "fields" container id (constant across forms)


def _map_rows(rows, ctx) -> list:
    """Normalize an inputMap/outputMap/mapping list to [{id,left,right}]. A side that
    names a form field (registered in ctx['field_paths']) is resolved to its full
    value-path formId.FIELDS.elementId.valueConfigId; process-variable ids and
    literals pass through."""
    paths = ctx.get("field_paths", {})

    def resolve(v):
        if isinstance(v, str) and v in paths:
            return paths[v]
        return v if isinstance(v, str) else str(v)
    out = []
    for i, m in enumerate(rows or []):
        left = m.get("to", m.get("left"))
        right = m.get("from", m.get("value", m.get("right", "")))
        out.append({"id": i, "left": resolve(left), "right": resolve(right)})
    return out


def _proc_map(rows, ctx, pvars: dict, kind: str) -> list:
    """RUN_PROCESS input/output map. One side names a PROCESS VARIABLE (resolved to its
    GUID via pvars — the backend requires the id, not the name; live-confirmed 2026-06-29),
    the other names a FORM FIELD (resolved to its value-path) or a literal/process-var id.
    Real exports show BOTH maps as left=process-variable-GUID, right=form-field-path
    (verified across OMS/Diligentic 2026-06-29) -- the orientation is the SAME for input
    and output; only which spec key names the process var differs:
    kind='in':  {to: procVar, from: formField}  -> left=procVarId(to),   right=fieldPath(from)
    kind='out': {to: formField, from: procVar}  -> left=procVarId(from),  right=fieldPath(to)"""
    paths = ctx.get("field_paths", {})

    def field(v):
        return paths.get(v, v if isinstance(v, str) else str(v))

    def pvar(v):
        return pvars.get(v, v if isinstance(v, str) else str(v))
    out = []
    for i, m in enumerate(rows or []):
        a = m.get("to", m.get("left"))
        b = m.get("from", m.get("value", m.get("right", "")))
        if kind == "in":   # process input <- form field
            out.append({"id": i, "left": pvar(a), "right": field(b)})
        else:              # form field <- process output (process var still on the LEFT)
            out.append({"id": i, "left": pvar(b), "right": field(a)})
    return out


def _ds_map(rows) -> list:
    """A DataStore operation input/output map: a list of DataStoreMapItem
    {id, left, right}. Accepts rows as {left,right} or {to,from} and passes the two
    sides through unchanged (their orientation is DataStore-op specific and confirmed
    live), only assigning the row id."""
    out = []
    for i, m in enumerate(rows or []):
        if not isinstance(m, dict):
            continue
        left = m.get("left", m.get("to"))
        right = m.get("right", m.get("from", m.get("value")))
        out.append({"id": m.get("id", i), "left": left, "right": right})
    return out


def _trigger(ev: dict, ctx) -> dict:
    """The {action, config} for one event trigger.
    do = map | process | js | form | datastore."""
    do = (ev.get("do") or "").strip().lower()
    if do in ("process", "run_process"):
        pid = ev["processId"]
        pvars = (ctx.get("process_vars") or {}).get(pid, {})
        return {"action": "RUN_PROCESS", "config": {
            "processId": pid, "syncRun": bool(ev.get("syncRun", False)),
            "mapLatestTriggerOnly": bool(ev.get("mapLatestTriggerOnly", False)),
            "inputMap": _proc_map(ev.get("inputs"), ctx, pvars, "in"),
            "outputMap": _proc_map(ev.get("outputs"), ctx, pvars, "out"),
            "conditions": [], "areConditionsConfigured": True}}
    if do in ("js", "javascript", "run_javascript"):
        return {"action": "RUN_JAVASCRIPT", "config": {"code": ev.get("code", "")}}
    if do in ("map", "map_form_data"):
        return {"action": "MAP_FORM_DATA", "config": {"mapping": _map_rows(ev.get("mapping"), ctx)}}
    if do in ("form", "trigger_form", "run_form", "open_form"):
        # EventAction.TRIGGER_FORM; config = EventTriggerFormConfig {formId, mapping, ...}
        # (verified vs ui-builder model/config/events/index.ts — NOT "RUN_FORM"/inputMap).
        return {"action": "TRIGGER_FORM", "config": {
            "formId": ev.get("formId"),
            "mapping": _map_rows(ev.get("mapping") or ev.get("inputs"), ctx)}}
    if do in ("datastore", "data_store", "run_data_store_operation", "run_data_store"):
        # EventAction.RUN_DATA_STORE_OPERATION; config = EventRunDataStoreOperationConfig
        # {dataStoreId, operation, inputMap, outputMap, filters?, areFiltersConfigured?}
        # (ui-builder model/config/events/index.ts). operation = DataStoreOperation
        # READ/ADD/UPDATE/DELETE; filters apply to every op except ADD. The map item is
        # {id, left, right} (DataStoreMapItem); the operation wire encoding + map
        # orientation must be re-verified live. See PROCESIO-RESOURCE-MODEL-NOTES.md.
        cfg = {
            "dataStoreId": ev.get("dataStoreId"),
            "operation": ev.get("operation"),
            "inputMap": _ds_map(ev.get("inputs") or ev.get("inputMap")),
            "outputMap": _ds_map(ev.get("outputs") or ev.get("outputMap")),
        }
        filters = ev.get("filters")
        if filters is not None:
            cfg["filters"] = filters
            cfg["areFiltersConfigured"] = bool(filters)
        else:
            cfg["areFiltersConfigured"] = bool(ev.get("areFiltersConfigured", False))
        return {"action": "RUN_DATA_STORE_OPERATION", "config": cfg}
    raise UsageError(
        f"unknown event trigger do={ev.get('do')!r} (use map|process|js|form|datastore)")


def _apply_events(spec: dict, configs: list, ctx) -> None:
    """Attach control events. Each spec event: {on, do, ...}. Grouped by the
    control's event config key as {debounce, events:[{id,type,action,config}]}."""
    grouped: dict[str, list] = {}
    for ev in spec.get("events") or []:
        on = (ev.get("on") or "click").strip().lower()
        key = _EVENT_KEY.get(on)
        if not key:
            raise UsageError(f"unknown event on={ev.get('on')!r}; known: {sorted(_EVENT_KEY)}")
        obj = {"id": _new_id(ctx), "type": _EVENT_TYPE[on]}
        obj.update(_trigger(ev, ctx))
        grouped.setdefault(key, []).append(obj)
    for key, objs in grouped.items():
        _set_config(configs, key, {"debounce": 0, "events": objs}, ctx)


def _resolve_late_field_refs(elements: list, ctx) -> None:
    """Second pass over built elements: resolve event map rows that named a form field
    declared AFTER the element carrying the event.

    `ctx['field_paths']` is filled as elements are built, so a trigger placed above its
    target fields keeps the raw field NAME in the map instead of the value-path. That is
    the normal layout for any form that shows results (submit button above the results
    panel), and the failure is silent: the API accepts the row, the designer renders it
    blank, and the fields never populate. Runs once every path is known, so ordering in
    the config no longer changes the wiring."""
    paths = ctx.get("field_paths") or {}
    if not paths:
        return

    def fix(rows) -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            for side in ("left", "right"):
                v = row.get(side)
                if isinstance(v, str) and v in paths:
                    row[side] = paths[v]

    for el in elements:
        for cfg in el.get("configs") or []:
            val = cfg.get("value")
            if not isinstance(val, dict):
                continue
            for ev in val.get("events") or []:
                ecfg = (ev or {}).get("config") or {}
                for key in ("inputMap", "outputMap", "mapping"):
                    fix(ecfg.get(key))


_HEADER = {"heading"}
_FOOTER = {"button"}
_CLEAR_DEFAULT = ("placeholder", "tooltip", "info-text")  # reset golden leftovers


def _config_value(el: dict, key: str):
    return next((c.get("value") for c in el.get("configs", []) if c.get("key") == key), None)


# Controls whose field-source config is NOT named `value`. A file-viewer holds its file
# in `src` (the platform's own empty state for it reads "Field source not set"), and
# _VALUE_TYPE already types file-viewer as File — so without this the control gets a
# data-model attribute but no field path, and an outputMap row targeting it silently
# keeps the raw field name instead of resolving to a value path.
_VALUE_CONFIG_KEY = {"file-viewer": "src"}


def _value_key(el_type) -> str:
    """The config key that holds this control's field value."""
    return _VALUE_CONFIG_KEY.get(el_type, "value")


_SKIP_OVERRIDE = {"type", "name", "options", "children", "configs", "events",
                  "columns", "cells", "hasHeader", "hasIndexColumn"}


def _build_element(spec: dict, ctx: dict, out: list) -> dict:
    """Build one element (flat) into `out`, recursing children with parentId set.
    PROCESIO uses a FLAT elements list + parentId (NOT nested `children`)."""
    kind = spec.get("type")
    if not kind:
        raise UsageError("each form element needs a 'type'")
    if kind == "table":
        return _build_table(spec, ctx, out)
    el = copy.deepcopy(_golden(kind))
    el["id"] = _new_id(ctx)
    el.pop("children", None)
    el["parentId"] = ctx.get("parent_id")
    section = el.get("section")
    if section not in ("header", "body", "footer"):
        section = "header" if kind in _HEADER else "footer" if kind in _FOOTER else "body"
    el["section"] = section
    configs = el.get("configs", [])
    for c in configs:
        c["id"] = _new_id(ctx)
        if c.get("key") == "visible":
            c["value"] = True
        if c.get("key") in ("required", "readonly"):
            c["value"] = False
        if c.get("key") in _CLEAR_DEFAULT:
            c["value"] = ""
    field = spec.get("name") or _slug(spec.get("label") or kind)
    _set_config(configs, "name", field, ctx)
    _set_config(configs, "id", field, ctx)
    val_cfg = next((c for c in configs if c.get("key") == _value_key(kind)), None)
    if val_cfg and ctx.get("form_id"):
        # The field-path value segment MUST be the element's OWN `value` config id.
        # Verified against real forms (OMS, eTransport): the data-model value-attr id
        # equals the element's value config id. A fresh id here resolves to "Unknown"
        # in the process-designer trigger-map "Form variable" selector.
        vaid = val_cfg["id"]
        ctx.setdefault("value_attr_ids", {})[el["id"]] = vaid
        ctx.setdefault("field_paths", {})[field] = (
            f'{ctx["dm_root_id"]}.{_FIELDS_NS}.{el["id"]}.{vaid}')
    for ck, cv in spec.items():
        if ck in _SKIP_OVERRIDE:
            continue
        key = _KEY_ALIASES.get(ck, ck)
        if key in _OVERRIDE_KEYS:
            _set_config(configs, key, cv, ctx)
    for ck, cv in (spec.get("configs") or {}).items():
        _set_config(configs, ck, cv, ctx)
    if "optionsSource" in spec:
        src = spec["optionsSource"] or {}
        st = {"json": "JSON", "static-list": "static-list", "url": "URL"}.get(
            str(src.get("type", "static-list")).lower(), "static-list")
        val = src.get("value")
        _set_config(configs, "sourceType", st, ctx)
        _set_config(configs, "sourceValue",
                    _options(val) if st == "static-list" and isinstance(val, list) else val, ctx)
    elif "options" in spec:
        _set_config(configs, "sourceType", "static-list", ctx)
        _set_config(configs, "sourceValue", _options(spec["options"]), ctx)
    _apply_events(spec, configs, ctx)
    _apply_element_style(spec, kind, configs, ctx)
    # array-valued control -> its `value` defaults to an empty array + is typed isList,
    # so the runtime emits/sends an ARRAY (not a single object/null). See _value_is_list.
    if val_cfg is not None and _value_is_list(el):
        val_cfg["value"] = []
        val_cfg["isList"] = True
    out.append(el)
    # children -> FLAT with parentId; columns/tabs keep an ordered child-name list
    child_els = [_build_element(ch, {**ctx, "parent_id": el["id"]}, out)
                 for ch in spec.get("children") or []]
    if kind == "columns":
        _set_config(configs, "columns", [_config_value(ce, "name") for ce in child_els], ctx)
    elif kind == "tabs":
        _set_config(configs, "tabs", [_config_value(ce, "name") for ce in child_els], ctx)
    return el


def _build_table(spec: dict, ctx: dict, out: list) -> dict:
    """A table = the table element + a static-table-row + the row's cell controls,
    wired by `childrenIdPerColumn` (colId -> [cellElementId]). All FLAT in `out`."""
    el = copy.deepcopy(_golden("table"))
    el["id"] = _new_id(ctx)
    el.pop("children", None)
    el["parentId"] = ctx.get("parent_id")
    el["section"] = "body"
    configs = el.get("configs", [])
    for c in configs:
        c["id"] = _new_id(ctx)
        if c.get("key") == "visible":
            c["value"] = True
    name = spec.get("name") or _slug(spec.get("label") or "table")
    _set_config(configs, "name", name, ctx)
    _set_config(configs, "id", name, ctx)
    if spec.get("label") is not None:
        _set_config(configs, "label", spec["label"], ctx)
    _set_config(configs, "hasHeader", bool(spec.get("hasHeader", True)), ctx)
    _set_config(configs, "hasIndexColumn", bool(spec.get("hasIndexColumn", False)), ctx)
    cols, col_ids = [], {}
    for col in spec.get("columns", []):
        cid = _new_id(ctx)
        col_ids[col["key"]] = cid
        cols.append({"id": cid, "key": col["key"], "label": col.get("label", col["key"])})
    _set_config(configs, "tableColumnsSourceType", "static-list", ctx)
    _set_config(configs, "tableColumnsSourceValue", cols, ctx)
    out.append(el)
    # the row: dynamic-table-row (user can add/remove rows) when spec.dynamic, else a
    # fixed static-table-row. Cells live in childrenIdPerColumn[colId] either way.
    dynamic = bool(spec.get("dynamic"))
    row = copy.deepcopy(_golden("dynamic-table-row" if dynamic else "static-table-row"))
    row["id"] = _new_id(ctx)
    row.pop("children", None)
    row["parentId"] = el["id"]
    row["section"] = "body"
    rcfg = row.get("configs", [])
    for c in rcfg:
        c["id"] = _new_id(ctx)
    rowname = name + "Row"
    _set_config(rcfg, "name", rowname, ctx)
    _set_config(rcfg, "id", rowname, ctx)
    out.append(row)
    cipc: dict = {}
    for col in spec.get("columns", []):
        cell = col.get("cell")
        if not cell:
            continue
        ce = _build_element(dict(cell), {**ctx, "parent_id": row["id"]}, out)
        cipc[col_ids[col["key"]]] = [ce["id"]]
    _set_config(rcfg, "childrenIdPerColumn", cipc, ctx)
    if dynamic:
        # the dynamic row carries the add/remove affordances + its own column mirror
        _set_config(rcfg, "canAdd", True, ctx)
        _set_config(rcfg, "canRemove", True, ctx)
        _set_config(rcfg, "addText", spec.get("addText", "Add row"), ctx)
        _set_config(rcfg, "hasHeader", bool(spec.get("hasHeader", True)), ctx)
        _set_config(rcfg, "hasIndexColumn", bool(spec.get("hasIndexColumn", False)), ctx)
        _set_config(rcfg, "tableColumnsSourceType", "static-list", ctx)
        _set_config(rcfg, "tableColumnsSourceValue", cols, ctx)
        _apply_events(spec, rcfg, ctx)   # onTableRowAdded/Deleted events, if any
    _set_config(configs, "rows", [rowname], ctx)
    return el


def _build_code(config: dict, ctx: dict) -> str:
    """Form-level CSS + JavaScript (the designer's 'Switch to code' editor) -> the
    encrypted `Data.code` blob. Accepts `css`/`javascript` (or a `code:{css,javascript}`
    object). Empty -> "" (forms render fine without it; verified live). The AES key comes
    from ctx['form_code_key'] (tests) or Credential Manager procesio/form-code-key."""
    code = config.get("code") if isinstance(config.get("code"), dict) else {}
    css = code.get("css", config.get("css"))
    js = code.get("javascript", config.get("javascript", config.get("js")))
    if not (css or js):
        return ""
    key = ctx.get("form_code_key")
    if not key:
        from tools._lib import creds  # lazy: avoid keyring import unless needed
        key = creds.get("procesio", "form-code-key")
    from tools.procesio.dto.form import code_cipher
    return code_cipher.encrypt_code(js or "", css or "", key)


def _apply_theme(theme: list, overrides: dict) -> list:
    """Apply {cssVariable: value} overrides onto the shell theme (deep-copied)."""
    if not overrides:
        return theme
    theme = copy.deepcopy(theme)
    norm = {(k if k.startswith("--") else f"--{k}"): v for k, v in overrides.items()}
    for section in theme or []:
        for prop in section.get("properties", []):
            cv = prop.get("cssVariable")
            if cv in norm:
                prop["value"] = norm[cv]
    return theme


# DARK_PALETTE — the 16 dark-mode color variables (ui-builder theme.ts DARK_PALETTE).
# A form carries both a light and a dark palette; the runtime swaps by themeMode
# (store state themeMode/activeThemeMode; getPaletteStyleSheet injects the active one).
# Persisted INSIDE the single `theme` array on the COLORS group as {light, dark}
# (see _apply_dark). Emitted only when the caller opts in via config `dark`/`themeDark`.
_DARK_PALETTE = {
    "--c-primary": "#4663f5", "--c-primary-variant": "#8aa0ff",
    "--c-error": "#ff6b6b", "--c-success": "#32d583", "--c-info": "#53b1fd",
    "--c-neutral--900": "#f8fafd", "--c-neutral--800": "#f2f5fa",
    "--c-neutral--700": "#c8cfdb", "--c-neutral--600": "#b0b8c4",
    "--c-neutral--500": "#98a0ae", "--c-neutral--400": "#3b4557",
    "--c-neutral--300": "#2a3241", "--c-neutral--200": "#222936",
    "--c-neutral--100": "#1a202b", "--c-neutral--50": "#0b0e14",
    "--c-neutral--0": "#141922",
}


def _apply_dark(theme_list: list, overrides: dict) -> list:
    """Enable dark mode on a built theme: turn the COLORS group's `properties` into a
    {light, dark} ModeProperties object (the shape ui-builder's getPaletteStyleSheet reads).
    light = the theme-applied color props; dark = the same props with values from the 16-var
    DARK_PALETTE plus any caller `themeDark` overrides, keyed by cssVariable. Every other
    group keeps a flat CSSProperty[]. themeMode is editor-only and never persisted."""
    theme_list = copy.deepcopy(theme_list)
    dark_vals = {**_DARK_PALETTE, **(overrides or {})}
    dark_vals = {(k if k.startswith("--") else f"--{k}"): v for k, v in dark_vals.items()}
    for group in theme_list or []:
        if str(group.get("label", "")).strip().lower() == "colors":
            light = group.get("properties")
            if isinstance(light, list):
                dark = [{**pr, "value": dark_vals.get(pr.get("cssVariable"), pr.get("value"))}
                        for pr in light]
                group["properties"] = {"light": light, "dark": dark}
            break
    return theme_list


_STR = "0317bfee-b2f5-4bde-bfe8-121212121214"
_BOOL = "0317bfee-b2f5-4bde-bfe8-121212121210"
_INT = "0317bfee-b2f5-4bde-bfe8-121212121211"
_DT = "0317bfee-b2f5-4bde-bfe8-121212121218"
_FILE = "10c6ac59-3929-49e6-99dc-121212121219"
_JSON = "0317bfee-b2f5-4bde-bfe8-121212121220"
_BOOL_CFG = {"visible", "readonly", "required", "submit", "multiple", "searchable",
             "clearable", "hasNow", "disabledIfFormIsInvalid", "canAdd", "canRemove",
             "outlined", "disabled"}
_VALUE_TYPE = {"number-input": _INT, "checkbox": _BOOL, "datetime-input": _DT,
               "file-upload": _FILE, "file-viewer": _FILE, "chat": _JSON}
# Controls whose `value` is a JSON ARRAY -> DM attr isList:true + value config default [].
# Inherently array-valued: chat + the array elements (list/table/dynamic-table-row).
# Array-valued ONLY when multiple:true: file-upload/select. Confirmed by Liza (PROCESIO):
# a multiple file-upload MUST be isList + default [] or the form sends a single object and
# a List<File> process input fails at launch ("... item is not an array: StartObject").
_VALUE_LIST = {"chat", "list", "table", "dynamic-table-row"}
_MULTIPLE_ARRAY_TYPES = {"file-upload", "select"}

def _value_is_list(el: dict) -> bool:
    t = el.get("type")
    if t in _VALUE_LIST:
        return True
    if t in _MULTIPLE_ARRAY_TYPES:
        return bool(next((c.get("value") for c in el.get("configs", [])
                          if c.get("key") == "multiple"), None))
    return False
_SKIP_DM_ATTR = {"sourceValue", "sourceType", "options", "childrenIdPerColumn",
                 "tableColumnsSourceValue", "tableColumnsSourceType", "rows", "columns",
                 "tabs", "style"}


def _attr_name(key: str) -> str:
    """Data-model attribute name = camelCase of the config key (PROCESIO compiles
    `info-text` -> `infoText`). Single-word keys pass through unchanged."""
    parts = str(key).split("-")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def _dm_attr(name, aid, type_id, parent, is_list=False):
    return {"id": aid, "name": name, "displayName": name, "dataTypeId": type_id,
            "isDataModel": False, "isList": is_list, "isProcesio": False,
            "isPublic": False, "parentDataTypeId": parent, "jsonProperty": None,
            "attributes": [], "hidden": False}


def _build_data_model(form_id: str, elements: list, ctx: dict) -> dict:
    """Build the form's `Data.dataModel` mirror. PROCESIO backs every form control
    with a data-model attribute: root "form" (id=form_id) -> `fields` container
    (id=_FIELDS_NS) -> one sub-model per element (id=elementId) -> an attribute per
    config (incl. `value`). RUN_PROCESS/MAP triggers reference fields by the path
    formId.fields.elementId.valueAttrId, and the runtime stores the field value in
    that attribute. Without this, the designer shows raw guids and values don't flow."""
    dm = copy.deepcopy(_shell().get("dataModel") or {})
    dm["id"] = form_id
    dm["name"] = dm.get("name") or "form"
    attrs = dm.get("attributes") or []
    fields = next((a for a in attrs if a.get("id") == _FIELDS_NS), None)
    if fields is None:
        fields = {"id": _FIELDS_NS, "dataTypeId": _FIELDS_NS, "name": "fields",
                  "displayName": "fields", "isDataModel": True, "isList": False,
                  "isProcesio": False, "isPublic": True, "jsonProperty": None,
                  "attributes": []}
        attrs.append(fields)
        dm["attributes"] = attrs
    fields["parentDataTypeId"] = form_id
    val_ids = ctx.get("value_attr_ids", {})
    submodels = []
    for el in elements:
        eid = el["id"]
        nm = next((c.get("value") for c in el.get("configs", []) if c.get("key") == "name"), None) or eid
        sub = {"id": eid, "dataTypeId": eid, "name": nm, "displayName": nm,
               "isDataModel": True, "isList": False, "isProcesio": False,
               "isPublic": False, "parentDataTypeId": _FIELDS_NS, "jsonProperty": None,
               "attributes": []}
        for c in el.get("configs", []):
            k = c.get("key")
            if not k or k.endswith("Events") or k in _SKIP_DM_ATTR:
                continue
            # The data-model attribute id MUST equal the element's config id for that
            # key (verified against real forms: every fields sub-model attr id == the
            # element's config id; 15/16 in OMS vs 0/16 with fresh ids -> "Unknown" in
            # the trigger-map UI). Reuse the config's own id.
            aid = c.get("id") or _new_id(ctx)
            vkey = _value_key(el.get("type"))
            tid = (_VALUE_TYPE.get(el.get("type"), _STR) if k == vkey
                   else (_BOOL if k in _BOOL_CFG else _STR))
            is_list = (k == vkey and _value_is_list(el))
            sub["attributes"].append(_dm_attr(_attr_name(k), aid, tid, eid, is_list))
        submodels.append(sub)
    fields["attributes"] = submodels
    return dm


def build(config: dict, ctx: dict) -> dict:
    ctx = dict(ctx)
    ctx["form_id"] = ctx.get("form_id") or _new_id(ctx)
    shell = _shell()
    # The designer's field-name resolver walks from the "form" handle variable
    # (Data.variables[0]) into Data.dataModel. So the dataModel ROOT id, the
    # field-path first segment, AND variables[0].id MUST be the SAME id, else a stored
    # field path can't be turned back into its name -> input shows the raw guid, output
    # shows blank (live-confirmed: variables[0]=65396456 but a fresh root id => unresolved).
    # The shell ships the FORM-scope root (scopes:["FORM"]) as that shared id; derive the
    # root from it so the three always agree. It is still != the form template id (what the
    # earlier "root != form id" fix required), so both invariants hold.
    _form_var = (shell.get("variables") or [{}])[0]
    ctx["dm_root_id"] = (ctx.get("dm_root_id") or _form_var.get("dataType")
                         or _form_var.get("id") or _new_id(ctx))
    ctx["field_paths"] = {}
    ctx["value_attr_ids"] = {}
    elements: list = []
    for e in config.get("elements", []):
        _build_element(e, ctx, elements)
    _resolve_late_field_refs(elements, ctx)
    data = {
        "code": _build_code(config, ctx),
        "theme": _apply_theme(shell.get("theme"), config.get("theme")),
        "events": shell.get("events", []),
        "images": shell.get("images", {"logo": None, "header": None}),
        "elements": elements,
        "messages": shell.get("messages"),
        "dataModel": _build_data_model(ctx["dm_root_id"], elements, ctx),
        "variables": shell.get("variables"),
        "browserTitle": config.get("browserTitle", config["name"]),
        "hideBranding": bool(config.get("hideBranding", False)),
    }
    if config.get("chainConfig") is not None:
        data["chainConfig"] = config["chainConfig"]
    # Dark theme (opt-in): the dark palette is persisted INSIDE the single `theme` array —
    # the COLORS group's `properties` becomes a {light, dark} ModeProperties object (verified
    # vs ui-builder main: getPaletteStyleSheet reads properties.light/.dark). themeMode is
    # editor-only and never saved. Emitted only when the caller opts in via `dark`/`themeDark`,
    # so light-only forms are byte-identical.
    if config.get("dark") or config.get("themeDark") is not None or config.get("themeMode") == "dark":
        data["theme"] = _apply_dark(data["theme"], config.get("themeDark"))
    # Guard the field-name-resolution invariant (see dm_root_id above): the dataModel
    # root and every field-path root must equal the form handle variable id, or the
    # designer renders process<->form maps as raw guids/blanks. Fail loudly here so a
    # future change can't silently reintroduce the bug.
    _fv = (data.get("variables") or [{}])[0].get("id")
    if data["dataModel"].get("id") != _fv:
        raise UsageError(f"form data-model root {data['dataModel'].get('id')!r} must "
                         f"equal the form handle variable id {_fv!r}")
    _bad = [p for p in ctx["field_paths"].values() if not str(p).startswith(f"{_fv}.")]
    if _bad:
        raise UsageError(f"form field paths must start with the form root {_fv!r}: {_bad[:3]}")
    ftype = config.get("type", "general")
    return {
        "Id": ctx["form_id"],
        "Name": config["name"],
        "IsPrivate": bool(config.get("isPrivate", False)),
        "Type": _FORM_TYPE.get(str(ftype).strip().lower(), ftype),
        "Status": 1 if config.get("publish", True) else 0,
        "State": bool(config.get("enabled", True)),
        "Assignees": config.get("assignees", []),
        "Data": data,
        "CustomUrl": None,
    }


def _collect_process_ids(elements: list, out: set) -> None:
    for e in elements or []:
        for ev in e.get("events") or []:
            if (ev.get("do") or "").strip().lower() in ("process", "run_process") and ev.get("processId"):
                out.add(ev["processId"])
        _collect_process_ids(e.get("children"), out)
        for col in e.get("columns") or []:
            if col.get("cell"):
                _collect_process_ids([col["cell"]], out)


def _prepare_ctx(client, config: dict) -> dict:
    """Impure pre-build step (has the live client): resolve every process referenced by a
    RUN_PROCESS event to its variable name->id map, so the builder can wire inputMap/
    outputMap by GUID (the backend rejects variable names). Fail loud on a bad processId."""
    pids: set = set()
    _collect_process_ids(config.get("elements"), pids)
    if not pids:
        return {}
    pvars: dict = {}
    for pid in pids:
        try:
            body = client.get(f"/api/Projects/{pid}")
        except Exception as e:  # noqa: BLE001
            raise UsageError(f"RUN_PROCESS references process {pid!r} which could not be "
                             f"fetched ({e}); check the processId.")
        if isinstance(body, dict) and "flow" not in body and isinstance(body.get("result"), dict):
            body = body["result"]
        flow = body.get("flow") if isinstance(body, dict) else None
        src = flow if isinstance(flow, dict) else (body if isinstance(body, dict) else {})
        variables = src.get("variables") or []
        pvars[pid] = {v.get("name"): v.get("id") for v in variables if v.get("name")}
    return {"process_vars": pvars}


def _extract_id(resp, dto):
    if isinstance(resp, dict) and (resp.get("id") or resp.get("Id")):
        return resp.get("id") or resp.get("Id")
    if isinstance(resp, str) and resp.strip():
        return resp.strip().strip('"')
    return dto.get("Id") if isinstance(dto, dict) else None


def _edit(client, resource_id, config, ctx):
    ctx = dict(ctx)
    ctx["form_id"] = resource_id
    dto = build(config, ctx)
    client.put("/api/FormTemplate", dto)
    return client.get(f"/api/FormTemplate/{resource_id}")


COMPONENT = Component(
    name="form",
    description="PROCESIO form template: a control tree (elements) rendered at runtime.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/FormTemplate"),
    get_path="/api/FormTemplate/{id}",
    extract_id=_extract_id,
    prepare_ctx=_prepare_ctx,
    edit=_edit,
)
