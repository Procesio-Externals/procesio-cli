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
import json

from tools.procesio.actiondef import ActionDef
from tools.procesio.dto.process.builder import fetch_datastore_meta, render_query_tokens
from tools.procesio.dto.process.normalize import normalize_designer_layer
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.flowmodel import nodeparam
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.handlers.fevalidate import run_fe_validation, save_flow
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



def _gate_and_put(client, flow: dict, args, result: dict, *, block_on_lint: bool = True) -> dict:
    """The tail every surgical writer shares: validate, lint, then save or say why not.

    One copy, because four call sites held drifted copies of it and a copy is where a
    fix stops arriving. Two of them disagreed about whether a lint problem blocks.

    `isValid` in the result is the STORED value re-read after the save, not the
    pre-save measurement. The two differ: the platform keeps whatever the body carries,
    so a flow that validates clean can still land on a process the server has marked
    broken unless the mark is stamped. On the paths that write nothing (dry run,
    blocked, invalid) there is no stored-after value, so it carries the verdict for the
    patched flow instead - which is the question those paths are asked.

    The blocking rule is unchanged: the runtime validator refuses the PUT, a designer
    error does not. Saving a half-finished process is intended platform behaviour, and
    the stamped mark is how the result stays honest about it.
    """
    valid, errors = _validate(client, flow)
    problems = _lint(client, flow)
    result["lint_problems"] = problems
    if not valid:                       # never PUT a flow the runtime validator rejects
        result["isValid"] = False
        result["errors"] = errors
        result["put"] = False
        return result
    if block_on_lint:
        blocking = [p for p in problems if p.get("kind") == "CUSTOMDATA_PLACEHOLDER"]
        if blocking:
            result["isValid"] = valid
            result["put"] = False
            result["blocked_by"] = blocking
            return result
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    if args.dry_run:
        result["isValid"] = bool(valid and fe["clean"])
        result["put"] = False
        result["dry_run"] = True
        return result
    saved = save_flow(client, flow, flow_id=args.id, valid=valid and fe["clean"])
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


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
    if getattr(args, "value_file", None):
        if args.value is not None:
            raise UsageError("pass either --value or --value-file, not both")
        import io as _io
        args.value = _io.open(args.value_file, encoding="utf-8", newline="").read()
    if args.value is None:
        raise UsageError("nothing to set: pass --value or --value-file")
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
    return _gate_and_put(client, flow, args, result)


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

    return _gate_and_put(client, flow, args, result)


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
    return _gate_and_put(client, flow, args, result)


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

    return _gate_and_put(client, flow, args, result, block_on_lint=False)


