"""Three form gaps measured live on QA on 2026-09-25 while testing Approval Control events.

1. form-create left the top-level `Assignees` empty on a form whose section had an assignee
   and whose approval control had an approver. The designer's save
   (user-playground Builder.component.vue::save + ui-builder utils/formBuilder/payload.ts)
   builds one ASSIGNEE step (type 1) per element with assignee users and one APPROVER step
   (type 2) per element with approver users: `{stepId: <element id>, orderId: n, users:
   [{userId}]}`, orderId counting 1, 2, 3 within each list.
2. form-create built a form data model with only `instance, fields` and no
   `dataModelAttributeFormatVersion`. The designer writes `instance, flow, fields,
   preventFormSubmit, browserTitle` and version "1" for a new form. Without the version the
   designer treats the form as the legacy "0" format and LOWER-CASES every field attribute on
   its next save (measured: `RequestText` became `requesttext`); without `preventFormSubmit`
   a form script cannot block a submit.
3. form-set-element-event refused to wire an approval trigger on an approval control saved
   before its event slots existed (old forms). The runtime back-fills missing configs from
   the element template on every load (ui-builder utils/formBuilder/elements.ts::
   actualizeElements); the CLI now does the same for the one slot it needs, and says so.
"""
from __future__ import annotations

import json

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import builder
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
U1, U2, U3 = "u-1111", "u-2222", "u-3333"


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


def _ids():
    n = iter(range(10_000))
    return {"new_id": lambda: f"id-{next(n)}"}


def _by_type(dto, kind):
    return [e for e in dto["Data"]["elements"] if e["type"] == kind]


# --------------------------------------------------------------------------- gap 1

def _approval_form(**top):
    return {
        "name": "AUTO approval gaps",
        **top,
        "elements": [
            {"type": "section", "label": "Request", "configs": {"assignee": U1},
             "children": [{"type": "input", "label": "Text", "name": "RequestText"}]},
            {"type": "approval", "label": "Approval step", "name": "Approval1",
             "approver": U2, "configs": {"approverReplacement": [U3, "", U2]}},
            {"type": "button", "label": "Submit", "submit": True},
        ],
    }


def test_assignees_are_derived_from_assignee_and_approver_configs_like_the_designer():
    dto = builder.build(_approval_form(isPrivate=True), _ids())
    section, = _by_type(dto, "section")
    approval, = _by_type(dto, "approval")
    assert dto["Assignees"] == [
        {"stepId": section["id"], "orderId": 1, "type": 1, "users": [{"userId": U1}]},
        # approver first, then replacements; blanks dropped, duplicates collapsed
        {"stepId": approval["id"], "orderId": 1, "type": 2,
         "users": [{"userId": U2}, {"userId": U3}]},
    ]


def test_order_ids_count_within_each_list():
    cfg = _approval_form()
    cfg["elements"].insert(2, {"type": "approval", "label": "Second", "name": "Approval2",
                               "approver": U3})
    dto = builder.build(cfg, _ids())
    approvers = [a for a in dto["Assignees"] if a["type"] == 2]
    assert [a["orderId"] for a in approvers] == [1, 2]
    assert [a["users"][0]["userId"] for a in approvers] == [U2, U3]


def test_a_form_with_approvers_becomes_a_user_task_when_type_is_not_given():
    assert builder.build(_approval_form(), _ids())["Type"] == 0


def test_an_explicit_type_is_respected():
    assert builder.build(_approval_form(type="general"), _ids())["Type"] == 1


def test_explicit_assignees_in_the_config_still_win_verbatim():
    mine = [{"stepId": "S", "orderId": 7, "type": 2, "users": [{"userId": "X"}]}]
    assert builder.build(_approval_form(assignees=mine), _ids())["Assignees"] == mine


def test_a_form_without_assignees_is_unchanged():
    dto = builder.build({"name": "plain", "elements": [{"type": "input", "label": "A"}]}, _ids())
    assert dto["Assignees"] == [] and dto["Type"] == 1


