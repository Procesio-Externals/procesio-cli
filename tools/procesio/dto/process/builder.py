"""Process (Flow) builder — data-driven from the action catalog.

config -> FlowRequestDto (POST /api/Projects). Verified live: a built flow passes
POST /api/Projects/validate, persists with the client-supplied Id, and runs to
STATUS_FINISH with output variables populated.

Design:
  * variables    -> VariableDto[]  (INPUT/PROCESS/OUTPUT, primitive or model type, isList)
  * actions      -> ActionDto[]    (any catalog template by name; Start/Stop auto-injected)
  * params       -> ParametersDto[] bound to the template's properties (TabPropertyId),
                    as a literal Value, a variable ref ("<%0%>" + Variable[]), a variable
                    with an attribute path, or a multi-var template.
  * edges        -> PortDto[]       (explicit branching, or implicit linear chain)

The action template structure (property ids/labels) comes from ctx["catalog"] —
the live workspace catalog (custom/connector actions included), with the bundled
snapshot as the offline default. The build step itself is PURE.
"""
from __future__ import annotations

import copy
import json
import re
import uuid
from functools import lru_cache
from pathlib import Path

from tools.procesio.dto import refdata
from tools.procesio.dto.framework import Component
from tools.procesio.dto.process import naming
from tools.procesio.errors import UsageError

DIR = Path(__file__).resolve().parent
_CATALOG = DIR.parent / "data" / "action_catalog.json"

START_TEMPLATE = "c0e32108-6e3e-4ab8-96bd-cd61be6edb33"
STOP_TEMPLATE = "c0e32108-6e3e-4ab8-96bd-cd61be6edb34"
JOIN_TEMPLATE = "fb6a9d14-dd15-420d-a2b2-fc637c0c37c6"   # flow-control Join (inputPorts=-1)
NULL_GUID = "00000000-0000-0000-0000-000000000000"
_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ERROR_MODEL = "10c6ac59-3929-49e6-99dc-121212121220"    # ErrorDataModel (error-port variable type)
_DIRECTION = {"input": 10, "process": 20, "output": 30}
# actions that have NO error port (per PROCESIO) — onError is rejected on these
_NO_ERROR_PORT = {"start", "stop", "join", "for each", "foreach"}
# Some action names are ambiguous (a versioned/list variant shares the name). For
# the flow-control actions the exact template matters (Join's inputPorts=-1 lets
# branches converge), so pin them by id; everything else resolves by name/id.
_CONTROL_TEMPLATE = {"start": START_TEMPLATE, "stop": STOP_TEMPLATE, "join": JOIN_TEMPLATE}

# Superseded/frozen action versions -> (latest replacement, migration hint).
# PROCESIO keeps frozen version pins (e.g. "Call API v3") in the catalog next to
# the live/latest action ("Call API"); referencing a pin silently builds on an
# OLD generation (different output props, missing features). The builder BLOCKS a
# superseded ref with an actionable message so a build can't quietly regress —
# pass --force (ctx["_force"]) to pin one intentionally. "Unversioned = latest" is
# NOT a universal rule (e.g. Read Mailbox V2 > Read Mailbox), so this is a CURATED
# map, not a heuristic; extend it as PROCESIO deprecates actions (source of truth:
# the live "To be decommissioned" palette folder + /api/Actions). See
# dto/process/description.md "Call API version" gotcha.
SUPERSEDED_ACTIONS = {
    "call api v1": ("Call API", "outputs are Response Status / Response Body / Response Headers / Response File"),
    "call api v2": ("Call API", "outputs are Response Status / Response Body / Response Headers / Response File"),
    "call api v3": ("Call API", "rename output params Status Output -> Response Status, Body Output -> Response Body"),
    "execute query v1": ("Execute Query", "bind SQL via @params (config map), not inline <%N%>"),
    "execute query v2": ("Execute Query", "bind SQL via @params (config map), not inline <%N%>"),
    "execute command v1": ("Execute Command", ""),
}


def _new_id(ctx) -> str:
    return (ctx.get("new_id") or (lambda: str(uuid.uuid4())))()


# -- catalog ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _bundled_catalog() -> list[dict]:
    return json.loads(_CATALOG.read_text(encoding="utf-8")).get("actions", [])


def catalog_index(extra: list[dict] | None = None) -> dict:
    """name(lower)->template and actionId->template. `extra` (a live catalog) wins."""
    idx: dict[str, dict] = {}
    for a in _bundled_catalog():
        idx[(a.get("name") or "").strip().lower()] = a
        if a.get("actionId"):
            idx[a["actionId"]] = a
    for a in (extra or []):
        idx[(a.get("name") or "").strip().lower()] = a
        if a.get("actionId"):
            idx[a["actionId"]] = a
    return idx


def _resolve_template(ref: str, ctx: dict) -> dict:
    idx = ctx.get("catalog") or catalog_index()
    key = (ref or "").strip().lower()
    sup = SUPERSEDED_ACTIONS.get(key)
    if sup and not ctx.get("_force"):                    # block frozen version pins
        latest, hint = sup
        raise UsageError(
            f"action {ref!r} is a superseded/frozen version — use {latest!r} (the "
            f"live/latest action)" + (f"; {hint}" if hint else "") +
            ". Pass --force to pin the old version intentionally.")
    if key in _CONTROL_TEMPLATE:                         # pin ambiguous control actions
        t = idx.get(_CONTROL_TEMPLATE[key])
        if t:
            return t
    t = idx.get(key) or idx.get(ref)
    if not t:
        raise UsageError(f"unknown action {ref!r} — not in the action catalog")
    return t


def _property_index(template: dict) -> dict:
    """label(lower)->property and id->property, across all tabs (recursing into
    side-pannel nested sub-properties whose `value` holds child settings)."""
    out: dict[str, dict] = {}

    def walk(settings):
        for s in settings or []:
            if s.get("label"):
                out.setdefault(s["label"].strip().lower(), s)
            if s.get("id"):
                out[s["id"]] = s
            val = s.get("value")
            if isinstance(val, list):                  # side-pannel nested props
                walk(val)
    for tab in template.get("configuration", []):
        walk(tab.get("settings", []))
    return out


# -- parameter binding --------------------------------------------------------

_GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _attr_chain(path, model_id, ctx: dict):
    """A VariableAttributeDto chain {attributeId, nextAttribute} from a list of attribute names.

    `attributeId` is parsed as a Guid by the API, so a NAME written there is not a soft failure —
    the whole save is rejected. Each step is resolved against the model the previous step lands in
    (`ctx['model_attrs']`, filled by prepare_ctx), which is also what lets a nested path work.

    A value that already looks like a Guid passes straight through, so a caller who knows the
    attribute id never needs the model resolved. When the model is unknown (offline, or an untyped
    variable) the name passes through unchanged, preserving the old behaviour rather than
    inventing an id.
    """
    if not path:
        return None
    head, *rest = path
    key = str(head).strip()
    attrs = (ctx.get("model_attrs") or {}).get(model_id) if model_id else None

    if attrs is None or _GUID_RE.match(key):
        return {"attributeId": key, "nextAttribute": _attr_chain(rest, None, ctx)}

    found = attrs.get(key.lower())
    if found is None:
        known = ", ".join(sorted(a.get("name", k) for k, a in attrs.items())) or "(none)"
        raise UsageError(
            f"attribute {head!r} is not on this variable's data model. Known attributes: {known}")
    return {"attributeId": found["id"],
            "nextAttribute": _attr_chain(rest, found.get("dataTypeId"), ctx)}


def _model_of(ctx: dict, var_name) -> str | None:
    """The data-model id of a bound variable, so its attribute path can be resolved."""
    return (ctx.get("var_models") or {}).get(str(var_name).strip().lower())