def variable_set_required(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    var = nodeparam.find_variable(flow, args.variable)
    if not var:
        raise UsageError(f"variable not found in process {args.id}: {args.variable}")
    want = args.required.strip().lower()
    if want not in ("1", "true", "yes", "0", "false", "no"):
        raise UsageError(f"--required must be true or false, got {args.required!r}")
    try:
        change = nodeparam.set_variable_required(
            flow, var, want in ("1", "true", "yes"),
            allow_contract_change=args.allow_contract_change)
    except ValueError as e:
        raise UsageError(str(e)) from e

    result = {"id": args.id, "title": flow.get("title"), "variable": var.get("name"), **change}
    if not change["changed"]:
        result["note"] = "isRequired already set; nothing to PUT"
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
    # Every save decides the mark: the platform stores what the body carries,
    # never computes it, so a pass-through PUT files a repaired flow as broken.
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    saved = save_flow(client, flow, flow_id=args.id, valid=bool(valid and fe["clean"]))
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


def variable_add(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    try:
        var = nodeparam.add_variable(
            flow, args.name, args.data_type, args.direction,
            is_list=bool(args.is_list), default_value=args.default,
            is_required=bool(args.required))
    except ValueError as e:
        raise UsageError(str(e)) from e

    result = {"id": args.id, "title": flow.get("title"), "variable": var["name"],
              "variable_id": var["id"], "dataType": var["dataType"],
              "direction": args.direction.lower(), "isList": var["isList"],
              "isRequired": var["isRequired"]}

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
    # Every save decides the mark: the platform stores what the body carries,
    # never computes it, so a pass-through PUT files a repaired flow as broken.
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    saved = save_flow(client, flow, flow_id=args.id, valid=bool(valid and fe["clean"]))
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


def variable_set_default(client, args) -> dict:
    import io as _io, json as _json
    flow = _fetch_flow(client, args.id)
    var = nodeparam.find_variable(flow, args.variable)
    if not var:
        raise UsageError(f"variable not found in process {args.id}: {args.variable}")
    if args.value is not None and args.value_file:
        raise UsageError("pass either --value or --value-file, not both")
    if args.clear:
        # Clearing needs no value, and combining the two hides which one won.
        if args.value is not None or args.value_file:
            raise UsageError("--clear removes the default; do not combine it with "
                             "--value or --value-file")
        value = None
    else:
        if args.value_file:
            raw = _io.open(args.value_file, encoding="utf-8", newline="").read()
        elif args.value is not None:
            raw = args.value
        else:
            raise UsageError("nothing to set: pass --value, --value-file, or --clear")
        if args.json:
            try:
                value = _json.loads(raw)
            except ValueError as e:
                raise UsageError(f"--json was passed but the value is not valid JSON: {e}") from e
        else:
            value = raw

    try:
        change = nodeparam.set_variable_default(
            flow, var, value, allow_contract_change=args.allow_contract_change)
    except ValueError as e:
        raise UsageError(str(e)) from e

    result = {"id": args.id, "title": flow.get("title"), "variable": var.get("name"), **change}
    if not change["changed"]:
        result["note"] = "default already set to that value; nothing to PUT"
        result["put"] = False
        return result
    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    result["lint_problems"] = _lint(client, flow)
    if not valid:
        result["errors"] = errors
        result["put"] = False
        return result
    if args.dry_run:
        result["put"] = False
        result["dry_run"] = True
        return result
    # Every save decides the mark: the platform stores what the body carries,
    # never computes it, so a pass-through PUT files a repaired flow as broken.
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    saved = save_flow(client, flow, flow_id=args.id, valid=bool(valid and fe["clean"]))
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


def node_insert(client, args) -> dict:
    import io as _io, json as _json, uuid as _uuid
    from tools.procesio.dto.process import builder as _b

    flow = _fetch_flow(client, args.id)
    anchor = nodeparam.find_node(flow, args.after) if hasattr(nodeparam, "find_node") else None
    if anchor is None:
        key = str(args.after).strip().lower()
        for a in flow.get("actions") or []:
            if str(a.get("id")) == args.after or str(a.get("actionName") or "").strip().lower() == key:
                anchor = a
                break
    if anchor is None:
        raise UsageError(f"anchor node not found in process {args.id}: {args.after}")

    params = {}
    if args.params_file:
        params = _json.loads(_io.open(args.params_file, encoding="utf-8").read())
    elif args.params:
        params = _json.loads(args.params)

    # ctx the builder needs: the action catalog, this flow's id, and its variables BY NAME so a
    # {"var": "x"} binding resolves to the same guid the rest of the flow already uses.
    ctx = {
        "flow_id": flow.get("id"),
        "catalog": _b.catalog_index(),
        "var_ids": {str(v.get("name")).strip().lower(): v.get("id")
                    for v in (flow.get("variables") or [])},
        "var_models": {}, "model_attrs": {},
        "new_id": lambda: str(_uuid.uuid4()),
    }
    try:
        template = _b._resolve_template(args.action, ctx)
    except Exception as e:
        raise UsageError(f"could not resolve action template {args.action!r}: {e}") from e

    counter = [0]
    built = _b._action_parameters(template, params, ctx, counter)
    pos = ((anchor.get("customData") or {}).get("position") or {})
    dto = _b._action_node(str(_uuid.uuid4()), template, args.name or args.action, built,
                          float(pos.get("x") or 0) + 160, float(pos.get("y") or 0), ctx)
    action = nodeparam.to_live_action(dto)

    ok, message = nodeparam.insert_node(flow, anchor, action)
    result = {"id": args.id, "title": flow.get("title"), "after": anchor.get("actionName"),
              "action": template.get("name"), "node_id": action.get("id"), "message": message}
    if not ok:
        result["inserted"] = False
        result["put"] = False
        return result

    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    result["lint_problems"] = _lint(client, flow)
    if not valid:                       # never PUT an invalid flow
        result["errors"] = errors
        result["inserted"] = False
        result["put"] = False
        return result
    if args.dry_run:
        result["inserted"] = True
        result["put"] = False
        result["dry_run"] = True
        return result
    # Every save decides the mark: the platform stores what the body carries,
    # never computes it, so a pass-through PUT files a repaired flow as broken.
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    saved = save_flow(client, flow, flow_id=args.id, valid=bool(valid and fe["clean"]))
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["inserted"] = True
    result["put"] = True
    return result


def process_rename(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    change = nodeparam.set_process_title(flow, args.title)
    result = {"id": args.id, **change}
    if not change["changed"]:
        result["note"] = "title already set; nothing to PUT"
        result["put"] = False
        return result
    return _gate_and_put(client, flow, args, result, block_on_lint=False)


def node_bind_var(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")
    param = nodeparam.find_param(node, args.property)
    if param is None:
        raise UsageError(
            f"property not found on node '{args.node}': {args.property} "
            f"(run node-params --node '{args.node}' to list the labels)")
    bindings = {}
    for spec in args.bind or []:
        if "=" not in spec:
            raise UsageError(f"--bind must be 'INDEX=variable', got: {spec}")
        idx, name = spec.split("=", 1)
        try:
            idx = int(idx.strip())
        except ValueError:
            raise UsageError(f"--bind index must be an integer, got: {idx}")
        var = nodeparam.find_variable(flow, name.strip())
        if not var:
            raise UsageError(f"--bind variable not found in process {args.id}: {name.strip()}")
        bindings[idx] = var.get("id")
    if not bindings:
        raise UsageError("at least one --bind INDEX=variable is required")
    try:
        change = nodeparam.bind_param_var(node, param, bindings, find=args.find, replace=args.replace)
    except ValueError as e:
        raise UsageError(str(e)) from e
    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "property": param.get("tabPropertyId"), **change}
    result["normalized"] = normalize_designer_layer(flow)
    return _gate_and_put(client, flow, args, result)


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
    p.add_argument("--value",
                   help="new literal text; keep every positional variable placeholder the old value had")
    p.add_argument("--value-file", dest="value_file",
                   help="read the new literal from a FILE instead of --value. Required for anything "
                        "larger than the OS argv limit (~32 KB on Windows) - a big Node body or an "
                        "embedded reference table cannot be passed on a command line")
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


def _varrequired_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--variable", required=True, help="input variable name or id")
    p.add_argument("--required", required=True,
                   help="true to make the input mandatory, false to make it optional")
    p.add_argument("--allow-contract-change", dest="allow_contract_change", action="store_true",
                   help="permit making an optional input required - tightens the public contract "
                        "and breaks callers that omit it")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="set + validate but do not PUT")


def _varadd_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--name", required=True, help="new variable name (must be unique in the flow)")
    p.add_argument("--data-type", dest="data_type", required=True,
                   help="alias (string, integer, boolean, json, object, file, date, datetime, guid) "
                        "or a data-type GUID")
    p.add_argument("--direction", required=True,
                   help="input (run payload), process (internal) or output (response)")
    p.add_argument("--is-list", dest="is_list", action="store_true", help="make it a list")
    p.add_argument("--default", help="default value")
    p.add_argument("--required", action="store_true",
                   help="mark an input as required (see variable-set-required)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="add + validate but do not PUT")


def _vardefault_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--variable", required=True, help="variable name or id")
    p.add_argument("--value", help="the default value, as text")
    p.add_argument("--value-file", dest="value_file",
                   help="read the default from a FILE (needed above the ~32 KB argv limit)")
    p.add_argument("--json", action="store_true",
                   help="parse the value as JSON before storing it (use for a File object)")
    p.add_argument("--clear", action="store_true", help="clear the default back to null")
    p.add_argument("--allow-contract-change", dest="allow_contract_change", action="store_true",
                   help="required for an input/output variable: it changes what a run does when "
                        "the caller supplies nothing")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="set + validate but do not PUT")


def _insert_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--after", required=True,
                   help="node to insert AFTER - its actionName (canvas label) or id")
    p.add_argument("--action", required=True,
                   help="action template NAME from the catalog (e.g. 'Data Store', 'Decisional')")
    p.add_argument("--name", help="canvas label for the new node (defaults to the template name)")
    p.add_argument("--params", help="parameters as a JSON object of {property label: binding}")
    p.add_argument("--params-file", dest="params_file",
                   help="read the parameters JSON from a file (needed above the argv limit)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build + splice + validate but do not PUT")


def _prename_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--title", required=True, help="new process title")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="patch + validate but do not PUT")


def _bindvar_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName (canvas label) or id")
    p.add_argument("--property", required=True,
                   help="parameter's designer label (e.g. 'Body') or its tabPropertyId")
    p.add_argument("--bind", action="append", required=True,
                   help="INDEX=variable: bind the value's <%%N%%> placeholder N to a process variable "
                        "(name or id). Repeatable. The value's placeholder set must equal the bound set.")
    p.add_argument("--find", help="optional exact literal to replace in the value first (e.g. a "
                                  "mistyped literal '<%%firstName%%>' token)")
    p.add_argument("--replace", help="replacement for --find (e.g. '<%%0%%>'); empty to delete it")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="patch + normalize + validate but do not PUT")


