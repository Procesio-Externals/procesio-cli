"""A list given for a repeatable argument reaches the tool as one flag per item.

The manifest says which arguments repeat. The bridge reads that for the one action being
run, from the one manifest: never from a registry scan, which a call must not pay for.
"""
from __future__ import annotations

import types

import bridge
import pytest
import registry


def _arg(name, repeatable=False):
    return types.SimpleNamespace(name=name, repeatable=repeatable)


def _manifest(actions=None, args=()):
    return types.SimpleNamespace(
        args=list(args), secrets=[],
        actions=[types.SimpleNamespace(name=n, args=a) for n, a in (actions or {}).items()])


@pytest.fixture
def seen(monkeypatch):
    """A registry with one tool and one agent, and a runner that records what it was given."""
    tool = _manifest({"node-bind-var": [_arg("id"), _arg("bind", True)],
                      "anonymize": [_arg("inputs")]})
    agent = _manifest({"plan": [_arg("video", True)]})
    flat = _manifest(args=[_arg("tag", True)])
    monkeypatch.setattr(registry, "get_tool",
                        lambda name, **k: {"procesio": tool, "flat": flat}[name])
    monkeypatch.setattr(registry, "get_agent", lambda name: {"video-guide": agent}[name])
    monkeypatch.setattr(bridge, "_scan_registry",
                        lambda: (_ for _ in ()).throw(AssertionError("a call scanned the registry")))
    monkeypatch.delenv("AAT_HOST_RUNNER_URL", raising=False)
    calls = {}

    def run(kind):
        def fake(name, argv, **kwargs):
            calls[kind] = (name, argv)
            return {"ok": True, "data": {}, "error": None}
        return fake
    monkeypatch.setattr(bridge.runner, "run_tool", run("tool"))
    monkeypatch.setattr(bridge.runner, "run_agent", run("agent"))
    return calls


def test_a_list_for_a_repeatable_argument_is_one_flag_per_item(seen):
    bridge.run_tool("procesio", "node-bind-var", {"id": "p-1", "bind": ["0=name", "1=email"]})
    assert seen["tool"] == ("procesio", ["node-bind-var", "--id", "p-1",
                                         "--bind", "0=name", "--bind", "1=email"])


def test_a_list_for_any_other_argument_is_still_one_json_value(seen):
    bridge.run_tool("procesio", "anonymize", {"inputs": ["a.csv", "b.csv"]})
    assert seen["tool"] == ("procesio", ["anonymize", "--inputs", '["a.csv", "b.csv"]'])


def test_the_mark_is_read_for_the_action_that_runs(seen):
    """`bind` repeats on one action only. The same name on another action is not repeated."""
    bridge.run_tool("procesio", "anonymize", {"bind": ["0=name"]})
    assert seen["tool"][1] == ["anonymize", "--bind", '["0=name"]']


def test_an_agent_s_repeatable_argument_is_repeated_too(seen):
    bridge.run_agent("video-guide", "plan", {"video": ["a.mp4", "b.mp4"]})
    assert seen["agent"] == ("video-guide", ["plan", "--video", "a.mp4", "--video", "b.mp4"])


def test_a_tool_without_actions_uses_its_own_arguments(seen):
    bridge.run_tool("flat", None, {"tag": ["a", "b"]})
    assert seen["tool"] == ("flat", ["--tag", "a", "--tag", "b"])


def test_an_unknown_tool_or_action_repeats_nothing_and_does_not_raise(seen):
    assert bridge._repeatable_args("tool", "ghost", "x") == frozenset()
    assert bridge._repeatable_args("tool", "procesio", "no-such-action") == frozenset()
    assert bridge._repeatable_args("agent", "ghost", None) == frozenset()


def test_the_argument_schema_says_when_an_argument_repeats():
    schema = bridge._args_schema([{"name": "bind", "repeatable": True}, {"name": "id"}])
    assert schema[0]["repeatable"] is True
    assert "repeatable" not in schema[1]


def test_the_procesio_manifest_marks_bind_as_repeatable():
    """Against the real manifest: this is the argument that could not take two values."""
    assert "bind" in bridge._repeatable_args("tool", "procesio", "node-bind-var")
    assert "bind" in bridge._repeatable_args("tool", "procesio", "node-add-binding")
    assert bridge._repeatable_args("tool", "procesio", "list-processes") == frozenset()
