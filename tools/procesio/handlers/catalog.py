"""Curated read actions for workspaces, data types, the action catalog, stored
connection credentials, and API keys. All are safe GETs over exact v1.19 paths.
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.flowmodel import families
from tools.procesio.handlers.common import add_paging_args, add_profile_arg


def list_workspaces(client, _args) -> dict:
    return {"result": client.get("/api/Workspaces")}


def _subworkspaces_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--parent-id", dest="parent_id", required=True,
                   help="master workspace GUID whose sub-workspaces to list")
    p.add_argument("--include-removed", dest="include_removed", action="store_true",
                   help="include soft-deleted (workspaceState='removed') workspaces")


def list_subworkspaces(client, args) -> dict:
    """Sub-workspaces of a master. ACTIVE-ONLY by default — the raw endpoint also
    returns soft-deleted ones (workspaceState='removed'), which the UI hides.
    Needs owner/admin context (use the userpass `account` profile)."""
    q = {"pageNumber": args.page, "pageItemCount": args.page_size}
    res = client.get(f"/api/Workspace/{args.parent_id}/subworkspaces", q)
    rows = res.get("pageItems") if isinstance(res, dict) else res
    rows = rows if isinstance(rows, list) else []
    if not args.include_removed:
        rows = [w for w in rows if str(w.get("workspaceState", "")).lower() != "removed"]
    return {"parent_id": args.parent_id, "count": len(rows),
            "include_removed": bool(args.include_removed), "workspaces": rows}


def _ws_users_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--target-workspace", dest="target_workspace",
                   help="targetWorkspace id (sub-workspace)")


def list_workspace_users(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "targetWorkspace": args.target_workspace}
    return {"result": client.get("/api/Workspace/users", q)}


def _search_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    add_paging_args(p)
    p.add_argument("--search", help="searchName filter")


def list_datatypes(client, args) -> dict:
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "searchName": args.search}
    return {"result": client.get("/api/DataTypes", q)}


def _actions_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--filter", dest="action_filter", help="actionFilter value")
    p.add_argument("--full", action="store_true", help="getFullAction=true")
    p.add_argument("--by-family", dest="by_family", action="store_true",
                   help="group the catalog by family (control/scripting/data/integration/…)")
    p.add_argument("--family", help="return only one family's actions")


def list_actions_catalog(client, args) -> dict:
    q = {"actionFilter": args.action_filter,
         "getFullAction": "true" if args.full else None}
    res = client.get("/api/Actions", q)
    if not (getattr(args, "by_family", False) or getattr(args, "family", None)):
        return {"result": res}
    items = res.get("actions") if isinstance(res, dict) else res
    items = items if isinstance(items, list) else []
    buckets: dict[str, list] = {}
    for a in items:
        name = a.get("name") or a.get("Name")
        buckets.setdefault(families.classify(name), []).append(
            {"name": name, "icon": a.get("icon"), "shape": a.get("shape"),
             "desc": families.describe(name)})
    if args.family:
        return {"result": {args.family: buckets.get(args.family, [])}}
    return {"result": {"families": buckets}}


def list_connections(client, args) -> dict:
    """PROCESIO's stored connection credentials (GET /api/Credentials)."""
    q = {"pageNumber": args.page, "pageItemCount": args.page_size,
         "searchName": args.search}
    return {"result": client.get("/api/Credentials", q)}


def list_connection_types(client, _args) -> dict:
    return {"result": client.get("/api/Credentials/types")}


def list_api_keys(client, _args) -> dict:
    return {"result": client.get("/api/ApiKey")}


ACTIONS = {
    "list-workspaces": ActionDef(
        func=list_workspaces, add_args=add_profile_arg, needs_client=True,
        description="List the caller's workspaces (GET /api/Workspaces, active-only).",
    ),
    "list-subworkspaces": ActionDef(
        func=list_subworkspaces, add_args=_subworkspaces_args, needs_client=True,
        description="List a master's sub-workspaces, active-only by default (--include-removed for soft-deleted).",
    ),
    "list-workspace-users": ActionDef(
        func=list_workspace_users, add_args=_ws_users_args, needs_client=True,
        description="List users in a workspace (GET /api/Workspace/users).",
    ),
    "list-datatypes": ActionDef(
        func=list_datatypes, add_args=_search_args, needs_client=True,
        description="List data types (GET /api/DataTypes).",
    ),
    "list-actions-catalog": ActionDef(
        func=list_actions_catalog, add_args=_actions_args, needs_client=True,
        description="List the action/connector catalog (GET /api/Actions).",
    ),
    "list-connections": ActionDef(
        func=list_connections, add_args=_search_args, needs_client=True,
        description="List stored connection credentials (GET /api/Credentials).",
    ),
    "list-connection-types": ActionDef(
        func=list_connection_types, add_args=add_profile_arg, needs_client=True,
        description="List supported connection types (GET /api/Credentials/types).",
    ),
    "list-api-keys": ActionDef(
        func=list_api_keys, add_args=add_profile_arg, needs_client=True,
        description="List API keys in the workspace (GET /api/ApiKey).",
    ),
}
