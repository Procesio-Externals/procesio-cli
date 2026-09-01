"""Generic <component>-create / <component>-edit actions for the DTO sub-tools.

One pair per registered component (dto/registry.py). Each:
  - validates --config against the component's JSON Schema (fail-fast),
  - builds the full DTO by merging onto the golden template (pure),
  - --dry-run: returns the built DTO (+ validate@source oracle if any), sends nothing,
  - otherwise create (POST) or edit (desired-state), then re-GET and return it.
"""
from __future__ import annotations

import argparse
import json

from tools.procesio.actiondef import ActionDef
from tools.procesio.dto import framework, registry
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_profile_arg


def _load_config(args) -> dict:
    raw = None
    if getattr(args, "config_file", None):
        with open(args.config_file, encoding="utf-8") as f:
            raw = f.read()
    elif getattr(args, "config", None):
        raw = args.config
    if raw is None:
        raise UsageError("provide --config '<json>' or --config-file <path>")
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"--config must be valid JSON: {e}") from e
    if not isinstance(cfg, dict):
        raise UsageError("--config must be a JSON object")
    return cfg


def _add_gate_args(p: argparse.ArgumentParser) -> None:
    """Shared save-gate flags (process only enforces them; harmless elsewhere)."""
    p.add_argument("--force", action="store_true",
                   help="bypass the pre-save FE (designer) + BE validation gate")
    p.add_argument("--no-types", dest="no_types", action="store_true",
                   help="skip the advisory data-type-mismatch (warning) layer in the gate")


def _create_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--config", help="resource config as a JSON object")
    p.add_argument("--config-file", dest="config_file", help="path to a JSON config file")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build + validate the DTO and return it without creating")
    _add_gate_args(p)


def _edit_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="id of the resource to edit")
    p.add_argument("--config", help="desired-state config as a JSON object")
    p.add_argument("--config-file", dest="config_file", help="path to a JSON config file")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build the DTO and return it without editing")
    _add_gate_args(p)


def _make_create(component):
    def func(client, args):
        config = _load_config(args)
        ctx = framework.prepare(component, client, config)
        ctx["_force"] = getattr(args, "force", False)
        ctx["_no_types"] = getattr(args, "no_types", False)
        dto = framework.build_dto(component, config, ctx)
        # Pre-save gate (process): FE designer + BE validation. Raises ValidationBlocked
        # on blocking errors unless --force. For --dry-run we force it open so the report
        # is shown without aborting. Components without a save_gate fall back to the oracle.
        if component.save_gate:
            gate_ctx = {**ctx, "_force": True} if args.dry_run else ctx
            oracle = component.save_gate(client, dto, gate_ctx)
        else:
            oracle = framework.run_validate(component, client, dto, ctx)
        if args.dry_run:
            return {"dry_run": True, "component": component.name, "dto": dto,
                    "validation": oracle}
        resp = framework.run_create(component, client, dto, ctx)
        rid = component.extract_id(resp, dto)
        verified = framework.run_get(component, client, rid, ctx) if rid else None
        out = {"created": True, "component": component.name, "id": rid,
               "validation": oracle, "result": verified if verified is not None else resp}
        if isinstance(resp, dict) and resp.get("_capture"):   # AUTO webhook listen+capture log
            out["capture"] = resp["_capture"]
        return out
    return func


def _make_edit(component):
    def func(client, args):
        config = _load_config(args)
        ctx = framework.prepare(component, client, config)
        ctx["_force"] = getattr(args, "force", False)
        ctx["_no_types"] = getattr(args, "no_types", False)
        if args.dry_run:
            # Build it the way the EDIT would, so the preview shows the ids the edit would keep.
            dto = framework.build_edit_dto(component, client, args.id, config, ctx)
            return {"dry_run": True, "edit": True, "component": component.name,
                    "id": args.id, "dto": dto}
        if not component.edit:
            raise UsageError(f"{component.name} does not support edit yet")
        framework.validate_config(component, config)
        resp = component.edit(client, args.id, config, ctx)
        return {"edited": True, "component": component.name, "id": args.id, "result": resp}
    return func


def build_actions() -> dict[str, ActionDef]:
    out: dict[str, ActionDef] = {}
    for name, comp in registry.all_components().items():
        out[f"{name}-create"] = ActionDef(
            func=_make_create(comp), add_args=_create_args, needs_client=True,
            description=f"Create a PROCESIO {name} from a validated config (build->validate->POST->re-GET). --dry-run to preview the DTO.",
        )
        out[f"{name}-edit"] = ActionDef(
            func=_make_edit(comp), add_args=_edit_args, needs_client=True,
            description=f"Edit a PROCESIO {name} to a desired-state config (--id required). --dry-run to preview the DTO.",
        )
    return out


ACTIONS = build_actions()
