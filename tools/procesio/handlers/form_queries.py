"""A form's saved Data Store queries: read them, change one in place, run one.

A form template carries its own SQL statements (top-level `queries`), each bound to
Data Store tables and columns through `<%N%>` tags and taking `@name` parameters. An
element event runs one by id (RUN_DATA_STORE_OPERATION, operation QUERY); the browser
never sends SQL, only the query id and the parameter values.

The write actions are surgical, like form_code.py: GET the live form, change one query,
PUT the whole template back through `build_put_body`. The PUT replaces the template, so
the full list is always sent.

Why the write and run actions are named `saved-statement` and not `query`: the shared
reversibility gate reads an action NAME, and the token `query` is one of its read verbs.
A saved statement can be an INSERT, UPDATE or DELETE, so running one must never be
classed as a read, and neither may the action that rewrites it.

Running goes through the form-runtime route, which is addressed by header
(`formTemplateWorkspaceId`, `formTemplateId`, optional `formInstanceId`). A public form
runs the query as the template owner; a private form needs a signed-in caller working in
the form's workspace, which is the ordinary workspace header this client already sends.
"""
from __future__ import annotations

import argparse
import copy
import uuid

from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.dto.form import queries as form_queries
from tools.procesio.errors import NotPersisted, UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body
from tools.procesio.handlers.formprocess import _json_call


def _queries(form: dict) -> list:
    return list(form.get("queries") or [])


def _elements(form: dict) -> list:
    return (form.get("data") or {}).get("elements") or []


def _save(client, args, form: dict, queries: list) -> dict:
    guard = guard_unchanged(lambda: _fetch(client, args.form_id), form, force=args.force)
    client.put("/api/FormTemplate", build_put_body({**form, "queries": queries}))
    return guard


def _stored(client, form_id: str) -> list | None:
    """The queries the form holds after a save, or None when the read-back is not a form."""
    try:
        return _queries(_fetch(client, form_id))
    except UsageError:
        return None


def get_queries(client, args) -> dict:
    form = _fetch(client, args.form_id)
    queries = _queries(form)
    used = form_queries.references(_elements(form))
    out = {"id": args.form_id, "name": form.get("name"), "count": len(queries),
           "queries": queries,
           "run_by": {q.get("id"): used.get(q.get("id"), []) for q in queries}}
    warnings = form_queries.warnings(queries, _elements(form))
    if warnings:
        out["warnings"] = warnings
    return out


def _read_sql(args):
    if args.sql is not None and args.sql_file:
        raise UsageError("pass either --sql or --sql-file, not both")
    if args.sql_file:
        with open(args.sql_file, encoding="utf-8") as f:
            return f.read()
    return args.sql


def _json_list(raw, what: str):
    if raw is None:
        return None
    value = parse_json_arg(raw, what)
    if not isinstance(value, list):
        raise UsageError(f"{what} must be a JSON array")
    return value


def set_saved_statement(client, args) -> dict:
    sql = _read_sql(args)
    bindings = _json_list(args.bindings, "--bindings")
    parameters = _json_list(args.parameters, "--parameters")
    if args.timeout_seconds is not None and args.clear_timeout:
        raise UsageError("pass either --timeout-seconds or --clear-timeout, not both")

    form = _fetch(client, args.form_id)
    queries = copy.deepcopy(_queries(form))
    ref = args.query_id or args.name
    if not ref:
        raise UsageError("name the query: --name, or --query-id for an existing one")
    current = form_queries.find(queries, args.query_id) if args.query_id \
        else form_queries.find(queries, args.name)
    previous = copy.deepcopy(current)

    if current is None:
        if sql is None or not args.name:
            raise UsageError(f"no saved query {ref!r} on this form; a new one needs "
                             f"--name and --sql (or --sql-file)")
        current = form_queries.from_config(
            {"id": args.query_id or str(uuid.uuid4()), "name": args.name, "sql": sql,
             "bindings": bindings, "parameters": parameters,
             "timeoutSeconds": args.timeout_seconds})
        queries.append(current)
    else:
        if args.name:
            current["name"] = args.name
        if bindings is not None:
            current["variable"] = form_queries.bindings(bindings)
        if sql is not None:
            current["value"] = sql
        if parameters is not None:
            current["parameters"] = parameters
        elif sql is not None:
            current["parameters"] = form_queries.sql_parameters(sql)
        if args.timeout_seconds is not None:
            current["timeoutSeconds"] = args.timeout_seconds
        elif args.clear_timeout:
            current["timeoutSeconds"] = None

    form_queries.check(queries)
    run_by = form_queries.references(_elements(form)).get(current.get("id"), [])
    result = {"id": args.form_id, "name": form.get("name"),
              "created": previous is None, "query": current, "previous": previous,
              "query_count": len(queries), "run_by": run_by}
    warnings = form_queries.warnings([current], _elements(form))
    if warnings:
        result["warnings"] = warnings
    if args.dry_run:
        return {"dry_run": True, **result}

    guard = _save(client, args, form, queries)
    stored = _stored(client, args.form_id)
    if stored is not None and form_queries.find(stored, current["id"]) is None:
        raise NotPersisted(
            "the PUT was accepted but the form does not hold the query. A build without "
            "saved queries ignores the field; otherwise another editor saved the form at "
            "the same time.", {"queryId": current["id"], "stored_queries": len(stored)})
    return {"updated": True, "verified": None if stored is None else True,
            "concurrency": guard, **result}