def node_set_error_port(client, args) -> dict:
    """Wire (or clear) ONE node's error port on a live process.

    The reason this is its own action rather than a process-edit config: a desired-state rebuild
    re-derives the whole flow, and the thing being fixed here is usually a flow nobody wants
    re-derived - a designer-built one, or one whose canvas positions are keyed on its action names.
    """
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")
    handler = None
    if not args.clear:
        if not args.handler:
            raise UsageError("--handler is required (or pass --clear to remove the error port)")
        handler = nodeparam.find_node(flow, args.handler)
        if not handler:
            raise UsageError(f"handler node not found in process {args.id}: {args.handler}")
    try:
        change = nodeparam.set_error_port(flow, node, handler, clear=bool(args.clear))
    except ValueError as e:
        raise UsageError(str(e)) from e
    result = {"id": args.id, "title": flow.get("title"), **change}
    result["normalized"] = normalize_designer_layer(flow)
    return _gate_and_put(client, flow, args, result)
def _errorport_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True,
                   help="the node whose error port to wire: actionName (canvas label) or id")
    p.add_argument("--handler",
                   help="the action a fault routes to: actionName or id. Its own successor is the "
                        "usual choice when that successor already tolerates a missing input")
    p.add_argument("--clear", action="store_true",
                   help="remove the error port (and its error variable, if nothing else uses it)")
    p.add_argument("--dry-run", action="store_true",
                   help="wire + normalize + validate but do not PUT")


