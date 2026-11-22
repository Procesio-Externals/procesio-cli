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

from tools.procesio import formlint
from tools.procesio.client import VARIABLES_ONLY
from tools.procesio.dto.form import fieldpath, queries as form_queries
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
    # document-signing element (TriggerKey.ON_SIGNING_*)
    "signed": "onSignedEvents", "declined": "onDeclinedEvents",
    "completed": "onCompletedEvents",
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
    "signed": "SIGNING_SIGNED", "declined": "SIGNING_DECLINED",
    "completed": "SIGNING_COMPLETED",
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


def _field_slug(s: str) -> str:
    """An auto-generated field NAME: a single lowercase word. A designer save lowercases
    and camelCases around underscores, so a single lowercase word survives it unchanged
    and formlint.lint_field_names does not flag it. Human-readable text stays in the
    field's label, not its name (_slug, which keeps case for flowgraph display, is left
    for that)."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower()) or "field"


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
                 for p in _group_props(g) if p.get("cssVariable")}
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


def _apply_element_classes(spec: dict, configs: list, ctx) -> None:
    """Set the element's `class` config from spec['classes'] (a list of class names, or one
    space-separated string). The runtime puts them on the element's WRAPPER div, and the
    designer offers every class the form's own CSS defines (Styling > Apply CSS classes)."""
    raw = spec.get("classes")
    if raw in (None, "", []):
        return
    names = raw.split() if isinstance(raw, str) else [str(c).strip() for c in raw]
    bad = [n for n in names if not re.fullmatch(r"-?[_a-zA-Z][_a-zA-Z0-9-]*", n)]
    if bad:
        raise UsageError(f"classes: not a CSS class name: {bad} (no leading dot, no spaces)")
    _set_config(configs, "class", names, ctx)


_FIELDS_NS = fieldpath.FIELDS_NS   # platform "fields" container id (constant across forms)


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


# Data Store event filters, as the designer saves them (captured on production 2026-11-19):
# one condition per row, the column's display name on the left, a form field's value path
# or a literal (as text) on the right, and `logicOperator` joining a condition to the NEXT
# one (1 = AND, 2 = OR, 0 on the last). Operator names are the form runtime's
# DataStoreOperator (form-runtime services/dataStore/dataStoreOperators.ts).
_DS_OPERATORS = {
    "EQUALS": "EQUALS", "=": "EQUALS", "==": "EQUALS", "EQ": "EQUALS",
    "DOESNOTEQUAL": "DOES_NOT_EQUAL", "NOTEQUALS": "DOES_NOT_EQUAL", "NOTEQUAL": "DOES_NOT_EQUAL",
    "!=": "DOES_NOT_EQUAL", "<>": "DOES_NOT_EQUAL", "NE": "DOES_NOT_EQUAL",
    "GREATERTHAN": "GREATER_THAN", ">": "GREATER_THAN", "GT": "GREATER_THAN",
    "GREATERTHANOREQUALTO": "GREATER_THAN_OR_EQUAL_TO", "GREATERTHANOREQUAL": "GREATER_THAN_OR_EQUAL_TO",
    ">=": "GREATER_THAN_OR_EQUAL_TO", "GTE": "GREATER_THAN_OR_EQUAL_TO",
    "LESSTHAN": "LESS_THAN", "<": "LESS_THAN", "LT": "LESS_THAN",
    "LESSTHANOREQUALTO": "LESS_THAN_OR_EQUAL_TO", "LESSTHANOREQUAL": "LESS_THAN_OR_EQUAL_TO",
    "<=": "LESS_THAN_OR_EQUAL_TO", "LTE": "LESS_THAN_OR_EQUAL_TO",
    "CONTAINS": "CONTAINS", "DOESNOTCONTAIN": "DOES_NOT_CONTAIN", "NOTCONTAINS": "DOES_NOT_CONTAIN",
    "STARTSWITH": "STARTS_WITH", "ENDSWITH": "ENDS_WITH", "LIKE": "LIKE", "NOTLIKE": "NOT_LIKE",
    "BETWEEN": "BETWEEN", "ISNOTBETWEEN": "IS_NOT_BETWEEN", "NOTBETWEEN": "IS_NOT_BETWEEN",
    "BELONGS": "BELONGS", "IN": "BELONGS", "DOESNOTBELONG": "DOES_NOT_BELONG", "NOTIN": "DOES_NOT_BELONG",
    "ISEMPTY": "IS_EMPTY", "ISNULL": "IS_EMPTY", "ISNOTEMPTY": "IS_NOT_EMPTY", "ISNOTNULL": "IS_NOT_EMPTY",
    "ISTRUE": "IS_TRUE", "ISFALSE": "IS_FALSE",
}
_DS_LOGIC = {"AND": 1, "OR": 2}
# A form field named on the right of a filter, resolved to its value path once every field
# is known (a filter may name a field declared after the element that carries the event).
_FIELD_REF = "\x00field:"


def _ds_operand(value="") -> dict:
    return {"variable": "", "attribute": {"id": "", "nextAttribute": None}, "value": value}


def _ds_filter_side(cond: dict, field_key: str, value_key: str) -> str:
    if cond.get(field_key) not in (None, ""):
        return _FIELD_REF + str(cond[field_key])
    value = cond.get(value_key)
    if value is None:
        return ""
    return json.dumps(value) if isinstance(value, (list, dict)) else (
        str(value).lower() if isinstance(value, bool) else str(value))


