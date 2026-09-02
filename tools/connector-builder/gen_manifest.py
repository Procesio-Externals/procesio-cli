"""Generate tool.yaml from the live ACTIONS dict (single source of truth).

Introspects each action's argparse to emit the manifest's actions/args, so the
manifest can never drift from the dispatcher (the manifest-sync test enforces the
same invariant). Run after adding/changing an action:

    .venv/Scripts/python tools/connector-builder/gen_manifest.py

Header metadata (name/description/secrets/routing) is curated here.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

TOOL_ROOT = Path(__file__).resolve().parent
FRAMEWORK_ROOT = TOOL_ROOT.parents[1]
for _p in (str(TOOL_ROOT), str(FRAMEWORK_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import main  # noqa: E402

DESCRIPTION = (
    "AI Connector Builder (connector-builder.procesio.app): turn API documentation "
    "into a compiled PROCESIO Custom Action .nupkg connector via an 8-stage LLM "
    "pipeline (gather -> clarify -> plan -> generate -> validate -> compile -> fix "
    "-> deliver). Drive the whole build lifecycle, read/write generated files, "
    "download the .nupkg artifact (to upload to PROCESIO for live testing), inspect "
    "logs/telemetry, and edit the builder's own knowledge base (prompts, spec "
    "modules, examples, validation rules). Two auth modes, both -> Bearer token: an "
    "acb_ API key, or username/password via /auth/login."
)

SECRETS = [
    {"name": "api-key",
     "description": "Connector Builder API key (acb_...). Used verbatim as the bearer token."},
    {"name": "username",
     "description": "Login email for username/password auth mode (e.g. user@example.com)."},
    {"name": "password",
     "description": "Login password for username/password auth mode (-> POST /auth/login -> JWT)."},
]

ROUTING = {
    "triggers": [
        "build a PROCESIO custom action / connector from API docs",
        "generate a .nupkg connector for PROCESIO from documentation",
        "create / run / drive an AI Connector Builder build",
        "approve / revise the plan / regenerate files / download the connector artifact",
        "edit the connector builder's prompts / spec modules / examples (improve generation)",
    ],
    "primary_action": "create-build",
    "example": ("connector-builder create-build --api-url <docs-url> --user-requirements '...'   "
                "(then gather / answer / approve-plan / approve-generate / download-artifact)"),
}

# Per-action one-line output hints (optional; advisory only).
OUTPUT_SCHEMAS = {
    "check": '{ "ok": true, "email": "...", "role": "admin", "base_url": "..." }',
    "create-build": '{ "id": "uuid", "status": "pending", ... }',
    "gather": '{ "status": "clarifying", "api_profile": {...}, "clarification_questions": [...] }',
    "answer": '{ "status": "planning", "implementation_plan": {...} }',
    "approve-plan": '{ "status": "generating", "step_status": "waiting_user", "generated_files": {...} }',
    "approve-generate": '{ "status": "approved", "build_id": "uuid" }',
    "download-artifact": '{ "out": "...", "bytes": N, "filename": "..._PROCESIO.API.nupkg" }',
    "list-builds": '{ "builds": [...], "total": N, "page": 1, "per_page": 20 }',
}

# argparse type object -> manifest type string.
_TYPE_MAP = {int: "integer", float: "number"}


def _arg_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    t = getattr(action, "type", None)
    if t in _TYPE_MAP:
        return _TYPE_MAP[t]
    # The --success / boolean-lambda flags parse to bool.
    if callable(t) and getattr(t, "__name__", "") == "<lambda>":
        return "boolean"
    return "string"


def _args_for(defn) -> list[dict]:
    parser = argparse.ArgumentParser()
    defn.add_args(parser)
    out: list[dict] = []
    for action in parser._actions:
        opts = [o for o in action.option_strings if o.startswith("--") and o != "--help"]
        if not opts:
            continue
        name = opts[0][2:]
        entry: dict = {"name": name, "type": _arg_type(action)}
        if getattr(action, "required", False):
            entry["required"] = True
        if action.help:
            entry["description"] = action.help
        out.append(entry)
    return out


def build_manifest() -> dict:
    actions = []
    for name in sorted(main.ACTIONS):
        defn = main.ACTIONS[name]
        entry: dict = {"name": name, "description": defn.description}
        args = _args_for(defn)
        if args:
            entry["args"] = args
        if name in OUTPUT_SCHEMAS:
            entry["output_schema"] = OUTPUT_SCHEMAS[name]
        actions.append(entry)
    return {
        "name": "connector-builder",
        "description": DESCRIPTION,
        "version": "0.2.0",
        "runtime": "python",
        "entrypoint": "main.py",
        "secrets": SECRETS,
        "routing": ROUTING,
        "actions": actions,
    }


def main_gen() -> None:
    manifest = build_manifest()
    text = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True, width=100)
    out = TOOL_ROOT / "tool.yaml"
    header = ("# GENERATED by gen_manifest.py from the live ACTIONS dict — do not\n"
              "# hand-edit actions/args; edit the handlers + header consts and rerun:\n"
              "#   .venv/Scripts/python tools/connector-builder/gen_manifest.py\n")
    out.write_text(header + text, encoding="utf-8")
    print(f"wrote {out} ({len(text)} bytes, {len(manifest['actions'])} actions)",
          file=sys.stderr)


if __name__ == "__main__":
    main_gen()