def _query_param_source(name: str, spec, kept: dict, flow: dict, tmp: list) -> dict:
    """One Parameters-map source, from a friendly spec.

    `keep` is the important one: a live source often carries a resolved ATTRIBUTE path into a
    loop item's model, and re-deriving that from a name would mean re-resolving a model this
    editor never saw. Keeping it verbatim is both safer and shorter.
    """
    import copy

    if isinstance(spec, dict) and spec.get("keep"):
        if name not in kept:
            raise UsageError(
                f"--params asks to keep @{name}, but this node's map has no such parameter "
                f"(it has: {', '.join(sorted(k for k in kept if k)) or 'none'})")
        return copy.deepcopy(kept[name])
    if isinstance(spec, dict) and "raw" in spec:
        return copy.deepcopy(spec["raw"])
    if isinstance(spec, dict) and "var" in spec:
        var = nodeparam.find_variable(flow, str(spec["var"]))
        if not var:
            raise UsageError(f"--params @{name} references unknown variable {spec['var']!r}")
        idx = tmp[0]
        tmp[0] += 1
        return {"value": f"<%{idx}%>",
                "variable": [{"id": idx, "variableId": var.get("id"), "attribute": None}]}
    value = spec.get("value") if isinstance(spec, dict) else spec
    return {"value": value, "variable": []}


