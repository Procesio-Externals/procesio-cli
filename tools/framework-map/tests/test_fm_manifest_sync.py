"""Guard: tool.yaml declares exactly the actions the dispatcher registers, and
each action's manifest args match its argparse (both directions), with
argparse-required flags marked required in the manifest.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from tools._lib.manifest import load_tool

import fm_main as main


def _manifest():
    return load_tool(Path(main.__file__).resolve().parent / "tool.yaml")


def test_manifest_actions_match_dispatch():
    m = _manifest()
    assert set(m.action_names()) == set(main.ACTIONS), (
        f"only in manifest: {set(m.action_names()) - set(main.ACTIONS)}; "
        f"only in code: {set(main.ACTIONS) - set(m.action_names())}")


def test_expected_actions():
    assert set(main.ACTIONS) == {"build", "check"}


def _argparse_names(defn):
    parser = argparse.ArgumentParser()
    defn.add_args(parser)
    names, required = set(), set()
    for action in parser._actions:
        for opt in action.option_strings:
            if opt.startswith("--") and opt != "--help":
                names.add(opt[2:])
                if getattr(action, "required", False):
                    required.add(opt[2:])
    return names, required


def test_manifest_args_match_argparse():
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        argparse_names, _ = _argparse_names(defn)
        manifest_names = {a.name for a in m.get_action(name).args}
        assert manifest_names == argparse_names, (
            f"{name}: only manifest {manifest_names - argparse_names}; "
            f"only argparse {argparse_names - manifest_names}")


def test_required_args_marked_required():
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        argparse_names, required_argparse = _argparse_names(defn)
        required_manifest = {a.name for a in m.get_action(name).args if a.required}
        assert required_argparse <= required_manifest
        assert required_manifest <= argparse_names


def test_no_secrets():
    assert _manifest().secrets == []
