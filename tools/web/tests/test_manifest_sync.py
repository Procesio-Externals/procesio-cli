"""Guard: tool.yaml must declare exactly the actions the dispatcher registers,
and every CLI flag must appear as a manifest arg (and vice-versa). Keeps the
manifest (source of truth) from drifting away from the runtime."""
from __future__ import annotations

from pathlib import Path

from tools._lib.manifest import load_tool
from tools.web import main


def _manifest():
    tool_root = Path(main.__file__).resolve().parent
    return load_tool(tool_root / "tool.yaml")


def test_manifest_loads():
    m = _manifest()
    assert m.name == "web"


def test_manifest_actions_match_dispatch():
    m = _manifest()
    manifest_actions = set(m.action_names())
    dispatch_actions = set(main.ACTIONS)
    assert manifest_actions == dispatch_actions, (
        f"only in manifest: {manifest_actions - dispatch_actions}; "
        f"only in code: {dispatch_actions - manifest_actions}"
    )


def test_manifest_args_match_argparse():
    import argparse

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
    import argparse

    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        required_argparse = set()
        for action in parser._actions:
            if getattr(action, "required", False):
                for opt in action.option_strings:
                    if opt.startswith("--"):
                        required_argparse.add(opt[2:])
        spec = m.get_action(name)
        required_manifest = {a.name for a in spec.args if a.required}
        assert required_argparse <= required_manifest, (
            f"action {name}: argparse-required but not manifest-required: "
            f"{required_argparse - required_manifest}"
        )


def test_no_secrets_declared():
    # web stores auth in gitignored session files, not Credential Manager.
    m = _manifest()
    assert m.secrets == []