def _make_parameter(prop_id: str, binding, ctx: dict, counter: list | None = None) -> dict:
    """Build one ParametersDto. Binding forms:
       literal scalar | {"value": x} -> Value=x, Variable=[]
       {"var": name[, "path": [...]]} -> Value="<%N%>", Variable=[{N, varId, attr}]
       {"template": "..<%0%>..<%1%>..", "vars": [name, ...]} -> multi-var
    `counter` is a per-ACTION global index ([next]); the <%N%> ids are unique
    across all of an action's parameters so actions that reuse one property id for
    several params (Javascript Code+Output, Decisional Cases+Default) don't collide.
    """
    var_ids = ctx.get("var_ids", {})
    counter = counter if counter is not None else [0]

    def resolve_var(name):
        vid = var_ids.get(str(name).strip().lower())
        if not vid:
            raise UsageError(f"parameter binds unknown variable {name!r}")
        return vid

    def take():
        i = counter[0]
        counter[0] += 1
        return i

    variable = []
    if isinstance(binding, dict) and "var" in binding:
        attr = _attr_chain(binding.get("path"), _model_of(ctx, binding["var"]), ctx)
        idx = take()
        variable = [{"id": idx, "variableId": resolve_var(binding["var"]), "attribute": attr}]
        value = f"<%{idx}%>"
    elif isinstance(binding, dict) and "template" in binding:
        # remap the template's local <%i%> -> a global index unique to the action
        local_to_global: dict[int, int] = {}
        for i, nm in enumerate(binding.get("vars", [])):
            g = take()
            local_to_global[i] = g
            if isinstance(nm, dict):                     # {"var": name, "path": [...]} attr ref
                attr = _attr_chain(nm.get("path"), _model_of(ctx, nm["var"]), ctx)
                variable.append({"id": g, "variableId": resolve_var(nm["var"]),
                                 "attribute": attr})
            else:
                variable.append({"id": g, "variableId": resolve_var(nm), "attribute": None})
        def _remap(t):                                # remap <%i%> in str/list/dict leaves
            if isinstance(t, str):
                return re.sub(r"<%(\d+)%>",
                              lambda m: f"<%{local_to_global.get(int(m.group(1)), m.group(1))}%>", t)
            if isinstance(t, list):
                return [_remap(x) for x in t]
            if isinstance(t, dict):
                return {k: _remap(v) for k, v in t.items()}
            return t
        value = _remap(binding["template"])
    elif isinstance(binding, dict) and "credential" in binding:
        # a credential reference: Value = the credential INSTANCE gid; the action's
        # credentialsTemplateId (the credential TYPE) is already in the template config.
        gid = binding["credential"]
        if not _GUID_RE.match(str(gid or "")):
            raise UsageError(
                f"credential binding must be a credential instance GUID, got {gid!r}")
        value = gid
    elif isinstance(binding, dict) and "value" in binding:
        value = binding["value"]
    else:
        value = binding                                 # bare literal
    return {"TabPropertyId": prop_id, "Variable": variable, "Value": value}


def _operand(spec, var_ids: dict, counter: list, ctx: dict) -> dict:
    """A decisional operand {value, variable}. A var operand -> value '<%N%>' with
    the variable recorded; a literal -> value=literal, variable=[]."""
    if isinstance(spec, dict) and "var" in spec:
        vid = var_ids.get(spec["var"].strip().lower())
        if not vid:
            raise UsageError(f"condition references unknown variable {spec['var']!r}")
        idx = counter[0]
        counter[0] += 1
        attr = _attr_chain(spec.get("path"), _model_of(ctx, spec.get("var")), ctx)
        return {"value": f"<%{idx}%>",
                "variable": [{"id": idx, "variableId": vid, "attribute": attr}]}
    val = spec.get("value") if isinstance(spec, dict) else spec
    return {"value": val, "variable": []}


_LOGIC = {"and": 1, "or": 0}


def _build_decisional(template: dict, spec: dict, node_id: dict, var_ids: dict, ctx: dict):
    """Build the Cases + Default ParametersDto and the branch PortDto list for a
    Decisional / AI Decisional action. Returns (params, ports). For AI Decisional a
    case `condition` is a natural-language STRING (not an operator tree)."""
    pidx = _property_index(template)
    cases_prop = pidx["cases"]
    cases_pid = cases_prop["id"]
    is_ai = cases_prop.get("type") == "ai-decisional-case"
    default_pid = pidx["default"]["id"]
    branches = spec["branches"]
    counter = [0]                       # shared <%N%> index across all conditions
    all_vars: list = []
    cases = []
    ports = []
    ai_meta: list = []                  # designer name/internalId per case (AI only)
    dec_meta: list = []                 # designer name per case (rule-based Decisional)
    default_target = None
    src = node_id[spec["id"]]
    for i, br in enumerate(b for b in branches if not b.get("default")):
        to = br["to"]
        if to not in node_id:
            raise UsageError(f"branch target {to!r} is not an action id")
        if is_ai:
            cond = br.get("condition")
            if not isinstance(cond, str) or not cond.strip():
                raise UsageError(
                    f"AI Decisional case -> {to!r} needs a natural-language 'condition' string")
            cases.append({"id": i, "actionid": node_id[to], "condition": cond})
            ai_meta.append({"id": i,
                            "name": br.get("name") or naming.derive_branch_name(br, True) or f"Case {i + 1}",
                            "internalId": _new_id(ctx)})
        else:
            conds = []
            for j, cnd in enumerate(br.get("when", [])):
                left = _operand(cnd.get("left"), var_ids, counter, ctx)
                right = _operand(cnd.get("right", ""), var_ids, counter, ctx)
                all_vars.extend(left["variable"]); all_vars.extend(right["variable"])
                conds.append({"id": j, "operator": cnd["op"],
                              "logicOperator": _LOGIC.get(str(cnd.get("logic", "and")).lower(), 1),
                              "leftOperator": left, "rightOperator": right, "auxOperator": None})
            cases.append({"id": i, "actionid": node_id[to], "condition": conds})
            dec_meta.append({"id": i,
                             "name": br.get("name") or naming.derive_branch_name(br, False) or f"Case {i + 1}"})
        ports.append(_port(src, node_id[to], ctx))
    for br in branches:
        if br.get("default"):
            default_target = node_id[br["to"]]
            ports.append(_port(src, node_id[br["to"]], ctx, {"Data": {"isDefault": "default"}}))
    if is_ai:
        ctx.setdefault("_ai_case_meta", {})[src] = ai_meta
    else:
        ctx.setdefault("_dec_case_meta", {})[src] = dec_meta
    params = [
        {"TabPropertyId": cases_pid, "Variable": all_vars, "Value": cases},
        {"TabPropertyId": default_pid, "Variable": [], "Value": default_target},
    ]
    return params, ports


def _doc_mapper_property(template: dict) -> dict | None:
    for tab in template.get("configuration", []):
        for s in tab.get("settings", []):
            if isinstance(s.get("value"), list):
                for sub in s["value"]:
                    if sub.get("type") == "document-mapper":
                        return sub
    return None


def _build_doc_mapper(template: dict, doc_map: dict, doc_vars: dict, var_ids: dict,
                      ctx: dict, counter: list) -> dict | None:
    """Build the Map Document Data (document-mapper) parameter: map each document
    template variable -> a process variable. doc_map = {docVarName: procVarName | {var:...}}."""
    prop = _doc_mapper_property(template)
    if prop is None:
        raise UsageError("this action has no document-mapper property")
    rows = []
    for i, (doc_var, binding) in enumerate(doc_map.items()):
        doc_id = doc_vars.get(doc_var.strip().lower()) or doc_var
        dst_idx = counter[0]
        counter[0] += 1
        destination = {"id": dst_idx, "variableId": doc_id, "attribute": None}
        src = _operand(binding if isinstance(binding, dict) else {"var": binding},
                       var_ids, counter, ctx)
        rows.append({"id": i, "source": src, "destination": destination})
    # source/destination carry their variables inline; the param-level Variable is empty
    return {"TabPropertyId": prop["id"], "Variable": [], "Value": rows}


# -- Data Store node: Set Values (data-store-mapper) + Where (data-store-decisional) --
# The Set Values row reuses the document-mapper source operand but names its target
# `column` (resolved by NAME). The Where value is a DataStoreQueryFilterGroupDto -- the
# filter tree shared verbatim with Process-Execution (Domain/Enums/DataStore/Filter).
_DS_OPERATORS = {
    "equals": "EQUALS", "eq": "EQUALS", "==": "EQUALS",
    "notequals": "DOES_NOT_EQUAL", "ne": "DOES_NOT_EQUAL", "!=": "DOES_NOT_EQUAL",
    "contains": "CONTAINS", "notcontains": "DOES_NOT_CONTAIN",
    "doesnotcontain": "DOES_NOT_CONTAIN",
    "greaterthan": "GREATER_THAN", "gt": "GREATER_THAN",
    "greaterthanorequal": "GREATER_THAN_OR_EQUAL_TO", "gte": "GREATER_THAN_OR_EQUAL_TO",
    "lessthan": "LESS_THAN", "lt": "LESS_THAN",
    "lessthanorequal": "LESS_THAN_OR_EQUAL_TO", "lte": "LESS_THAN_OR_EQUAL_TO",
    "istrue": "IS_TRUE", "isfalse": "IS_FALSE",
    "isempty": "IS_EMPTY", "isnotempty": "IS_NOT_EMPTY",
    "belongs": "BELONGS", "notbelongs": "DOES_NOT_BELONG", "doesnotbelong": "DOES_NOT_BELONG",
}
_DS_LOGIC = {"and": 1, "or": 2}


