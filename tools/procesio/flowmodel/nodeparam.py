"""Surgical read/write of ONE runtime parameter on ONE node of a PROCESIO flow.

Why this exists: the desired-state builders (`process-create` / `process-edit`) rebuild a whole flow
from a config. That is the right tool when you own the config, and the wrong one when a live flow was
hand-built in the designer and a single literal has to change — an API endpoint that moved host, a
timeout, a SQL statement, a script body. Rebuilding such a flow from a reconstructed config risks
losing everything the config cannot express; changing one `parameters[]` value risks nothing.

Model (see PROCESIO-API-NOTES.md):
  - a node = `flow['actions'][i]`; its RUNTIME layer is `parameters[]`, each entry
    `{tabPropertyId, value, variable[]}`. `value` is the literal text with `<%N%>` placeholders;
    `variable[]` binds each `N` to a `{id, variableId, attribute}`.
  - the DESIGNER layer (`customData.configuration[].settings[]`) mirrors it, keyed by the SAME id as
    `tabPropertyId`, except a variable ref is the raw variable GUID there. NEVER hand-write it —
    `dto.process.normalize.normalize_designer_layer` regenerates it from the runtime layer.

Scope guard: only a STRING parameter value may be set here. List/dict-shaped values (request-payload
tabs, decisional cases, subprocess maps, document mappers) are structured DTOs whose designer mirror is
not a clean 1:1 — those belong to the builder, not to a text patch.

Pure: mutates a raw flow DTO dict in place; the caller fetches / normalizes / validates / PUTs.
"""
from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"<%(\d+)%>")


def find_node(flow: dict, key: str) -> dict | None:
    """A node by id or by its canvas label (`actionName`). Exact match, id first."""
    actions = flow.get("actions") or []
    for a in actions:
        if a.get("id") == key:
            return a
    for a in actions:
        if a.get("actionName") == key:
            return a
    return None


def _settings_index(node: dict) -> dict:
    """{setting.id: setting} for a node's designer settings, recursing into side-pannel nesting."""
    byid: dict = {}

    def walk(settings):
        for s in settings or []:
            if isinstance(s, dict):
                if s.get("id"):
                    byid[s["id"]] = s
                if isinstance(s.get("value"), list):
                    walk(s["value"])
    for tab in (node.get("customData") or {}).get("configuration") or []:
        walk(tab.get("settings") or [])
    return byid


def _label_of(node: dict, property_id: str) -> str | None:
    s = _settings_index(node).get(property_id)
    return s.get("label") if s else None


def placeholders(value) -> list[int]:
    """The `<%N%>` indexes a parameter value binds, sorted — the value's variable contract."""
    return sorted({int(m) for m in _PLACEHOLDER.findall(value)}) if isinstance(value, str) else []


def describe_node(flow: dict, node: dict) -> dict:
    """One node's parameters with the designer label, value shape and bound variable names —
    everything needed to pick the property to patch, without dumping the whole DTO."""
    vmap = {v.get("id"): v.get("name") for v in flow.get("variables") or []}
    params = []
    for p in node.get("parameters") or []:
        v = p.get("value")
        bound = [{"index": ve.get("id"), "variable": vmap.get(ve.get("variableId")), "id": ve.get("variableId")}
                 for ve in (p.get("variable") or [])]
        params.append({
            "property": p.get("tabPropertyId"),
            "label": _label_of(node, p.get("tabPropertyId")),
            "kind": type(v).__name__ if v is not None else "null",
            "editable": isinstance(v, str),
            "value": v if isinstance(v, (str, int, float, type(None))) else "<structured>",
            "binds": bound,
        })
    return {"node": node.get("actionName"), "id": node.get("id"),
            "template": node.get("actionTemplateName"),
            "disabled": bool(node.get("isDisabled")), "parameters": params}


def scan(flow: dict) -> list[dict]:
    """Every node with its parameter surface."""
    return [describe_node(flow, a) for a in flow.get("actions") or []]


def find_param(node: dict, key: str) -> dict | None:
    """A parameter by tabPropertyId or by its designer label (case-insensitive)."""
    params = node.get("parameters") or []
    for p in params:
        if p.get("tabPropertyId") == key:
            return p
    want = (key or "").strip().lower()
    for p in params:
        lbl = _label_of(node, p.get("tabPropertyId"))
        if lbl and lbl.strip().lower() == want:
            return p
    return None