def node_set_query(client, args) -> dict:
    """Replace a Query Store node's STATEMENT and its chips together, on a live process.

    node-set-param can only rewrite the text, and it guards that the `<%N%>` set does not move -
    correctly, because those indices bind Variable[] positionally. That makes it useless for the
    edits a statement actually needs: naming one more column, or naming the same column again
    (unavoidable when a value has to be reassembled from several expressions over it, and a
    placeholder cannot be repeated). Here the statement is written with the same
    {{ds:Store}} / {{col:Store.Column}} tokens a config uses, and the chips are regenerated from
    it - so text and bindings cannot drift apart.
    """
    sql = args.sql
    if args.sql_file:
        with open(args.sql_file, encoding="utf-8") as fh:
            sql = fh.read()
    if not sql or not sql.strip():
        raise UsageError("--sql or --sql-file is required")

    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")

    query, pmap = nodeparam.find_query_params(node)
    if query is None:
        raise UsageError(
            f"node {args.node!r} has no Query Store statement "
            f"(template {node.get('actionTemplateName')!r})")
    spec = None
    if args.params or args.params_file:
        raw = args.params
        if args.params_file:
            with open(args.params_file, encoding="utf-8") as fh:
                raw = fh.read()
        try:
            spec = json.loads(raw)
        except ValueError as e:
            raise UsageError(f"--params must be a JSON object of {{name: source}}: {e}") from e
        if not isinstance(spec, dict):
            raise UsageError("--params must be a JSON OBJECT of {name: source}")
    # The node numbers its query chips, its Parameters-map sources AND its output bindings from
    # ONE sequence. Rewriting the statement alone is safe only while the map is empty; once it is
    # not, the map has to be restated so the whole node can be renumbered together.
    if spec is None and (pmap is not None and (pmap.get("value") or [])):
        raise UsageError(
            "this node's Parameters map is not empty, and its sources share one index sequence "
            "with the statement's chips - restate the map with --params (use {\"keep\": true} "
            "for a source you are not changing) so the node can be renumbered as a whole.")

    ctx = {"datastore_meta": fetch_datastore_meta(client)}
    before_chips = len(query.get("variable") or [])
    before_text = query.get("value")
    text, chips = render_query_tokens(sql, ctx)
    query["value"] = text
    query["variable"] = chips

    before_params = [r.get("destination", {}).get("value") for r in (pmap.get("value") or [])]         if pmap is not None else []
    if spec is not None:
        if pmap is None:
            raise UsageError("this node has no Parameters map to write")
        kept = {r.get("destination", {}).get("value"): r.get("source")
                for r in (pmap.get("value") or [])}
        # A temporary index clear of everything already in the node: the renumber pass assigns
        # the real ones, and it can only do that if each source starts out distinguishable.
        used = set()
        for p in node.get("parameters") or []:
            used |= nodeparam._collect_indices(p)
        tmp = [max(used) + 1000 if used else 1000]
        rows = []
        for i, (pname, src_spec) in enumerate(spec.items()):
            name = str(pname).lstrip("@")
            rows.append({"id": i, "source": _query_param_source(name, src_spec, kept, flow, tmp),
                         "destination": {"value": name, "variable": []}})
        pmap["value"] = rows

    nodeparam.renumber_node_placeholders(node, [query, pmap])

    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "chips_before": before_chips, "chips_after": len(chips),
              "changed": before_text != text,
              "stores_referenced": sorted({c["dataStoreId"] for c in chips if c.get("dataStoreId")}),
              "statement": text}
    result["normalized"] = normalize_designer_layer(flow)
    return _gate_and_put(client, flow, args, result)
def _setquery_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True,
                   help="the Query Store node: actionName (canvas label) or id")
    p.add_argument("--sql", help="the statement, written with {{ds:Store}} / "
                                 "{{col:Store.Column}} tokens")
    p.add_argument("--sql-file", help="read the statement from a file (needed above the argv "
                                      "limit, which a real statement usually is)")
    p.add_argument("--params", help="the Parameters map as JSON {name: source}, where a source "
                                    "is {\"keep\": true} (reuse the live source verbatim, "
                                    "attribute path included), {\"var\": \"name\"}, "
                                    "{\"raw\": {...}} or a literal. REQUIRED when the node's "
                                    "map is non-empty, because the whole node is renumbered")
    p.add_argument("--params-file", help="read the Parameters map JSON from a file")
    p.add_argument("--dry-run", action="store_true",
                   help="render + validate but do not PUT")


def _resolve_attr(client, flow: dict, varname: str, attrname: str) -> tuple[str, str]:
    """(variableId, attributeId) for `variable.Attribute`, resolving the attribute BY NAME.

    By name rather than by id because an id is unreadable in a command line and unverifiable by
    the next reader, while a name is checked here against the variable's own model - so a typo is
    refused with the list of what the model actually has, instead of writing a binding that
    resolves to nothing at run time.
    """
    var = nodeparam.find_variable(flow, varname)
    if not var:
        raise UsageError(f"--bind references unknown variable {varname!r}")
    model = var.get("dataType")
    if not model:
        raise UsageError(f"variable {varname!r} has no data model, so it has no attributes")
    try:
        dt = client.get(f"/api/DataTypes/{model}") or {}
    except ProcesioAPIError as e:
        raise UsageError(f"could not read the model of {varname!r}: {e}") from e
    attrs = dt.get("attributes") or dt.get("Attributes") or []
    want = attrname.strip().lower()
    for at in attrs:
        if str(at.get("name") or at.get("Name") or "").strip().lower() == want:
            return var["id"], (at.get("id") or at.get("Id"))
    known = ", ".join(sorted(str(a.get("name") or a.get("Name")) for a in attrs)) or "(none)"
    raise UsageError(f"{varname!r} has no attribute {attrname!r}; it has: {known}")


