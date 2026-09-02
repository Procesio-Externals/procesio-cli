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