def set_param_value(node: dict, param: dict, new_value: str, *, allow_binding_change: bool = False) -> dict:
    """Set one parameter's literal `value`, in place. Returns {changed, before, after}.

    Refuses a non-string current value (structured DTO — builder territory) and, unless
    `allow_binding_change`, refuses a new text whose `<%N%>` set differs from the old one: the
    placeholder set IS the contract with `variable[]`, and silently dropping or inventing one
    unbinds a variable at runtime with no validation error.
    """
    old = param.get("value")
    if not isinstance(old, str):
        raise ValueError(
            f"parameter '{_label_of(node, param.get('tabPropertyId')) or param.get('tabPropertyId')}' "
            f"holds a {type(old).__name__}, not text - structured parameters are edited through the "
            f"process builder (process-edit), not as a text patch")
    if not allow_binding_change and placeholders(old) != placeholders(new_value):
        raise ValueError(
            f"placeholder set would change {placeholders(old)} -> {placeholders(new_value)}; "
            f"each <%N%> binds variable[] entry N, so this silently unbinds a variable. "
            f"Pass --allow-binding-change only when variable[] is being rewritten too")
    param["value"] = new_value
    return {"changed": old != new_value, "before": old, "after": new_value}


def bind_param_var(node: dict, param: dict, bindings: dict, *, find=None, replace=None) -> dict:
    """Set a parameter's `variable[]` bindings, optionally rewriting the value first, in place.

    `bindings` maps each `<%N%>` index to a variable id. A NAMED token like `<%firstName%>` typed as
    literal text is NOT a runtime placeholder (only positional `<%N%>` substitutes), so it renders
    verbatim; the fix is to turn it INTO `<%0%>` and bind index 0 to the variable. Pass `find`/`replace`
    to make that small substitution on the value here (so the 30 KB body need not be re-sent), then the
    value's placeholder set must equal the binding index set, or the write is refused - a `<%N%>` with
    no binding substitutes to nothing, a binding with no `<%N%>` is dead.
    """
    old = param.get("value")
    if not isinstance(old, str):
        raise ValueError(
            f"parameter '{_label_of(node, param.get('tabPropertyId')) or param.get('tabPropertyId')}' "
            f"holds a {type(old).__name__}, not text - structured parameters are builder territory")
    value = old
    if find is not None:
        if find not in value:
            raise ValueError(f"--find text is not present in the parameter value")
        value = value.replace(find, replace if replace is not None else "")
    idxs = set(placeholders(value))
    if idxs != set(bindings):
        raise ValueError(
            f"after the edit the value binds placeholders {sorted(idxs)} but --bind covers "
            f"{sorted(bindings)} - each <%N%> must have exactly one binding and vice versa")
    param["value"] = value
    param["variable"] = [{"id": i, "variableId": bindings[i], "attribute": None} for i in sorted(bindings)]
    return {"changed": True, "value_changed": old != value, "before": old if old != value else None,
            "after": value if old != value else None, "bindings": {i: bindings[i] for i in sorted(bindings)}}


# --- literal text replacement across a node's runtime + designer layers -------------------------
#
# Some values a flow author needs to change live INSIDE a structured parameter — a Map Data row's
# source expression, a decisional case's literal, a subprocess input's constant. Those are lists of
# dicts whose designer mirror is not a clean 1:1 with the runtime layer (the runtime holds `<%N%>`,
# the designer the variable GUID), so the normalizer deliberately leaves them alone and
# `set_param_value` refuses them. An EXACT-LITERAL replace is the one edit that is still safe there:
# the same literal appears verbatim in both layers, so replacing it in every string leaf of both
# keeps them consistent without either layer having to be understood.

def _walk_strings(obj, path: str, fn):
    """Apply `fn(path, str) -> str` to every string leaf of a nested list/dict, in place."""
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            p = f"{path}.{k}"
            if isinstance(v, str):
                obj[k] = fn(p, v)
            else:
                _walk_strings(v, p, fn)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            if isinstance(v, str):
                obj[i] = fn(p, v)
            else:
                _walk_strings(v, p, fn)