def node_add_binding(client, args) -> dict:
    """Add bindings to ONE node parameter, with an optional literal edit in the same write.

    The gap this fills: node-bind-var takes a string parameter and replaces the whole binding
    list, and node-replace-text refuses a replacement containing a `<%N%>`. Neither can do the
    edit that keeps coming up - put one more placeholder inside a STRUCTURED parameter (an HTTP
    body template is a dict) and bind it, without restating the bindings already there.
    """
    flow = _fetch_flow(client, args.id)
    node = nodeparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")
    param = nodeparam.find_param(node, args.property)
    if param is None:
        raise UsageError(
            f"property not found on node '{args.node}': {args.property} "
            f"(run node-params --node '{args.node}' to list the labels)")

    bindings = {}
    for spec in args.bind or []:
        if "=" not in spec:
            raise UsageError(f"--bind must be 'INDEX=variable[.Attribute]', got: {spec}")
        idx, ref = spec.split("=", 1)
        try:
            idx = int(idx.strip())
        except ValueError:
            raise UsageError(f"--bind index must be an integer, got: {idx}")
        ref = ref.strip()
        if "." in ref:
            varname, _, attrname = ref.partition(".")
            vid, aid = _resolve_attr(client, flow, varname, attrname)
            bindings[idx] = {"variableId": vid, "attributeId": aid}
        else:
            var = nodeparam.find_variable(flow, ref)
            if not var:
                raise UsageError(f"--bind references unknown variable {ref!r}")
            bindings[idx] = {"variableId": var["id"], "attributeId": None}

    try:
        change = nodeparam.add_param_bindings(node, param, bindings,
                                              find=args.find, replace=args.replace)
    except ValueError as e:
        raise UsageError(str(e)) from e
    result = {"id": args.id, "title": flow.get("title"), "node": node.get("actionName"),
              "property": param.get("tabPropertyId"), **change}
    return _gate_and_put(client, flow, args, result)
def _addbinding_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName (canvas label) or id")
    p.add_argument("--property", required=True,
                   help="the parameter's designer label (e.g. 'Request Parameters') or its id")
    p.add_argument("--bind", action="append",
                   help="INDEX=variable or INDEX=variable.Attribute (repeatable). The attribute "
                        "is resolved BY NAME against the variable's model, so a typo is refused "
                        "rather than written")
    p.add_argument("--find", help="exact literal to replace first (reaches every string leaf, so "
                                  "it works inside a structured parameter)")
    p.add_argument("--replace", help="replacement literal; unlike node-replace-text it MAY "
                                     "introduce a new placeholder, which is the point")
    p.add_argument("--dry-run", action="store_true",
                   help="edit + validate but do not PUT")


