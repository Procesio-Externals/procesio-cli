"""RUN_PROCESS input/output map resolution on a form element event (handlers/form_events).

The bug this guards: `isList` was hardcoded false on both sides of every map row, and a caller's
own value was discarded. A list-valued process variable then bound into a scalar slot, so the form
received nothing from a process that had run perfectly — and there is no error anywhere to read,
because both the API and the designer accept the row. Every result-set mapping was silently wrong.
"""
from __future__ import annotations

import pytest

from tools.procesio.errors import UsageError
from tools.procesio.handlers import form_events as fe


PID = "process-1"


class _Client:
    """Serves one process's variable DTOs, the way GET /api/Projects/{id} does."""

    def __init__(self, variables):
        self.variables = variables

    def get(self, path):
        assert path == f"/api/Projects/{PID}"
        return {"flow": {"variables": self.variables}}


def _client() -> _Client:
    return _Client([
        {"id": "var-rows", "name": "bookingResultRaw", "isList": True},
        {"id": "var-name", "name": "clientName", "isList": False},
    ])


def _row(config, side="outputMap", index=0):
    return config[side][index]


def test_a_list_process_variable_maps_as_a_list_on_both_sides():
    config = {"processId": PID,
              "outputMap": [{"id": 0, "left": {"value": "bookingResultRaw"},
                             "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    row = _row(out)
    assert row["left"]["isList"] is True
    assert row["right"]["isList"] is True, "the form side holds what the process side produced"


def test_a_scalar_process_variable_still_maps_as_a_scalar():
    config = {"processId": PID,
              "inputMap": [{"id": 0, "left": {"value": "clientName"},
                            "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    row = _row(out, "inputMap")
    assert row["left"]["isList"] is False
    assert row["right"]["isList"] is False


def test_a_variable_named_by_guid_resolves_its_list_ness_too():
    config = {"processId": PID,
              "outputMap": [{"id": 0, "left": {"value": "var-rows"},
                             "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    assert _row(out)["left"]["value"] == "var-rows"
    assert _row(out)["left"]["isList"] is True


def test_an_explicit_is_list_from_the_caller_wins_over_the_variable():
    """Mapping ONE attribute out of a list is a scalar row against a list variable."""
    config = {"processId": PID,
              "outputMap": [{"id": 0,
                             "left": {"value": "bookingResultRaw", "isList": False},
                             "right": {"value": "form-var", "isList": False}}]}

    out = fe._resolve_maps(config, _client())

    assert _row(out)["left"]["isList"] is False
    assert _row(out)["right"]["isList"] is False


def test_a_variable_name_is_resolved_to_its_guid():
    config = {"processId": PID,
              "inputMap": [{"id": 0, "left": {"value": "clientName"},
                            "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    assert _row(out, "inputMap")["left"]["value"] == "var-name"


def test_the_two_sides_keep_the_path_shapes_the_designer_expects():
    config = {"processId": PID,
              "outputMap": [{"id": 0, "left": {"value": "bookingResultRaw"},
                             "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    assert _row(out)["left"]["path"] == {}
    assert _row(out)["right"]["path"] is None


def test_an_attribute_path_supplied_by_the_caller_survives():
    config = {"processId": PID,
              "outputMap": [{"id": 0,
                             "left": {"value": "bookingResultRaw", "path": {"attributeId": "a1"}},
                             "right": {"value": "form-var"}}]}

    out = fe._resolve_maps(config, _client())

    assert _row(out)["left"]["path"] == {"attributeId": "a1"}


def test_an_unknown_variable_fails_loudly_before_anything_is_written():
    config = {"processId": PID,
              "inputMap": [{"id": 0, "left": {"value": "nope"}, "right": {"value": "f"}}]}

    with pytest.raises(UsageError) as e:
        fe._resolve_maps(config, _client())

    assert "nope" in str(e.value)
    assert "clientName" in str(e.value), "the error must name what IS available"


def test_a_config_without_a_process_id_is_refused():
    with pytest.raises(UsageError):
        fe._resolve_maps({"outputMap": []}, _client())
