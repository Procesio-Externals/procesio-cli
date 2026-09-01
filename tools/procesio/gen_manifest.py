"""Regenerate tool.yaml's `actions:` block from the live dispatcher.

The manifest is the source of truth (CLAUDE.md Hard rule 3) and the sync guard
(tests/test_manifest_sync.py) demands it match the dispatcher's actions/args
EXACTLY. With 250+ actions the file is ~200 KB — far too large to hand-edit,
especially under the Cowork mount's ~15 KB Write/Edit cap. So this script is the
ONLY supported way to change the action surface:

    1. change handlers / autogen / dto actions,
    2. run `python -m tools.procesio.gen_manifest` (writes tool.yaml directly via
       Python — not the capped Write tool),
    3. `pytest tools/procesio/tests/test_manifest_sync.py` stays green.

It preserves the hand-written header (everything up to and including the
`actions:` line — name/description/version/routing/secrets + comments) verbatim,
and regenerates only the actions list, sorted by name for a stable diff. Arg
type/required/description are introspected from each action's argparse exactly as
the sync test reads them, so the two can never drift.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

TOOL_ROOT = Path(__file__).resolve().parent
MANIFEST = TOOL_ROOT / "tool.yaml"


def _arg_type(action: argparse.Action) -> str:
    if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
        return "boolean"
    if action.type is int:
        return "integer"
    if action.type is float:
        return "number"
    return "string"


def _action_args(defn) -> list[dict]:
    """The arg specs for one ActionDef, in argparse declaration order — the exact
    surface the sync test compares against."""
    parser = argparse.ArgumentParser()
    defn.add_args(parser)
    out: list[dict] = []
    for action in parser._actions:
        names = [o for o in action.option_strings if o.startswith("--") and o != "--help"]
        if not names:
            continue
        name = names[0][2:]
        out.append({
            "name": name,
            "type": _arg_type(action),
            "required": bool(getattr(action, "required", False)),
            "description": (action.help or "").strip(),
        })
    return out


def build_actions_block() -> list[dict]:
    from tools.procesio import main
    actions = []
    for name in sorted(main.ACTIONS):
        defn = main.ACTIONS[name]
        actions.append({
            "name": name,
            "description": (defn.description or "").strip(),
            "args": _action_args(defn),
        })
    return actions


def _header_text() -> str:
    """Everything up to and including the `actions:` line, preserved verbatim so
    hand-written comments / routing / secrets / the long description are kept."""
    text = MANIFEST.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.rstrip("\n") == "actions:":
            return "".join(lines[: i + 1])
    raise SystemExit("tool.yaml has no top-level `actions:` line to anchor on")


def render() -> str:
    header = _header_text()
    body = yaml.safe_dump(
        build_actions_block(),
        sort_keys=False, default_flow_style=False, allow_unicode=True,
        width=10_000,  # never wrap a description onto a second line
    )
    return header + body


def main() -> int:
    new_text = render()
    # newline="\n" is load-bearing: the repo stores this manifest with LF, and a
    # default Windows write turns every one of its ~9,000 lines into a diff hunk, which
    # buries the handful that actually changed and makes the manifest unreviewable.
    MANIFEST.write_text(new_text, encoding="utf-8", newline="\n")  # direct write (not capped)
    n_actions = new_text.count("\n- name:")
    print(f"wrote {MANIFEST} ({len(new_text)} bytes, {n_actions} actions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
