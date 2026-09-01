"""connector-builder agent: dispatch, manifest sync, next-step doctrine, checklist."""
from __future__ import annotations

import argparse
from pathlib import Path

import pytest

import cba_main as main
from tools._lib.manifest import load_agent


# -- manifest sync -----------------------------------------------------------

def _manifest():
    root = Path(main.__file__).resolve().parent
    return load_agent(root / "agent.yaml")


def test_manifest_loads_and_names_match():
    m = _manifest()
    assert m.name == "connector-builder"
    assert set(m.action_names()) == set(main.ACTIONS)


def test_manifest_args_match_argparse():
    m = _manifest()
    for name, defn in main.ACTIONS.items():
        parser = argparse.ArgumentParser()
        defn.add_args(parser)
        argparse_names = {opt[2:] for a in parser._actions for opt in a.option_strings
                          if opt.startswith("--") and opt != "--help"}
        manifest_names = {a.name for a in m.get_action(name).args}
        assert manifest_names == argparse_names, name


def test_drives_connector_builder_and_procesio():
    m = _manifest()
    assert set(m.tools) == {"connector-builder", "procesio"}


# -- dispatch ----------------------------------------------------------------

def _run(action, argv, ctx=None):
    return main.dispatch(action, argv, context_builder=(lambda: ctx) if ctx else None)


def test_unknown_action_raises():
    from agents._lib import errors
    with pytest.raises(errors.UsageError):
        _run("nope", [])


def test_status_runs_without_network():
    out = _run("status", [])
    assert out["agent"] == "connector-builder"


def test_guidance_unknown_topic():
    from agents._lib import errors
    with pytest.raises(errors.AgentError):
        _run("guidance", ["--topic", "bogus"])


def test_guidance_playbook_loads():
    out = _run("guidance", ["--topic", "playbook"])
    assert "content" in out and "build" in out["content"].lower()


def test_guidance_troubleshooting_loads():
    out = _run("guidance", ["--topic", "troubleshooting"])
    c = out["content"].lower()
    # The operational knowledge from the live run must be present in the agent.
    assert "nu1301" in c and "504" in c and "definition of done" in c


def test_guidance_all_includes_troubleshooting():
    out = _run("guidance", ["--topic", "all"])
    assert "troubleshooting" in out["topics"]


# -- next-step doctrine ------------------------------------------------------

def test_next_step_pending_recommends_start_or_gather(fake_context):
    out = _run("next-step", ["--status", "pending"], fake_context)
    actions = {r["action"] for r in out["recommended"]}
    assert {"start-build", "gather"} <= actions


def test_next_step_generate_waiting_user(fake_context):
    out = _run("next-step",
               ["--status", "generating", "--step-status", "waiting_user"], fake_context)
    assert out["phase"] == "generate-review"
    assert "approve-generate" in {r["action"] for r in out["recommended"]}


def test_next_step_completed_hands_off_to_procesio(fake_context):
    out = _run("next-step", ["--status", "completed"], fake_context)
    assert any(h["tool"].startswith("procesio") for h in out["handoff"])


def test_next_step_live_build_id_invokes_tool(fake_context):
    fake_context.responses[("connector-builder", "get-build")] = {
        "status": "planning", "step_status": "waiting_user"}
    out = _run("next-step", ["--build-id", "B1"], fake_context)
    assert fake_context.calls[0] == ("connector-builder", "get-build", ("--build-id", "B1"))
    assert out["phase"] == "plan-review"


def test_next_step_compile_restore_is_platform_not_code(fake_context):
    fake_context.responses[("connector-builder", "get-build")] = {
        "status": "failed", "last_failed_step": 6,
        "error_message": "Compilation failed due to NuGet package restore error. "
                         "Failed to retrieve information about 'Ringhel.Procesio.Action.Core' (NU1301)."}
    out = _run("next-step", ["--build-id", "B1"], fake_context)
    assert out["diagnosis"]["kind"] == "platform_nuget_restore"
    assert out["diagnosis"]["not_your_code"] is True


def test_next_step_bad_version_is_code(fake_context):
    fake_context.responses[("connector-builder", "get-build")] = {
        "status": "failed", "last_failed_step": 6,
        "error_message": "NU1102: Unable to find package Foo with version 9.9.9"}
    out = _run("next-step", ["--build-id", "B1"], fake_context)
    assert out["diagnosis"]["kind"] == "bad_package_version"
    assert out["diagnosis"]["not_your_code"] is False


def test_next_step_unknown_status_raises(fake_context):
    from agents._lib import errors
    with pytest.raises(errors.AgentError):
        _run("next-step", ["--status", "weird"], fake_context)


def test_next_step_requires_input(fake_context):
    from agents._lib import errors
    with pytest.raises(errors.AgentError):
        _run("next-step", [], fake_context)


# -- checklist ---------------------------------------------------------------

def test_checklist_covers_full_loop():
    out = _run("checklist", ["--goal", "Stripe connector"])
    phases = [s["phase"] for s in out["steps"]]
    for expected in ("scope", "deliver", "install", "test", "improve"):
        assert expected in phases
    assert out["goal"] == "Stripe connector"