def _ds_side_property(template: dict, wanted_type: str) -> dict | None:
    """Find a Data Store side-panel child setting by its control `type`."""
    for tab in template.get("configuration", []):
        for s in tab.get("settings", []):
            if s.get("type") == wanted_type:
                return s
            if isinstance(s.get("value"), list):
                for sub in s["value"]:
                    if sub.get("type") == wanted_type:
                        return sub
    return None


def _ds_resolve_operator(raw) -> str:
    if isinstance(raw, bool):
        raise UsageError("Data Store Where operator must be an operator name")
    key = str(raw).strip().lower().replace("_", "").replace(" ", "")
    if key in _DS_OPERATORS:
        return _DS_OPERATORS[key]
    up = str(raw).strip().upper()
    if up in set(_DS_OPERATORS.values()):        # already a decisional token
        return up
    raise UsageError(f"unknown Data Store Where operator {raw!r}; known: "
                     f"{', '.join(sorted(_DS_OPERATORS))}")


def _build_ds_mapper(template: dict, ds_map: dict, var_ids: dict, ctx: dict, counter: list) -> dict:
    """Data Store `Set Values` (data-store-mapper) for InsertRows/UpdateRows: each entry
    maps a COLUMN NAME -> a value binding. Runtime row {id, source:{value,variable}, column}.
    A bare string/number binding is a LITERAL value (unlike docMap, where bare = variable)."""
    prop = _ds_side_property(template, "data-store-mapper")
    if prop is None:
        raise UsageError("this action has no data-store-mapper property "
                         "(Set Values renders only for a Data Store Insert/Update)")
    rows = []
    for i, (col, binding) in enumerate(ds_map.items()):
        rows.append({"id": i, "source": _operand(binding, var_ids, counter, ctx), "column": col})
    return {"TabPropertyId": prop["id"], "Variable": [], "Value": rows}


def _ds_mapper_config(rows):
    """data-store-mapper designer rows -- the shape PROCESIO's designer actually stores:
    {id, left:<columnName>, right:<varId|literal>} (verified against a live export)."""
    out = []
    for r in rows or []:
        src = r.get("source") or {}
        right = _ref_from_variable(src.get("variable"))
        if right is None:
            right = src.get("value")
        out.append({"id": r.get("id"), "left": r.get("column"), "right": right})
    return out


def _build_ds_where(template: dict, where_spec, var_ids: dict, ctx: dict, counter: list) -> dict:
    """Data Store `Where` (data-store-decisional) for Select/Update/Delete. The runtime value
    is a JSON ARRAY of InputDataStoreDecisional (Domain.DTOs.DataStore.Decisional) -- the SAME
    operand/condition tree a rule `Decisional` uses, NOT the REST filter group. Verified live:
      [{id:<GUID>, condition:[{id, operator, logicOperator, leftOperator, rightOperator, auxOperator}]}]
    The element `id` MUST be a GUID (an int there deserializes into a .NET Guid? as null ->
    'Nullable object must have a value.'). The LEFT operand is the COLUMN (a literal display
    name); the RIGHT operand is the compared value/variable, whose `<%N%>` binding lives INLINE
    (the parameter-level `Variable` stays EMPTY, unlike a rule Decisional). `logicOperator`
    connects a condition to the NEXT one (last condition = 0). Spec forms:
      [{column, op, value}]                          -> ANDed conditions
      {logic:'and'|'or', conditions:[{column, op, value}]}
    `op` is a decisional operator name (equals, notEquals, contains, greaterThan, ...)."""
    prop = _ds_side_property(template, "data-store-decisional")
    if prop is None:
        raise UsageError("this action has no data-store-decisional property "
                         "(Where renders only for a Data Store Select/Update/Delete)")
    if isinstance(where_spec, dict):
        logic = _DS_LOGIC.get(str(where_spec.get("logic", "and")).strip().lower(), 1)
        conds_spec = where_spec.get("conditions") or where_spec.get("where") or []
    else:
        logic = 1
        conds_spec = where_spec or []
    n = len(conds_spec)
    conds = []
    for j, c in enumerate(conds_spec):
        if not isinstance(c, dict):
            raise UsageError("each Data Store Where condition is {column, op, value}")
        col = c.get("column") or c.get("name")
        if not col:
            raise UsageError("each Data Store Where condition needs a 'column' (display name)")
        op = _ds_resolve_operator(c.get("op", c.get("operator", "equals")))
        left = {"value": col, "variable": []}
        right = _operand(c.get("value", ""), var_ids, counter, ctx)
        conds.append({"id": j, "operator": op,
                      "logicOperator": (logic if j < n - 1 else 0),
                      "leftOperator": left, "rightOperator": right, "auxOperator": None})
    element = {"id": _new_id(ctx), "condition": conds}
    return {"TabPropertyId": prop["id"], "Variable": [], "Value": [element]}


def _ds_where_config(value, ctx):
    """data-store-decisional designer value -- the shape PROCESIO's designer stores (verified
    against a live export): [{id, name:'Where', target:'', condition:[{id, uid, operator,
    leftOperator, rightOperator, auxOperator, logicOperator}]}]. Operands -> designer form via
    _operand_config; the element `id` is carried over from the runtime element so the two layers
    agree, and each condition gets a fresh `uid` (a client render key)."""
    out = []
    for el in value or []:
        conds = []
        for c in el.get("condition") or []:
            conds.append({
                "id": c.get("id"), "uid": _new_id(ctx), "operator": c.get("operator"),
                "leftOperator": _operand_config(c.get("leftOperator")),
                "rightOperator": _operand_config(c.get("rightOperator")),
                "auxOperator": {"variable": "", "attribute": {"id": "", "nextAttribute": None}, "value": ""},
                "logicOperator": c.get("logicOperator", 1),
            })
        out.append({"id": el.get("id"), "name": "Where", "target": "", "condition": conds})
    return out


def _is_foreach(a: dict) -> bool:
    return (a.get("action") or "").strip().lower() in ("for each", "foreach")


def _build_subprocess(template: dict, spec: dict, var_ids: dict, ctx: dict, counter: list) -> list[dict]:
    """Build the Call/Trigger Subprocess params: started-flow placeholder, the target
    flow (flow-list), and the input/output variable maps. spec:
      {target, inputs: {subInputVarId: parentBinding}, outputs: {parentVarName: subOutputVarId}}.
    Sub-process variable ids are GUIDs the caller supplies (e.g. from read-flow-graph on
    the target flow); parent vars resolve by name. Runtime row shape matches the document
    mapper ({id, source, destination}); the designer shape is {id, subprocess, process}."""
    pidx = _property_index(template)
    out: list[dict] = []
    started = next((s for s in pidx.values() if s.get("type") == "ignore"), None)
    if started:
        out.append({"TabPropertyId": started["id"], "Variable": [], "Value": NULL_GUID})
    flowlist = next((s for s in pidx.values() if s.get("type") == "flow-list"), None)
    if not flowlist:
        raise UsageError("this action has no flow-list property (not a subprocess action)")
    out.append({"TabPropertyId": flowlist["id"], "Variable": [], "Value": spec.get("target")})
    in_prop = next((s for s in pidx.values() if s.get("type") == "process-inputs"), None)
    if in_prop:
        rows = []
        for i, (sub_var_id, binding) in enumerate((spec.get("inputs") or {}).items()):
            src = _operand(binding if isinstance(binding, dict) else {"var": binding},
                           var_ids, counter, ctx)
            rows.append({"id": i, "source": src,
                         "destination": {"id": i, "variableId": sub_var_id, "attribute": None}})
        out.append({"TabPropertyId": in_prop["id"], "Variable": [], "Value": rows})
    out_prop = next((s for s in pidx.values() if s.get("type") == "process-outputs"), None)
    if out_prop:
        rows = []
        for i, (parent_var, sub_var_id) in enumerate((spec.get("outputs") or {}).items()):
            pid = var_ids.get(str(parent_var).strip().lower())
            if not pid:
                raise UsageError(f"subprocess output binds unknown variable {parent_var!r}")
            idx = counter[0]
            counter[0] += 1
            rows.append({"id": i,
                         "source": {"value": f"<%{idx}%>",
                                    "variable": [{"id": idx, "variableId": sub_var_id, "attribute": None}]},
                         "destination": {"id": i, "variableId": pid, "attribute": None}})
        out.append({"TabPropertyId": out_prop["id"], "Variable": [], "Value": rows})
    return out