# --------------------------------------------------------------------------- gap 2

PREVENT = "d63722f4-0cd1-4bc2-8174-28276e7c7ab5"
TITLE = "b8c1f2a3-4d5e-4a6b-8c7d-9e0f1a2b3c4d"
FLOW = "c16e9d56-8484-444d-b1c5-36e48afb1d3d"
INSTANCE = "8b49c48a-0834-40d0-920a-4c53566495a8"
BOOL, STR = "0317bfee-b2f5-4bde-bfe8-121212121210", "0317bfee-b2f5-4bde-bfe8-121212121214"


def test_data_model_matches_what_the_designer_saves_for_a_new_form():
    dto = builder.build(_approval_form(), _ids())
    data = dto["Data"]
    assert data["dataModelAttributeFormatVersion"] == "1"
    dm = data["dataModel"]
    top = {a["name"]: a for a in dm["attributes"]}
    assert [a["name"] for a in dm["attributes"]] == [
        "instance", "flow", "fields", "preventFormSubmit", "browserTitle"]
    root = data["variables"][0]["id"]
    assert dm["id"] == root
    assert all(a["parentDataTypeId"] == root for a in dm["attributes"])
    assert (top["preventFormSubmit"]["id"], top["preventFormSubmit"]["dataTypeId"]) == (PREVENT, BOOL)
    assert (top["browserTitle"]["id"], top["browserTitle"]["dataTypeId"]) == (TITLE, STR)
    assert top["flow"]["id"] == FLOW and "statusEnum" in [a["name"] for a in top["flow"]["attributes"]]
    assert top["instance"]["id"] == INSTANCE
    assert [a["name"] for a in top["instance"]["attributes"]] == [
        "id", "workspaceId", "submitter", "currentUser"]
    # the fields container still carries one sub-model per element, named as-is (format "1")
    assert "RequestText" in [a["name"] for a in top["fields"]["attributes"]]


# --------------------------------------------------------------------------- gap 3

def _old_form():
    """An approval control as saved before its event slots existed (QA form 8d789e26…,
    created 2025-06-03): 15 configs, no onBefore*/onAfter* keys."""
    old_keys = ["label", "tooltip", "description", "info-text", "visible", "comment",
                "responseDate", "responseUser", "response", "name", "id", "approver",
                "approverReplacement", "additionalApprovers", "onInputEvents"]
    configs = [{"id": f"c-{k}", "key": k, "value": None} for k in old_keys]
    next(c for c in configs if c["key"] == "name")["value"] = "Approval1"
    return {
        "id": "F-OLD", "name": "Complex (Copy)", "isPrivate": True, "type": 0, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {"code": "", "dataModel": {"id": "dm"}, "elements": [
            {"id": "A1", "type": "approval", "configs": configs},
            {"id": "I1", "type": "input", "configs": [{"id": "c-n", "key": "name", "value": "Input1"}]},
        ]},
    }


_JS = {"code": "console.log($event)"}


def test_a_missing_approval_slot_is_backfilled_from_the_template_and_reported():
    s = FakeSession(queue=[FakeResp(200, _old_form()), FakeResp(200, _old_form()), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F-OLD", "--element", "Approval1", "--on", "beforeapprove",
                 "--action", "RUN_JAVASCRIPT", "--config", json.dumps(_JS)], s)

    assert out["updated"] is True
    assert out["backfilled"] == ["onBeforeApproveEvents"]
    put = s.calls[-1]
    assert put["method"] == "PUT"
    els = put["json"]["Data"]["elements"]
    assert els[1] == _old_form()["data"]["elements"][1]            # sibling untouched
    configs = els[0]["configs"]
    slot = [c for c in configs if c["key"] == "onBeforeApproveEvents"]
    assert len(slot) == 1
    assert slot[0]["type"] == "field-events" and slot[0]["id"] not in {c.get("id") for c in _old_form()["data"]["elements"][0]["configs"]}
    assert slot[0]["value"]["events"][0]["type"] == "BEFORE_APPROVE"
    # every existing config survives, in its original order
    assert [c for c in configs if c["key"] != "onBeforeApproveEvents"] == _old_form()["data"]["elements"][0]["configs"]