def replace_text(node: dict, find: str, replace: str, *, property_key: str | None = None) -> list[dict]:
    """Replace an exact literal in every string leaf of the node's runtime parameters AND designer
    settings. Returns one hit per changed leaf: {layer, path, before, after, count}.

    `property_key` narrows the edit to one parameter (by tabPropertyId or designer label); omit it to
    sweep the whole node. Both layers are swept, which is what keeps runtime and designer consistent
    for the structured settings the normalizer cannot regenerate.
    """
    if not find:
        raise ValueError("--find must be a non-empty literal")
    only = None
    if property_key:
        p = find_param(node, property_key)
        if p is None:
            raise ValueError(f"property not found on node '{node.get('actionName')}': {property_key}")
        only = p.get("tabPropertyId")

    hits: list[dict] = []

    def sub(layer):
        def fn(path, s):
            if find not in s:
                return s
            new = s.replace(find, replace)
            hits.append({"layer": layer, "path": path, "before": s, "after": new,
                         "count": s.count(find)})
            return new
        return fn

    for p in node.get("parameters") or []:
        if only and p.get("tabPropertyId") != only:
            continue
        v = p.get("value")
        base = f"parameters[{p.get('tabPropertyId')}]"
        if isinstance(v, str):
            nv = sub("runtime")(base, v)
            p["value"] = nv
        else:
            _walk_strings(v, base, sub("runtime"))

    settings = _settings_index(node)
    for sid, s in settings.items():
        if only and sid != only:
            continue
        v = s.get("value")
        base = f"customData[{sid}]"
        if isinstance(v, str):
            s["value"] = sub("designer")(base, v)
        else:
            _walk_strings(v, base, sub("designer"))
    return hits


# --- process-variable type surgery --------------------------------------------------------------
#
# A flow variable is `{id, name, dataType, type, isList, isRequired, defaultValue}`. `type` is the
# DIRECTION: 10 input / 20 process / 30 output / 40 system. Inputs and outputs ARE the process's
# public contract (the run payload and the webhook response), so retyping one silently breaks every
# caller — that is why retyping them needs an explicit override here.

VAR_DIRECTION = {10: "input", 20: "process", 30: "output", 40: "system"}


def find_variable(flow: dict, key: str) -> dict | None:
    """A variable by id or by name."""
    variables = flow.get("variables") or []
    for v in variables:
        if v.get("id") == key:
            return v
    for v in variables:
        if v.get("name") == key:
            return v
    return None


def set_variable_type(flow: dict, var: dict, data_type: str, *,
                      is_list: bool | None = None, allow_contract_change: bool = False) -> dict:
    """Retype one flow variable in place. Returns {changed, before, after}.

    Refuses an input (10) or output (30) variable without `allow_contract_change`: those are the run
    payload and the response shape a caller depends on.
    """
    direction = var.get("type")
    if direction in (10, 30) and not allow_contract_change:
        raise ValueError(
            f"'{var.get('name')}' is an {VAR_DIRECTION.get(direction)} variable - retyping it changes "
            f"the process's public contract (run payload / webhook response). Pass "
            f"--allow-contract-change if that is genuinely intended")
    before = {"dataType": var.get("dataType"), "isList": var.get("isList")}
    var["dataType"] = data_type
    if is_list is not None:
        var["isList"] = is_list
    after = {"dataType": var.get("dataType"), "isList": var.get("isList")}
    return {"changed": before != after, "before": before, "after": after,
            "direction": VAR_DIRECTION.get(direction, direction)}