def _subprocess_map_config(rows, is_input):
    """process-inputs/outputs runtime rows {id, source:{value,variable}, destination:{variableId}}
    -> designer rows {id, subprocess:<sub var>, process:<parent var>}. Sub side = destination
    for inputs, source for outputs; parent side is the other."""
    out = []
    for r in rows or []:
        src = _ref_from_variable((r.get("source") or {}).get("variable")) or (r.get("source") or {}).get("value")
        dst = (r.get("destination") or {}).get("variableId")
        sub, proc = (dst, src) if is_input else (src, dst)
        out.append({"id": r.get("id"), "subprocess": sub, "process": proc})
    return out


def _action_parameters(template: dict, params: dict, ctx: dict, counter: list | None = None) -> list[dict]:
    if not params:
        return []
    pidx = _property_index(template)
    counter = counter if counter is not None else [0]   # global <%N%> index per action
    out = []
    for key, binding in params.items():
        prop = pidx.get(str(key).strip().lower()) or pidx.get(key)
        if not prop:
            known = sorted({s["label"] for t in template.get("configuration", [])
                            for s in t.get("settings", []) if s.get("label")})
            raise UsageError(
                f"action {template.get('name')!r} has no property {key!r}; known: {known}")
        out.append(_make_parameter(prop["id"], binding, ctx, counter))
    return out


# -- nodes / ports ------------------------------------------------------------

def _config_value_from_param(value, variable):
    """The DESIGNER reads each setting's `value` from CustomData.configuration; the
    RUNTIME reads Parameters[]. They mirror each other EXCEPT a variable reference is
    a raw variableId (with .attrId for attribute paths) in the config but a `<%N%>`
    placeholder in the Parameter. Convert a Parameter (Value + Variable[]) to the
    designer config value by replacing each `<%N%>` with its bound variable id."""
    if not variable:
        return value
    idmap = {}
    for v in variable:
        ref = v.get("variableId")
        attr = v.get("attribute")
        while attr:
            ref = f"{ref}.{attr.get('attributeId')}"
            attr = attr.get("nextAttribute")
        idmap[v.get("id")] = ref

    def repl(t):
        if isinstance(t, str):
            return re.sub(r"<%(\d+)%>",
                          lambda m: str(idmap.get(int(m.group(1)), m.group(0))), t)
        if isinstance(t, list):
            return [repl(x) for x in t]
        if isinstance(t, dict):
            return {k: repl(x) for k, x in t.items()}
        return t
    return repl(value)


def _ref_from_variable(vs):
    """A param variable list -> the raw variableId (with .attrId for an attribute
    path), the way the designer config stores a variable reference."""
    if not vs:
        return None
    ref = vs[0].get("variableId")
    attr = vs[0].get("attribute")
    while attr:
        ref = f"{ref}.{attr.get('attributeId')}"
        attr = attr.get("nextAttribute")
    return ref


def _docmapper_config(rows):
    """document-mapper: runtime rows {id, source:{value,variable}, destination:{variableId}}
    -> designer rows {id, process:<varId|literal>, document:<docVarId>}."""
    out = []
    for r in rows or []:
        src = r.get("source") or {}
        proc = _ref_from_variable(src.get("variable")) or src.get("value")
        out.append({"id": r.get("id"), "process": proc,
                    "document": (r.get("destination") or {}).get("variableId")})
    return out


def _operand_config(op):
    """decisional operand: runtime {value:'<%N%>', variable:[{variableId,attr}]}
    -> designer {variable:'', attribute:{id:'',nextAttribute:None}, value:<varId|literal>}.
    Literal values are coerced to strings (the designer operand field is text)."""
    op = op or {}
    val = _ref_from_variable(op.get("variable"))
    if val is None:
        val = op.get("value", "")
    val = "" if val is None else val if isinstance(val, str) else str(val)
    return {"variable": "", "attribute": {"id": "", "nextAttribute": None}, "value": val}


def _decisional_cases_config(cases, ctx, aid=None):
    """decisional-case: runtime {id, actionid, condition:[{operator, leftOperator,...}]}
    -> designer {id, name, target, condition:[{id, uid, operator, leftOperator,...}]}.
    The per-case name comes from the meta _build_decisional stashes (keyed by node id),
    so a rule-based branch reads its condition label instead of "Case N"."""
    meta = {m["id"]: m for m in (ctx.get("_dec_case_meta") or {}).get(aid, [])}
    out = []
    for i, c in enumerate(cases or []):
        conds = []
        for cnd in c.get("condition") or []:
            conds.append({
                "id": cnd.get("id"), "uid": _new_id(ctx), "operator": cnd.get("operator"),
                "logicOperator": cnd.get("logicOperator", 1),
                "leftOperator": _operand_config(cnd.get("leftOperator")),
                "rightOperator": _operand_config(cnd.get("rightOperator")),
                "auxOperator": {"variable": "", "attribute": {"id": "", "nextAttribute": None}, "value": ""},
                # fields the designer requires to render/validate a condition
                "value": None,
                "rightOperandAsListRequired": False,
                "operandsAsListOptional": True,
            })
        out.append({"id": c.get("id"),
                    "name": meta.get(c.get("id"), {}).get("name") or c.get("name") or f"Case {i + 1}",
                    "target": c.get("actionid"), "condition": conds})
    return out


def _ai_decisional_cases_config(cases, ctx, aid):
    """ai-decisional-case: runtime {id, actionid, condition:<str>} -> designer
    {id, name, target, condition:<str>, internalId}. name/internalId come from the meta
    stashed by _build_decisional (keyed by node id); fall back to defaults if absent."""
    meta = {m["id"]: m for m in (ctx.get("_ai_case_meta") or {}).get(aid, [])}
    out = []
    for i, c in enumerate(cases or []):
        m = meta.get(c.get("id"), {})
        out.append({"id": c.get("id"), "name": m.get("name") or f"Case {i + 1}",
                    "target": c.get("actionid"), "condition": c.get("condition"),
                    "internalId": m.get("internalId") or _new_id(ctx)})
    return out


# config settings whose DESIGNER value shape differs from the runtime Parameter and
# needs a bespoke transform (otherwise the designer shows the row empty + invalid)
def _apply_values_to_config(cfg_tree: list, params: list, ctx: dict, aid=None) -> None:
    """Set each configuration setting's `value` to mirror its Parameter in the shape
    the DESIGNER expects, so the action shows configured (the flow runs from
    Parameters regardless). Most settings mirror the Parameter with <%N%>->varId;
    document-mapper / decisional-case need a bespoke shape."""
    byid: dict = {}

    def index(settings):
        for s in settings or []:
            if s.get("id"):
                byid[s["id"]] = s
            if isinstance(s.get("value"), list):
                index(s["value"])
    for tab in cfg_tree:
        index(tab.get("settings", []))
    for p in params:
        s = byid.get(p.get("TabPropertyId"))
        if s is None:
            continue
        stype = s.get("type")
        if stype == "document-mapper":
            s["value"] = _docmapper_config(p.get("Value"))
        elif stype == "data-store-mapper":
            s["value"] = _ds_mapper_config(p.get("Value"))
        elif stype == "data-store-decisional":
            s["value"] = _ds_where_config(p.get("Value"), ctx)
        elif stype == "decisional-case":
            s["value"] = _decisional_cases_config(p.get("Value"), ctx, aid)
        elif stype == "ai-decisional-case":
            s["value"] = _ai_decisional_cases_config(p.get("Value"), ctx, aid)
        elif stype == "process-inputs":
            s["value"] = _subprocess_map_config(p.get("Value"), True)
        elif stype == "process-outputs":
            s["value"] = _subprocess_map_config(p.get("Value"), False)
        else:
            cv = _config_value_from_param(p.get("Value"), p.get("Variable"))
            # DESIGNER number inputs bind a STRING: a raw int/float renders EMPTY, then
            # the FE range-check reads Number("")=0 and flags "value between min and max"
            # (even though the RUNTIME Parameter, which stays numeric, executes fine).
            # PROCESIO's own templates store number settings as strings (e.g. "60").
            if stype == "number" and isinstance(cv, (int, float)) and not isinstance(cv, bool):
                cv = repr(cv) if isinstance(cv, float) else str(cv)
            s["value"] = cv


# value-shapes the designer reads for the bespoke types (used by the build audit)
_BESPOKE_REQUIRED = {"document-mapper": ("process", "document"),
                     "data-store-mapper": ("left", "right"),
                     "data-store-decisional": ("condition",),
                     "decisional-case": ("target", "condition"),
                     "ai-decisional-case": ("target", "condition"),
                     "process-inputs": ("subprocess", "process"),
                     "process-outputs": ("subprocess", "process")}


