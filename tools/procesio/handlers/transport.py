"""Transport: export selected components to a `.procesio` bundle.

Wraps `POST /api/Transport/export-entities` (requires Workspace.Admin -> use the
userpass `account` profile). Accepts component **names, ids, or `all`** per type
and resolves names -> ids against the scoped workspace, builds the selection DTO,
exports, and saves the raw `.procesio` file. Credentials are excluded unless you
ask for them.

Verified end to end 2026-06-23 (see PROCESIO-API-NOTES.md).
"""
from __future__ import annotations

import argparse
import json
import re

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg

_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# cli arg (dest) -> (export body key, list endpoint, extra query, name fields)
_RESOLVE = {
    "data_models": ("dataModelIds", "/api/DataTypes",
                    {"includeProcesioEntries": "false", "includeExternalEntries": "true"},
                    ("name", "Name")),
    "processes":   ("flowIds", "/api/Projects", {}, ("title", "name")),
    "documents":   ("documentIds", "/api/DocumentTemplate", {}, ("name", "Name")),
    "webhooks":    ("webhookIds", "/api/Webhooks", {}, ("name", "Name")),
    "forms":       ("formIds", "/api/FormTemplate", {}, ("name", "Name")),
    "credentials": ("credentialIds", "/api/Credentials", {}, ("name", "Name")),
    # Data stores are a first-class export category: `ExportEntitiesDto` carries
    # `dataStoreIds`, the header form of the endpoint takes `exportDataStores`,
    # the import endpoint takes `importDataStores`, and the pack format has a
    # `DataStores` section. Omitting this entry meant `export` never asked for a
    # store, so a pack silently arrived without one - and a referencing process
    # travelled carrying a store id the receiving workspace does not have.
    "data_stores": ("dataStoreIds", "/api/DataStore", {}, ("name", "Name")),
}
_BODY_KEYS = [v[0] for v in _RESOLVE.values()]


def _list_all(client, path, extra) -> list[dict]:
    q = {"pageNumber": 1, "pageItemCount": 500}
    q.update(extra)
    res = client.get(path, q)
    if isinstance(res, list):
        return res
    if isinstance(res, dict):
        for k in ("pageItems", "data", "items", "List"):
            if isinstance(res.get(k), list):
                return res[k]
    return []


def _id_of(item: dict):
    return item.get("id") or item.get("Id") or item.get("gid") or item.get("Gid")


def _resolve(client, spec: str, path, extra, namekeys) -> tuple[list, dict]:
    spec = (spec or "").strip()
    if not spec:
        return [], {}
    if spec.lower() == "all":
        items = _list_all(client, path, extra)
        return [_id_of(it) for it in items if _id_of(it)], {"all": True, "matched": len(items)}
    items = None
    ids, matched, unresolved = [], {}, []
    for tok in [t.strip() for t in spec.split(",") if t.strip()]:
        if _GUID.match(tok):
            ids.append(tok)
            matched[tok] = tok
            continue
        if items is None:
            items = _list_all(client, path, extra)
        found = None
        for it in items:
            if any(str(it.get(nk, "")).strip().lower() == tok.lower() for nk in namekeys):
                found = _id_of(it)
                break
        if found:
            ids.append(found)
            matched[tok] = found
        else:
            unresolved.append(tok)
    if unresolved:
        raise UsageError(f"could not resolve names in {path}: {unresolved}")
    return ids, matched