def _ds_filters(filters, logic, ctx) -> list:
    """Compact conditions -> the designer's filter list. A condition is {column, op, value |
    field, aux | auxField, logic?}; `logic` (and | or) joins it to the next one and defaults
    to the event's `logic`, then AND. A list already in the designer shape (it has
    `leftOperator`) is sent as it is."""
    if not isinstance(filters, list):
        raise UsageError("`filters` must be a list of conditions")
    if not filters or any(isinstance(f, dict) and "leftOperator" in f for f in filters):
        return filters
    default = str(logic or "and").strip().upper()
    out = []
    for i, cond in enumerate(filters):
        if not isinstance(cond, dict) or not cond.get("column"):
            raise UsageError(f"filter {i} needs a `column` (the Data Store column's display name)")
        raw_op = str(cond.get("op") or cond.get("operator") or "equals")
        op = _DS_OPERATORS.get(raw_op.replace("_", "").replace(" ", "").upper())
        if not op:
            raise UsageError(f"filter {i}: unknown operator {raw_op!r}; use one of "
                             f"{sorted(set(_DS_OPERATORS.values()))}")
        join = str(cond.get("logic") or default).strip().upper()
        if join not in _DS_LOGIC:
            raise UsageError(f"filter {i}: logic must be `and` or `or`, not {join.lower()!r}")
        out.append({
            "id": i, "uid": _new_id(ctx), "operator": op,
            "leftOperator": _ds_operand(str(cond["column"])),
            "rightOperator": _ds_operand(_ds_filter_side(cond, "field", "value")),
            "auxOperator": _ds_operand(_ds_filter_side(cond, "auxField", "aux")),
            "logicOperator": _DS_LOGIC[join] if i < len(filters) - 1 else 0,
            "value": None, "rightOperandAsListRequired": op in ("BELONGS", "DOES_NOT_BELONG"),
            "operandsAsListOptional": True,
        })
    return out


# Row operations of a Data Store event. Verified in the form runtime on production
# (2026-11-19): the inputMap maps a column display name (left) to a form value or a
# literal (right); the only output is `success`. An ADD fills CreatedById / UpdatedById
# itself. With no filter, UPDATE and DELETE target the rows whose EVERY mapped column
# equals the mapped value (form-runtime buildDataStorePkFilter over the whole mapped row).
_DS_WRITES = ("ADD", "UPDATE", "DELETE")


def _ds_write_outputs(operation: str, outputs: list) -> list:
    mapped = {row["left"]: row["right"] for row in outputs}
    unknown = [n for n in mapped if n != "success"]
    if unknown:
        raise UsageError(f"an {operation} has only the `success` output, not {unknown}; "
                         f"read the rows back with a READ or a query in the same trigger")
    return [{"id": 0, "left": "success", "right": mapped.get("success") or ""}]


def _check_ds_write(operation: str, store_id, inputs: list, filters, ctx) -> None:
    """Refuse at build what the runtime or the server always refuses, and say what an
    unfiltered DELETE will remove."""
    columns = [row["left"] for row in inputs if row.get("left")]
    if operation == "ADD" and filters:
        raise UsageError("an ADD takes no filters: it writes one new row from its inputs")
    if operation == "UPDATE" and not filters:
        raise UsageError(
            "an UPDATE needs `filters` to say which rows change. Without them the form "
            "runtime targets the rows whose every mapped column already equals the new "
            "value, so it changes nothing, and if a key column is mapped the server refuses "
            "the call (\"Primary key columns cannot be updated from this endpoint\").")
    known = (ctx.get("ds_columns") or {}).get(store_id)
    if not known:
        return
    unknown = [c for c in columns if c not in known["names"]]
    if unknown:
        raise UsageError(f"Data Store {store_id} has no column {unknown}; its columns are "
                         f"{known['names']} (display names)")
    if operation == "UPDATE":
        keys = [c for c in columns if c in known["pk"]]
        if keys:
            raise UsageError(f"an UPDATE cannot set primary key column {keys}: the server "
                             f"refuses the call. Filter on the key instead and map only the "
                             f"columns that change.")
    if operation == "DELETE" and not filters:
        extra = [c for c in columns if c not in known["pk"]]
        if extra:
            _warn(ctx, f"a DELETE with no filter removes every row whose {', '.join(columns)} "
                       f"all equal the mapped values, not only one row: {extra} is not a key "
                       f"column. Map only the key column(s), or add `filters`.")


def _query_trigger(ev: dict, ctx) -> dict:
    """The RUN_DATA_STORE_OPERATION config that runs one of the form's saved queries, in
    the shape a designer save writes: no Data Store, no filters, the query by id, one
    inputMap row per mapped parameter and all four outputs (unmapped ones with an empty
    right side). `query` names the query by name or id; parameter names are the declared
    spellings, because the run refuses any other."""
    query = form_queries.resolve(ctx.get("queries") or [], ev.get("query") or ev.get("queryId"))
    inputs = _ds_map(ev.get("inputs") or ev.get("inputMap"))
    form_queries.check_parameter_names(query, [row["left"] for row in inputs])
    mapped = {row["left"]: row["right"] for row in _ds_map(ev.get("outputs") or ev.get("outputMap"))}
    unknown = [name for name in mapped if name not in form_queries.OUTPUTS]
    if unknown:
        raise UsageError(f"a query event has no output {unknown}; "
                         f"use {' | '.join(form_queries.OUTPUTS)}")
    outputs = [{"id": i, "left": name, "right": mapped.get(name) or ""}
               for i, name in enumerate(form_queries.OUTPUTS)]
    return {"action": "RUN_DATA_STORE_OPERATION", "config": {
        "dataStoreId": None, "operation": "QUERY", "inputMap": inputs,
        "outputMap": outputs, "filters": [], "queryId": query["id"]}}


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
        operation = str(ev.get("operation") or "").strip().upper()
        if operation == "QUERY":
            return _query_trigger(ev, ctx)
        inputs = _ds_map(ev.get("inputs") or ev.get("inputMap"))
        outputs = _ds_map(ev.get("outputs") or ev.get("outputMap"))
        if operation == "READ":
            # as a designer save writes a READ: page and countPerPage always present, and
            # all four outputs with an empty right side for the ones not mapped
            given = {row["left"]: row["right"] for row in inputs}
            inputs = [{"id": 0, "left": "page", "right": str(given.pop("page", "1"))},
                      {"id": 1, "left": "countPerPage",
                       "right": str(given.pop("countPerPage", "1000"))}]
            if given:
                raise UsageError(f"a READ takes only page and countPerPage as inputs, not "
                                 f"{sorted(given)}; filter rows with `filters`")
            mapped = {row["left"]: row["right"] for row in outputs}
            unknown = [n for n in mapped if n not in form_queries.OUTPUTS]
            if unknown:
                raise UsageError(f"a READ has no output {unknown}; use "
                                 f"{' | '.join(form_queries.OUTPUTS)}")
            outputs = [{"id": i, "left": n, "right": mapped.get(n) or ""}
                       for i, n in enumerate(form_queries.OUTPUTS)]
        filters = ev.get("filters")
        if operation in _DS_WRITES:
            outputs = _ds_write_outputs(operation, outputs)
            _check_ds_write(operation, ev.get("dataStoreId"), inputs, filters, ctx)
        cfg = {
            "dataStoreId": ev.get("dataStoreId"),
            "operation": operation or ev.get("operation"),
            "inputMap": inputs,
            "outputMap": outputs,
        }
        if filters is not None:
            cfg["filters"] = _ds_filters(filters, ev.get("logic"), ctx)
            cfg["areFiltersConfigured"] = bool(filters)
        else:
            cfg["areFiltersConfigured"] = bool(ev.get("areFiltersConfigured", False))
        if operation in _DS_WRITES:
            # as a designer save writes a row operation
            cfg.setdefault("filters", [])
            cfg["queryId"] = None
            cfg["areFiltersConfigured"] = True
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