def set_variable_required(flow: dict, var: dict, required: bool, *,
                          allow_contract_change: bool = False) -> dict:
    """Set one INPUT variable's `isRequired` flag in place. Returns {changed, before, after}.

    Only an input (10) variable has a caller-supplied value, so `isRequired` is meaningless
    anywhere else and setting it there is refused rather than silently written.

    The two directions are NOT symmetric, and only one of them is guarded:

    * **Clearing** it (required -> optional) can never break an existing caller: every payload
      that was valid before is still valid. It is allowed outright.
    * **Setting** it (optional -> required) tightens the public contract and breaks every caller
      that legitimately omitted the field, so it needs `allow_contract_change`.

    Clearing the flag is safe for CALLERS but not automatically safe for the FLOW: a Node body
    that injects the variable through a bare raw placeholder (`var f = <%6%>;`) becomes
    `var f = ;` -- a SyntaxError -- the first time the value is genuinely absent. Guard such an
    injection as `[<%6%>][0]` (which yields `undefined`) BEFORE clearing the flag. This function
    cannot see into node bodies, so it cannot check that for you.
    """
    direction = var.get("type")
    if direction != 10:
        raise ValueError(
            f"'{var.get('name')}' is a {VAR_DIRECTION.get(direction, direction)} variable - only an "
            f"input variable carries a caller-supplied value, so isRequired means nothing on it")
    required = bool(required)
    before = {"isRequired": var.get("isRequired")}
    if required and not before["isRequired"] and not allow_contract_change:
        raise ValueError(
            f"making input '{var.get('name')}' required tightens the process's public contract and "
            f"breaks every caller that omits it. Pass --allow-contract-change if that is intended")
    var["isRequired"] = required
    after = {"isRequired": var.get("isRequired")}
    return {"changed": before != after, "before": before, "after": after,
            "direction": VAR_DIRECTION.get(direction, direction)}



VAR_DIRECTION_BY_NAME = {"input": 10, "process": 20, "output": 30}

_DATATYPE_ALIASES = {
    "boolean": "0317bfee-b2f5-4bde-bfe8-121212121210",
    "integer": "0317bfee-b2f5-4bde-bfe8-121212121211",
    "float":   "0317bfee-b2f5-4bde-bfe8-121212121212",
    "double":  "0317bfee-b2f5-4bde-bfe8-121212121213",
    "string":  "0317bfee-b2f5-4bde-bfe8-121212121214",
    "date":    "0317bfee-b2f5-4bde-bfe8-121212121215",
    "time":    "0317bfee-b2f5-4bde-bfe8-121212121217",
    "datetime":"0317bfee-b2f5-4bde-bfe8-121212121218",
    "guid":    "0317bfee-b2f5-4bde-bfe8-121212121222",
    "json":    "0317bfee-b2f5-4bde-bfe8-121212121220",
    "object":  "0317bfee-b2f5-4bde-bfe8-121212121221",
    "file":    "10c6ac59-3929-49e6-99dc-121212121219",
}


def resolve_data_type(spec: str) -> str:
    """A friendly alias ('string', 'file') or a data-type GUID -> the GUID."""
    key = str(spec or "").strip().lower()
    if key in _DATATYPE_ALIASES:
        return _DATATYPE_ALIASES[key]
    if "-" in str(spec):
        return str(spec).strip()
    raise ValueError(
        f"unknown data type {spec!r}; use a GUID or one of: {', '.join(sorted(_DATATYPE_ALIASES))}")


def add_variable(flow: dict, name: str, data_type: str, direction: str, *,
                 is_list: bool = False, default_value=None, is_required: bool = False,
                 new_id: str | None = None) -> dict:
    """Append one variable to a flow in place. Returns the variable that was added.

    A flow's variables are addressed BY ID everywhere else - node parameter binds, a form's
    input/output maps - so adding one is safe for existing wiring in a way that renaming or
    retyping is not: nothing can already point at an id that did not exist.

    Refused rather than guessed:
    * a duplicate NAME, even though the platform keys on id. Two variables sharing a name make
      every later name-based lookup ambiguous, and the form-event tooling resolves names to ids.
    * an unknown direction. 10/20/30 are input/process/output; a variable with no direction is
      not addressable from either the run payload or the response.
    """
    import uuid as _uuid

    nm = str(name or "").strip()
    if not nm:
        raise ValueError("a variable needs a name")
    dirn = str(direction or "").strip().lower()
    if dirn not in VAR_DIRECTION_BY_NAME:
        raise ValueError(f"direction must be one of input, process, output - got {direction!r}")
    for v in flow.get("variables") or []:
        if str(v.get("name")) == nm:
            raise ValueError(f"a variable named {nm!r} already exists in this flow "
                             f"(id {v.get('id')}); pick another name")
    var = {
        "id": new_id or str(_uuid.uuid4()),
        "contextId": None,
        "dataType": resolve_data_type(data_type),
        "type": VAR_DIRECTION_BY_NAME[dirn],
        "name": nm,
        "defaultValue": default_value,
        "isList": bool(is_list),
        "isError": False,
        "isRequired": bool(is_required),
    }
    flow.setdefault("variables", []).append(var)
    return var



