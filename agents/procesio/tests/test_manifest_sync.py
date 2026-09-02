"""Guard: agent.yaml must declare exactly the actions the dispatcher registers,
the per-action args must match, and every driven tool must be registered.
"""
from __future__ import annotations

from pathlib import Path

from tools._lib.manifest import load_agent
from agents.procesio import main


def _manifest():
    agent_root = Path(main.__file__).resolve().parent
    return load_agent(agent_root / "agent.yaml")


def test_manifest_actions_match_dispatch():
    m = _manifest()
    assert set(m.action_names()) == set(main.ACTIONS), (
        f"only in manifest: {set(m.action_names()) - set(main.ACTIONS)}; "
        f"only in code: {set(main.ACTIONS) - set(m.action_names())}")


def test_expected_actions_registered():
    assert set(main.ACTIONS) == {
        "status", "guidance", "checklist", "verify", "audit"}


def test_declared_tools_are_registered():
    from registry import get_tool
    for tool_name in _manifest().tools:
        get_tool(tool_name)  # raises KeyError if missing


def test_manifest_args_match_dispatch():
    """Each action's manifest args (kebab) must match the argparse flags the
    handler registers (so the contract cannot drift from the code)."""
    import argparse
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        code_args = {a.dest.replace("_", "-") for a in parser._actions
                     if a.dest not in ("help",)}
        spec = m.get_action(name)
        manifest_args = {a.name for a in spec.args}
        assert manifest_args == code_args, (
            f"{name}: manifest {manifest_args} != code {code_args}")