def _resolve_late_field_refs(elements: list, ctx, form_events: list | None = None) -> None:
    """Second pass, over every event of the form (element slots and the form's own
    `Data.events`): resolve map rows that named a form field declared AFTER the event.

    `ctx['field_paths']` is filled as elements are built, so a trigger placed above its
    target fields keeps the raw field NAME in the map instead of the value-path. That is
    the normal layout for any form that shows results (submit button above the results
    panel), and the failure is silent: the API accepts the row, the designer renders it
    blank, and the fields never populate. Runs once every path is known, so ordering in
    the config no longer changes the wiring."""
    paths = ctx.get("field_paths") or {}
    row_sources = ctx.get("row_source_paths") or {}
    tables = ctx.get("table_rows") or {}
    options = ctx.get("option_sources") or {}

    def fix(rows, sides) -> None:
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            for side in sides:
                v = row.get(side)
                if isinstance(v, str) and v in paths:
                    row[side] = paths[v]

    def list_target(target: str, what: str):
        """A list of rows reaches a dynamic table through its row's source, and a dropdown
        through its own source (which then needs a source type to build options)."""
        if target in row_sources:
            return row_sources[target]
        named = next((n for n, o in options.items() if o[0] == target), None)
        if target in options or named:
            path, source_type, source_value = options[target if target in options else named]
            if not source_type.get("value"):
                source_type["value"] = "JSON"
            if not isinstance(source_value.get("value"), list):
                # declares the source in the data model as the list of options it becomes
                source_value["value"] = []
            return path
        if target in tables:
            raise UsageError(
                f"{what} cannot fill table {target!r}: only a dynamic table (dynamic: true) "
                f"takes them, through its row's source. Written anywhere else the rows "
                f"arrive with every cell empty.")
        return None

    def filter_fields(conds) -> None:
        for cond in conds or []:
            if not isinstance(cond, dict):
                continue
            for side in ("rightOperator", "auxOperator"):
                operand = cond.get(side)
                v = operand.get("value") if isinstance(operand, dict) else None
                if isinstance(v, str) and v.startswith(_FIELD_REF):
                    name = v[len(_FIELD_REF):]
                    if name not in paths:
                        raise UsageError(f"a Data Store filter names form field {name!r}, "
                                         f"which the form does not have")
                    operand["value"] = paths[name]
            filter_fields(cond.get("value") if isinstance(cond.get("value"), list) else None)

    def resolve(ev: dict) -> None:
        ecfg = ev.get("config") or {}
        action = ev.get("action")
        if action == "RUN_DATA_STORE_OPERATION":
            # The left side of a Data Store map is a Data Store name (page, countPerPage,
            # a column, a parameter, rows / count ...), never a form field, even when a
            # field happens to share it.
            sides = ("right",)
            reads = ecfg.get("operation") in ("QUERY", "READ")
            for row in (ecfg.get("outputMap") or []) if reads else []:
                target = row.get("right")
                if row.get("left") == "rows" and isinstance(target, str):
                    limit = (_ROW_LIMIT_TABLE if target in row_sources
                             else _ROW_LIMIT_OPTIONS if target in options else None)
                    hit = list_target(target, "a Data Store read's rows")
                    if hit:
                        row["right"] = hit
                    if limit:
                        _row_limit_check(ecfg, limit, target, ctx)
            filter_fields(ecfg.get("filters"))
        else:
            sides = ("left", "right")
            if action == "RUN_PROCESS":
                # A process's list output fills a table or a dropdown the same way (verified
                # in the form runtime for a table). The form side of a process map is `right`.
                for row in ecfg.get("outputMap") or []:
                    target = row.get("right")
                    if isinstance(target, str) and (target in row_sources or target in options):
                        row["right"] = list_target(target, "a process output")
        for key in ("inputMap", "outputMap", "mapping"):
            fix(ecfg.get(key), sides)

    for el in elements:
        for cfg in el.get("configs") or []:
            # {debounce, events} or a bare list of events (older / hand-written slots)
            for ev in formlint.slot_events(cfg.get("key"), cfg.get("value")):
                resolve(ev)
    for ev in form_events or []:
        if isinstance(ev, dict):
            resolve(ev)


# Rows a form should load into one element. The backend does not limit what a form read
# returns; these are the form-runtime team's numbers for a smooth form (2026-11-19).
_ROW_LIMIT_TABLE = 200
_ROW_LIMIT_OPTIONS = 100
_LIMIT_CLAUSE = re.compile(r"\bLIMIT\b", re.IGNORECASE)


def _row_limit_check(ecfg: dict, limit: int, target: str, ctx) -> None:
    what = "a table" if limit == _ROW_LIMIT_TABLE else "a dropdown"
    if ecfg.get("operation") == "QUERY":
        query = form_queries.find(ctx.get("queries") or [], ecfg.get("queryId"))
        sql = str((query or {}).get("value") or "")
        if query and not _LIMIT_CLAUSE.search(form_queries.code_only(sql)):
            _warn(ctx, f"query {query.get('name')!r} fills {what} ({target}) with no LIMIT, and "
                       f"the backend returns every row. Add LIMIT {limit} (the form-runtime "
                       f"team's limit for {what}).")
        return
    page = next((r.get("right") for r in ecfg.get("inputMap") or []
                 if r.get("left") == "countPerPage"), None)
    try:
        size = int(str(page))
    except (TypeError, ValueError):
        return
    if size > limit:
        _warn(ctx, f"a READ fills {what} ({target}) with up to {size} rows per call "
                   f"(countPerPage). Keep it at {limit} or fewer for {what}, and page or filter "
                   f"for more.")


