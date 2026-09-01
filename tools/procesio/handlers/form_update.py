"""form-update — apply an arbitrary change to a LIVE form and save it safely.

The canonical GET -> modify -> PUT path for raw form surgery that no narrower
action covers (change a label, a theme var, a table column header, a select
option, publish a draft, rename). It fetches the form, deep-merges a caller
`--data` patch into its `Data`, optionally overrides top-level Name/Status/State,
and PUTs the accepted PascalCase envelope via `form_code.build_put_body` — the
only body shape the server accepts (the camelCase GET echo is rejected 403).

Unlike `form-edit`, it does NOT rebuild the form from a desired-state config, so
existing elements/theme/code/logic survive untouched — only what the patch names
changes. Like the other surgical actions it is a last-write-wins read-modify-write
guarded by `guard_unchanged` (--force to override); see form_code.py.

Merge semantics (deep merge, deliberately NOT RFC-7386): nested objects merge
recursively; arrays, scalars, and null REPLACE the target value (null sets the key
to null — it does not delete it). To swap an array wholesale (elements, variables,
theme) pass the whole new array; to flip one scalar deep in Data pass just that
key, e.g. --data '{"hideBranding": true}'.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.procesio import formlint
from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.dto.form import addelement
from tools.procesio.handlers.form_code import _fetch, build_put_body


def _deep_merge(target, patch):
    """Deep-merge `patch` into `target`. Nested dicts merge; arrays/scalars/null replace."""
    if not isinstance(patch, dict) or not isinstance(target, dict):
        return patch
    out = dict(target)
    for k, v in patch.items():
        out[k] = _deep_merge(out.get(k), v) if isinstance(v, dict) else v
    return out


def _load_patch(args) -> dict | None:
    raw = None
    if args.data_file:
        raw = Path(args.data_file).read_text(encoding="utf-8")
    elif args.data:
        raw = args.data
    if raw is None:
        return None
    try:
        patch = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"--data must be valid JSON: {e}") from e
    if not isinstance(patch, dict):
        raise UsageError("--data must be a JSON object (a merge patch for the form's Data)")
    return patch


def form_update(client, args) -> dict:
    patch = _load_patch(args)
    state = None if args.state is None else (args.state == "true")
    is_private = None if args.is_private is None else (args.is_private == "true")
    if (patch is None and args.name is None and args.status is None
            and state is None and is_private is None):
        raise UsageError(
            "nothing to update: pass --data/--data-file (a Data merge patch) "
            "and/or --name/--status/--state/--is-private"
        )

    form = _fetch(client, args.id)
    existing = dict(form.get("data") or {})
    data = existing
    if patch is not None:
        data = _deep_merge(existing, patch)

    # Non-blocking safety lints (warnings only — never refuse the save). They catch
    # traps the server accepts silently: a phantom parentId, duplicate id/name
    # configs, a multiple-select missing isList, and a patch key that isn't an
    # existing Data field (the {"Data": {...}} wrapping mistake). See formlint.py.
    lints = formlint.lint_form_data(data)
    if patch is not None:
        lints = formlint.lint_patch_keys(existing, patch) + lints

    body = build_put_body(form, data=data, name=args.name, status=args.status, state=state,
                          is_private=is_private)
    result = {
        "id": form.get("id"),
        "name": body["Name"],
        "status": body["Status"],
        "state": body["State"],
        "isPrivate": body["IsPrivate"],
        "patched_keys": sorted(patch) if patch else [],
        "dry_run": bool(args.dry_run),
        "applied": False,
    }
    if lints:
        result["lints"] = lints
    if args.dry_run:
        result["dto"] = body
        return result
    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    client.put("/api/FormTemplate", body)
    result["applied"] = True
    result["concurrency"] = guard
    return result


def form_add_element(client, args) -> dict:
    raw = (Path(args.elements_file).read_text(encoding="utf-8") if args.elements_file
           else args.elements)
    if not raw:
        raise UsageError("pass --elements '<json>' or --elements-file <path>")
    try:
        specs = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"--elements must be valid JSON: {e}") from e
    if isinstance(specs, dict):
        specs = [specs]
    if not isinstance(specs, list):
        raise UsageError("--elements must be an element object or a list of them")

    form = _fetch(client, args.id)
    data = addelement.add_elements(form, specs, parent=args.parent)

    lints = formlint.lint_form_data(data)
    body = build_put_body(form, data=data)
    added = [e for e in data["elements"] if e not in (form.get("data") or {}).get("elements", [])]
    result = {
        "id": form.get("id"), "name": body["Name"],
        "added": [{"id": e["id"], "type": e.get("type"),
                   "name": addelement._name_of(e)} for e in added],
        "element_count": len(data["elements"]),
        "parent": args.parent,
        "dry_run": bool(args.dry_run), "applied": False,
    }
    warning = addelement.unreachable_in_row(data["elements"], args.parent and
                                           addelement._resolve_parent(data["elements"], args.parent))
    if warning:
        result["warning"] = warning
    if lints:
        result["lints"] = lints
    if args.dry_run:
        return result
    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    client.put("/api/FormTemplate", body)
    result["applied"] = True
    result["concurrency"] = guard
    return result


def _add_element_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--elements", help="one authoring-config element object, or a JSON list of them")
    p.add_argument("--elements-file", dest="elements_file",
                   help="path to a JSON file with the element(s)")
    p.add_argument("--parent", help="place them inside this container, by element name or id")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build the new Data and report what would be added, without saving")
    add_force_arg(p)


def _update_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--data", help="JSON object deep-merged into the form's Data (a merge patch)")
    p.add_argument("--data-file", dest="data_file",
                   help="path to a JSON file with the Data merge patch")
    p.add_argument("--name", help="rename the form (top-level Name)")
    p.add_argument("--status", type=int, choices=[0, 1],
                   help="publication status: 1=published, 0=draft")
    p.add_argument("--state", choices=["true", "false"], help="enabled flag (true/false)")
    p.add_argument("--is-private", dest="is_private", choices=["true", "false"],
                   help="reachability: false + --status 1 makes the form answer an anonymous "
                        "visitor on its custom URL; true keeps it behind a PROCESIO login")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build the PUT DTO and return it without saving (GET only)")
    add_force_arg(p)


ACTIONS = {
    "form-add-element": ActionDef(
        func=form_add_element,
        add_args=_add_element_args,
        needs_client=True,
        description=(
            "Add one or more controls to a LIVE form (authoring-config elements), splicing them "
            "into Data.elements AND the data model without regenerating what is already there - "
            "so every existing field path, and every process map that references one, survives. "
            "--parent places them in a container by name or id; --dry-run previews."
        ),
    ),
    "form-update": ActionDef(
        func=form_update,
        add_args=_update_args,
        needs_client=True,
        description=(
            "Safely save an arbitrary change to a LIVE form: GET it, deep-merge a --data "
            "patch into its Data (and/or override --name/--status/--state/--is-private), then PUT the "
            "server-accepted PascalCase DTO. Preserves elements/theme/code (never rebuilds "
            "like form-edit). Last-write-wins guard (--force); --dry-run previews the DTO."
        ),
    ),
}