def _audit_config(actions: list) -> None:
    """Build-time guard: catch params whose DESIGNER config didn't get filled in the
    expected shape (the cause of 'action not configured properly' in the designer even
    when the flow runs). Raises UsageError listing each problem."""
    problems: list[str] = []
    for a in actions:
        cd = a.get("CustomData") or {}
        byid: dict = {}

        def index(settings):
            for s in settings or []:
                if s.get("id"):
                    byid[s["id"]] = s
                if isinstance(s.get("value"), list):
                    index(s["value"])
        for tab in cd.get("configuration", []):
            index(tab.get("settings", []))
        an = a.get("ActionName")
        for p in a.get("Parameters", []):
            s = byid.get(p.get("TabPropertyId"))
            if s is None:
                problems.append(f"{an!r}: parameter {p.get('TabPropertyId')} has no config setting")
                continue
            stype = s.get("type")
            val = s.get("value")
            req = _BESPOKE_REQUIRED.get(stype)
            if req:
                rows = val if isinstance(val, list) else []
                if not all(isinstance(r, dict) and all(k in r for k in req) for r in rows):
                    problems.append(f"{an!r}: {stype} config rows missing {req} (designer would show empty)")
            elif p.get("Value") not in (None, "", [], {}) and val is None:
                problems.append(f"{an!r}: setting {s.get('label')!r} has a value at runtime but empty in the designer")
    if problems:
        nl = chr(10)
        raise UsageError("process config audit failed - the designer would flag these "
                         "as not configured:" + nl + "  - " + (nl + "  - ").join(problems))


def _ensure_sql_bind_property(template: dict, params: list) -> list:
    """Give an Execute Query / Execute Command node its `Parameters config tab`, empty if unbound.

    The builder emits only the properties a config names. The designer renders this one from the
    TEMPLATE, finds no value, and refuses the save with "Please make sure that the action is
    defined/configured properly" — so a SQL node built without it cannot be saved at all, bound or
    not. Keyed off the template NAME here because that is all the builder has; the two families
    have different bind ids and using the wrong one leaves every @param unbound at runtime.
    """
    from tools.procesio.flowmodel import sqlparam

    family = (template.get("name") or "").strip().lower()
    if family == "execute query":
        pid = sqlparam.PID_BIND
    elif family == "execute command":
        pid = sqlparam.EC_PID_BIND
    else:
        return params
    if any(p.get("TabPropertyId") == pid for p in params):
        return params
    return params + [{"TabPropertyId": pid, "Variable": [], "Value": []}]


def _ensure_engine_state_properties(template: dict, params: list) -> list:
    """Seed the ENGINE-STATE properties a template declares (`type: "ignore"`) with its own values.

    These never appear in the designer and no config names them, so the builder used to drop them —
    and the engine then reads its own defaults. On a `For Each` that is fatal and silent: without
    `Action start time` (seeded `2010-01-01T00:00:00Z`) the elapsed time is measured from year one,
    so the loop reports "Foreach timeout exceeded!" on its first iteration whatever the cap. The
    template carries the correct seed for each one, which is why they are copied rather than
    invented. Only For Each and Call Subprocess declare any.
    """
    have = {p.get("TabPropertyId") for p in params}
    extra = []
    for cfg in template.get("configuration") or []:
        for s in cfg.get("settings") or []:
            if s.get("type") == "ignore" and s.get("id") not in have:
                extra.append({"TabPropertyId": s["id"], "Variable": [], "Value": s.get("value")})
    return params + extra if extra else params


# The input-setting types whose template default the DESIGNER pre-fills and persists,
# and which are safe to copy verbatim. `code-editor` is deliberately excluded: its
# default is a placeholder function/script, and an unbound Code is a caller error we
# do not want to paper over with a no-op body.
_INPUT_DEFAULT_TYPES = {"check-box", "select", "number", "text"}


def _ensure_input_defaults(template: dict, params: list) -> list:
    """Materialise the INPUT-side (direction 1) template defaults the designer pre-fills.

    When an action is dropped in the designer, every input setting starts at its template
    default (Node `Timeout` 60, Format DateTime `Language` en-US, Export To CSV `Column
    delimiter` ",", ...) and that value is PERSISTED on save. The builder only emitted the
    params the caller bound, so an unbound default-bearing input was DROPPED and the engine
    then received a zero/empty value — silently wrong, and fatal for `Node`: an unbound
    `Timeout` runs as 00:00:00 and the action dies with "value ('00:00:00') must be greater
    than '00:00:00'" (measured live, B-048 cluster 2). Copy the template's own default for
    any safe scalar input the caller left unbound, so a headless-built node matches a
    designer-built one. Restricted to check-box/select/number/text with a non-empty default;
    `code-editor` placeholders and empty defaults are left out. A caller who genuinely wants
    an input empty binds it to "" explicitly, which lands in `params` and skips this.
    """
    have = {p.get("TabPropertyId") for p in params}
    extra = []
    for cfg in template.get("configuration") or []:
        for s in cfg.get("settings") or []:
            if (s.get("direction") == 1
                    and s.get("type") in _INPUT_DEFAULT_TYPES
                    and s.get("id") not in have
                    and s.get("value") not in (None, "", [], {})):
                extra.append({"TabPropertyId": s["id"], "Variable": [], "Value": s.get("value")})
    return params + extra if extra else params


def _action_node(aid, template, name, params, x, y, ctx, parent_id=None) -> dict:
    cfg_tree = copy.deepcopy(template.get("configuration", []))
    _apply_values_to_config(cfg_tree, params, ctx, aid)
    is_area = (template.get("shape") == "area")
    area = ({"width": 416, "height": 200, "x": 0, "y": 0} if is_area
            else {"width": 48, "height": 48, "x": 0, "y": 0})
    return {
        "Id": aid, "FlowId": ctx["flow_id"], "TemplateId": template["actionId"],
        "ParentId": parent_id, "VariableErrorId": None, "Status": 1, "Category": "",
        "ActionName": name, "ActionTemplateName": template.get("name") or name,
        "Ports": [], "Parameters": params,
        "CustomData": {
            "type": template.get("shape") or "square", "name": name,
            "icon": template.get("icon") or "", "position": {"x": x, "y": y},
            "configuration": cfg_tree,
            "inputPorts": template.get("inputPorts", 1),
            "outputPorts": template.get("outputPorts", 1),
            "wasDropped": True, "areaSize": area,
        },
        "IsTestable": bool(template.get("isTestable")), "IsDisabled": False,
        "BreakPoint": None, "TestValues": None, "ErrorMessage": "", "Events": None,
    }


def _port(src, dst, ctx, extra=None) -> dict:
    p = {"Id": _new_id(ctx), "FlowId": ctx["flow_id"], "SourceId": src,
         "DestinationId": dst, "Type": 0, "State": 1, "Data": {}, "Errors": {}, "Config": {}}
    if extra:
        p.update(extra)
    return p


# -- variables ----------------------------------------------------------------

def _variable(v: dict, ctx: dict) -> dict:
    name = v["name"]
    if "model" in v:
        ref = v["model"].strip()
        dt = ctx.get("models", {}).get(ref.lower()) or ref
    else:
        dt = refdata.primitive_type_id(v.get("type", "string"))
    direction = _DIRECTION[v.get("direction", "process").strip().lower()]
    return {
        "Id": ctx["var_ids"][name.strip().lower()], "ContextId": None, "DataType": dt,
        "Type": direction, "Name": name, "DefaultValue": v.get("default"),
        "IsList": bool(v.get("isList", False)), "IsError": bool(v.get("isError", False)),
        "IsRequired": bool(v.get("required", False)),
    }


# -- main build ---------------------------------------------------------------

