# -*- coding: utf-8 -*-
"""Transport: a Data Store mapper must be repaired before a pack is shipped.

WHY THIS EXISTS. The platform's EXPORT re-spells every Data Store mapper row
from the shape the back end accepts into the Call SubProcess wire shape, and
the import does not translate it back:

    accepted   {"id": i, "source": {"value": "<%i%>",
                                    "variable": [{"id": i, "variableId": g,
                                                  "attribute": None}]},
                "column": "<NAME>"}
    in a pack  {"id": i, "process": "<flowId>.<variableId>",
                "document": "<NAME>"}

Nothing is lost - the column name and the variable GUID both survive under
different keys - so every structural check passes on a process that cannot
run. It fails only when executed, with "A Data Store Decisional column
reference cannot be null or empty".

These tests assert on the TRANSFORMED PACK, because that is the artefact
shipped and the defect is invisible in any response.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio.handlers import transport

FLOW_ID = "8463a145-78a8-490b-a1da-a2e6615c231c"
VAR_0 = "b3bf9af2-52ea-4192-94b0-b95afef7fa4a"
VAR_1 = "b55f6ad7-3499-4820-b2f5-e9d62d9c773b"


def _pack(rows):
    return {"DataTypes": [], "Credentials": [], "Webhooks": [],
            "DocumentTemplates": [], "Forms": [], "DataStores": [],
            "TimeStamp": "2026-08-24T00:00:00Z",
            "Flows": [{"Title": "w", "Id": FLOW_ID, "Variables": [],
                       "Actions": [{"Parameters": [
                           {"TabPropertyId": "x", "Value": rows,
                            "Variable": []}]}]}]}


def _exported_rows():
    return [{"id": 0, "process": "%s.%s" % (FLOW_ID, VAR_0),
             "document": "row_key"},
            {"id": 1, "process": "%s.%s" % (FLOW_ID, VAR_1),
             "document": "tenant_id"}]


def _repair(pack):
    return transport.repair_datastore_mapper_pack(pack)


def test_exported_rows_are_rewritten_into_the_accepted_shape():
    out, changed = _repair(_pack(_exported_rows()))
    rows = out["Flows"][0]["Actions"][0]["Parameters"][0]["Value"]
    assert changed == 2
    assert sorted(rows[0]) == ["column", "id", "source"]
    assert rows[0]["column"] == "row_key"
    assert rows[0]["source"]["value"] == "<%0%>"
    assert rows[0]["source"]["variable"] == [
        {"id": 0, "variableId": VAR_0, "attribute": None}]


def test_the_placeholder_index_tracks_the_row_id():
    """The <%i%> placeholder must match the id INSIDE its own inline array."""
    out, _ = _repair(_pack(_exported_rows()))
    for row in out["Flows"][0]["Actions"][0]["Parameters"][0]["Value"]:
        i = row["id"]
        assert row["source"]["value"] == "<%%%d%%>" % i
        assert row["source"]["variable"][0]["id"] == i


def test_the_variable_guid_is_taken_from_the_composite_not_invented():
    out, _ = _repair(_pack(_exported_rows()))
    rows = out["Flows"][0]["Actions"][0]["Parameters"][0]["Value"]
    assert [r["source"]["variable"][0]["variableId"] for r in rows] == \
        [VAR_0, VAR_1]


def test_no_document_or_process_key_survives():
    out, _ = _repair(_pack(_exported_rows()))
    blob = json.dumps(out)
    assert '"document"' not in blob
    assert '"process"' not in blob
    assert blob.count('"column"') == 2
    assert blob.count('"source"') == 2


def test_it_is_IDEMPOTENT_so_a_fixed_export_is_never_corrupted():
    """If PROCESIO fixes the export, this must become a no-op.

    A repair that mangles an already-correct pack is worse than no repair,
    because it would break the very case it is waiting for.
    """
    once, first = _repair(_pack(_exported_rows()))
    twice, second = _repair(once)
    assert second == 0, "a second pass must change nothing"
    assert twice == once


def test_an_already_accepted_row_is_passed_through_untouched():
    good = [{"id": 0,
             "source": {"value": "<%0%>",
                        "variable": [{"id": 0, "variableId": VAR_0,
                                      "attribute": None}]},
             "column": "row_key"}]
    out, changed = _repair(_pack(good))
    assert changed == 0
    assert out["Flows"][0]["Actions"][0]["Parameters"][0]["Value"] == good


def test_the_parameter_variable_list_stays_empty():
    """The variable array belongs INSIDE the source operand, not on the
    parameter. Populating both is what fourteen earlier shapes got wrong."""
    out, _ = _repair(_pack(_exported_rows()))
    assert out["Flows"][0]["Actions"][0]["Parameters"][0]["Variable"] == []


def test_a_pack_with_no_mapper_is_left_alone():
    pack = _pack([{"id": 0, "somethingElse": 1}])
    out, changed = _repair(pack)
    assert changed == 0
    assert out == pack


def test_the_input_pack_is_not_mutated_in_place():
    src = _pack(_exported_rows())
    before = json.dumps(src)
    _repair(src)
    assert json.dumps(src) == before, "the caller's pack must be untouched"


def test_the_action_is_registered_and_offline():
    a = transport.ACTIONS["repair-datastore-mapper"]
    assert a.needs_client is False, "this is an offline pack transform"
    assert a.description


@pytest.mark.parametrize("bad", [None, 12, "text", [], [1, 2]])
def test_a_non_mapper_parameter_value_is_ignored(bad):
    pack = _pack(_exported_rows())
    pack["Flows"][0]["Actions"][0]["Parameters"].append(
        {"TabPropertyId": "y", "Value": bad, "Variable": []})
    out, changed = _repair(pack)
    assert changed == 2
    assert out["Flows"][0]["Actions"][0]["Parameters"][1]["Value"] == bad