def _element_configs_by_name(elements) -> dict:
    out = {}
    for e in elements or []:
        cfgs = e.get("configs") or []
        name = next((c.get("value") for c in cfgs if c.get("key") == "name"), None)
        if name and e.get("id"):
            out[name] = (e["id"], {c.get("key"): c.get("id") for c in cfgs if c.get("id")})
    return out


def _remap_live_events(events, old_elements, new_elements, ctx) -> list:
    """A form's own events kept by an edit name fields by value path
    (<root>.<fields>.<element id>.<config id>), and the rebuild gives every element new
    ids. Map each old element's paths to the new element of the same name, config by
    config; warn about a path whose element the edit removed."""
    old = _element_configs_by_name(old_elements)
    new = _element_configs_by_name(new_elements)
    pairs = {}
    for name, (oid, ocfg) in old.items():
        if name in new:
            nid, ncfg = new[name]
            for key, ocid in ocfg.items():
                if key in ncfg:
                    pairs[f"{oid}.{ocid}"] = f"{nid}.{ncfg[key]}"

    def walk(v):
        if isinstance(v, str):
            for o, n in pairs.items():
                if o in v:
                    v = v.replace(o, n)
            return v
        if isinstance(v, list):
            return [walk(x) for x in v]
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        return v

    out = walk(copy.deepcopy(events or []))
    prefix = f"{ctx.get('dm_root_id')}.{_FIELDS_NS}."
    live_ids = {e.get("id") for e in new_elements or []}
    stale = set(re.findall(re.escape(prefix) + r"([0-9a-fA-F-]{36})", json.dumps(out)))
    gone = sorted(stale - live_ids)
    if gone:
        _warn(ctx, f"a form-level event (onLoad / submit) still names element(s) {gone} that "
                   f"this edit does not have: those maps now point at nothing. List the form's "
                   f"`events` in the config to rebuild them.")
    return out


# The form's own triggers (Data.events), as the designer saves them.
_FORM_EVENT_TYPE = {"load": "FORM_LOAD", "beforesubmit": "FORM_BEFORE_SUBMIT",
                    "aftersubmit": "FORM_AFTER_SUBMIT"}


def _form_events(specs, ctx) -> list:
    """Config `events` -> `Data.events`: [{id, type, action, config}], one per trigger, in
    the order given. Same `do` vocabulary as an element event."""
    out = []
    for ev in specs or []:
        on = str(ev.get("on") or "load").strip().lower().replace("_", "").replace(" ", "")
        if on not in _FORM_EVENT_TYPE:
            raise UsageError(f"{ev.get('on')!r} is not a form-level event; use one of "
                             f"{sorted(_FORM_EVENT_TYPE)} (element triggers go on the element)")
        obj = {"id": _new_id(ctx), "type": _FORM_EVENT_TYPE[on]}
        obj.update(_trigger(ev, ctx))
        out.append(obj)
    return out


_HEADER = {"heading"}
# Elements whose options come from `sourceType` + `sourceValue`. The runtime builds an
# option from each item as {name: item.label or item.name, value: item.value}
# (ui-builder js/model/config/option.ts), and only when a source type is set.
_OPTION_KINDS = {"select", "radiobox"}
_FOOTER = {"button"}
_CLEAR_DEFAULT = ("placeholder", "tooltip", "info-text")  # reset golden leftovers


def _config_value(el: dict, key: str):
    return next((c.get("value") for c in el.get("configs", []) if c.get("key") == key), None)


# Controls whose field-source config is NOT named `value`. A file-viewer holds its file
# in `src` (the platform's own empty state for it reads "Field source not set"), and
# _VALUE_TYPE already types file-viewer as File — so without this the control gets a
# data-model attribute but no field path, and an outputMap row targeting it silently
# keeps the raw field name instead of resolving to a value path.
#
# Shared with the surgical event editor (handlers/form_events.py), which has to CHECK the
# same paths against a live form: one rule, one place. Two copies would be a rule nothing
# enforces, and a wrong value path is accepted by the platform without any error at all.
_VALUE_CONFIG_KEY = fieldpath.VALUE_CONFIG_KEY
_value_key = fieldpath.value_key


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
    field = spec.get("name") or _field_slug(spec.get("label") or kind)
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
        ctx.setdefault("field_paths", {})[field] = fieldpath.build(
            ctx["dm_root_id"], el["id"], vaid)
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
    if kind in _OPTION_KINDS and ctx.get("form_id"):
        # a Data Store read or a process can fill these options at run time: `rows` aimed
        # at the element writes its source (see _resolve_late_field_refs)
        src_val = next((c for c in configs if c.get("key") == "sourceValue"), None)
        src_type = next((c for c in configs if c.get("key") == "sourceType"), None)
        if src_val is not None and src_type is not None:
            ctx.setdefault("option_sources", {})[field] = (
                fieldpath.build(ctx["dm_root_id"], el["id"], src_val["id"]), src_type, src_val)
    _apply_events(spec, configs, ctx)
    _apply_element_style(spec, kind, configs, ctx)
    _apply_element_classes(spec, configs, ctx)
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
    name = spec.get("name") or _field_slug(spec.get("label") or "table")
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
    rowname = name + "row"
    # every table and row name, so a query's `rows` aimed at one that cannot take them
    # (a static table) is refused instead of being saved to a path that shows nothing
    is_dynamic = bool(spec.get("dynamic"))
    ctx.setdefault("table_rows", {}).update({name: is_dynamic, rowname: is_dynamic})
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
        source = next((c for c in rcfg if c.get("key") == "sourceValue"), None)
        if source and ctx.get("form_id"):
            path = fieldpath.build(ctx["dm_root_id"], row["id"], source["id"])
            ctx.setdefault("row_source_paths", {}).update({name: path, rowname: path})
    _set_config(configs, "rows", [rowname], ctx)
    return el