def _hoist_subprocess_literals(config: dict) -> dict:
    """Subprocess input mappings require the PARENT side to be a plain VARIABLE. PROCESIO
    tolerates a raw literal in a mapping's `process` field for **Call** Subprocess at
    runtime, but the designer marks a **Trigger** Subprocess with a literal input INVALID
    ("Mapping of required subprocess variable (X) is missing"), which blocks the launch
    (statusCode 373). For every literal subprocess input, synthesize a hidden process
    variable (DefaultValue = the literal, which IS delivered at runtime) and rewrite the
    binding to reference it. No-op when there are no literal subprocess inputs. NOTE: an
    attribute-path binding ({"var":x,"path":[...]}) also lands a dotted "varId.attrId" in
    the `process` field the designer dislikes — compute such values into a plain variable
    (e.g. a Node) before the subprocess call rather than passing a path.
    """
    def _literal(binding):
        if isinstance(binding, dict):
            if "var" in binding or "template" in binding:
                return (False, None)
            if "value" in binding:
                return (True, binding["value"])
            return (False, None)
        if isinstance(binding, (list, tuple)):
            return (False, None)
        return (True, binding)                      # bare scalar literal
    def _ptype(v):
        if isinstance(v, bool):  return "boolean"
        if isinstance(v, int):   return "integer"
        if isinstance(v, float): return "decimal"
        return "string"
    extra: list[dict] = []
    seen = {v["name"].strip().lower() for v in config.get("variables", [])}
    i = 0
    new_actions = []
    for a in config.get("actions", []):
        sp = a.get("subprocess")
        if not sp or not sp.get("inputs"):
            new_actions.append(a)
            continue
        new_inputs = dict(sp["inputs"])
        touched = False
        for sub_var_id, binding in list(new_inputs.items()):
            is_lit, lit = _literal(binding)
            if not is_lit:
                continue
            name = f"_sublit{i}"
            i += 1
            while name.lower() in seen:
                name = f"_sublit{i}"
                i += 1
            seen.add(name.lower())
            extra.append({"name": name, "type": _ptype(lit),
                          "direction": "process", "default": lit})
            new_inputs[sub_var_id] = {"var": name}
            touched = True
        if touched:
            a = dict(a)
            a["subprocess"] = dict(sp)
            a["subprocess"]["inputs"] = new_inputs
        new_actions.append(a)
    if not extra:
        return config
    config = dict(config)
    config["actions"] = new_actions
    config["variables"] = list(config.get("variables", [])) + extra
    return config


def build(config: dict, ctx: dict) -> dict:
    ctx = dict(ctx)
    ctx["flow_id"] = ctx.get("flow_id") or _new_id(ctx)
    config = _hoist_subprocess_literals(config)

    # variables: assign ids first so params can reference them. On EDIT, reuse the
    # existing flow's variable ids (by name) so EXTERNAL references stay valid (a form
    # RUN_PROCESS inputMap/outputMap binds a process variable by id).
    _existing = ctx.get("existing_var_ids", {})
    var_ids = {v["name"].strip().lower():
               (_existing.get(v["name"].strip().lower()) or _new_id(ctx))
               for v in config.get("variables", [])}
    ctx["var_ids"] = var_ids
    variables = [_variable(v, ctx) for v in config.get("variables", [])]

    # action nodes (auto Start/Stop unless the user defined their own — needed for
    # branching, where each branch must terminate at its own Stop: a Stop accepts
    # only one input port)
    user_actions = config.get("actions", [])
    ids = {a.get("id") or f"a{i}": a for i, a in enumerate(user_actions)}
    node_id = {cid: _new_id(ctx) for cid in ids}
    has_start = any((a.get("action") or "").strip().lower() == "start" for a in user_actions)
    has_stop = any((a.get("action") or "").strip().lower() == "stop" for a in user_actions)
    start_id = node_id["start"] = _new_id(ctx) if not has_start else None
    stop_id = node_id["stop"] = _new_id(ctx) if not has_stop else None

    start_tpl = _resolve_template("Start", ctx)
    stop_tpl = _resolve_template("Stop", ctx)
    nodes = {}
    name_entries: list = []              # (cid, name, is_auto) for post-loop disambiguation
    order = list(ids.keys())
    branch_ports: list = []
    error_ports: list = []                              # (cid, handler_cid)
    error_vars: list = []                               # ErrorDataModel variables
    for i, cid in enumerate(order):
        a = ids[cid]
        tpl = _resolve_template(a["action"], ctx)
        counter = [0]                   # global <%N%> index shared across this action's params
        params = _action_parameters(tpl, a.get("params", {}), ctx, counter)
        if a.get("docMap"):             # Map Document Data (Generate Document)
            dv = (ctx.get("doc_vars") or {}).get(cid, {})
            params = params + [_build_doc_mapper(tpl, a["docMap"], dv, var_ids, ctx, counter)]
        if a.get("dsMap"):              # Data Store Set Values (Insert/Update)
            params = params + [_build_ds_mapper(tpl, a["dsMap"], var_ids, ctx, counter)]
        if a.get("dsWhere"):            # Data Store Where (Select/Update/Delete)
            params = params + [_build_ds_where(tpl, a["dsWhere"], var_ids, ctx, counter)]
        if a.get("branches"):           # Decisional routing
            bparams, bports = _build_decisional(tpl, a, node_id, var_ids, ctx)
            params = params + bparams
            branch_ports.append((cid, bports))
        if a.get("subprocess"):         # Call/Trigger Subprocess variable mapping
            params = params + _build_subprocess(tpl, a["subprocess"], var_ids, ctx, counter)
        parent_id = None
        if a.get("parent"):
            pcid = a["parent"]
            if pcid not in node_id or node_id.get(pcid) is None:
                raise UsageError(f"action {cid!r} parent {pcid!r} is not an action id")
            if _is_foreach(a) and _is_foreach(ids.get(pcid, {})):
                raise UsageError(
                    f"a For Each ({cid!r}) cannot be nested directly inside another For "
                    f"Each ({pcid!r}); put a Call/Trigger Subprocess inside the loop and "
                    f"place the inner For Each in that subprocess")
            parent_id = node_id[pcid]
        explicit = a.get("name")
        derived = None if explicit else naming.derive_action_name(a, tpl.get("name") or "")
        node_name = explicit or derived or tpl.get("name")
        # ONLY an enriched name is disambiguated; a template-name fallback (Stop, Node,
        # Generate GUID) stays shared across nodes, exactly as before auto-naming.
        name_entries.append((cid, node_name, derived is not None))
        params = _ensure_sql_bind_property(tpl, params)
        params = _ensure_engine_state_properties(tpl, params)
        params = _ensure_input_defaults(tpl, params)
        nodes[cid] = _action_node(node_id[cid], tpl, node_name,
                                  params, 100 + 300 * (i + 1), 300, ctx, parent_id)
        if a.get("onError"):            # error port -> handler + capture error variable
            if (a.get("action") or "").strip().lower() in _NO_ERROR_PORT:
                raise UsageError(f"action {a['action']!r} has no error port "
                                 f"(Start/Stop/Join/For Each don't) — remove onError")
            handler = a["onError"]
            if handler not in node_id:
                raise UsageError(f"onError target {handler!r} is not an action id")
            ev_id = _new_id(ctx)
            error_vars.append({
                "Id": ev_id, "ContextId": None, "DataType": ERROR_MODEL, "Type": 20,
                "Name": f"{cid}_error", "DefaultValue": None, "IsList": False,
                "IsError": True, "IsRequired": False,
            })
            nodes[cid]["VariableErrorId"] = ev_id
            error_ports.append((cid, handler))
    if not has_start:
        nodes["start"] = _action_node(start_id, start_tpl, "Start", [], 100, 300, ctx)
    if not has_stop:
        nodes["stop"] = _action_node(stop_id, stop_tpl, "Stop", [],
                                     100 + 300 * (len(order) + 1), 300, ctx)
    entry = "start" if not has_start else order[0]

    # edges: explicit, or implicit linear start->...->stop
    edges = config.get("edges")
    if not edges:
        chain = (["start"] if not has_start else []) + order + (["stop"] if not has_stop else [])
        edges = [[chain[i], chain[i + 1]] for i in range(len(chain) - 1)]
    # entry edge (null -> first node)
    nodes[entry]["Ports"].append(_port(NULL_GUID, node_id[entry], ctx))
    for e in edges:
        if isinstance(e, dict):
            frm, to = e["from"], e["to"]
            extra = {k: v for k, v in e.items() if k in ("Type", "Config", "Data")}
        else:
            frm, to = e[0], e[1]
            extra = None
        if frm not in node_id or to not in node_id:
            raise UsageError(f"edge references unknown action id(s): {frm!r}->{to!r}")
        if node_id[frm] is None or node_id[to] is None:
            raise UsageError(
                f"edge {frm!r}->{to!r} references an auto Start/Stop that wasn't created "
                f"(you defined your own Start/Stop action) — wire to your own action id")
        nodes[frm]["Ports"].append(_port(node_id[frm], node_id[to], ctx, extra))
    # branch (decisional) ports are defined by the action's `branches`, not edges
    for cid, bports in branch_ports:
        nodes[cid]["Ports"].extend(bports)
    # error ports (Type=1, Data isDefault=error) -> handler
    for cid, handler in error_ports:
        nodes[cid]["Ports"].append(_port(node_id[cid], node_id[handler], ctx,
                                         {"Type": 1, "Data": {"isDefault": "error"}}))

    seq = (["start"] if not has_start else []) + order + (["stop"] if not has_stop else [])
    # auto-name un-named actions by what they do and make the derived names unique
    # within the flow. Cosmetic only (every reference is by id); explicit names untouched.
    for cid, nm in naming.disambiguate(name_entries).items():
        if nodes[cid]["ActionName"] != nm:
            nodes[cid]["ActionName"] = nm
            nodes[cid]["CustomData"]["name"] = nm
    actions = [nodes[cid] for cid in seq]
    _audit_config(actions)
    _engine_layout(actions, {cid: node_id[cid] for cid in seq if node_id.get(cid)},
                   ctx, config)           # final tidy layout (create) / scoped (edit)
    webhooks = _build_webhooks(config.get("webhooks", []), var_ids, ctx) + config.get("_webhooks", [])
    return {
        "Id": ctx["flow_id"], "ParentId": None, "Status": 1,
        "Title": config["title"], "Description": config.get("description", ""),
        "IsValid": True, "Active": True, "Timeout": int(config.get("timeout", 0)),
        "CurrentActionId": None, "DebugMode": False, "IsNotification": False,
        "Variables": variables + error_vars, "Actions": actions, "Webhooks": webhooks,
        "CustomResponse": (_custom_response(config.get("customResponse"), var_ids, ctx)
                           or config.get("_customResponse")),
        "DataRetention": None, "CanvasData": None,
    }