ACTIONS = {
    "node-insert": ActionDef(
        func=node_insert, add_args=_insert_args, needs_client=True,
        description="Insert ONE action into a live process immediately after another, rewiring the "
                    "graph: the new node takes the anchor's successor and the anchor is repointed at "
                    "it -> validate + flow-lint -> PUT. Refuses an anchor with more than one outgoing "
                    "port (which branch it belongs on is a design decision). --dry-run previews."),
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
    "node-bind-var": ActionDef(
        func=node_bind_var, add_args=_bindvar_args, needs_client=True,
        description="Bind a process variable into one node parameter's value: set its variable[] "
                    "so a <%N%> placeholder actually substitutes at runtime. --bind INDEX=variable "
                    "(repeatable); optional --find/--replace turns a mistyped literal token (e.g. a "
                    "text '<%firstName%>' that never resolves) into '<%0%>' in the same write. The "
                    "value's placeholder set must equal the bound set. Regenerates the designer layer "
                    "-> validate + flow-lint -> PUT. --dry-run previews."),
    "node-set-error-port": ActionDef(
        func=node_set_error_port, add_args=_errorport_args, needs_client=True,
        description="Wire ONE node's error port to a handler action on a live process, so a fault "
                    "routes instead of killing the run. Writes all THREE parts the engine needs (the "
                    "type-1 port, the node's variableErrorId, and an isError variable of the error "
                    "datatype); wiring only some of them validates clean and never fires. Reach for it "
                    "when a flow a FORM launches on load must still reach Stop with one section empty. "
                    "The handler is named, never inferred, because it has to tolerate a null input - "
                    "the node's own successor is the usual choice. --clear removes it. Refused on "
                    "Start/Stop/Join/For Each, which have no error port. Validates + flow-lints before "
                    "PUT; --dry-run previews."),
    "node-set-query": ActionDef(
        func=node_set_query, add_args=_setquery_args, needs_client=True,
        description="Replace a Query Store node's STATEMENT and its Data Store chips together on "
                    "a live process, writing the SQL with the same {{ds:Store}} / "
                    "{{col:Store.Column}} tokens a process config uses. This is the edit "
                    "node-set-param cannot make: it holds the `<%N%>` set fixed (those indices "
                    "bind Variable[] positionally), so it refuses a statement that names one more "
                    "column - or names the same column twice, which is unavoidable when a value "
                    "must be rebuilt from several expressions over it, because a placeholder is "
                    "not reusable. Each token occurrence gets its own chip. Refused when the "
                    "node's Parameters map is non-empty, since the map's sources share the index "
                    "sequence. Validates + flow-lints before PUT; --dry-run previews."),
    "node-add-binding": ActionDef(
        func=node_add_binding, add_args=_addbinding_args, needs_client=True,
        description="Add bindings to ONE node parameter, optionally editing its text in the same "
                    "write - the edit neither node-bind-var nor node-replace-text can make. "
                    "node-bind-var takes a STRING parameter and replaces the whole binding list; "
                    "node-replace-text refuses a replacement that contains a <%N%>. This one "
                    "reaches inside a STRUCTURED parameter (an HTTP body template is a dict), may "
                    "introduce a new placeholder, and KEEPS the bindings already there. "
                    "--bind INDEX=variable.Attribute resolves the attribute by NAME against the "
                    "variable's model, so a wrong one is refused with the list of real ones "
                    "instead of binding to nothing at run time. Refuses an edit that leaves a "
                    "<%N%> unbound or a binding unused. Validates + flow-lints before PUT; "
                    "--dry-run previews."),
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
    "variable-add": ActionDef(
        func=variable_add, add_args=_varadd_args, needs_client=True,
        description="Add ONE variable to a live process (name, data type, direction) -> validate + "
                    "flow-lint -> PUT. Safe for existing wiring: everything else addresses variables "
                    "by id, and nothing can already point at an id that did not exist. Refuses a "
                    "duplicate NAME (the form-event tooling resolves names to ids) and an unknown "
                    "direction. --dry-run previews."),
    "variable-set-default": ActionDef(
        func=variable_set_default, add_args=_vardefault_args, needs_client=True,
        description="Set (or --clear) one variable's defaultValue on a live process -> validate + "
                    "flow-lint -> PUT. This is how an input stops being something the caller must "
                    "supply: a File default is honoured on a run that omits it, and the platform "
                    "re-stages the file into that run's own instance. Needs --allow-contract-change "
                    "on an input/output. --json parses the value first (use for a File object)."),
    "variable-set-required": ActionDef(
        func=variable_set_required, add_args=_varrequired_args, needs_client=True,
        description="Set or clear one INPUT variable's isRequired flag on a live process -> validate "
                    "+ flow-lint -> PUT. Clearing it is allowed outright (no existing caller breaks); "
                    "making an optional input required needs --allow-contract-change. Refused on a "
                    "non-input variable. Guard any bare raw placeholder that reads the variable "
                    "(`var f = <%6%>;` -> `[<%6%>][0]`) BEFORE clearing, or an absent value becomes "
                    "a SyntaxError at run time."),
    "process-rename": ActionDef(
        func=process_rename, add_args=_prename_args, needs_client=True,
        description="Rename a live process (its title) -> validate + flow-lint -> PUT. The title is "
                    "cosmetic (wiring is by id), so this is the safe way to give a '... (Copy)' from "
                    "duplicate-process a real name without a desired-state rebuild. --dry-run previews."),
}