def set_variable_default(flow: dict, var: dict, default_value, *,
                         allow_contract_change: bool = False) -> dict:
    """Set one variable's `defaultValue` in place. Returns {changed, before, after}.

    This is how an input stops being something the caller must supply. Verified on a File
    variable: a run that omits it entirely still receives the object, and the platform
    RE-STAGES the referenced file into the calling flow's own instance path. So a value a user
    should never have to provide - a configuration, a reference table, an empty placeholder -
    can be set once by an admin and then simply is not a field on anyone's form.

    Two cautions, both learned rather than assumed:

    * A File default carries a `path` pointing into some flow instance's storage. If that
      instance is cleaned up - data retention is per-flow and finite - the default becomes a
      dangling reference. Stamp defaults from a file whose lifetime you control, and re-check
      after any retention change.
    * Changing an input's default changes what a run does when the caller says nothing. That
      is a contract change in every sense that matters, even though the signature is unchanged,
      so an input/output variable needs `allow_contract_change`.
    """
    direction = var.get("type")
    if direction in (10, 30) and not allow_contract_change:
        raise ValueError(
            f"'{var.get('name')}' is an {VAR_DIRECTION.get(direction)} variable - changing its "
            f"default changes what a run does when the caller supplies nothing. Pass "
            f"--allow-contract-change if that is intended")
    before = {"defaultValue": var.get("defaultValue")}
    var["defaultValue"] = default_value
    after = {"defaultValue": var.get("defaultValue")}
    return {"changed": before != after, "before": before, "after": after,
            "direction": VAR_DIRECTION.get(direction, direction)}



def _camel(key: str) -> str:
    """`TabPropertyId` -> `tabPropertyId`. The DTO builder emits PascalCase (the CREATE shape);
    a flow read back from the API is camelCase. Splicing one into the other without this is the
    silent-corruption case: the API accepts both, the designer renders neither consistently."""
    return key[:1].lower() + key[1:] if key else key


def to_live_action(dto: dict) -> dict:
    """Convert a builder ActionDto (PascalCase) into the camelCase shape a LIVE flow carries.

    Only the top level and the `parameters` rows need it - `customData` is already authored in
    the live casing by the builder, and its `configuration` tree is copied from the template.
    """
    out = {}
    for k, v in dto.items():
        ck = _camel(k)
        if ck == "parameters" and isinstance(v, list):
            out[ck] = [{_camel(pk): pv for pk, pv in row.items()} if isinstance(row, dict) else row
                       for row in v]
        elif ck == "ports" and isinstance(v, list):
            out[ck] = [{_camel(pk): pv for pk, pv in row.items()} if isinstance(row, dict) else row
                       for row in v]
        else:
            out[ck] = v
    return out


def insert_node(flow: dict, after: dict, action: dict) -> tuple[bool, str]:
    """Splice one already-built action into a flow immediately AFTER `after`, in place.

    Ports live on the SOURCE action and carry `destinationId`, so an insertion is two edits and
    not one: the new node gets a port to whatever `after` pointed at, and `after`'s own outgoing
    port is repointed at the new node. Do only the first and the new node is unreachable; do only
    the second and the tail of the flow is orphaned. Both failures validate.

    Refused rather than guessed: an anchor with more than one outgoing port (which branch the new
    node belongs on is a design decision), and an anchor that is not in this flow.
    """
    actions = flow.get("actions") or []
    anchor_id = after.get("id")
    if not any(a.get("id") == anchor_id for a in actions):
        return False, "anchor %r is not in this flow" % (after.get("actionName") or anchor_id)

    outgoing = [p for p in after.get("ports") or []
                if p.get("sourceId") == anchor_id and p.get("destinationId")]
    if len(outgoing) > 1:
        return False, ("anchor %r has %d outgoing ports - which branch the new node belongs on is a "
                       "design decision, so wire it explicitly instead"
                       % (after.get("actionName"), len(outgoing)))

    new_id = action.get("id")
    successor = outgoing[0]["destinationId"] if outgoing else None
    action.setdefault("ports", [])
    if successor:
        action["ports"].append({
            "id": str(__import__("uuid").uuid4()), "flowId": flow.get("id"),
            "sourceId": new_id, "destinationId": successor,
            "type": 0, "state": 1, "data": {}, "errors": {}, "config": {}})
        outgoing[0]["destinationId"] = new_id
        tail = "between %r and its successor" % (after.get("actionName"),)
    else:
        tail = "after %r, which had no successor" % (after.get("actionName"),)

    actions.append(action)
    flow["actions"] = actions
    return True, "inserted %r (%s) %s" % (action.get("actionName"),
                                          action.get("actionTemplateName"), tail)