def _resolve_subset(relayout, new_cids, all_cids):
    """Map a relayout directive to a list of config ids to re-tidy, or None for a full
    layout. new_cids/all_cids are config-local ids."""
    if relayout is None:
        return new_cids
    if relayout == "all":
        return None
    if relayout in ("none", []):
        return []
    if relayout == "new":
        return list(new_cids or [])
    if isinstance(relayout, list):
        return [c for c in relayout if c in all_cids]
    if isinstance(relayout, dict):
        s = set(new_cids or []) if relayout.get("new") else set()
        for c in (relayout.get("actions") or []) + (relayout.get("edited") or []):
            if c in all_cids:
                s.add(c)
        return list(s)
    return new_cids


def _engine_layout(actions, id_of, ctx, config):
    """Final layout step over the assembled actions.

    A FULL layout (a fresh build, or an edit with relayout="all") is routed through
    `adapter.layout_flow(..., cluster=True)` -- the SAME path as `relayout-process` -- so a
    newly-built process gets the whole reference arrangement: clustering (long chains fold
    into stacked shelves = the "stacking" arrangement), the branch-placement conventions
    (error/default dead-end branches drop perpendicular), fan lanes, and cycle-awareness.
    Calling the bare `engine.layout` here left `CLUSTER=False` (its default) and skipped
    every adapter post-pass, so freshly-built processes came out flat / un-stacked.

    A PARTIAL re-tidy (an edit that repositions only a subset) stays on the bare engine in
    `subset` mode, so every untouched action is left byte-stable."""
    from tools.procesio.layout import engine
    by_id = {a["Id"]: a for a in actions}
    existing = ctx.get("existing_positions")
    if existing:                          # apply carried-over positions before laying out
        for cid, pos in existing.items():
            a = by_id.get(id_of.get(cid))
            if a and pos and pos.get("x") is not None:
                a["CustomData"]["position"] = {"x": pos["x"], "y": pos["y"]}
    if existing is None:
        subset = None                     # CREATE -> full layout
    else:
        new_cids = [c for c in id_of if c not in existing]
        sub_cids = _resolve_subset(config.get("relayout"), new_cids, list(id_of))
        subset = None if sub_cids is None else [id_of[c] for c in sub_cids if c in id_of]

    if subset is None:
        # FULL layout: go through the adapter so clustering + the branch/fan/cycle
        # conventions apply (bare engine.layout defaults CLUSTER=False). The adapter reads
        # a flow dict, writes positions/areaSize onto a COPY of the actions, and returns
        # that bundle; copy the results back onto the real actions by id. The builder's
        # ports already carry Type=1/Data.isDefault ("error"/"default"), so the branch
        # conventions fire correctly on a fresh build.
        from tools.procesio.layout import adapter
        # Hand the adapter a position-FREE copy so its Start-anchor (built for in-place
        # relayout of a LIVE process, to keep the user's viewport) is a no-op here: a fresh
        # build has no viewport to preserve, so the layout normalizes to the canvas margin
        # (the established fresh-build contract) instead of anchoring to the provisional seed
        # grid. Arrangement (clustering / branch / fan / cycle conventions) is unaffected --
        # it is computed from the graph, not from the input positions.
        probe = [{**a, "CustomData": {k: v for k, v in a["CustomData"].items()
                                      if k != "position"}} for a in actions]
        res = adapter.layout_flow({"Actions": probe}, cluster=True)
        laid = {a["Id"]: a for a in (res["bundle"].get("Actions") or [])}
        for a in actions:
            src = laid.get(a["Id"])
            if src is None:
                continue
            cd = src.get("CustomData") or {}
            if cd.get("position"):
                a["CustomData"]["position"] = dict(cd["position"])
            if cd.get("areaSize") is not None:
                a["CustomData"]["areaSize"] = dict(cd["areaSize"])
        return

    # PARTIAL re-tidy: reposition only `subset` among fixed neighbours (byte-stable rest).
    enodes = [{"id": a["Id"], "width": a["CustomData"]["areaSize"]["width"],
               "height": a["CustomData"]["areaSize"]["height"], "parent_id": a.get("ParentId"),
               "kind": a["CustomData"]["type"], "position": a["CustomData"]["position"]}
              for a in actions]
    eedges = [{"source": p["SourceId"], "dest": p["DestinationId"], "type": p.get("Type", 0)}
              for a in actions for p in a["Ports"]
              if p["SourceId"] != NULL_GUID and p.get("DestinationId")]
    res = engine.layout(enodes, eedges, subset=subset)
    parent_of = {a["Id"]: a["ParentId"] for a in actions if a.get("ParentId") in res["areas"]}
    writes = engine.designer_writes(res["positions"], res["areas"], parent_of)
    targets = set(subset)
    for a in actions:
        w = writes.get(a["Id"])
        if w and a["Id"] in targets:
            a["CustomData"]["position"] = w["pos"]
            if w["areaSize"] is not None:
                a["CustomData"]["areaSize"] = w["areaSize"]


def _custom_response(spec, var_ids: dict, ctx: dict):
    """The flow's synchronous webhook response (CustomResponseDto). Returns the
    value of a process variable to the caller: {Variable:{id:0, variableId}, Value:"<%0%>"}.
    spec: {"var": name} | {"value": literal} | a bare literal."""
    if spec is None:
        return None
    if isinstance(spec, dict) and "var" in spec:
        vid = var_ids.get(spec["var"].strip().lower())
        if not vid:
            raise UsageError(f"customResponse binds unknown variable {spec['var']!r}")
        return {"Variable": {"id": 0, "variableId": vid, "attribute": None}, "Value": "<%0%>"}
    val = spec.get("value") if isinstance(spec, dict) else spec
    return {"Variable": None, "Value": val}


_WH_SOURCE = {"header": 1, "query": 2, "body": 3}


def _build_webhooks(specs: list, var_ids: dict, ctx: dict) -> list:
    """Attach webhooks to the flow. Each spec: {webhookId, variables:[{name, source}]}
    binds a process variable to the webhook's Header(1)/Query(2)/Body(3)."""
    out = []
    for w in specs or []:
        wvars = []
        for b in w.get("variables", []):
            vid = var_ids.get(b["name"].strip().lower())
            if not vid:
                raise UsageError(f"webhook binds unknown variable {b['name']!r}")
            wvars.append({"VariableId": vid,
                          "VariableType": _WH_SOURCE.get(str(b.get("source", "body")).strip().lower(), 3)})
        out.append({"Id": _new_id(ctx), "WebhookId": w["webhookId"],
                    "WebhookVariables": wvars, "IsObsoleted": False,
                    "FilterRules": {"Value": [], "Parameters": []}})
    return out


# -- live context + transport -------------------------------------------------

_CATALOG_FETCH_SECONDS = 30


def _fetch_live_catalog(client, seconds: int = _CATALOG_FETCH_SECONDS):
    """`GET /api/Actions?getFullAction=true` on a HARD wall-clock deadline.

    That endpoint serialises every action's full configuration tree and is
    occasionally pathologically slow while the rest of the API stays sub-second.
    A `requests` timeout is per-socket-read, not total, so a trickling response
    can outlive it indefinitely — which means the caller's `except Exception`
    fallback to the bundled catalog would NEVER fire and the whole build hangs
    with no output. Run it on a daemon thread and abandon it at the deadline so
    the fallback is reachable. Losing the live catalog only costs custom /
    connector actions; every stock action is in the bundled catalog."""
    import threading
    box: dict = {}

    def _work():
        try:
            box["r"] = client.get("/api/Actions", {"getFullAction": "true"},
                                  timeout=seconds)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller below
            box["err"] = exc

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        raise TimeoutError(
            f"live action catalog fetch exceeded {seconds}s - using the bundled catalog")
    if "err" in box:
        raise box["err"]
    return box.get("r")