def _build_code(config: dict, ctx: dict) -> str:
    """Form-level CSS + JavaScript (the designer's 'Switch to code' editor) -> the
    encrypted `Data.code` blob. Accepts `css`/`javascript` (or a `code:{css,javascript}`
    object). Empty -> "" (forms render fine without it; verified live). The AES key comes
    from ctx['form_code_key'] (tests) or the key stored for the call's environment
    (form_code_keys: one per installation)."""
    code = config.get("code") if isinstance(config.get("code"), dict) else {}
    css = code.get("css", config.get("css"))
    js = code.get("javascript", config.get("javascript", config.get("js")))
    if not (css or js):
        return ""
    # the saved blob is encrypted, so a lint of the DTO cannot read it: check it here
    from tools.procesio import formlint
    for w in (formlint.lint_form_code_scope(css, js) + formlint.lint_form_code_runtime(css, js)
              + formlint.lint_form_code_sandbox(js)):
        _warn(ctx, w)
    key = ctx.get("form_code_key")
    if not key:
        # The key stored for THIS call's environment, never another installation's:
        # a blob encrypted with the wrong key blanks the form.
        from tools.procesio import form_code_keys
        key = form_code_keys.key_for(ctx.get("form_code_env"))
    from tools.procesio.dto.form import code_cipher
    return code_cipher.encrypt_code(js or "", css or "", key)


def _apply_theme(theme: list, overrides: dict) -> list:
    """Apply {cssVariable: value} overrides onto the shell theme (deep-copied). A group
    whose properties are {light, dark} (the Colors group, as the designer saves it) takes
    `theme` overrides on its light side; `themeDark` sets the dark side (_apply_dark)."""
    if not overrides:
        return theme
    theme = copy.deepcopy(theme)
    norm = _norm_vars(overrides)
    for section in theme or []:
        for prop in _group_props(section):
            cv = prop.get("cssVariable")
            if cv in norm:
                prop["value"] = norm[cv]
    return theme


def _norm_vars(overrides: dict) -> dict:
    return {(k if k.startswith("--") else f"--{k}"): v for k, v in (overrides or {}).items()}


def _group_props(group: dict, mode: str = "light") -> list:
    """A theme group's CSSProperty list; for a {light, dark} group, the `mode` side."""
    props = (group or {}).get("properties")
    if isinstance(props, dict):
        props = props.get(mode)
    return [p for p in props or [] if isinstance(p, dict)]


def _unknown_theme_vars(theme: list, overrides: dict) -> list:
    """Override keys the theme does not define: they would be dropped without a word."""
    known = {p.get("cssVariable") for g in theme or [] for p in _group_props(g)}
    return sorted(k for k in _norm_vars(overrides) if k not in known)


def _warn(ctx, message: str) -> None:
    """A non-blocking build finding. `ctx["_build_warnings"]` is a list the caller created
    before any copy of ctx was made, so every copy appends to the same one."""
    found = ctx.get("_build_warnings") if isinstance(ctx, dict) else None
    if isinstance(found, list) and message not in found:
        found.append(message)


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
    for group in theme_list or []:
        props = group.get("properties")
        if str(group.get("label", "")).strip().lower() == "colors" and isinstance(props, dict):
            # the shell already carries the designer's own dark palette: only the
            # caller's themeDark overrides change it
            norm = _norm_vars(overrides)
            for pr in props.get("dark") or []:
                if pr.get("cssVariable") in norm:
                    pr["value"] = norm[pr["cssVariable"]]
            return theme_list
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
# PROCESIO's generic Object type. A select's STATIC option list is a list of these in
# the data model (designer capture, 2026-10-01).
_OBJECT = "0317bfee-b2f5-4bde-bfe8-121212121221"
# A config of type `function` (stepper goToNextStep/goToPreviousStep, the side panel's
# open/close) is callable from form JS only when its data-model attribute has this type:
# the runtime builds the callable for dataTypeId FUNCTION and nothing else, so a function
# typed as a string throws "... is not a function". The designer also hides it
# (user-playground Form.model.ts, NonPrimitives.FUNCTION).
_FUNCTION = "1c2fd144-836e-419a-aa25-9e624a4c7e40"
_BOOL_CFG = {"visible", "readonly", "required", "submit", "multiple", "searchable",
             "clearable", "hasNow", "disabledIfFormIsInvalid", "canAdd", "canRemove",
             "outlined", "disabled",
             # document-signing toggles (the designer types a config by its value)
             "allowDecline", "setupEditable", "fieldsEditable"}
_INT_CFG = {"maxFileSize"}
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
# Configs that get NO data-model attribute. `sourceType` / `sourceValue` used to be here,
# grouped with the layout configs, but the designer writes both into the data model, and
# only data-model attributes reach `ProcesioForm` in form JS: with them skipped, a script
# on an API-built form could never read a select's options (measured live 2026-10-01;
# FORM-DEV-GUIDE/08, "A script reads a select's options and gets nothing").
_SKIP_DM_ATTR = {"options", "childrenIdPerColumn",
                 "tableColumnsSourceValue", "tableColumnsSourceType", "rows", "columns",
                 "tabs", "style",
                 # a document-signing element's design (exposed: false): the designer gives
                 # them no attribute, and the envelope is seeded from the saved form instead
                 "templateSigners", "templateSpots", "blockFields"}


def _attr_name(key: str) -> str:
    """Data-model attribute name = camelCase of the config key (PROCESIO compiles
    `info-text` -> `infoText`). Single-word keys pass through unchanged."""
    parts = str(key).split("-")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def _dm_attr(name, aid, type_id, parent, is_list=False):
    return {"id": aid, "name": name, "displayName": name, "dataTypeId": type_id,
            "isDataModel": False, "isList": is_list, "isProcesio": False,
            "isPublic": False, "parentDataTypeId": parent, "jsonProperty": None,
            "attributes": [], "hidden": type_id == _FUNCTION}