def set_process_title(flow: dict, title: str) -> dict:
    """Set a flow's title in place. Returns {changed, before, after}.

    The title is cosmetic - the platform wires everything by id, never by name (same reasoning as
    rename-actions) - so this touches only the top-level `title` field, no node parameter and no
    designer customData, and cannot break a flow. A `duplicate` always lands as '... (Copy)', so this
    is the follow-up that gives the copy a real name.
    """
    before = flow.get("title")
    flow["title"] = title
    return {"changed": before != title, "before": before, "after": title}


# --------------------------------------------------------------------------- node removal

_TERMINALS = ("Start", "Stop")


def delete_node(flow: dict, node: dict) -> tuple[bool, str]:
    """Remove one action from a flow and reconnect the graph around it, in place.

    A dead node is not free: it still executes, still bills an execution, and still throws into
    whatever error variable it was given, so a node whose upstream contract moved on fails on every
    single run with nothing downstream to show for it. Deleting it over the API means healing the
    edges by hand — every port that pointed AT this node is re-pointed at the node's own successor,
    or dropped when it has none. Miss that and the tail of the flow is stranded.

    Refused rather than guessed: `Start` / `Stop` (a flow needs both), a node with more than one
    outgoing port (which successor inherits the incoming edges is a design decision, not a default),
    and a node that is not in this flow. Variables are left alone — another node may still read them,
    and an unused variable costs nothing. Returns (changed, message).
    """
    actions = flow.get("actions") or []
    if not any(a is node or a.get("id") == node.get("id") for a in actions):
        return False, "node %r is not in this flow" % (node.get("actionName") or node.get("id"))

    template = node.get("actionTemplateName")
    if template in _TERMINALS:
        return False, "refusing to delete the %s node - a flow needs both Start and Stop" % template

    outgoing = [p for p in node.get("ports") or []
                if p.get("destinationId") and p.get("sourceId") == node.get("id")]
    if len(outgoing) > 1:
        return False, ("node %r has more than one outgoing port - which successor inherits its "
                       "incoming edges is a design decision, so rewire it explicitly first"
                       % node.get("actionName"))

    node_id = node.get("id")
    successor = outgoing[0]["destinationId"] if outgoing else None

    rewired, dropped = 0, 0
    for action in actions:
        if action.get("id") == node_id:
            continue
        kept = []
        reachable = {p.get("destinationId") for p in action.get("ports") or []
                     if p.get("destinationId") != node_id}
        for port in action.get("ports") or []:
            if port.get("destinationId") != node_id:
                kept.append(port)
                continue
            # A self-loop or a duplicate edge is worse than a missing one: the designer renders both
            # and the engine follows them, so heal only into a successor this node does not reach.
            if successor and successor != action.get("id") and successor not in reachable:
                port["destinationId"] = successor
                port["flowId"] = flow.get("id", port.get("flowId"))
                reachable.add(successor)
                kept.append(port)
                rewired += 1
            else:
                dropped += 1
        action["ports"] = kept

    flow["actions"] = [a for a in actions if a.get("id") != node_id]
    return True, ("deleted %r (%s); %d edge(s) rewired to its successor, %d dropped"
                  % (node.get("actionName"), template, rewired, dropped))
