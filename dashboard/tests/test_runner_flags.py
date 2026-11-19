"""How a {name: value} object becomes command-line flags.

The one rule that is not obvious: a list is ONE JSON value, unless the tool's manifest
marks the argument as repeatable. Many tools take a JSON list in a single flag, and the
value alone cannot say which of the two a tool expects.
"""
from __future__ import annotations

from dashboard.server import runner


def test_a_value_becomes_one_flag_and_one_value():
    assert runner.flags_from({"id": "p-1", "page": 2}) == ["--id", "p-1", "--page", "2"]


def test_a_true_boolean_is_a_bare_flag_and_a_false_one_is_left_out():
    assert runner.flags_from({"dry-run": True, "force": False}) == ["--dry-run"]


def test_a_list_is_one_json_value_by_default():
    assert runner.flags_from({"inputs": ["a.csv", "b.csv"]}) == ["--inputs", '["a.csv", "b.csv"]']


def test_a_list_for_a_repeatable_argument_is_one_flag_per_item():
    flags = runner.flags_from({"id": "p-1", "bind": ["0=name", "1=email"]}, {"bind"})
    assert flags == ["--id", "p-1", "--bind", "0=name", "--bind", "1=email"]


def test_only_the_named_arguments_are_repeated():
    flags = runner.flags_from({"bind": ["0=name"], "inputs": ["a", "b"]}, {"bind"})
    assert flags == ["--bind", "0=name", "--inputs", '["a", "b"]']


def test_one_value_for_a_repeatable_argument_is_one_flag():
    assert runner.flags_from({"bind": "0=name"}, {"bind"}) == ["--bind", "0=name"]


def test_an_empty_list_for_a_repeatable_argument_adds_nothing():
    assert runner.flags_from({"bind": []}, {"bind"}) == []


def test_an_item_that_is_an_object_is_json():
    flags = runner.flags_from({"set": [{"a": 1}, "b"]}, frozenset({"set"}))
    assert flags == ["--set", '{"a": 1}', "--set", "b"]


def test_no_arguments_is_no_flags():
    assert runner.flags_from(None) == [] and runner.flags_from({}, {"bind"}) == []


def test_a_tool_call_is_given_the_shared_lock_folder_and_no_other_setting_of_the_server(monkeypatch):
    """A tool started for a turn gets a safe base environment, not the server's. The lock folder
    is in it: each such call has a temp folder of its own, so a lock kept there orders nobody."""
    monkeypatch.setenv("AAT_LOCK_DIR", "/data/locks")
    monkeypatch.setenv("AAT_MCP_HTTP_TOKEN", "not for a tool")
    monkeypatch.delenv("AAT_TOOL_ENV_ALLOW", raising=False)
    env = runner._safe_base_env()
    assert env["AAT_LOCK_DIR"] == "/data/locks"
    assert "AAT_MCP_HTTP_TOKEN" not in env