def delete_saved_statement(client, args) -> dict:
    form = _fetch(client, args.form_id)
    queries = _queries(form)
    target = form_queries.resolve(queries, args.query_id)
    run_by = form_queries.references(_elements(form)).get(target.get("id"), [])
    if run_by and not args.allow_referenced:
        raise UsageError(
            f"query {target.get('name')!r} is still run by an event on {', '.join(map(str, run_by))}; "
            f"rewire or remove those events first, or pass --allow-referenced to remove it "
            f"anyway (the events then fail with 'Query not found for this form template')")
    remaining = [q for q in queries if q is not target]
    result = {"id": args.form_id, "name": form.get("name"), "removed": target,
              "run_by": run_by, "query_count": len(remaining)}
    if args.dry_run:
        return {"dry_run": True, **result}
    guard = _save(client, args, form, remaining)
    stored = _stored(client, args.form_id)
    if stored is not None and form_queries.find(stored, target.get("id")) is not None:
        raise NotPersisted("the PUT was accepted but the form still holds the query",
                           {"queryId": target.get("id")})
    return {"deleted": True, "verified": None if stored is None else True,
            "concurrency": guard, **result}


_SERVER_DEFAULT_TIMEOUT = 60
_CLIENT_MARGIN = 30
_CLIENT_FLOOR = 120


def client_timeout(query: dict) -> int:
    """How long the run waits for an answer: the query's own server limit plus a margin,
    never under the client's usual 120 s. Waiting less than the server would turn a slow
    UPDATE or DELETE that still commits into a reported failure, and a retry of it into a
    second write."""
    limit = query.get("timeoutSeconds")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        limit = _SERVER_DEFAULT_TIMEOUT
    return max(_CLIENT_FLOOR, limit + _CLIENT_MARGIN)


def run_saved_statement(client, args) -> dict:
    params = parse_json_arg(args.params, "--params") if args.params else {}
    if not isinstance(params, dict):
        raise UsageError("--params must be a JSON object of {parameter name: value}")
    form_ws = args.form_workspace_id or client.workspace_id \
        or (client.profile or {}).get("workspace_id")
    if not form_ws:
        raise UsageError("--form-workspace-id is required: the run is scoped by the "
                         "formTemplateWorkspaceId header")

    form = _fetch(client, args.form_id)
    query = form_queries.resolve(_queries(form), args.query_id)
    form_queries.check_parameter_names(query, list(params))
    declared = list(query.get("parameters") or [])

    body = _json_call(
        client, "POST", f"/api/Form/dataStore/query/{query['id']}",
        body={"parameters": params} if params else None,
        headers={"formTemplateWorkspaceId": form_ws, "formTemplateId": args.form_id,
                 "formInstanceId": args.form_instance_id},
        timeout=client_timeout(query))
    rows = (body or {}).get("rows") if isinstance(body, dict) else None
    rows = rows if isinstance(rows, dict) else {}
    return {"form_id": args.form_id, "query_id": query["id"], "query": query.get("name"),
            "parameters_sent": sorted(params),
            "parameters_bound_null": [p for p in declared if p not in params],
            "count": rows.get("totalItemCount"),
            "rows": rows.get("pageItems"),
            "columns": body.get("columns") if isinstance(body, dict) else None,
            "response": body}


