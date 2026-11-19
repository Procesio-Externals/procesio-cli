"""Guard: tool.yaml must declare exactly the actions the dispatcher registers,
and every declared arg must match the action's argparse (both directions),
with required argparse flags marked required in the manifest."""
from __future__ import annotations

import argparse
from pathlib import Path

from tools._lib.manifest import load_tool
from tools.procesio import main


def _manifest():
    tool_root = Path(main.__file__).resolve().parent
    return load_tool(tool_root / "tool.yaml")


def test_manifest_actions_match_dispatch():
    m = _manifest()
    manifest_actions = set(m.action_names())
    dispatch_actions = set(main.ACTIONS)
    assert manifest_actions == dispatch_actions, (
        f"only in manifest: {manifest_actions - dispatch_actions}; "
        f"only in code: {dispatch_actions - manifest_actions}"
    )


def test_manifest_args_match_argparse():
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        argparse_names = set()
        for action in parser._actions:
            for opt in action.option_strings:
                if opt.startswith("--") and opt != "--help":
                    argparse_names.add(opt[2:])
        spec = m.get_action(name)
        manifest_names = {a.name for a in spec.args}
        assert manifest_names == argparse_names, (
            f"action {name}: only in manifest {manifest_names - argparse_names}; "
            f"only in argparse {argparse_names - manifest_names}"
        )


def test_required_args_marked_required_in_manifest():
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        argparse_names = set()
        required_argparse = set()
        for action in parser._actions:
            for opt in action.option_strings:
                if opt.startswith("--") and opt != "--help":
                    argparse_names.add(opt[2:])
                    if getattr(action, "required", False):
                        required_argparse.add(opt[2:])
        spec = m.get_action(name)
        required_manifest = {a.name for a in spec.args if a.required}
        assert required_argparse <= required_manifest, (
            f"action {name}: argparse-required but not manifest-required: "
            f"{required_argparse - required_manifest}"
        )
        assert required_manifest <= argparse_names, (
            f"action {name}: manifest-required but not an argparse flag: "
            f"{required_manifest - argparse_names}"
        )


def test_a_flag_that_repeats_is_marked_repeatable_and_no_other_is():
    """A caller that holds a list (an MCP client does) reads this mark to know that the
    flag is given once per value. Without it the list arrives as one value, and the tool
    reads the whole list as a single item."""
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        repeats = set()
        for action in parser._actions:
            names = [o for o in action.option_strings if o.startswith("--") and o != "--help"]
            if names and isinstance(action, argparse._AppendAction):
                repeats.add(names[0][2:])
        marked = {a.name for a in m.get_action(name).args if a.repeatable}
        assert marked == repeats, (
            f"action {name}: repeats in argparse {sorted(repeats)}, "
            f"marked repeatable in the manifest {sorted(marked)}")
