"""SQL Server action hardening: convert inline `N'<%N%>'` string-substitution in Execute Query /
Execute Command nodes (SQL-injection-prone, and the wrong action config) into the safe form —
named `@params` bound via the `Parameters config tab`. See tools/procesio/PROCESIO-SQL-ACTIONS-NOTES.md.

  sql-scan          list a process's SQL nodes with inline-vs-parameterized status (read-only)
  sql-parameterize  convert one node (--node) or every inline node (--all) -> validate -> PUT
                    (--dry-run converts + validates but does not PUT; an invalid flow is never PUT)
  sql-convert       move one node between the Execute Command and Execute Query families, and
                    optionally rebind its Output -> validate + flow-lint -> PUT. Needed whenever a
                    procedure that ends in SELECT sits on a Command node: Command returns
                    rows-affected, so the result set is discarded with no error to show for it.

JSON in / JSON out; impure (live client). Thin, validated wrappers over GET/validate/PUT /api/Projects.
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.flowmodel import sqlparam
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.handlers.fevalidate import run_fe_validation, save_flow


def _enabled(node: dict) -> bool:
    """False if the node is disabled in the designer (so --all never touches a disabled node)."""
    cd = node.get("customData") or {}
    return not (node.get("isDisabled") or node.get("disabled") or cd.get("isDisabled"))


def _fetch_flow(client, pid: str) -> dict:
    flow = client.get(f"/api/Projects/{pid}")
    return flow.get("flow") if isinstance(flow, dict) and "flow" in flow else flow


def _validate(client, flow: dict):
    """(is_valid, errors). Empty 200 == valid (mirrors process-validate)."""
    try:
        res = client.post("/api/Projects/validate", flow)
    except ProcesioAPIError as e:
        det = e.details if isinstance(e.details, dict) else {"body": e.details}
        return False, det.get("body", det)
    empty = (not res) or (isinstance(res, dict) and list(res.keys()) == ["raw_text"] and not res["raw_text"])
    return (True, None) if empty else (False, res)


def _lint(client, flow: dict) -> list[dict]:
    """Designer-layer save-blockers the BE validator does not report (same oracle as flow-lint)."""
    from tools.procesio.handlers.flowlint import _template_sidepanel_ids, lint_flow_dto

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


def sql_scan(client, args) -> dict:
    flow = _fetch_flow(client, args.id)
    return {"id": args.id, "title": flow.get("title"), "sql_nodes": sqlparam.scan(flow)}


def sql_parameterize(client, args) -> dict:
    if not args.node and not args.all:
        raise UsageError("pass --node <label|id> to convert one node, or --all for every inline SQL node")
    flow = _fetch_flow(client, args.id)
    if args.all:
        targets = [a for a in flow.get("actions") or []
                   if sqlparam.is_sql_node(a) and sqlparam.is_inline(a) and _enabled(a)]
    else:
        n = sqlparam.find_node(flow, args.node)
        if not n:
            raise UsageError(f"node not found in process {args.id}: {args.node}")
        targets = [n]

    changes = []
    for n in targets:
        ok, msg = sqlparam.parameterize_node(n)
        changes.append({"node": n.get("actionName"), "id": n.get("id"), "converted": ok, "msg": msg})
    converted = [c for c in changes if c["converted"]]
    result = {"id": args.id, "converted": len(converted), "changes": changes}
    if not converted:
        result["note"] = "nothing to convert (already parameterized or no inline SQL)"
        return result

    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    if not valid:                      # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result
    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    if args.dry_run:
        result["isValid"] = bool(valid and fe["clean"])
        result["put"] = False
        result["dry_run"] = True
        return result
    # The mark is stamped from the FE+BE verdict and then re-read: the platform stores
    # whatever the body carries and never computes this field, so passing the fetched
    # value through would leave a corrected process marked broken.
    saved = save_flow(client, flow, flow_id=args.id, valid=valid and fe["clean"])
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


def _resolve_variable(flow: dict, key: str) -> str:
    """A flow variable's id, from its id or its name. Ambiguity is an error, never a guess."""
    variables = flow.get("variables") or []
    if any(v.get("id") == key for v in variables):
        return key
    matches = [v for v in variables if v.get("name") == key]
    if not matches:
        known = ", ".join(sorted(str(v.get("name")) for v in variables))
        raise UsageError(f"variable not found: {key} (process has: {known})")
    if len(matches) > 1:
        raise UsageError(f"variable name {key!r} is ambiguous - pass its id instead")
    return matches[0]["id"]