def _form_arg(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--form-id", dest="form_id", required=True, help="form template id")


def _write_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="report the change without writing")
    add_force_arg(p)


def _set_args(p: argparse.ArgumentParser) -> None:
    _form_arg(p)
    p.add_argument("--query-id", dest="query_id",
                   help="id of the query to change; with no match it is the new query's id")
    p.add_argument("--name", help="query name: selects the query when --query-id is not "
                                  "given, otherwise renames it")
    p.add_argument("--sql", help="the statement, with a numbered tag for each bound Data "
                                 "Store table or column and @name for each parameter")
    p.add_argument("--sql-file", dest="sql_file", help="path to a file holding the statement")
    p.add_argument("--bindings",
                   help="JSON array, one binding per numbered tag: {id, type: dataStoreTable, "
                        "dataStoreId} or {id, type: dataStoreColumn, dataStoreId, columnId}")
    p.add_argument("--parameters",
                   help="JSON array of the @names the statement takes; when omitted and "
                        "--sql is given they are derived from the statement")
    p.add_argument("--timeout-seconds", dest="timeout_seconds", type=int,
                   help="1..600 (the default is 60)")
    p.add_argument("--clear-timeout", dest="clear_timeout", action="store_true",
                   help="go back to the default timeout")
    _write_args(p)


def _delete_args(p: argparse.ArgumentParser) -> None:
    _form_arg(p)
    p.add_argument("--query-id", dest="query_id", required=True, help="query id or name")
    p.add_argument("--allow-referenced", dest="allow_referenced", action="store_true",
                   help="remove the query even though an element event still runs it")
    _write_args(p)


def _run_args(p: argparse.ArgumentParser) -> None:
    _form_arg(p)
    p.add_argument("--query-id", dest="query_id", required=True, help="query id or name")
    p.add_argument("--params",
                   help="JSON object {parameter: value}, names exactly as the query "
                        "declares them (e.g. {\"@product\": \"apple\"}); a declared "
                        "parameter left out binds NULL")
    p.add_argument("--form-workspace-id", dest="form_workspace_id",
                   help="workspace that owns the form (formTemplateWorkspaceId header); "
                        "defaults to the call's workspace")
    p.add_argument("--form-instance-id", dest="form_instance_id",
                   help="form instance the run belongs to (formInstanceId header)")


ACTIONS = {
    "form-get-queries": ActionDef(
        func=get_queries, add_args=_form_arg, needs_client=True,
        description="Read a form's saved Data Store queries (SQL, tag bindings, declared "
                    "parameters, timeout) and which elements run each one. A query no "
                    "event runs comes back under `warnings`: a designer save drops it.",
    ),
    "form-set-saved-statement": ActionDef(
        func=set_saved_statement, add_args=_set_args, needs_client=True,
        description="Add or change ONE saved Data Store query of a form in place (surgical: "
                    "the other queries and the form's content are untouched). Selects by "
                    "--query-id, else by --name; no match creates it. Omitted fields keep "
                    "their value; a new --sql without --parameters re-derives the @names. "
                    "Checks tags against bindings, parameter names, timeout and duplicate "
                    "ids/names before the save, then reads the form back. Returns the "
                    "previous query. Wire the query to an event (operation QUERY) or the "
                    "next designer save drops it.",
    ),
    "form-delete-saved-statement": ActionDef(
        func=delete_saved_statement, add_args=_delete_args, needs_client=True,
        description="Remove one saved Data Store query from a form (by id or name). Refused "
                    "while an element event still runs it, unless --allow-referenced. "
                    "Returns the removed query.",
    ),
    "form-run-saved-statement": ActionDef(
        func=run_saved_statement, add_args=_run_args, needs_client=True,
        description="RUN one of a form's saved Data Store queries the way the form does "
                    "(POST api/Form/dataStore/query/{id}). NOT read-only: the statement "
                    "can be an INSERT, UPDATE or DELETE, and it runs for real. --params "
                    "names are checked against the declared ones first. Returns rows "
                    "(keyed by column display name), columns and count; for a write, "
                    "count is the affected rows and rows is empty.",
    ),
}