def _dm_shape(el: dict, c: dict) -> tuple[str, bool] | None:
    """(dataTypeId, isList) of the data-model attribute one element config gets, or None
    when it gets none. Shared by form-create and form-add-element, so the two can never
    disagree about what the designer would write.

    `sourceValue` follows a designer capture: a STATIC option list is a list of Objects.
    A JSON or URL source has not been captured from the designer, so its `sourceValue`
    stays out rather than be given a guessed type. `sourceType` is a plain string."""
    k = c.get("key")
    if not k or k.endswith("Events") or k in _SKIP_DM_ATTR:
        return None
    if k == "sourceValue":
        if el.get("type") == "dynamic-table-row":
            return _OBJECT, True   # designer capture: present on every dynamic row, set or not
        return (_OBJECT, True) if isinstance(c.get("value"), list) else None
    vkey = _value_key(el.get("type"))
    if k == vkey:
        return _VALUE_TYPE.get(el.get("type"), _STR), _value_is_list(el)
    if c.get("type") == "function":
        return _FUNCTION, False
    return (_BOOL if k in _BOOL_CFG else _INT if k in _INT_CFG else _STR), False


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
            shape = _dm_shape(el, c)
            if shape is None:
                continue
            # The data-model attribute id MUST equal the element's config id for that
            # key (verified against real forms: every fields sub-model attr id == the
            # element's config id; 15/16 in OMS vs 0/16 with fresh ids -> "Unknown" in
            # the trigger-map UI). Reuse the config's own id.
            aid = c.get("id") or _new_id(ctx)
            sub["attributes"].append(
                _dm_attr(_attr_name(c["key"]), aid, shape[0], eid, shape[1]))
        submodels.append(sub)
    fields["attributes"] = submodels
    # Every top-level attribute (instance, flow, fields, preventFormSubmit, browserTitle — the
    # set the designer's generateFormDataModel writes) hangs off the root.
    for a in attrs:
        a["parentDataTypeId"] = form_id
    return dm


# The designer writes "1" for a form it creates (user-playground Builder.component.vue: a new
# form gets FormDataModelAttributeFormatVersion.VERSION_1 = "same attribute as name"). A form
# with NO version is read as the legacy "0" format, and the designer's next save lower-cases
# every field attribute (measured on QA 2026-09-25: `RequestText` -> `requesttext`), which
# breaks any form script that addresses the field by its real name. This builder names field
# attributes exactly as the element name, i.e. format "1", so it must say so.
_DM_FORMAT_VERSION = "1"

# Who works a step and who approves it, read the way the designer does before it saves
# (ui-builder form-builder/assignee::getElementAssignees and approval::getElementApprovers).
_ASSIGNEE_KEYS = ("assignee", "assigneeReplacement", "additionalAssignment")
_APPROVER_KEYS = ("approver", "approverReplacement", "additionalApprovers")
_ASSIGNEE, _APPROVER = 1, 2


def _unique_ids(values) -> list:
    users: list = []
    for uid in values:
        if isinstance(uid, str) and uid.strip() and uid not in users:
            users.append(uid)
    return users


def _step_users(el: dict, keys: tuple) -> list:
    values: list = []
    for key in keys:
        value = _config_value(el, key)
        values.extend(value if isinstance(value, list) else [value])
    return _unique_ids(values)


def _hidden_by_config(el: dict) -> bool:
    # ui-builder elementAvailability::isElementHiddenByConfig: hidden only when `visible` is
    # present and falsy.
    visible = next((c.get("value") for c in el.get("configs", []) if c.get("key") == "visible"),
                   None)
    return any(c.get("key") == "visible" for c in el.get("configs", [])) and not visible


def _approver_steps(el: dict, by_id: dict) -> list:
    """[(stepId, users)] for one element, as ui-builder approval::getElementApproversByStepId.

    A dynamic table row does not approve as itself: each entry of its `approvalSteps` with a
    `rowIndex` is its own step (id = the step id, users = approver + approverReplacement), and
    only while the row sits in a table and is not hidden (model/config/table/approvals.ts::
    getDynamicRowApprovalSteps). Every other element is one step under its own id.
    """
    if el.get("type") != "dynamic-table-row":
        return [(el["id"], _step_users(el, _APPROVER_KEYS))]
    parent = by_id.get(el.get("parentId"))
    if not parent or parent.get("type") != "table" or _hidden_by_config(el):
        return []
    steps = _config_value(el, "approvalSteps") or []
    out = []
    for step in steps if isinstance(steps, list) else []:
        if not isinstance(step, dict) or step.get("rowIndex") is None or not step.get("id"):
            continue
        replacement = step.get("approverReplacement") or []
        out.append((step["id"], _unique_ids([step.get("approver"), *replacement])))
    return out


def derive_assignees(elements: list) -> list:
    """The form's top-level `Assignees`, built like the designer's save.

    ASSIGNEE (1) steps first, then APPROVER (2) steps, `orderId` counting 1, 2, 3 within each
    list, a step only when it has users, each step id once, users sent as `{userId}` only (the
    platform fills in the names). Mirrors ui-builder utils/formBuilder/payload.ts::
    getFormBuilderUsersFullData and user-playground Builder.component.vue::save. Checked against
    19 designer-saved forms on QA (2026-10-05), dynamic-row approvals included: identical.
    The designer also drops users who are not in the workspace; that needs a live lookup and is
    not done here.
    """
    by_id = {e.get("id"): e for e in elements}
    out: list = []
    for kind in (_ASSIGNEE, _APPROVER):
        order, seen = 0, set()
        for el in elements:
            steps = ([(el["id"], _step_users(el, _ASSIGNEE_KEYS))] if kind == _ASSIGNEE
                     else _approver_steps(el, by_id))
            for step_id, users in steps:
                if not users or step_id in seen:
                    continue
                seen.add(step_id)
                order += 1
                out.append({"stepId": step_id, "orderId": order, "type": kind,
                            "users": [{"userId": u} for u in users]})
    return out


def _assignee_key(rows) -> list:
    """Assignees compared by what routes a step (names and key casing ignored)."""
    out = []
    for r in rows or []:
        g = {str(k).lower(): v for k, v in r.items()}
        users = [str({str(k).lower(): v for k, v in u.items()}.get("userid")) for u in g.get("users") or []]
        out.append((str(g.get("stepid")), int(g.get("orderid") or 0), int(g.get("type") or 0), tuple(users)))
    return out