def test_dry_run_reports_the_backfill_without_writing():
    s = FakeSession(queue=[FakeResp(200, _old_form())])
    out = _call("form-set-element-event",
                ["--id", "F-OLD", "--element", "Approval1", "--on", "afterapprovalsubmit",
                 "--action", "RUN_JAVASCRIPT", "--config", json.dumps(_JS), "--dry-run"], s)
    assert out["dry_run"] is True and out["backfilled"] == ["onAfterApprovalSubmitEvents"]
    assert all(c["method"] == "GET" for c in s.calls)


def test_a_trigger_the_element_type_cannot_raise_is_still_refused():
    s = FakeSession(queue=[FakeResp(200, _old_form())])
    with pytest.raises(UsageError, match="cannot raise"):
        _call("form-set-element-event",
              ["--id", "F-OLD", "--element", "Input1", "--on", "beforeapprove",
               "--action", "RUN_JAVASCRIPT", "--config", json.dumps(_JS)], s)
    assert all(c["method"] == "GET" for c in s.calls)


def test_an_existing_slot_is_used_as_is_and_nothing_is_reported_as_backfilled():
    s = FakeSession(queue=[FakeResp(200, _old_form()), FakeResp(200, _old_form()), FakeResp(200, {})])
    out = _call("form-set-element-event",
                ["--id", "F-OLD", "--element", "Approval1", "--on", "input",
                 "--action", "RUN_JAVASCRIPT", "--config", json.dumps(_JS)], s)
    assert out["backfilled"] == []
    configs = s.calls[-1]["json"]["Data"]["elements"][0]["configs"]
    assert len(configs) == len(_old_form()["data"]["elements"][0]["configs"])


# --------------------------------------------------------------- dynamic-row approval steps
# Shape of a real designer-saved "Dynamic Table Approval" form (QA, ids replaced): approval
# steps live in each dynamic row's `approvalSteps`, and each step is its own APPROVER step.

def _cfg_el(eid, etype, parent=None, **configs):
    return {"id": eid, "type": etype, "parentId": parent,
            "configs": [{"key": k, "value": v} for k, v in configs.items()]}


def _step(sid, approver, replacement=None, row_index="0"):
    return {"id": sid, "rowIndex": row_index, "approver": approver,
            "approverReplacement": replacement or []}


def _table_form():
    return [
        _cfg_el("SEC", "section", assignee=U1),
        _cfg_el("T", "table", assignee=U2),
        _cfg_el("R1", "dynamic-table-row", "T", visible=True, approvalSteps=[
            _step("S1", U1), _step("S2", U2, [U3, U2]),
            _step("S-UNPLACED", U3, row_index=None)]),        # no rowIndex: not a step
        _cfg_el("R2", "dynamic-table-row", "T", visible=False,  # hidden row: no steps
                approvalSteps=[_step("S-HIDDEN", U1)]),
        _cfg_el("R3", "dynamic-table-row", "SEC",               # not in a table: no steps
                approvalSteps=[_step("S-ORPHAN", U1)]),
        _cfg_el("A", "approval", approver=U3),
    ]


def test_dynamic_row_approval_steps_are_their_own_steps_like_the_designer():
    rows = builder.derive_assignees(_table_form())
    assert [(r["type"], r["stepId"], r["orderId"], [u["userId"] for u in r["users"]])
            for r in rows] == [
        (1, "SEC", 1, [U1]), (1, "T", 2, [U2]),
        (2, "S1", 1, [U1]), (2, "S2", 2, [U2, U3]), (2, "A", 3, [U3]),
    ]


# --------------------------------------------------------------- surgical edits keep routing true