def _export_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--data-models", dest="data_models",
                   help="data-model names/ids/all (comma-separated)")
    p.add_argument("--processes", help="process names (title)/ids/all (comma-separated)")
    p.add_argument("--documents", help="document names/ids/all (comma-separated)")
    p.add_argument("--webhooks", help="webhook names/ids/all (comma-separated)")
    p.add_argument("--forms", help="form names/ids/all (comma-separated)")
    p.add_argument("--credentials",
                   help="credential names/ids/all (default: none — excluded)")
    p.add_argument("--data-stores", dest="data_stores",
                   help="data-store names/ids/all (comma-separated). A process "
                        "that reads or writes a store does NOT carry the store "
                        "itself — name it here or the pack arrives with a "
                        "dangling reference")
    p.add_argument("--export-sensitive-data", dest="export_sensitive_data",
                   action="store_true", help="include credential secrets (default off)")
    p.add_argument("--output", help="output .procesio path (default procesio-export.procesio)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="resolve names + build the selection, but do not export or save")


def export(client, args) -> dict:
    if not client.workspace_id and not client.profile.get("workspace_id"):
        raise UsageError("export is workspace-scoped — pass --workspace-id <ws>")
    body = {"exportSensitiveData": bool(args.export_sensitive_data)}
    resolved = {}
    for dest, (bodykey, path, extra, namekeys) in _RESOLVE.items():
        spec = getattr(args, dest, None)
        ids, matched = _resolve(client, spec, path, extra, namekeys)
        body[bodykey] = ids
        if spec:
            resolved[dest] = {"spec": spec, "ids": ids, "matched": matched}
    for k in _BODY_KEYS:
        body.setdefault(k, [])
    if not any(body[k] for k in _BODY_KEYS):
        raise UsageError("nothing selected to export — pass at least one of "
                         "--data-models/--processes/--documents/--webhooks/"
                         "--forms/--credentials/--data-stores")
    if args.dry_run:
        return {"dry_run": True, "workspace_id": client.workspace_id,
                "resolved": resolved, "body": body}

    status, content, _headers = client.request_bytes(
        "POST", "/api/Transport/export-entities", body=body)
    if not (200 <= status < 300):
        raise ProcesioAPIError(status, "export failed",
                               {"body": content[:300].decode("utf-8", "replace")})
    out = args.output or "procesio-export.procesio"
    with open(out, "wb") as f:
        f.write(content)
    sections = {}
    try:
        doc = json.loads(content)
        for sec in ("DataTypes", "Flows", "DocumentTemplates", "Credentials",
                    "Webhooks", "Forms", "DataStores"):
            sections[sec] = len(doc.get(sec, []) or [])
    except Exception:  # noqa: BLE001
        sections = {"_note": "saved, but response was not parseable JSON"}
    return {"saved": out, "bytes": len(content), "workspace_id": client.workspace_id,
            "sections": sections, "resolved": resolved}


# ---------------------------------------------------------------------------
# Data Store mapper repair
#
# The platform's EXPORT re-spells every Data Store mapper row into the Call
# SubProcess wire shape, and the import does not translate it back. Nothing is
# lost - the column name and the variable GUID both survive under different
# keys - so the pack passes every structural check while carrying a process
# that CANNOT RUN. It fails only on execution, with
#     "A Data Store Decisional column reference cannot be null or empty."
#
#     in a pack  {"id": i, "process": "<flowId>.<variableId>",
#                 "document": "<COLUMN NAME>"}
#     accepted   {"id": i, "source": {"value": "<%i%>",
#                                     "variable": [{"id": i, "variableId": g,
#                                                   "attribute": None}]},
#                 "column": "<COLUMN NAME>"}
#
# The transform is IDEMPOTENT on purpose: a row already carrying `column` is
# passed through untouched, so if the export is ever fixed this becomes a
# no-op rather than corrupting a correct pack.
# ---------------------------------------------------------------------------

def _repair_mapper_rows(rows: list) -> tuple[list, int]:
    """Rewrite exported mapper rows into the shape the back end accepts."""
    out, changed = [], 0
    for row in rows:
        if not isinstance(row, dict) or "document" not in row:
            out.append(row)                      # already accepted, or not a mapper row
            continue
        i = row.get("id", 0)
        variable_id = str(row.get("process") or "").split(".")[-1]
        out.append({
            "id": i,
            # the placeholder index matches the id INSIDE its own inline array
            "source": {"value": "<%%%d%%>" % i,
                       "variable": [{"id": i, "variableId": variable_id,
                                     "attribute": None}]},
            "column": row.get("document"),
        })
        changed += 1
    return out, changed


def _is_mapper_value(value) -> bool:
    return (isinstance(value, list) and bool(value)
            and all(isinstance(r, dict) for r in value)
            and any("document" in r or "column" in r for r in value))


def repair_datastore_mapper_pack(pack: dict) -> tuple[dict, int]:
    """Return (repaired copy, rows changed). The input is never mutated."""
    out = json.loads(json.dumps(pack))
    changed = 0
    for flow in out.get("Flows") or []:
        for action in flow.get("Actions") or []:
            for param in action.get("Parameters") or []:
                value = param.get("Value")
                if not _is_mapper_value(value):
                    continue
                rows, n = _repair_mapper_rows(value)
                if n:
                    param["Value"] = rows
                    # the variable array belongs INSIDE the source operand.
                    # The parameter's own list stays empty.
                    param["Variable"] = param.get("Variable") or []
                    changed += n
    return out, changed


def _repair_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--in", dest="in_path", required=True,
                   help="the .procesio pack to repair (a path, or '-' for stdin)")
    p.add_argument("--out", dest="out_path",
                   help="write the repaired pack here (omit to print it)")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="report what would change without writing anything")


def repair_datastore_mapper(args) -> dict:
    import sys as _sys
    from pathlib import Path as _Path

    if args.in_path == "-":
        raw = _sys.stdin.read()
    else:
        src = _Path(args.in_path)
        if not src.is_file():
            raise UsageError("--in is not a readable file: %s" % args.in_path)
        raw = src.read_text(encoding="utf-8")
    try:
        pack = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError("--in is not valid JSON: %s" % e)

    repaired, changed = repair_datastore_mapper_pack(pack)
    blob = json.dumps(repaired, ensure_ascii=False)
    result = {"rows_repaired": changed,
              "already_correct": changed == 0,
              "spelling_counts": {k: blob.count('"%s"' % k)
                                  for k in ("column", "source",
                                            "document", "process")},
              "idempotent": True}
    if args.dry_run:
        result["written"] = None
        result["dry_run"] = True
        return {"result": result}
    if args.out_path:
        _Path(args.out_path).write_text(blob, encoding="utf-8")
        result["written"] = args.out_path
    else:
        result["pack"] = repaired
        result["written"] = None
    return {"result": result}


ACTIONS = {
    "export": ActionDef(
        func=export, add_args=_export_args, needs_client=True,
        description=("Export components to a .procesio file (Transport). Accepts "
                     "names/ids/all per type; credentials excluded by default; "
                     "--dry-run to preview the selection."),
    ),
    "repair-datastore-mapper": ActionDef(
        func=repair_datastore_mapper, add_args=_repair_args, needs_client=False,
        description=("Repair a .procesio pack whose Data Store mapper the export "
                     "re-spelled into the refused `document`/`process` form "
                     "(offline). An imported process carrying the exported form "
                     "cannot run. Idempotent: an already-correct pack is "
                     "unchanged."),
    ),
}