def reconcile_assignees(current: list, before: list, after: list) -> tuple[list, dict | None]:
    """(the Assignees to save, a report or None) for a surgical change from `before` to `after`
    elements.

    The designer re-derives the list on every save, so a surgical edit that echoes the old list
    leaves a removed approver still routed, or a new approval control unrouted. Only a change
    that alters the derived routing re-derives it, and then the WHOLE list is saved as the
    designer would save it; any other edit keeps `current` byte-for-byte, so it never rewrites
    routing it did not touch."""
    derived = derive_assignees(after)
    if _assignee_key(derive_assignees(before)) == _assignee_key(derived):
        return current, None
    return derived, {"rederived": True, "before": _assignee_key(current),
                     "after": _assignee_key(derived)}


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
    # Created here, not with setdefault where a table is built: a table inside a section,
    # column or tab is built with a COPY of ctx, and a dict first created on the copy is
    # lost, so the query wiring would never see that table.
    ctx["row_source_paths"] = {}
    ctx["table_rows"] = {}
    ctx["option_sources"] = {}
    # The PUT replaces the whole template, so a save without `Queries` deletes them. A
    # config that lists `queries` decides them; one that does not keeps whatever the edit
    # read from the live form, and a create sends none.
    if "queries" in config:
        queries = [form_queries.from_config(q, lambda: _new_id(ctx)) for q in config["queries"] or []]
        form_queries.check(queries)
    else:
        queries = ctx.get("live_queries") or None
    ctx["queries"] = queries or []
    elements: list = []
    for e in config.get("elements", []):
        _build_element(e, ctx, elements)
    # The form's own triggers (onLoad, before / after submit). A config that lists `events`
    # decides them; one that does not keeps the live form's (an edit) or the shell's (a
    # create), because the PUT replaces the whole template and would drop them.
    if "events" in config:
        form_events = _form_events(config["events"], ctx)
    elif ctx.get("live_events") is not None:
        # the rebuild gives every element a new id: point the kept events at them
        form_events = _remap_live_events(ctx["live_events"], ctx.get("live_elements"),
                                         elements, ctx)
    else:
        form_events = shell.get("events", [])
    _resolve_late_field_refs(elements, ctx, form_events)
    data = {
        "code": _build_code(config, ctx),
        "theme": _apply_theme(shell.get("theme"), config.get("theme")),
        "events": form_events,
        "images": shell.get("images", {"logo": None, "header": None}),
        "elements": elements,
        "messages": shell.get("messages"),
        "dataModel": _build_data_model(ctx["dm_root_id"], elements, ctx),
        "variables": shell.get("variables"),
        "browserTitle": config.get("browserTitle", config["name"]),
        "hideBranding": bool(config.get("hideBranding", False)),
        "dataModelAttributeFormatVersion": _DM_FORMAT_VERSION,
    }
    if config.get("chainConfig") is not None:
        data["chainConfig"] = config["chainConfig"]
    # Dark theme: the dark palette is persisted INSIDE the single `theme` array, as the
    # COLORS group's {light, dark} ModeProperties. The shell theme is the designer's own
    # getDefaultTheme() (sync_theme.py), which carries both sides on every form, as a form
    # saved in the designer does; `themeDark` overrides the dark side. themeMode is
    # editor-only and never saved. An older flat shell still gets the opt-in conversion.
    if config.get("dark") or config.get("themeDark") is not None or config.get("themeMode") == "dark":
        data["theme"] = _apply_dark(data["theme"], config.get("themeDark"))
    for key, label in (("theme", "theme"), ("themeDark", "themeDark")):
        unknown = _unknown_theme_vars(shell.get("theme"), config.get(key))
        if unknown:
            _warn(ctx, f"{label} sets {', '.join(unknown)}, which the form theme does not define, "
                       f"so the form ignores {'it' if len(unknown) == 1 else 'them'}. The theme "
                       f"follows the designer's ui-builder (dto/form/theme_source.json).")
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
    # An explicit `assignees` list still wins verbatim; otherwise derive it the way the
    # designer's save does, so an approver actually receives the approval step.
    assignees = config["assignees"] if "assignees" in config else derive_assignees(elements)
    # The designer saves a form that involves users as a USER_TASK. Only fill the gap when
    # the caller did not choose a type.
    if "type" in config:
        ftype = config["type"]
    else:
        involves_users = bool(assignees) or any(e.get("type") == "assignee" for e in elements)
        ftype = "usertask" if involves_users else "general"
    dto = {
        "Id": ctx["form_id"],
        "Name": config["name"],
        "IsPrivate": bool(config.get("isPrivate", False)),
        "Type": _FORM_TYPE.get(str(ftype).strip().lower(), ftype),
        "Status": 1 if config.get("publish", True) else 0,
        "State": bool(config.get("enabled", True)),
        "Assignees": assignees,
        "Data": data,
        "CustomUrl": None,
    }
    if queries is not None:
        dto["Queries"] = queries
    return dto


def _collect_process_ids_config(config: dict, out: set) -> None:
    """Every process a RUN_PROCESS event names, on the elements and on the form itself."""
    _collect_process_ids(config.get("elements"), out)
    _collect_process_ids([{"events": config.get("events") or []}], out)


def _collect_process_ids(elements: list, out: set) -> None:
    for e in elements or []:
        for ev in e.get("events") or []:
            if (ev.get("do") or "").strip().lower() in ("process", "run_process") and ev.get("processId"):
                out.add(ev["processId"])
        _collect_process_ids(e.get("children"), out)
        for col in e.get("columns") or []:
            if col.get("cell"):
                _collect_process_ids([col["cell"]], out)


def _collect_write_stores(elements: list, out: set) -> None:
    """Every Data Store an ADD / UPDATE / DELETE event writes, on elements (with their
    children and table cells) and on the form itself."""
    for e in elements or []:
        for ev in e.get("events") or []:
            if (str(ev.get("do") or "").lower() in ("datastore", "data_store", "run_data_store_operation",
                                                     "run_data_store")
                    and str(ev.get("operation") or "").upper() in _DS_WRITES
                    and ev.get("dataStoreId")):
                out.add(ev["dataStoreId"])
        _collect_write_stores(e.get("children"), out)
        _collect_write_stores([c["cell"] for c in e.get("columns") or [] if c.get("cell")], out)


