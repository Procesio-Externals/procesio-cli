"""Custom-action (connector) lifecycle for a workspace — HAR-verified.

PROCESIO custom actions are connector packages (`.nupkg`, built with the Custom
Actions SDK) installed into a workspace. The wire format (from the
"work with Custom actions" HAR):

  - **upload/install:** `POST /api/actions`, `multipart/form-data`, single field
    **`package`** = the `.nupkg` file (Content-Type `application/x-compressed`),
    `workspaceid` header → response `{"id": "<actionId>"}`. Permission CustomActions.Write.
    The action's DISPLAY NAME and icon come from the **`name` and `path` request
    HEADERS**, not from the package: the backend assigns `actionTemplate.Name =
    headers.ActionName`, and `ClassDecorator.Name` inside the assembly is only
    validated as non-empty, then discarded. Omit the `name` header and the action
    installs with an EMPTY name — invisible to search in the designer toolbar.
  - **delete/uninstall:** `DELETE /api/actions/{id}` (workspaceid header) → 200.
    Permission CustomActions.Delete.
  - **list custom:** `GET /api/actions/node?getFullAction=true&isCustom=true` →
    `{"actions": [...]}` (only the workspace's custom actions; `isProcesioAction:false`).
    `GET /api/actions` returns the FULL catalog (built-in + custom).

The `/api/actions/event` calls in the HAR are in-DESIGNER configuration events
(adding output mappings while editing the action) — NOT package management — so
they are intentionally out of scope here.

JSON in / JSON out; impure (live client). See PROCESIO-API-NOTES.md.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_profile_arg


def _summary(a: dict) -> dict:
    return {"actionId": a.get("actionId") or a.get("id"), "name": a.get("name"),
            "description": (a.get("description") or "")[:140],
            "inputPorts": a.get("inputPorts"), "outputPorts": a.get("outputPorts"),
            "isCustom": not a.get("isProcesioAction", True)}


def upload_customaction(client, args) -> dict:
    """Install a custom action from a `.nupkg` package: POST /api/actions as
    multipart field `package`. Returns the new action id.

    `--action-name` sets the name the designer shows; without it the action
    installs nameless (see the module docstring)."""
    path = Path(args.file)
    if not path.is_file():
        raise UsageError(f"package file not found: {args.file}")
    data = path.read_bytes()
    if not data:
        raise UsageError(f"package file is empty: {args.file}")
    filename = args.name or path.name
    # The backend reads the display name off the `name` header. Default it to the
    # package's stem so an upload is never nameless in the designer.
    action_name = args.action_name or path.stem
    resp = client.request_multipart(
        "/api/actions",
        files={"package": (filename, data, "application/x-compressed")},
        headers={"name": action_name, "path": args.icon_path or ""})
    action_id = resp.get("id") if isinstance(resp, dict) else None
    return {"uploaded": True, "id": action_id, "name": filename,
            "actionName": action_name, "bytes": len(data)}


def delete_customaction(client, args) -> dict:
    """Uninstall a custom action: DELETE /api/actions/{id}."""
    client.request("DELETE", f"/api/actions/{args.id}")
    return {"deleted": True, "id": args.id}


def list_customactions(client, args) -> dict:
    """List the workspace's custom actions (default) or the full catalog (--all)."""
    if args.all:
        r = client.get("/api/Actions")
        items = r.get("actions") if isinstance(r, dict) else (r or [])
    else:
        r = client.get("/api/Actions/node",
                       {"getFullAction": "true", "isCustom": "true"})
        items = r.get("actions") if isinstance(r, dict) else (r or [])
    items = items or []
    return {"count": len(items), "actions": [_summary(a) for a in items]}


# -- argparse -----------------------------------------------------------------

def _upload_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--file", required=True, help="path to the custom-action .nupkg package")
    p.add_argument("--name", help="override the upload filename (default: the file's basename)")
    p.add_argument("--action-name",
                   help="display name shown in the designer (sent as the 'name' header; "
                        "default: the package filename without its extension)")
    p.add_argument("--icon-path", help="icon path for the action (sent as the 'path' header)")


def _delete_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="custom action id (from upload / list)")


def _list_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--all", action="store_true",
                   help="list the full catalog (built-in + custom); default is custom only")


ACTIONS = {
    "customaction-upload": ActionDef(
        func=upload_customaction, add_args=_upload_args, needs_client=True,
        description="Install a custom action from a .nupkg package (POST /api/actions multipart)."),
    "customaction-delete": ActionDef(
        func=delete_customaction, add_args=_delete_args, needs_client=True,
        description="Uninstall a custom action (DELETE /api/actions/{id})."),
    "customaction-list": ActionDef(
        func=list_customactions, add_args=_list_args, needs_client=True,
        description="List the workspace's custom actions (--all for the full catalog)."),
}
