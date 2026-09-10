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
    # Separate from --force on purpose: --force answers "save it even though it is
    # invalid"; this answers "yes, delete what the config leaves out". A create has
    # nothing to remove, so the flag is only offered on edit.
    p.add_argument("--allow-remove", dest="allow_remove", action="store_true",
                   help="permit this desired-state config to REMOVE actions/variables "
                        "the live resource has (refused by default)")
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
        ctx["_allow_remove"] = getattr(args, "allow_remove", False)
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


def _payload_docs(comp) -> tuple[dict, list]:
    """The component's OWN schema and a working config, for the manifest.

    Both are read from the files the component already ships: the schema is the one
    `validate_config` enforces, and the example is a test fixture. Reading them here
    rather than restating them means a caller that only sees the manifest gets the same
    contract the tool enforces, and no second copy exists to fall behind. Absent files
    are not an error - a component without them simply publishes less.
    """
    schema: dict = {}
    try:
        if comp.schema_path.exists():
            schema = {"config": json.loads(comp.schema_path.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        schema = {}

    examples: list = []
    fixtures = comp.dir / "fixtures"
    try:
        for f in sorted(fixtures.glob("*.config.json")):
            examples.append(json.loads(f.read_text(encoding="utf-8")))
            break                       # one worked example is the point, not a corpus
    except (OSError, json.JSONDecodeError):
        examples = []
    return schema, examples


def _list_properties(comp) -> list[str]:
    """The config's top-level LIST properties, read from the component's own schema.

    These are the collections the desired-state rule bites on, so naming them turns an
    abstract rule ("the config replaces the definition") into an instruction a caller can
    follow ("append to `actions` and send the whole list back"). Derived rather than
    written down, so a schema that grows a list cannot leave the description behind.
    """
    try:
        schema = json.loads(comp.schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    props = schema.get("properties")
    if not isinstance(props, dict):
        return []
    return [k for k, v in props.items()
            if not k.startswith("_") and isinstance(v, dict) and v.get("type") == "array"]


def build_actions() -> dict[str, ActionDef]:
    out: dict[str, ActionDef] = {}
    for name, comp in registry.all_components().items():
        arg_schemas, examples = _payload_docs(comp)
        lists = _list_properties(comp)
        # Named lists make both descriptions concrete; a component with none still gets
        # the rule, worded for a flat config.
        listed = ", ".join(lists[:5])
        # "node" is the word a caller reaches for when it wants to put one step on a
        # canvas, and it belongs ONLY to the component that has such a list. Spraying it
        # over every component would make a search for "add node" return six identical
        # -edit actions and bury the one that answers the question.
        node = " (no add-node either: a node IS an entry in actions)" if "actions" in lists else ""
        adder = getattr(comp, "add_action", "")

        out[f"{name}-create"] = ActionDef(
            func=_make_create(comp), add_args=_create_args, needs_client=True,
            description=(
                f"Create a PROCESIO {name} from a validated config "
                f"(build->validate->POST->re-GET). --config carries the WHOLE definition "
                f"in ONE call - not a skeleton to fill in later"
                + (f": put all of {listed} in it up front" if lists else "")
                + ". There is no separate add/insert step afterwards. "
                f"--dry-run previews the DTO without creating."
            ),
            arg_schemas=arg_schemas, examples=examples,
        )
        # The single fact that cost the most re-discovery: an agent holding only the arg
        # schema knows --config takes a config, and reasonably assumes some add/insert/
        # append action exists for putting ONE node in. None does, so it searches, fails,
        # and eventually learns the rule by tripping the removal guard. Say it here, in
        # the first sentence, and the search that goes looking for "add node" lands on
        # this action and reads the answer.
        out[f"{name}-edit"] = ActionDef(
            func=_make_edit(comp), add_args=_edit_args, needs_client=True,
            description=(
                f"Edit a PROCESIO {name} (--id required). DESIRED STATE: the --config you "
                f"send REPLACES the whole definition"
                + ((f". To ADD one item WITHOUT restating the rest, use {adder}; "
                    f"otherwise GET the {name}, append yours to the matching list "
                    f"({listed}), and send the WHOLE config back. Batch freely: N items "
                    f"cost the same single call as 1."
                    if adder else
                    f". There is NO add / insert / append action{node} - to ADD or change "
                    f"one item, GET the {name}, append yours to the matching list "
                    f"({listed}), and send the WHOLE config back. Batch freely: N items "
                    f"cost the same single call as 1.")
                   # A flat component has no lists to append to, so the add/insert
                   # vocabulary would only put it in the way of searches meant for the
                   # components that do.
                   if lists else
                   f" - send the COMPLETE config every time, not only the fields you "
                   f"want to change.")
                + " Anything you omit is REMOVED (refused unless --allow-remove)."
                + (f" To move ONE field without restating the rest, use "
                   f"{comp.patch_action} instead - it deep-merges a patch."
                   if getattr(comp, "patch_action", "") else "")
                + " --dry-run previews the DTO."
            ),
            arg_schemas=arg_schemas, examples=examples,
        )
    return out


ACTIONS = build_actions()