def test_an_edit_that_does_not_change_routing_keeps_the_stored_list_byte_for_byte():
    stale = [{"stepId": "whatever", "orderId": 9, "type": 2, "users": [{"userId": "x"}]}]
    before = [_cfg_el("A", "approval", approver=U1, label="Old")]
    after = [_cfg_el("A", "approval", approver=U1, label="New")]
    assert builder.reconcile_assignees(stale, before, after) == (stale, None)


def test_an_edit_that_changes_routing_rederives_the_whole_list():
    before = [_cfg_el("A", "approval", approver=U1)]
    after = [_cfg_el("A", "approval", approver=U2)]
    saved, report = builder.reconcile_assignees([], before, after)
    assert saved == [{"stepId": "A", "orderId": 1, "type": 2, "users": [{"userId": U2}]}]
    assert report["rederived"] is True and report["after"] == [("A", 1, 2, (U2,))]


def _live_approval_form(**top):
    approver = {"id": "c-appr", "key": "approver", "value": U1}
    return {
        "id": "F-LIVE", "name": "Live", "isPrivate": True, "type": 0, "status": 1, "state": True,
        "customUrl": None,
        "assignees": [{"stepId": "A1", "orderId": 1, "type": 2,
                       "users": [{"userId": U1, "firstName": "G", "lastName": "G"}]}],
        "data": {
            "code": "", "variables": [{"id": "root", "dataType": "root", "name": "form"}],
            "dataModel": {"id": "root", "name": "form", "attributes": [
                {"id": "11223344-5566-7788-99aa-aabbccddeeff", "name": "fields",
                 "parentDataTypeId": "root", "attributes": []}]},
            "elements": [
                {"id": "A1", "type": "approval", "parentId": None, "section": "body",
                 "configs": [{"id": "c-name", "key": "name", "value": "Approval1"},
                             {"id": "c-label", "key": "label", "value": "Approve"}, approver]},
            ]},
        **top,
    }


def test_set_element_config_rederives_assignees_when_the_approver_changes():
    s = FakeSession(queue=[FakeResp(200, _live_approval_form()), FakeResp(200, {})])
    out = _call("form-set-element-config",
                ["--id", "F-LIVE", "--element", "Approval1", "--set", f"approver={U2}"], s)
    put = s.calls[-1]["json"]
    assert put["Assignees"] == [{"stepId": "A1", "orderId": 1, "type": 2, "users": [{"userId": U2}]}]
    assert out["assignees"]["rederived"] is True


def test_set_element_config_leaves_assignees_alone_for_a_label_change():
    s = FakeSession(queue=[FakeResp(200, _live_approval_form()), FakeResp(200, {})])
    out = _call("form-set-element-config",
                ["--id", "F-LIVE", "--element", "Approval1", "--set", "label=Check"], s)
    assert s.calls[-1]["json"]["Assignees"] == _live_approval_form()["assignees"]   # echoed
    assert "assignees" not in out


def test_add_element_routes_a_new_approval_control():
    s = FakeSession(queue=[FakeResp(200, _live_approval_form()), FakeResp(200, {})])
    spec = {"type": "approval", "name": "Approval2", "approver": U3}
    out = _call("form-add-element", ["--id", "F-LIVE", "--elements", json.dumps(spec)], s)
    put = s.calls[-1]["json"]
    new_id = out["added"][0]["id"]
    assert put["Assignees"] == [
        {"stepId": "A1", "orderId": 1, "type": 2, "users": [{"userId": U1}]},
        {"stepId": new_id, "orderId": 2, "type": 2, "users": [{"userId": U3}]},
    ]
    assert out["assignees"]["rederived"] is True


def test_delete_element_unroutes_a_removed_approval_control():
    s = FakeSession(queue=[FakeResp(200, _live_approval_form()), FakeResp(200, {})])
    out = _call("form-delete-element", ["--id", "F-LIVE", "--element", "Approval1"], s)
    assert s.calls[-1]["json"]["Assignees"] == []
    assert out["assignees"]["rederived"] is True