def _store_columns(client, store_id: str) -> dict:
    """{names, pk}: the store's own columns (display names) and its primary key."""
    try:
        body = client.get(f"/api/DataStore/{store_id}")
    except Exception as e:  # noqa: BLE001
        raise UsageError(f"a Data Store event writes store {store_id!r}, which could not be "
                         f"read ({e}); check the dataStoreId.")
    if isinstance(body, dict) and isinstance(body.get("result"), dict):
        body = body["result"]
    cols = [c for c in (body.get("columns") or []) if isinstance(c, dict) and not c.get("isSystemColumn")]
    return {"names": [c.get("name") for c in cols],
            "pk": [c.get("name") for c in cols if c.get("isPrimaryKey")]}


def _prepare_ctx(client, config: dict) -> dict:
    """Impure pre-build step (has the live client): resolve every process referenced by a
    RUN_PROCESS event to its variable name->id map, so the builder can wire inputMap/
    outputMap by GUID (the backend rejects variable names). Fail loud on a bad processId.
    Also records the call's environment, which decides the form-code-key."""
    env = getattr(client, "env", None)
    ctx: dict = {"form_code_env": env.get("name") if isinstance(env, dict) else None}
    stores: set = set()
    _collect_write_stores([*(config.get("elements") or []),
                           {"events": config.get("events") or []}], stores)
    if stores:
        ctx["ds_columns"] = {sid: _store_columns(client, sid) for sid in sorted(stores)}
    pids: set = set()
    _collect_process_ids_config(config, pids)
    if not pids:
        return ctx
    pvars: dict = {}
    for pid in pids:
        try:
            body = client.get(f"/api/Projects/{pid}", VARIABLES_ONLY)
        except Exception as e:  # noqa: BLE001
            raise UsageError(f"RUN_PROCESS references process {pid!r} which could not be "
                             f"fetched ({e}); check the processId.")
        if isinstance(body, dict) and "flow" not in body and isinstance(body.get("result"), dict):
            body = body["result"]
        flow = body.get("flow") if isinstance(body, dict) else None
        src = flow if isinstance(flow, dict) else (body if isinstance(body, dict) else {})
        variables = src.get("variables") or []
        pvars[pid] = {v.get("name"): v.get("id") for v in variables if v.get("name")}
    ctx["process_vars"] = pvars
    return ctx


def _extract_id(resp, dto):
    if isinstance(resp, dict) and (resp.get("id") or resp.get("Id")):
        return resp.get("id") or resp.get("Id")
    if isinstance(resp, str) and resp.strip():
        return resp.strip().strip('"')
    return dto.get("Id") if isinstance(dto, dict) else None


def _live_form(client, resource_id) -> dict:
    body = client.get(f"/api/FormTemplate/{resource_id}")
    if isinstance(body, dict) and isinstance(body.get("result"), dict):
        body = body["result"]
    if not isinstance(body, dict) or "data" not in body:
        raise UsageError(f"could not read form {resource_id!r} to keep its saved queries "
                         f"and form events; nothing was written")
    return body


def _edit_ctx(client, resource_id, config, ctx):
    """What an edit carries over from the LIVE form: its saved queries and its own events
    (onLoad, before / after submit), each unless the config lists it. Shared with the
    dry-run preview."""
    ctx = dict(ctx)
    ctx["form_id"] = resource_id
    if "queries" not in config or "events" not in config:
        live = _live_form(client, resource_id)
        if "queries" not in config:
            ctx["live_queries"] = live.get("queries") or []
        if "events" not in config:
            ctx["live_events"] = (live.get("data") or {}).get("events") or []
            ctx["live_elements"] = (live.get("data") or {}).get("elements") or []
    return ctx


def _edit(client, resource_id, config, ctx):
    dto = build(config, _edit_ctx(client, resource_id, config, ctx))
    client.put("/api/FormTemplate", dto)
    ctx["_sent_dto"] = dto   # for persist_check on the read-back
    return client.get(f"/api/FormTemplate/{resource_id}")


def _persist_check(dto, stored) -> list[str]:
    """Saved queries the save accepted and did not keep. A build without the saved-query
    feature ignores `Queries` and answers 200, so the form exists while every QUERY event
    points at a query that is not there."""
    sent = (dto or {}).get("Queries") if isinstance(dto, dict) else None
    if not sent:
        return []
    body = stored.get("result") if isinstance(stored, dict) and isinstance(
        stored.get("result"), dict) else stored
    if not isinstance(body, dict):
        return []
    kept = {str(q.get("id") or "").lower() for q in body.get("queries") or [] if isinstance(q, dict)}
    lost = [q.get("name") for q in sent if str(q.get("id") or "").lower() not in kept]
    if not lost:
        return []
    why = ("this environment returns no `queries` at all, so its build does not have saved "
           "form queries yet (they need Web-Api v3.3.0, form-runtime v1.34.0 and "
           "user-playground v1.117.0; `server-build` reads the Web-Api version)"
           if "queries" not in body else "another save may have replaced them")
    return [f"the form was saved but the server did not keep its saved queries "
            f"{', '.join(map(repr, lost))}: {why}. Every QUERY event on the form points at a "
            f"query that does not exist."]


def _lint(resource) -> list[str]:
    """Non-blocking formlint warnings for a built DTO (`Data`) or a fetched form (`data`)."""
    from tools.procesio import formlint
    if not isinstance(resource, dict):
        return []
    data = resource.get("Data") or resource.get("data")
    queries = resource.get("Queries") or resource.get("queries")
    elements = data.get("elements") if isinstance(data, dict) else []
    events = data.get("events") if isinstance(data, dict) else []
    out = formlint.lint_form_data(data) + form_queries.warnings(queries, elements, events)
    status = resource.get("Status", resource.get("status"))
    if status == 0:
        out.append("the form is a draft (status 0, what a Save in the designer leaves): it is "
                   "not reachable by its link, which answers \"Form not found\", until it is "
                   "published (Publish in the designer, or a form-edit / form-create with "
                   "publish left on)")
    return out


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
    edit_ctx=_edit_ctx,
    persist_check=_persist_check,
    patch_action="form-update",
    add_action="form-add-element",
    lint=_lint,
)
