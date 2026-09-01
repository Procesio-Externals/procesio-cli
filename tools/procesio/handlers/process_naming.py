"""Rename the ACTIONS (canvas nodes) of a LIVE process in place.

Fresh flows arrive with every node carrying its template's default label ("Node",
"Call API", "Decisional"), which makes a canvas of a dozen script nodes unreadable —
they are distinguishable only by opening each one. This action sets meaningful labels
in bulk, from an id → name map.

Two fields carry the label and BOTH must move together, or the designer and the API
disagree about what a node is called: the DTO's `ActionName` and `CustomData.name`.
The designer renders `CustomData.name`; list/inspect surfaces read `ActionName`.

Labels are cosmetic — nothing references an action by name. Wiring is by id
(`Ports.SourceId`/`DestinationId`, a Decisional case's `actionid`), so renaming can
never break a flow. The validate gate still runs before the save.

Endpoints (Web-API v1.19, ProcessTemplateController):
  get       GET  /api/Projects/{id}      -> {flow: FlowResponseDto}
  validate  POST /api/Projects/validate  (does NOT persist — a safety gate)
  update    PUT  /api/Projects           (FlowRequestDto; id identifies target)

Workspace-scoped: pass --workspace-id (the GUID after `#` in a designer URL).
Case-insensitive for read AND write, so it handles both a PascalCase export and the
camelCase live DTO.
"""
from __future__ import annotations

import argparse
import copy

from tools.procesio import config
from tools.procesio.actiondef import ActionDef
from tools.procesio.client import parse_json_arg
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged


def _key(d: dict, *names: str):
    """The actual key present in `d` matching any of `names` (case-insensitive)."""
    low = {str(k).lower(): k for k in d}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


def _get(d, *names, default=None):
    k = _key(d, *names) if isinstance(d, dict) else None
    return d[k] if k else default


def _designer_url(client, process_id: str, workspace_id: str | None) -> str:
    # Designer host from the active environment (folded into the profile); defaults
    # to production.
    app_base = config.app_base(client.profile)
    frag = f"#{workspace_id}" if workspace_id else ""
    return f"{app_base}/admin/process/designer/{process_id}{frag}"


def _load_map(args) -> dict:
    """The id → new-name map, from --map (JSON) or --map-file (path to JSON)."""
    if bool(args.map) == bool(args.map_file):
        raise UsageError("pass exactly one of --map (JSON object) or --map-file (path)")
    if args.map_file:
        try:
            with open(args.map_file, encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as e:
            raise UsageError(f"could not read --map-file {args.map_file}: {e}")
        mapping = parse_json_arg(raw, "map-file")
    else:
        mapping = parse_json_arg(args.map, "map")
    if not isinstance(mapping, dict) or not mapping:
        raise UsageError('the map must be a non-empty JSON object: {"<action-id>": "New name"}')
    for k, v in mapping.items():
        if not isinstance(v, str) or not v.strip():
            raise UsageError(f"name for action {k!r} must be a non-empty string (got {v!r})")
    return {str(k): v.strip() for k, v in mapping.items()}


def _resolve(mapping: dict, action_ids: list[str]) -> tuple[dict, list[str], list[str]]:
    """Match map keys to real action ids: exact first, then unique id-prefix.

    Returns (resolved id → name, unknown keys, ambiguous keys). A prefix is accepted
    only when it matches exactly one action, so a truncated id can never rename the
    wrong node.
    """
    by_id = {a.lower(): a for a in action_ids}
    resolved, unknown, ambiguous = {}, [], []
    for key, name in mapping.items():
        k = key.lower()
        if k in by_id:
            resolved[by_id[k]] = name
            continue
        hits = [full for low, full in by_id.items() if low.startswith(k)]
        if len(hits) == 1:
            resolved[hits[0]] = name
        elif len(hits) > 1:
            ambiguous.append(key)
        else:
            unknown.append(key)
    return resolved, unknown, ambiguous


def apply_names(flow: dict, mapping: dict) -> tuple[dict, list[dict], list[str], list[str]]:
    """Return (new flow, changes, unknown keys, ambiguous keys). Never mutates `flow`."""
    new_flow = copy.deepcopy(flow)
    actions = _get(new_flow, "Actions", default=[]) or []
    ids = [str(_get(a, "Id")) for a in actions if _get(a, "Id")]
    resolved, unknown, ambiguous = _resolve(mapping, ids)

    changes = []
    for action in actions:
        aid = str(_get(action, "Id") or "")
        if aid not in resolved:
            continue
        new_name = resolved[aid]
        name_key = _key(action, "ActionName") or "actionName"
        before = action.get(name_key)
        action[name_key] = new_name

        cd_key = _key(action, "CustomData")
        if cd_key and isinstance(action[cd_key], dict):
            cd = action[cd_key]
            cd[_key(cd, "name") or "name"] = new_name

        if before != new_name:
            changes.append({"id": aid, "template": _get(action, "ActionTemplateName"),
                            "from": before, "to": new_name})
    return new_flow, changes, unknown, ambiguous


def _rename_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id whose actions to rename")
    p.add_argument("--map", help='id → name map as JSON: {"<action-id>": "New name", ...}. '
                                 "A unique id PREFIX is accepted in place of a full id.")
    p.add_argument("--map-file", dest="map_file",
                   help="path to a JSON file holding the same id → name map")
    p.add_argument("--no-validate", dest="no_validate", action="store_true",
                   help="skip the POST /api/Projects/validate safety gate before saving")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="report the renames WITHOUT saving (no PUT)")
    add_force_arg(p)


