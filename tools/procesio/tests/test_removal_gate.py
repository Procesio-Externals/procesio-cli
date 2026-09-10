"""The removal gate: a desired-state save may not silently delete what it omits.

Why this exists. `process-edit --config` replaces the definition, so anything the config
leaves out is removed, and the payload cannot say whether that was meant: a config with 4
actions against a live flow of 13 looks identical whether the author intended to drop 9 or
had lost track of the flow. Neither existing guard catches it — the validation gate asks
whether the RESULT is valid (a truncated flow usually still is), and `PUT /api/Projects`
persists even when it answers HTTP 400 (by design: unfinished work must be saveable).

Seen live: an incomplete write cut a 13-action flow to 2, and the next step — reading that
state and rebuilding from a partial picture — dropped 8 more variables. So the gate does not
judge the removal; it makes the consequence visible before it is paid and asks for intent.
"""
from __future__ import annotations

import pytest

from tools.procesio.dto.process.builder import _removal_gate
from tools.procesio.errors import RemovalBlocked


def _live(actions=(), variables=()):
    return {"_live_flow": {
        "actions": [{"name": n} for n in actions],
        "variables": [{"name": n} for n in variables],
    }}


def _dto(actions=(), variables=()):
    return {"Actions": [{"Name": n} for n in actions],
            "Variables": [{"Name": n} for n in variables]}


def test_keeping_everything_passes():
    _removal_gate(_dto(["Start", "Trim", "Stop"], ["a", "b"]),
                  _live(["Start", "Trim", "Stop"], ["a", "b"]))


def test_adding_is_never_a_removal():
    _removal_gate(_dto(["Start", "Trim", "To Upper", "Stop"], ["a", "b", "c"]),
                  _live(["Start", "Trim", "Stop"], ["a", "b"]))


def test_dropping_an_action_is_refused():
    with pytest.raises(RemovalBlocked) as e:
        _removal_gate(_dto(["Start", "Stop"]), _live(["Start", "Trim", "Stop"]))
    assert e.value.removed["actions"] == ["Trim"]


def test_dropping_a_variable_is_refused():
    with pytest.raises(RemovalBlocked) as e:
        _removal_gate(_dto(["Start"], ["a"]), _live(["Start"], ["a", "b"]))
    assert e.value.removed["variables"] == ["b"]


def test_the_message_names_what_would_disappear():
    """The gate does not decide whether the removal is right - the caller does, from this
    list. One line means an intentional edit; nine mean a lost picture of the flow."""
    with pytest.raises(RemovalBlocked) as e:
        _removal_gate(_dto(["Start", "Stop"], ["payload"]),
                      _live(["Start", "Trim", "Normalize Diacritics", "Stop"],
                            ["payload", "customerObj", "emailObj"]))
    msg = str(e.value)
    assert "2 action(s): Trim, Normalize Diacritics" in msg
    assert "2 variable(s): customerObj, emailObj" in msg
    assert "--allow-remove" in msg


def test_allow_remove_lets_it_through():
    ctx = _live(["Start", "Trim", "Stop"], ["a", "b"])
    ctx["_allow_remove"] = True
    _removal_gate(_dto(["Start"]), ctx)


def test_generated_error_ports_are_not_authored_state():
    """Error variables come and go with their owning action, so their absence from a
    config is never the caller's removal."""
    ctx = {"_live_flow": {"actions": [{"name": "Start"}], "variables": [
        {"name": "a"}, {"name": "Trim_error", "isError": True}]}}
    _removal_gate(_dto(["Start"], ["a"]), ctx)


def test_pascal_and_camel_live_shapes_both_read():
    """The live flow comes back camelCase from the API and PascalCase from a DTO round
    trip; the gate must not go blind on either."""
    ctx = {"_live_flow": {"Actions": [{"Name": "Start"}, {"Name": "Trim"}],
                          "Variables": [{"Name": "a"}]}}
    with pytest.raises(RemovalBlocked):
        _removal_gate(_dto(["Start"], ["a"]), ctx)


def test_no_live_flow_is_not_a_removal():
    """A create, or an edit whose live read failed, has nothing to compare against - the
    gate must stay out of the way rather than block on missing evidence."""
    _removal_gate(_dto(["Start", "Stop"]), {})
