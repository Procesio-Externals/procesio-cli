"""Curated Data Store actions — PROCESIO's user-defined dynamic data tables.

A *data store* is a typed table (columns backed by a data model); tenants read and
write its rows over the Web-Api DataStore surface, which proxies to the Data-Store
service. Rows are JSON dicts keyed by **column display name** (never the internal
alias). This handler wraps the surface so a user or agent gets typed create / row
CRUD / CSV actions instead of dropping to the untyped generic `request`.

Verified routes (Web-Api, tags DataStore; permission entity in parens):
  Metadata / schema — entity `DataStoreSchema`
    create          POST   /api/DataStore                       (DataStoreSchema.Write)
    update          PUT    /api/DataStore                       (DataStoreSchema.Update)
    modify-column   PATCH  /api/DataStore/{id}/column           (DataStoreSchema.Update)
    delete          DELETE /api/DataStore/{id}                  (DataStoreSchema.Delete)
    get             GET    /api/DataStore/{id}                  (DataStoreSchema.Read)
    list            GET    /api/DataStore                       (DataStoreSchema.Read)
    from-data-model POST   /api/DataStore/from-data-model       (DataStoreSchema.Write)
    from-json       POST   /api/DataStore/from-json             (DataStoreSchema.Write)
    get-data-model  GET    /api/DataStore/{id}/data-model       (DataStoreSchema.Read)
    list-restricted GET    /api/DataStore/restricted            (DataStoreSchema.Read)
  Rows — entity `DataStoreRows`
    get-rows        POST   /api/DataStore/{id}/rows/filter      (DataStoreRows.Read)
    add-rows        POST   /api/DataStore/{id}/rows             (DataStoreRows.Create)
    update-row      PUT    /api/DataStore/{id}/rows             (DataStoreRows.Update)
    delete-rows     DELETE /api/DataStore/{id}/rows             (DataStoreRows.Delete)
  CSV jobs — entity `DataStoreRows`
    export-start    POST   /api/DataStore/{id}/export-start
    export-download GET    /api/DataStore/{id}/export-download/{jobId}
    import-start    POST   /api/DataStore/{id}/import-start      (multipart)
    import-failures GET    /api/DataStore/{id}/import-failures/{jobId}

CONTRACT (verified against PROCESIO/Web-Api main, 2026-08 — the "unified row filters"
design):
  * READ is `POST .../rows/filter` with **pagination on the QUERY STRING**
    (`?pageNumber=&pageItemCount=`) and an optional body `InternalDataStoreGetRowsDto`:
      {"filter": <group>, "sort": [{"column","direction"}]}   (send no body -> read all)
    where <group> is a RECURSIVE filter tree:
      group     = {"id","logic"(0 NONE|1 AND|2 OR),"items":[node]}
      node      = {"id","type"(1 Condition|2 Group),"logic",
                   "condition":<condition> | "group":<group>}
      condition = {"id","column","operator"(QueryOperators 0..20),"value","auxValue"?}
    `auxValue` is the 2nd bound for Between/NotBetween; In/NotIn take a list `value`;
    IsNull/IsNotNull/IsTrue/IsFalse take no value.
  * UPDATE `PUT .../rows` body = {"values":{col:val}, "filter":<group>} (filter MANDATORY).
  * DELETE `DELETE .../rows` body = {"filter":<group>} (filter MANDATORY).
  * ADD `POST .../rows` body = {"rows":[{displayName:value}]}.
Rows are keyed by column DISPLAY name everywhere. For advanced/nested trees pass a raw
`--filter '<group json>'` (sent verbatim); `--filters` builds a flat AND/OR group from
simple conditions. JSON in / JSON out; impure (live client).
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_paging_args, add_profile_arg

# QueryOperators — the filter operator enum used by the row filter tree, shared verbatim
# across Web-Api / Process-Execution / Data-Store (Domain/Enums/DataStore/Filter/
# QueryOperators.cs). Numeric values are the wire form. Names matched case-insensitively.
_OPERATORS = {
    "none": 0, "equals": 1, "notequals": 2, "greaterthan": 3,
    "greaterthanorequal": 4, "lessthan": 5, "lessthanorequal": 6, "between": 7,
    "notbetween": 8, "like": 9, "notlike": 10, "in": 11, "notin": 12,
    "isnull": 13, "isnotnull": 14, "istrue": 15, "isfalse": 16, "contains": 17,
    "notcontains": 18, "startswith": 19, "endswith": 20,
}
_LOGIC = {"none": 0, "and": 1, "or": 2}                       # LogicOperators
_SORT_DIRECTIONS = {"none": 0, "asc": 1, "ascending": 1,      # SortDirection
                    "desc": 2, "descending": 2}
_NODE_CONDITION = 1                                           # DataStoreFilterNodeType
_NODE_GROUP = 2

# DataStore table create/alter/drop provisions a physical MySQL table server-side and
# can take 1-3 minutes — well past the default 60s read / 180s write deadline. Give those
# lifecycle ops a longer budget; row reads/writes are fast and keep the default.
_PROVISION = {"read_timeout": 300, "deadline": 300}


def _resolve_operator(raw) -> int:
    """Accept an operator as a name (case-insensitive, e.g. 'Contains') or a raw
    numeric value; return the numeric QueryOperators value (0..20)."""
    if isinstance(raw, bool):
        raise UsageError("filter operator must be an operator name or number")
    if isinstance(raw, int):
        return raw
    key = str(raw).strip().lower().replace("_", "").replace(" ", "")
    if key.isdigit():
        return int(key)
    if key not in _OPERATORS:
        raise UsageError(
            f"unknown filter operator {raw!r}; expected one of "
            f"{', '.join(sorted(_OPERATORS))} (or a numeric value)")
    return _OPERATORS[key]


def _resolve_logic(raw) -> int:
    if isinstance(raw, int):
        return raw
    key = str(raw or "and").strip().lower()
    if key.isdigit():
        return int(key)
    return _LOGIC.get(key, 1)


def _resolve_direction(raw) -> int:
    if isinstance(raw, int):
        return raw
    key = str(raw).strip().lower()
    if key.isdigit():
        return int(key)
    return _SORT_DIRECTIONS.get(key, 1)


# -- filter tree builders ----------------------------------------------------

def _build_condition(f: dict, idx: int) -> dict:
    if not isinstance(f, dict):
        raise UsageError("each filter must be an object {column, operator, value}")
    col = f.get("column") or f.get("displayName") or f.get("name")
    if not col:
        raise UsageError("each filter needs a 'column' (the column display name)")
    cond = {"id": idx, "column": col,
            "operator": _resolve_operator(f.get("operator", "equals")),
            "value": f.get("value")}
    if "auxValue" in f or "aux" in f:
        cond["auxValue"] = f.get("auxValue", f.get("aux"))
    return cond


def _build_group(filters, logic: int) -> dict:
    """Build a flat DataStoreQueryFilterGroupDto from a list of simple conditions
    [{column, operator, value, auxValue?}] combined by `logic` (AND/OR)."""
    items = []
    for i, f in enumerate(filters or []):
        items.append({"id": i, "type": _NODE_CONDITION, "logic": logic,
                      "condition": _build_condition(f, i)})
    return {"id": 0, "logic": logic, "items": items}


def _filter_from_args(args):
    """Resolve a filter group from --filter (raw group JSON, verbatim) or --filters
    (simple condition list) + --logic. Returns the group dict or None."""
    raw = getattr(args, "filter", None)
    if raw:
        return parse_json_arg(raw, "filter")
    simple = parse_json_arg(getattr(args, "filters", None), "filters")
    if simple:
        if not isinstance(simple, list):
            raise UsageError("--filters must be a JSON array of {column,operator,value}")
        return _build_group(simple, _resolve_logic(getattr(args, "logic", "and")))
    return None


def _build_sort(raw) -> list:
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out = []
    for s in items:
        if not isinstance(s, dict):
            raise UsageError("sort must be an object or a list of objects")
        out.append({"column": s.get("column") or s.get("displayName") or s.get("name"),
                    "direction": _resolve_direction(s.get("direction", "asc"))})
    return out


def _add_filter_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--filters",
                   help='simple conditions as JSON: [{"column","operator"(name or number),'
                        '"value","auxValue"?}] combined by --logic. operator names: '
                        "equals/contains/startsWith/greaterThan/between/in/isNull/... (QueryOperators)")
    p.add_argument("--filter",
                   help="raw filter GROUP as JSON (a full recursive DataStoreQueryFilterGroupDto: "
                        '{"id","logic","items":[...]}) sent verbatim; overrides --filters')
    p.add_argument("--logic", default="and", help="how --filters combine: and | or (default and)")


# -- metadata / schema ------------------------------------------------------

def _create_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--payload", required=True,
                   help="DataStoreMetadataDto as JSON: "
                        '{"name","description"?,"columns"?:[{"name","dataTypeId",'
                        '"isList"?,"isPrimaryKey"?,"isRequired"?}]}')


def datastore_create(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.post("/api/DataStore", body, **_PROVISION)}


def datastore_update(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.put("/api/DataStore", body, **_PROVISION)}


def _modify_column_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--payload", required=True,
                   help='DataStoreModifyColumnDto as JSON: '
                        '{"originalColumn":{...},"updatedColumn":{...}}')


def datastore_modify_column(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.patch(f"/api/DataStore/{args.id}/column", body, **_PROVISION)}


def _id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")


def datastore_delete(client, args) -> dict:
    return {"result": client.delete(f"/api/DataStore/{args.id}", **_PROVISION)}


def datastore_get(client, args) -> dict:
    return {"result": client.get(f"/api/DataStore/{args.id}")}


def datastore_get_data_model(client, args) -> dict:
    return {"result": client.get(f"/api/DataStore/{args.id}/data-model")}


def _list_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--search", help="filter by name (searchName), if supported")


def datastore_list(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "searchName": args.search}
    return {"result": client.get("/api/DataStore", q)}


def datastore_list_restricted(client, args) -> dict:
    return {"result": client.get("/api/DataStore/restricted")}


def _from_data_model_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--payload", required=True,
                   help='DataStoreFromDataModelDto as JSON: {"dataModelId","name",'
                        '"description"?,"primaryKeyAttributeIds"?:[...]}')


def datastore_from_data_model(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.post("/api/DataStore/from-data-model", body, **_PROVISION)}


def _from_json_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--payload", required=True,
                   help='DataStoreFromJsonDto as JSON: {"name","description"?,'
                        '"content":"<raw JSON or a JSON-returning URL>",'
                        '"primaryKeyAttributeNames"?:[...]}')


def datastore_from_json(client, args) -> dict:
    body = parse_json_arg(args.payload, "payload")
    return {"result": client.post("/api/DataStore/from-json", body, **_PROVISION)}


# -- rows -------------------------------------------------------------------

def _get_rows_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    add_paging_args(p)
    _add_filter_args(p)
    p.add_argument("--sort",
                   help='sort as JSON: {"column","direction":"asc"|"desc"} '
                        "(or a list of such objects)")
    p.add_argument("--body",
                   help="raw request body JSON sent verbatim to POST .../rows/filter "
                        "(overrides --filters/--filter/--sort; pagination stays on the query string)")


def datastore_get_rows(client, args) -> dict:
    # Pagination is on the QUERY STRING; the body carries only filter + sort.
    q = {"pageNumber": args.page or 1, "pageItemCount": args.page_size or 50}
    if args.body:
        body = parse_json_arg(args.body, "body")
    else:
        body = {}
        flt = _filter_from_args(args)
        if flt is not None:
            body["filter"] = flt
        sort = _build_sort(parse_json_arg(args.sort, "sort"))
        if sort:
            body["sort"] = sort
        body = body or None            # empty body allowed -> read all rows
    return {"result": client.post(f"/api/DataStore/{args.id}/rows/filter", body, q)}


def _add_rows_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--rows", required=True,
                   help='rows as a JSON array of dicts keyed by column DISPLAY name: '
                        '[{"Name":"...","Status":"..."}]')


def datastore_add_rows(client, args) -> dict:
    rows = parse_json_arg(args.rows, "rows")
    if not isinstance(rows, list):
        raise UsageError("--rows must be a JSON array of row objects")
    return {"result": client.post(f"/api/DataStore/{args.id}/rows", {"rows": rows})}


def _update_row_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--values", help='columns to set, as a JSON object '
                                    '{"Status":"Done"} (keyed by display name)')
    _add_filter_args(p)
    p.add_argument("--body", help="raw DataStoreUpdateRowRequestDto JSON sent verbatim "
                                  "(overrides --values/--filter)")


def datastore_update_row(client, args) -> dict:
    if args.body:
        body = parse_json_arg(args.body, "body")
    else:
        values = parse_json_arg(args.values, "values")
        if not values:
            raise UsageError("update-row needs --values (columns to set)")
        flt = _filter_from_args(args)
        if not flt:
            raise UsageError("update-row needs a --filter/--filters selecting the rows "
                             "(a non-empty filter is mandatory)")
        body = {"values": values, "filter": flt}
    return {"result": client.put(f"/api/DataStore/{args.id}/rows", body)}


def _delete_rows_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    _add_filter_args(p)
    p.add_argument("--body", help="raw DataStoreDeleteRowsRequestDto JSON sent verbatim "
                                  "(overrides --filter)")


def datastore_delete_rows(client, args) -> dict:
    if args.body:
        body = parse_json_arg(args.body, "body")
    else:
        flt = _filter_from_args(args)
        if not flt:
            raise UsageError("delete-rows needs a --filter/--filters selecting the rows "
                             "(a non-empty filter is mandatory)")
        body = {"filter": flt}
    # DELETE carries a JSON body here, so go through request() directly —
    # client.delete()'s 2nd arg is query, not body.
    return {"result": client.request("DELETE", f"/api/DataStore/{args.id}/rows",
                                     body=body)}


# -- CSV import / export ----------------------------------------------------

def _export_start_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")


def datastore_export_start(client, args) -> dict:
    # export-start takes no body (includeSystemColumns is server-side false).
    return {"result": client.post(f"/api/DataStore/{args.id}/export-start", None)}


def _export_download_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--job-id", dest="job_id", required=True, help="CSV export jobId")
    p.add_argument("--out", required=True, help="local path to write the CSV to")


def datastore_export_download(client, args) -> dict:
    status, content, _ = client.request_bytes(
        "GET", f"/api/DataStore/{args.id}/export-download/{args.job_id}")
    if not (200 <= status < 300):
        raise ProcesioAPIError(int(status or 0), f"HTTP {status}",
                               {"body": content[:500].decode("utf-8", "replace")})
    out = Path(args.out)
    out.write_bytes(content)
    return {"result": {"out": str(out), "bytes": len(content)}}


def _import_start_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--file", required=True, help="local CSV file to import")


def datastore_import_start(client, args) -> dict:
    path = Path(args.file)
    if not path.is_file():
        raise UsageError(f"file not found: {path}")
    files = {"file": (path.name, path.read_bytes(), "text/csv")}
    return {"result": client.request_multipart(
        f"/api/DataStore/{args.id}/import-start", files=files)}


def _import_failures_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data store id (dataStoreId)")
    p.add_argument("--job-id", dest="job_id", required=True, help="CSV import jobId")


def datastore_import_failures(client, args) -> dict:
    return {"result": client.get(
        f"/api/DataStore/{args.id}/import-failures/{args.job_id}")}


ACTIONS = {
    "datastore-create": ActionDef(
        func=datastore_create, add_args=_create_args, needs_client=True,
        description="Create a data store (POST /api/DataStore) from a JSON --payload."),
    "datastore-update": ActionDef(
        func=datastore_update, add_args=_create_args, needs_client=True,
        description="Update a data store's metadata (PUT /api/DataStore) from --payload (include id)."),
    "datastore-modify-column": ActionDef(
        func=datastore_modify_column, add_args=_modify_column_args, needs_client=True,
        description="Modify one column (PATCH /api/DataStore/{id}/column) from --payload."),
    "datastore-delete": ActionDef(
        func=datastore_delete, add_args=_id_args, needs_client=True,
        description="Delete a data store (DELETE /api/DataStore/{id})."),
    "datastore-get": ActionDef(
        func=datastore_get, add_args=_id_args, needs_client=True,
        description="Get a data store's metadata (GET /api/DataStore/{id})."),
    "datastore-list": ActionDef(
        func=datastore_list, add_args=_list_args, needs_client=True,
        description="List data stores (GET /api/DataStore)."),
    "datastore-list-restricted": ActionDef(
        func=datastore_list_restricted, add_args=add_profile_arg, needs_client=True,
        description="List data stores the caller is restricted to (GET /api/DataStore/restricted)."),
    "datastore-from-data-model": ActionDef(
        func=datastore_from_data_model, add_args=_from_data_model_args, needs_client=True,
        description="Create a data store from an existing data model (POST /api/DataStore/from-data-model)."),
    "datastore-from-json": ActionDef(
        func=datastore_from_json, add_args=_from_json_args, needs_client=True,
        description="Create a data store from raw JSON / a JSON URL (POST /api/DataStore/from-json)."),
    "datastore-get-data-model": ActionDef(
        func=datastore_get_data_model, add_args=_id_args, needs_client=True,
        description="Get the data model backing a data store (GET /api/DataStore/{id}/data-model)."),
    "datastore-get-rows": ActionDef(
        func=datastore_get_rows, add_args=_get_rows_args, needs_client=True,
        description="Read rows (POST /api/DataStore/{id}/rows/filter): paging on the query "
                    "string, filter tree + sort in the body (--filters/--filter/--sort)."),
    "datastore-add-rows": ActionDef(
        func=datastore_add_rows, add_args=_add_rows_args, needs_client=True,
        description="Insert rows (POST /api/DataStore/{id}/rows) from a JSON --rows array."),
    "datastore-update-row": ActionDef(
        func=datastore_update_row, add_args=_update_row_args, needs_client=True,
        description="Update rows (PUT /api/DataStore/{id}/rows) — set --values on rows a "
                    "--filter/--filters selects (filter mandatory)."),
    "datastore-delete-rows": ActionDef(
        func=datastore_delete_rows, add_args=_delete_rows_args, needs_client=True,
        description="Delete rows (DELETE /api/DataStore/{id}/rows) a --filter/--filters "
                    "selects (filter mandatory)."),
    "datastore-export-start": ActionDef(
        func=datastore_export_start, add_args=_export_start_args, needs_client=True,
        description="Start a CSV export job (POST /api/DataStore/{id}/export-start)."),
    "datastore-export-download": ActionDef(
        func=datastore_export_download, add_args=_export_download_args, needs_client=True,
        description="Download a finished CSV export (GET /api/DataStore/{id}/export-download/{jobId}) to --out."),
    "datastore-import-start": ActionDef(
        func=datastore_import_start, add_args=_import_start_args, needs_client=True,
        description="Start a CSV import job (POST /api/DataStore/{id}/import-start) from a --file."),
    "datastore-import-failures": ActionDef(
        func=datastore_import_failures, add_args=_import_failures_args, needs_client=True,
        description="Get a CSV import job's failures (GET /api/DataStore/{id}/import-failures/{jobId})."),
}
