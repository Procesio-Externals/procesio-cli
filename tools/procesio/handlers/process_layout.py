"""Live process operations that pair with the offline layout engine: duplicate a
process, and re-lay-out a LIVE process in place (read → layout → save back).

These bridge the offline `layout-flow` (which operates on a `.procesio` bundle) to the
live Web-API, so you can duplicate a process and apply an auto-layout to the copy without
leaving the tool.

Endpoints (Web-API v1.19, ProcessTemplateController):
  duplicate  POST /api/Projects/{id}/duplicate      -> {hasWebhook}  (no new id returned;
                                                        we diff the project list to find it)
  get        GET  /api/Projects/{id}                 -> {flow: FlowResponseDto}
  validate   POST /api/Projects/validate             (does NOT persist — a safety gate)
  update     PUT  /api/Projects                       (FlowRequestDto; id identifies target)

The re-layout engine is chosen by the LAYOUT_ENGINE env flag (legacy default, `elk`
opt-in) via `layout.dispatch` — set `LAYOUT_ENGINE=elk` for this invocation to use ELK
without changing any config file. The chosen engine is reported in the result.

Both actions are workspace-scoped: pass --workspace-id (the GUID after `#` in a
designer URL, https://procesio.app/admin/process/designer/{id}#{workspaceId}).
"""
from __future__ import annotations

import argparse

from tools.procesio import config
from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, UsageError
from tools.procesio.handlers.common import add_profile_arg
from tools.procesio.layout import adapter, dispatch

def _designer_url(client, process_id: str, workspace_id: str | None) -> str:
    # The designer host comes from the active environment (folded into the profile);
    # defaults to production. Distinct from the Web API host.
    app_base = config.app_base(client.profile)
    frag = f"#{workspace_id}" if workspace_id else ""
    return f"{app_base}/admin/process/designer/{process_id}{frag}"


def _project_ids(client) -> set[str]:
    """All process (project) ids visible in the client's current workspace scope."""
    res = client.get("/api/Projects", {"pageNumber": 1, "pageItemCount": 500})
    items = res.get("pageItems") if isinstance(res, dict) else res
    ids = set()
    for p in (items or []):
        pid = p.get("id") or p.get("Id")
        if pid:
            ids.add(pid)
    return ids


def _flow_of(client, process_id: str) -> dict:
    res = client.get(f"/api/Projects/{process_id}")
    return res.get("flow") if isinstance(res, dict) and "flow" in res else res


# -- duplicate-process ------------------------------------------------------

def _dup_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id to duplicate")


def duplicate_process(client, args) -> dict:
    ws = client.workspace_id
    before = _project_ids(client)
    try:
        dup = client.post(f"/api/Projects/{args.id}/duplicate")
    except ProcesioAPIError as e:
        raise UsageError(f"duplicate failed for {args.id} (workspace {ws}): {e.details}")
    after = _project_ids(client)
    new_ids = sorted(after - before)
    copy_id = new_ids[0] if len(new_ids) == 1 else None
    title = None
    if copy_id:
        try:
            title = _flow_of(client, copy_id).get("title")
        except ProcesioAPIError:
            title = None
    return {"result": {
        "source_id": args.id,
        "workspace_id": ws,
        "copy_id": copy_id,
        "copy_candidates": new_ids if copy_id is None else None,
        "title": title,
        "has_webhook": (dup or {}).get("hasWebhook") if isinstance(dup, dict) else None,
        "designer_url": _designer_url(client, copy_id, ws) if copy_id else None,
    }}


# -- relayout-process -------------------------------------------------------

def _relayout_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id to re-lay-out in place")
    p.add_argument("--no-validate", dest="no_validate", action="store_true",
                   help="skip the POST /api/Projects/validate safety gate before saving")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="compute + return the new layout WITHOUT saving (no PUT)")
    p.add_argument("--no-cluster", dest="cluster", action="store_false", default=True,
                   help="legacy engine: disable clustering (clustering is ON by default — the "
                        "classic engine folds long chains into shelves)")


def relayout_process(client, args) -> dict:
    ws = client.workspace_id
    engine_name = dispatch.selected_engine()   # from LAYOUT_ENGINE env: legacy (default) | elk
    try:
        flow = _flow_of(client, args.id)
    except ProcesioAPIError as e:
        raise UsageError(f"could not read process {args.id} (workspace {ws}): {e.details}")

    # DEFAULT: classic (legacy) engine + clustering ON (the default preference; ELK stays opt-in).
    res = adapter.layout_flow(flow, cluster=getattr(args, "cluster", True))  # engine from LAYOUT_ENGINE
    new_flow = res["bundle"]
    summary = {
        "process_id": args.id,
        "workspace_id": ws,
        "engine": engine_name,
        "nodes_moved": res["nodes_moved"],
        "areas_resized": res["areas_resized"],
        "bbox": res["bbox"],
        "designer_url": _designer_url(client, args.id, ws),
    }
    if args.dry_run:
        return {"result": {**summary, "saved": False, "dry_run": True}}

    validated = None
    if not args.no_validate:
        try:
            client.post("/api/Projects/validate", new_flow)
            validated = True
        except ProcesioAPIError as e:
            raise UsageError(
                f"re-laid-out flow failed validation (not saved): {e.details}")

    try:
        client.put("/api/Projects", new_flow)
    except ProcesioAPIError as e:
        raise UsageError(f"save (PUT) failed for {args.id}: {e.details}")
    return {"result": {**summary, "validated": validated, "saved": True}}


ACTIONS = {
    "duplicate-process": ActionDef(
        func=duplicate_process, add_args=_dup_args, needs_client=True,
        description=("Duplicate a process (POST /api/Projects/{id}/duplicate) and return "
                     "the copy's id + designer URL (found by diffing the workspace's "
                     "project list). Workspace-scoped: pass --workspace-id."),
    ),
    "relayout-process": ActionDef(
        func=relayout_process, add_args=_relayout_args, needs_client=True,
        description=("Re-lay-out a LIVE process in place: read the flow, run the "
                     "auto-layout engine (LAYOUT_ENGINE env: legacy default / elk), "
                     "validate, and save back (PUT /api/Projects). --dry-run to preview "
                     "without saving. Workspace-scoped: pass --workspace-id."),
    ),
}