def rename_actions(client, args) -> dict:
    ws = client.workspace_id
    mapping = _load_map(args)
    try:
        res = client.get(f"/api/Projects/{args.id}")
    except ProcesioAPIError as e:
        raise UsageError(f"could not read process {args.id} (workspace {ws}): {e.details}")
    flow = res.get("flow") if isinstance(res, dict) and "flow" in res else res

    new_flow, changes, unknown, ambiguous = apply_names(flow, mapping)
    if ambiguous:
        raise UsageError(f"ambiguous id prefix(es) — they match more than one action: {ambiguous}")
    if unknown:
        raise UsageError(f"no action in process {args.id} matches: {unknown}")

    summary = {
        "process_id": args.id,
        "workspace_id": ws,
        "renamed_count": len(changes),
        "renamed": changes,
        "designer_url": _designer_url(client, args.id, ws),
    }
    if args.dry_run:
        return {"result": {**summary, "saved": False, "dry_run": True}}

    def _refetch():
        r = client.get(f"/api/Projects/{args.id}")
        return r.get("flow") if isinstance(r, dict) and "flow" in r else r
    guard = guard_unchanged(_refetch, flow, force=args.force)   # abort if it moved since read

    validated = None
    if not args.no_validate:
        try:
            client.post("/api/Projects/validate", new_flow)
            validated = True
        except ProcesioAPIError as e:
            raise UsageError(f"renamed flow failed validation (not saved): {e.details}")

    try:
        client.put("/api/Projects", new_flow)
    except ProcesioAPIError as e:
        raise UsageError(f"save (PUT) failed for {args.id}: {e.details}")
    return {"result": {**summary, "validated": validated, "saved": True, "concurrency": guard}}


ACTIONS = {
    "rename-actions": ActionDef(
        func=rename_actions, add_args=_rename_args, needs_client=True,
        description=("Rename a LIVE process's canvas actions in bulk from an id → name map "
                     "(--map JSON or --map-file), setting BOTH ActionName and "
                     "CustomData.name; validates, then saves (PUT /api/Projects). Names are "
                     "cosmetic — wiring is by id — so this cannot break a flow. --dry-run to "
                     "preview. Workspace-scoped: pass --workspace-id."),
    ),
}
