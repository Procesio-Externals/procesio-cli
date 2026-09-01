"""Surgical node-parameter read/write on a LIVE process.

  node-params     list a process's nodes (or one node) with each runtime parameter's designer label,
                  current value and bound variables — read-only.
  node-set-param  set ONE parameter's literal text on ONE node -> regenerate the designer layer from
                  the runtime layer (normalizer) -> BE validate + designer flow-lint -> PUT.
                  --dry-run patches + validates but never PUTs; an invalid flow is never PUT.
  node-replace-text  replace an EXACT literal in every string leaf of a node's runtime parameters AND
                  designer settings — the safe way to reach a value nested inside a structured
                  parameter (a Map Data row's expression, a decisional literal), which node-set-param
                  refuses and the normalizer cannot regenerate. Same validate -> lint -> PUT gate.

This is the safe path for "one literal moved" edits on a designer-built flow (an API endpoint whose
host changed, a timeout, a SQL statement, a script body), where a desired-state rebuild would risk
everything the config cannot express. Structured parameters stay builder territory — see
flowmodel/nodeparam.py. Never hand-write customData: the normalizer derives it (standing rule).

JSON in / JSON out; impure (live client). Thin wrappers over GET / validate / PUT /api/Projects.
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.dto.process.normalize import normalize_designer_layer
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.flowmodel import nodeparam
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.handlers.flowlint import _template_sidepanel_ids, lint_flow_dto


def _fetch_flow(client, pid: str) -> dict:
    flow = client.get(f"/api/Projects/{pid}")
    return flow.get("flow") if isinstance(flow, dict) and "flow" in flow else flow


def _validate(client, flow: dict):
    """(is_valid, errors). Empty 200 == valid (same oracle as process-validate / sql-parameterize)."""
    try:
        res = client.post("/api/Projects/validate", flow)
    except ProcesioAPIError as e:
        det = e.details if isinstance(e.details, dict) else {"body": e.details}
        return False, det.get("body", det)
    empty = (not res) or (isinstance(res, dict) and list(res.keys()) == ["raw_text"] and not res["raw_text"])
    return (True, None) if empty else (False, res)


def _lint(client, flow: dict) -> list[dict]:
    try:
        tmpl_sp = _template_sidepanel_ids(client)
    except Exception:  # noqa: BLE001 - catalog unreachable -> lint what does not need it
        tmpl_sp = {}

    def target_vars_of(fid: str) -> dict:
        try:
            r = client.get(f"/api/Projects/{fid}")
            f = r.get("flow", r) if isinstance(r, dict) else r
            return {v["id"]: v for v in f.get("variables") or []}
        except Exception:  # noqa: BLE001 - unreadable target -> can't assert its contract
            return {}
    return lint_flow_dto(flow, tmpl_sp, target_vars_of)


def node_params(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    if args.node:
        n = nodeparam.find_node(flow, args.node)
        if not n:
            raise UsageError(f"node not found in process {args.id}: {args.node}")
        nodes = [nodeparam.describe_node(flow, n)]
    else:
        nodes = nodeparam.scan(flow)
    return {"id": args.id, "title": flow.get("title"), "node_count": len(nodes), "nodes": nodes}


def node_set_param(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")
    param = nodeparam.find_param(node, args.property)
    if param is None:
        raise UsageError(
            f"property not found on node '{args.node}': {args.property} "
            f"(run node-params --node '{args.node}' to list the labels)")
    try:
        change = nodeparam.set_param_value(node, param, args.value,
                                           allow_binding_change=args.allow_binding_change)
    except ValueError as e:
        raise UsageError(str(e)) from e

    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "property": param.get("tabPropertyId"), **change}
    if not change["changed"]:
        result["note"] = "value already set; nothing to PUT"
        result["put"] = False
        return result

    result["normalized"] = normalize_designer_layer(flow)
    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    problems = _lint(client, flow)
    result["lint_problems"] = problems
    if not valid:                       # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result
    blocking = [p for p in problems if p.get("kind") == "CUSTOMDATA_PLACEHOLDER"]
    if blocking:
        result["put"] = False
        result["blocked_by"] = blocking
        return result
    if args.dry_run:
        result["put"] = False
        result["dry_run"] = True
        return result
    client.put("/api/Projects", flow)
    result["put"] = True
    return result


def node_delete(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")

    changed, msg = nodeparam.delete_node(flow, node)
    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "node_id": node.get("id"), "deleted": changed, "msg": msg}
    if not changed:
        result["put"] = False
        return result

    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    problems = _lint(client, flow)
    result["lint_problems"] = problems
    if not valid:                       # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result
    blocking = [p for p in problems if p.get("kind") == "CUSTOMDATA_PLACEHOLDER"]
    if blocking:
        result["put"] = False
        result["blocked_by"] = blocking
        return result
    if args.dry_run:
        result["put"] = False
        result["dry_run"] = True
        return result
    client.put("/api/Projects", flow)
    result["put"] = True
    return result


def node_replace_text(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")
    if not args.allow_binding_change and ("<%" in args.find or "<%" in args.replace):
        raise UsageError(
            "--find/--replace touch a <%N%> placeholder, which binds variable[] positionally; "
            "pass --allow-binding-change only when variable[] is being rewritten too")
    try:
        hits = nodeparam.replace_text(node, args.find, args.replace, property_key=args.property)
    except ValueError as e:
        raise UsageError(str(e)) from e

    total = sum(h["count"] for h in hits)
    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "find": args.find, "replace": args.replace,
              "replacements": total, "leaves_changed": len(hits), "hits": hits}
    if args.expect is not None and total != args.expect:
        result["put"] = False
        result["error_note"] = f"expected {args.expect} replacements, found {total} - nothing written"
        return result
    if not hits:
        result["note"] = "literal not found; nothing to PUT"
        result["put"] = False
        return result

    result["normalized"] = normalize_designer_layer(flow)
    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    problems = _lint(client, flow)
    result["lint_problems"] = problems
    if not valid:                       # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result
    blocking = [p for p in problems if p.get("kind") == "CUSTOMDATA_PLACEHOLDER"]
    if blocking:
        result["put"] = False
        result["blocked_by"] = blocking
        return result
    if args.dry_run:
        result["put"] = False
        result["dry_run"] = True
        return result
    client.put("/api/Projects", flow)
    result["put"] = True
    return result


def variable_set_type(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    var = nodeparam.find_variable(flow, args.variable)
    if not var:
        raise UsageError(f"variable not found in process {args.id}: {args.variable}")
    is_list = None
    if args.is_list is not None:
        is_list = args.is_list.strip().lower() in ("1", "true", "yes")
    try:
        change = nodeparam.set_variable_type(flow, var, args.data_type, is_list=is_list,
                                             allow_contract_change=args.allow_contract_change)
    except ValueError as e:
        raise UsageError(str(e)) from e

    result = {"id": args.id, "title": flow.get("title"), "variable": var.get("name"), **change}
    if not change["changed"]:
        result["note"] = "type already set; nothing to PUT"
        result["put"] = False
        return result

    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    result["lint_problems"] = _lint(client, flow)
    if not valid:                       # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result
    if args.dry_run:
        result["put"] = False
        result["dry_run"] = True
        return result
    client.put("/api/Projects", flow)
    result["put"] = True
    return result


def _params_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", help="one node's actionName (canvas label) or id; omit for every node")


def _set_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName (canvas label) or id")
    p.add_argument("--property", required=True,
                   help="parameter's designer label (e.g. 'Endpoint') or its tabPropertyId")
    p.add_argument("--value", required=True,
                   help="new literal text; keep every positional variable placeholder the old value had")
    p.add_argument("--allow-binding-change", dest="allow_binding_change", action="store_true",
                   help="permit a different placeholder set (only when variable[] is rewritten too)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="patch + normalize + validate but do not PUT")


def _delete_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName (canvas label) or id to delete")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="delete + heal + validate but do not PUT")


def _replace_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName (canvas label) or id")
    p.add_argument("--property", help="narrow the sweep to one parameter (designer label or tabPropertyId)")
    p.add_argument("--find", required=True, help="exact literal to replace (no regex)")
    p.add_argument("--replace", required=True, help="replacement literal")
    p.add_argument("--expect", type=int,
                   help="assert this many replacements; a mismatch writes nothing")
    p.add_argument("--allow-binding-change", dest="allow_binding_change", action="store_true",
                   help="permit a find/replace that touches a positional variable placeholder")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="replace + normalize + validate but do not PUT")


def _vartype_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--variable", required=True, help="variable name or id")
    p.add_argument("--data-type", dest="data_type", required=True,
                   help="target dataType id (e.g. ...121221 Object, ...121220 Json, ...121214 String)")
    p.add_argument("--is-list", dest="is_list", help="true/false to also set isList; omit to keep it")
    p.add_argument("--allow-contract-change", dest="allow_contract_change", action="store_true",
                   help="permit retyping an input (10) / output (30) variable - changes the public contract")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="retype + validate but do not PUT")


ACTIONS = {
    "node-params": ActionDef(
        func=node_params, add_args=_params_args, needs_client=True,
        description="List a live process's nodes with each runtime parameter's designer label, "
                    "current value, editability and bound variables (read-only)."),
    "node-set-param": ActionDef(
        func=node_set_param, add_args=_set_args, needs_client=True,
        description="Surgically set ONE node parameter's literal text on a live process (an endpoint, "
                    "timeout, SQL or script body) -> regenerate the designer layer from the runtime "
                    "layer -> validate + flow-lint -> PUT. --dry-run to preview; an invalid flow is "
                    "never PUT. Structured (list/dict) parameters stay process-edit territory."),
    "node-delete": ActionDef(
        func=node_delete, add_args=_delete_args, needs_client=True,
        description="Delete ONE action from a live process and heal the graph: every port that pointed "
                    "at it is re-pointed at its successor (or dropped when it has none) -> validate + "
                    "flow-lint -> PUT. Refuses Start/Stop and a node with more than one outgoing port. "
                    "--dry-run previews; variables are left alone."),
    "node-replace-text": ActionDef(
        func=node_replace_text, add_args=_replace_args, needs_client=True,
        description="Replace an EXACT literal in every string leaf of a node's runtime parameters AND "
                    "designer settings on a live process - the safe way to reach a value nested inside "
                    "a structured parameter (a Map Data expression, a decisional literal). --expect N "
                    "asserts the hit count; --dry-run previews. Validates + flow-lints before PUT."),
    "variable-set-type": ActionDef(
        func=variable_set_type, add_args=_vartype_args, needs_client=True,
        description="Retype one variable of a live process (dataType, optionally isList) -> validate + "
                    "flow-lint -> PUT. Refuses an input/output variable without --allow-contract-change, "
                    "because those are the run payload and the response shape callers depend on."),
}