def prepare_ctx(client, config: dict) -> dict:
    """Fetch the live workspace action catalog (custom/connector actions included)
    and resolve any `model:` variable references to live data-model ids."""
    ctx: dict = {}
    try:
        r = _fetch_live_catalog(client)
        live = r.get("actions") if isinstance(r, dict) else r
        ctx["catalog"] = catalog_index(extra=live or [])
    except Exception:  # noqa: BLE001 - fall back to the bundled catalog offline
        ctx["catalog"] = catalog_index()
    refs = {v["model"].strip().lower() for v in config.get("variables", []) if v.get("model")}
    if refs:
        models: dict[str, str] = {}
        r = client.get("/api/DataTypes", {"addProperties": False, "pageNumber": 1,
                                          "pageItemCount": 500, "includeProcesioEntries": True,
                                          "includeExternalEntries": True})
        for it in (r.get("pageItems") if isinstance(r, dict) else r) or []:
            nm = (it.get("name") or it.get("Name") or "").strip().lower()
            if nm:
                models[nm] = it.get("id") or it.get("Id")
        ctx["models"] = models

    # An attribute path is written into `attribute.attributeId`, which the API parses as a Guid, so
    # the NAME a config uses has to be resolved to an id before the save. Fetch each referenced
    # model's attributes (recursively, so a nested path can descend) and index them by name.
    model_attrs: dict[str, dict] = {}

    def index_model(model_id: str, seen: set) -> None:
        if not model_id or model_id in model_attrs or model_id in seen:
            return
        seen.add(model_id)
        try:
            d = client.get(f"/api/DataTypes/{model_id}")
        except Exception:  # noqa: BLE001 - unreadable model -> paths fall back to pass-through
            return
        d = d.get("result", d) if isinstance(d, dict) else d
        entries = {}
        for a in (d.get("attributes") or []):
            nm = (a.get("name") or a.get("Name") or "").strip()
            if not nm:
                continue
            child = a.get("dataTypeId") or a.get("DataTypeId")
            entries[nm.lower()] = {"id": a.get("id") or a.get("Id"), "name": nm,
                                   "dataTypeId": child}
            if a.get("isDataModel") or a.get("IsDataModel"):
                index_model(child, seen)
        model_attrs[model_id] = entries

    var_models: dict[str, str] = {}
    for v in config.get("variables", []):
        ref = (v.get("model") or "").strip()
        if not ref:
            continue
        mid = (ctx.get("models") or {}).get(ref.lower()) or ref
        var_models[v["name"].strip().lower()] = mid
        index_model(mid, set())
    if var_models:
        ctx["var_models"] = var_models
    if model_attrs:
        ctx["model_attrs"] = model_attrs

    # resolve document-template variables for any action that maps them (docMap)
    doc_vars: dict[str, dict] = {}
    for a in config.get("actions", []):
        if not a.get("docMap"):
            continue
        doc_id = (a.get("params", {}) or {}).get("Select Document Template")
        if isinstance(doc_id, dict):
            doc_id = doc_id.get("value")
        if not doc_id:
            continue
        try:
            d = client.get(f"/api/DocumentTemplate/{doc_id}")
            doc_vars[a.get("id")] = {(v.get("name") or "").strip().lower(): v.get("id")
                                     for v in (d.get("variables") or [])}
        except Exception:  # noqa: BLE001
            doc_vars[a.get("id")] = {}
    if doc_vars:
        ctx["doc_vars"] = doc_vars
    return ctx


def _extract_id(resp, dto):
    # POST /api/Projects returns empty; the flow keeps the client-supplied Id.
    return dto.get("Id") if isinstance(dto, dict) else None


def _validate(client, dto, ctx):
    """validate@source oracle. POST /api/Projects/validate -> empty = valid; a
    non-empty body / 4xx is the validation error payload (returned, not raised, so
    a dry-run still yields the DTO + the reason)."""
    try:
        res = client.post("/api/Projects/validate", dto)
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "detail": getattr(e, "details", str(e))}
    if isinstance(res, dict) and res.get("raw_text", "") == "":
        return {"valid": True}
    return {"valid": not res, "detail": res}


def _save_gate(client, dto, ctx):
    """Front-end (designer) + back-end validation gate. Runs before EVERY process
    save (create + edit); raises errors.ValidationBlocked on blocking errors unless
    ctx['_force']. See handlers/fevalidate.pre_save_validate for the FE->BE order.

    It also STAMPS the verdict onto dto["IsValid"] before returning, which is why it
    takes the dto rather than just reporting. build() sets that field to a hardcoded
    True, and the platform never computes it - it stores whatever the body carries. So
    without the stamp every save asserts the process is valid, and a deliberate --force
    save of a half-built process is filed as a good one. Both create and edit run this,
    so stamping here covers every desired-state save from one place.
    """
    from tools.procesio.handlers.fevalidate import pre_save_validate
    report = pre_save_validate(client, dto, force=bool(ctx.get("_force")),
                               include_types=not ctx.get("_no_types"))
    fe_clean = (report.get("fe") or {}).get("clean") is not False
    be_ok = (report.get("be") or {}).get("valid") is not False
    dto["IsValid"] = bool(fe_clean and be_ok)
    return report


def _edit_ctx(client, resource_id, config, ctx):
    """Everything an edit carries over from the LIVE flow. Shared with the dry-run preview, so
    `--dry-run` shows the ids and positions the edit would actually write rather than a create's."""
    ctx = dict(ctx)
    ctx["flow_id"] = resource_id
    flow: dict = {}
    try:                                  # preserve variable ids across edits
        cur = client.get(f"/api/Projects/{resource_id}")
        flow = cur.get("flow", cur) if isinstance(cur, dict) else {}
        ctx["existing_var_ids"] = {
            (v.get("name") or "").strip().lower(): v.get("id")
            for v in (flow.get("variables") or [])
            if v.get("name") and not v.get("isError")}
    except Exception:  # noqa: BLE001
        pass
    try:                                  # preserve canvas positions across edits
        from collections import defaultdict, deque
        live = flow.get("actions") or flow.get("Actions") or []
        byname = defaultdict(deque)
        for la in live:
            cd = la.get("customData") or la.get("CustomData") or {}
            byname[(la.get("actionName") or la.get("name")
                    or la.get("ActionName") or "")].append(cd.get("position"))
        existing = {}
        for ca in config.get("actions", []):
            _tnm = _resolve_template(ca["action"], ctx).get("name")
            nm = ca.get("name") or naming.derive_action_name(ca, _tnm) or _tnm
            if byname[nm] and ca.get("id"):
                existing[ca["id"]] = byname[nm].popleft()
        for auto, nm in (("start", "Start"), ("stop", "Stop")):
            if byname[nm]:
                existing[auto] = byname[nm].popleft()
        ctx["existing_positions"] = {k: v for k, v in existing.items() if v}
    except Exception:  # noqa: BLE001
        pass
    ctx["_live_flow"] = flow          # the edit still needs the live CanvasData blob
    return ctx


def _edit(client, resource_id, config, ctx):
    ctx = _edit_ctx(client, resource_id, config, ctx)
    dto = build(config, ctx)
    # Preserve the designer canvas blob across a desired-state edit. build() resets
    # CanvasData to None (a fresh process has none), but an edit must NOT drop the live
    # value: it carries the viewport pan/zoom AND the decorative Shapes, which persist
    # under canvasData.shapes (canvas-engine PRC-4391). Dropping it wipes every shape on
    # the process. Live API is camelCase (canvasData); the PUT DTO is PascalCase.
    flow = ctx.get("_live_flow") or {}
    live_canvas = flow.get("canvasData")
    if live_canvas is None:
        live_canvas = flow.get("CanvasData")
    if live_canvas is not None:
        dto["CanvasData"] = live_canvas
    _save_gate(client, dto, ctx)
    client.put("/api/Projects", dto)
    return client.get(f"/api/Projects/{resource_id}")


COMPONENT = Component(
    name="process",
    description="PROCESIO process (flow): variables + actions wired into a runnable graph.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/Projects"),
    get_path="/api/Projects/{id}",
    extract_id=_extract_id,
    prepare_ctx=prepare_ctx,
    validate=_validate,
    edit=_edit,
    edit_ctx=_edit_ctx,
    save_gate=_save_gate,
)