def sql_convert(client, args) -> dict:
    target = sqlparam.EQ_TEMPLATE if args.to == "query" else sqlparam.EC_TEMPLATE
    flow = _fetch_flow(client, args.id)
    node = sqlparam.find_node(flow, args.node)
    if not node:
        raise UsageError(f"node not found in process {args.id}: {args.node}")

    changed, msg = sqlparam.convert_family(node, target)
    result = {"id": args.id, "node": node.get("actionName"), "node_id": node.get("id"),
              "to": target, "converted": changed, "msg": msg}

    if args.output_variable:
        var_id = _resolve_variable(flow, args.output_variable)
        rebound, rmsg = sqlparam.rebind_output(node, var_id)
        result["output_rebound"] = rebound
        result["output_msg"] = rmsg
        changed = changed or rebound

    if not changed:
        result["note"] = "nothing to change"
        result["put"] = False
        return result

    valid, errors = _validate(client, flow)
    result["isValid"] = valid
    if not valid:                      # never PUT an invalid flow
        result["errors"] = errors
        result["put"] = False
        return result

    # The BE validator does not see designer save-blockers, and "Execute Query with a null Output"
    # is exactly one of them — the case this conversion is most likely to create.
    problems = _lint(client, flow)
    result["lint_clean"] = not problems
    if problems:
        result["lint_problems"] = problems
        result["put"] = False
        return result

    fe = run_fe_validation(client, flow)
    result["fe"] = fe
    if args.dry_run:
        result["isValid"] = bool(valid and fe["clean"])
        result["put"] = False
        result["dry_run"] = True
        return result
    # The mark is stamped from the FE+BE verdict and then re-read: the platform stores
    # whatever the body carries and never computes this field, so passing the fetched
    # value through would leave a corrected process marked broken.
    saved = save_flow(client, flow, flow_id=args.id, valid=valid and fe["clean"])
    result["isValid"] = saved["isValid"]
    result["stamped"] = saved["stamped"]
    if "readback_error" in saved:
        result["readback_error"] = saved["readback_error"]
    result["put"] = True
    return result


def _scan_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")


def _param_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", help="node actionName or id to convert")
    p.add_argument("--all", action="store_true", help="convert every inline SQL node in the process")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="convert + validate but do not PUT")


def _convert_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id")
    p.add_argument("--node", required=True, help="node actionName or id to convert")
    p.add_argument("--to", required=True, choices=("query", "command"),
                   help="target family: query (returns a result set) or command (returns rows affected)")
    p.add_argument("--output-variable", dest="output_variable",
                   help="flow variable name or id to bind the node's Output to")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="convert + validate + lint but do not PUT")


ACTIONS = {
    "sql-convert": ActionDef(
        func=sql_convert, add_args=_convert_args, needs_client=True,
        description=("Move one SQL node between the Execute Command and Execute Query families "
                     "(--to) and optionally rebind its Output (--output-variable); validate + "
                     "flow-lint then PUT (--dry-run to preview). A SELECT-ing procedure on a Command "
                     "node discards its result set silently - this is the fix.")),
    "sql-scan": ActionDef(
        func=sql_scan, add_args=_scan_args, needs_client=True,
        description="List a process's SQL Server actions (Execute Query/Command) with inline-vs-parameterized status."),
    "sql-parameterize": ActionDef(
        func=sql_parameterize, add_args=_param_args, needs_client=True,
        description="Convert inline N'<%N%>' SQL nodes to safe named-@param binding (--node or --all); validate then PUT (--dry-run to preview)."),
}
