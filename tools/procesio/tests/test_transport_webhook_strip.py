# -*- coding: utf-8 -*-
"""Transport: a webhook binding must be stripped before a pack is shipped.

WHY THIS EXISTS. Everything else a process depends on is left behind by an
export - Data Store rows, credentials - so an imported process arrives visibly
incomplete and someone provisions it. A webhook BINDING is the exception: it
lives in the process definition, so it TRAVELS.

    the schema, asked with nothing bound:
        webhooks/0: Additional properties are not allowed ('id' was unexpected)
        webhooks/0: 'webhookId' is a required property

And the launch endpoint is anonymous - every verb on /api/Webhooks/launch/{id}
documents "Permission required: None" - so the id IS the access control.

A pack therefore carries a live capability for the SOURCE installation while
being LESS functional at the destination, where the id names nothing. That is
the opposite failure direction from every other missing binding, and a pack is
the artefact designed to be handed to a customer.

The export path already excludes credentials by default. This is the same
policy applied to the one binding that does travel.

These tests assert on the TRANSFORMED PACK, because that is the artefact
shipped, and they search for the id in the serialised bytes rather than
trusting a count - a report of "1 removed" is not evidence that no copy
survives somewhere else in the document.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio.handlers import transport

FLOW_ID = "8463a145-78a8-490b-a1da-a2e6615c231c"
HOOK_A = "a39d899f-1c4e-4db2-974f-cd85c5c013f8"
HOOK_B = "b30f3633-c39d-4a40-845b-55f322db2f33"


def _pack(flow_hooks=None, top_hooks=None):
    return {"DataTypes": [], "Credentials": [],
            "Webhooks": list(top_hooks or []),
            "DocumentTemplates": [], "Forms": [], "DataStores": [],
            "TimeStamp": "2026-08-26T00:00:00Z",
            "Flows": [{"Title": "w", "Id": FLOW_ID, "Variables": [],
                       "Webhooks": list(flow_hooks or []),
                       "Actions": [{"Parameters": []}]}]}


def _strip(pack):
    return transport.strip_webhook_bindings_pack(pack)


# --- it removes what it is for -------------------------------------------

def test_a_bound_flow_exports_with_the_array_emptied():
    out, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    assert out["Flows"][0]["Webhooks"] == []
    assert rep["flow_bindings_removed"] == 1


def test_the_id_is_absent_from_the_serialised_pack():
    """The artefact is what ships, so the artefact is what is searched."""
    out, _ = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    blob = json.dumps(out, ensure_ascii=False)
    assert HOOK_A not in blob


def test_the_id_is_absent_dash_stripped_too():
    """A GUID written without dashes is the same secret."""
    out, _ = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    blob = json.dumps(out, ensure_ascii=False)
    assert HOOK_A.replace("-", "") not in blob.replace("-", "")


def test_several_bindings_on_one_flow_all_go():
    out, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A},
                                        {"webhookId": HOOK_B}]))
    assert out["Flows"][0]["Webhooks"] == []
    assert rep["flow_bindings_removed"] == 2
    blob = json.dumps(out, ensure_ascii=False)
    assert HOOK_A not in blob and HOOK_B not in blob


def test_top_level_webhook_entities_are_removed_and_counted_separately():
    """Two arrays, two exposures. A pack author who passed --webhooks
    deliberately is entitled to be told which of the two was removed."""
    out, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}],
                            top_hooks=[{"Id": HOOK_B, "Name": "n"}]))
    assert out["Webhooks"] == []
    assert rep["flow_bindings_removed"] == 1
    assert rep["webhook_entities_removed"] == 1


def test_an_id_hidden_anywhere_else_is_reported_not_silently_left():
    """The strip removes two known arrays. If a copy of a webhook id survives
    somewhere else in the pack, saying nothing would be worse than the leak -
    the caller would believe the pack was clean."""
    p = _pack(flow_hooks=[{"webhookId": HOOK_A}])
    p["Flows"][0]["Actions"][0]["Parameters"].append(
        {"TabPropertyId": "x", "Value": "https://host/api/Webhooks/launch/%s"
                                        % HOOK_A, "Variable": []})
    out, rep = _strip(p)
    assert out["Flows"][0]["Webhooks"] == []
    assert rep["residual_ids_found"] == 1
    assert rep["clean"] is False


# --- it is idempotent -----------------------------------------------------

def test_a_pack_with_no_webhooks_is_unchanged():
    src = _pack()
    out, rep = _strip(src)
    assert out == src
    assert rep["flow_bindings_removed"] == 0
    assert rep["webhook_entities_removed"] == 0
    assert rep["already_clean"] is True


def test_running_it_twice_changes_nothing_the_second_time():
    once, _ = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    twice, rep = _strip(once)
    assert twice == once
    assert rep["already_clean"] is True


def test_a_flow_with_no_webhooks_key_at_all_is_left_alone():
    """Absence of the key is not the same as an empty array, and inventing the
    key would change the pack the import sees."""
    src = _pack()
    del src["Flows"][0]["Webhooks"]
    out, rep = _strip(src)
    assert "Webhooks" not in out["Flows"][0]
    assert rep["already_clean"] is True


# --- it does not damage what it is not for --------------------------------

def test_the_input_is_never_mutated():
    src = _pack(flow_hooks=[{"webhookId": HOOK_A}])
    _strip(src)
    assert src["Flows"][0]["Webhooks"] == [{"webhookId": HOOK_A}]


def test_everything_else_in_the_pack_survives_byte_for_byte():
    src = _pack(flow_hooks=[{"webhookId": HOOK_A}])
    src["Flows"][0]["Actions"][0]["Parameters"].append(
        {"TabPropertyId": "keep", "Value": [{"id": 0, "column": "row_key"}],
         "Variable": []})
    out, _ = _strip(src)
    a, b = json.loads(json.dumps(src)), json.loads(json.dumps(out))
    a["Flows"][0]["Webhooks"] = []
    assert a == b


def test_a_camelcase_definition_is_handled_too():
    """A pack uses PascalCase; a definition read back from get-process uses
    camelCase. The same function is used to check both, so it must see both."""
    d = {"flow": {"webhooks": [{"webhookId": HOOK_A}], "actions": []}}
    out, rep = transport.strip_webhook_bindings_pack(d)
    assert out["flow"]["webhooks"] == []
    assert rep["flow_bindings_removed"] == 1


# --- the report is honest -------------------------------------------------

def test_the_report_names_the_flows_it_touched_not_just_a_count():
    out, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    assert rep["flows_unbound"] == [FLOW_ID]


def test_the_report_never_carries_the_id_itself():
    """A report is printed and logged. It must be safe to print."""
    _, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}],
                          top_hooks=[{"Id": HOOK_B}]))
    blob = json.dumps(rep, ensure_ascii=False)
    assert HOOK_A not in blob
    assert HOOK_B not in blob


def test_clean_is_true_only_when_nothing_residual_remains():
    _, rep = _strip(_pack(flow_hooks=[{"webhookId": HOOK_A}]))
    assert rep["clean"] is True


def test_a_launch_url_with_no_binding_to_strip_still_makes_clean_false():
    """The id-keyed residual scan is blind to a launch URL that was never a binding: a pack
    with no Webhooks key but a pasted /api/Webhooks/launch/ URL in a Call API parameter
    removes nothing, so removed_ids is empty and the id-based residual count is zero. The
    independent launch-URL scan is what keeps 'clean' honest - the endpoint is anonymous, so
    the URL is the live capability whether or not a binding was present to strip."""
    unbound = "c1a2b3c4-d5e6-47f8-9a0b-1c2d3e4f5061"
    p = _pack()
    del p["Webhooks"]
    del p["Flows"][0]["Webhooks"]
    p["Flows"][0]["Actions"][0]["Parameters"].append(
        {"TabPropertyId": "x",
         "Value": "https://host/api/Webhooks/launch/%s" % unbound, "Variable": []})
    out, rep = _strip(p)
    assert rep["flow_bindings_removed"] == 0
    assert rep["residual_ids_found"] == 0        # nothing removed, so the id-keyed scan finds nothing
    assert rep["launch_urls_found"] == 1
    assert rep["clean"] is False


# --- the action wiring ----------------------------------------------------

def test_the_action_is_registered_and_needs_no_client():
    a = transport.ACTIONS["strip-webhook-bindings"]
    assert a.needs_client is False


def test_the_cli_writes_the_stripped_pack(tmp_path):
    src = tmp_path / "in.procesio"
    dst = tmp_path / "out.procesio"
    src.write_text(json.dumps(_pack(flow_hooks=[{"webhookId": HOOK_A}])),
                   encoding="utf-8")

    class A:
        in_path, out_path, dry_run = str(src), str(dst), False

    res = transport.strip_webhook_bindings(A())["result"]
    assert res["flow_bindings_removed"] == 1
    assert res["written"] == str(dst)
    assert HOOK_A not in dst.read_text(encoding="utf-8")


def test_a_dry_run_writes_nothing(tmp_path):
    src = tmp_path / "in.procesio"
    dst = tmp_path / "out.procesio"
    src.write_text(json.dumps(_pack(flow_hooks=[{"webhookId": HOOK_A}])),
                   encoding="utf-8")

    class A:
        in_path, out_path, dry_run = str(src), str(dst), True

    res = transport.strip_webhook_bindings(A())["result"]
    assert res["flow_bindings_removed"] == 1
    assert res["written"] is None
    assert not dst.exists()


def test_bad_json_is_a_usage_error(tmp_path):
    src = tmp_path / "in.procesio"
    src.write_text("{not json", encoding="utf-8")

    class A:
        in_path, out_path, dry_run = str(src), None, False

    with pytest.raises(Exception):
        transport.strip_webhook_bindings(A())
