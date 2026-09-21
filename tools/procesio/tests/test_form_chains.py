"""form-set-element-chains: rewrite ordered event chains from names, in one save.

The action exists because a MAP_FORM_DATA row or condition pointing at a wrong path is saved
without an error and then silently does nothing, so every name is resolved (and every unknown one
refused) before the single PUT."""
from __future__ import annotations

import json

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form.fieldpath import FIELDS_NS
from tools.procesio.tests.conftest import FakeResp, FakeSession

ROOT = "root-1"


def _builder(session):
    return lambda prof: ProcesioClient(
        profile={"type": "apikey", "key": "N", "value": "V"}, name="t", session=session)


def _form():
    return {
        "id": "F1", "name": "F", "type": 0, "status": 1, "state": True,
        "data": {
            "dataModel": {"id": ROOT},
            "variables": [{"name": "form", "id": ROOT}, {"name": "isPF", "id": "var-pf"}],
            "elements": [
                {"id": "btn", "type": "button", "configs": [
                    {"id": "c-btn-name", "key": "name", "value": "validate"},
                    {"id": "c-btn-vis", "key": "visible", "value": True},
                    {"id": "c-btn-click", "key": "onClickEvents", "value": {"debounce": 0, "events": [
                        {"id": "ev-js1", "type": "CLICK", "action": "RUN_JAVASCRIPT",
                         "config": {"code": "a()"}},
                        {"id": "ev-map", "type": "CLICK", "action": "MAP_FORM_DATA",
                         "config": {"mapping": []}},
                        {"id": "ev-js2", "type": "CLICK", "action": "RUN_JAVASCRIPT",
                         "config": {"code": "b()"}},
                    ]}},
                ]},
                {"id": "inp", "type": "input", "configs": [
                    {"id": "c-inp-name", "key": "name", "value": "Input2"},
                    {"id": "c-inp-val", "key": "value", "value": ""},
                    {"id": "c-inp-dis", "key": "disabled", "value": False},
                ]},
                {"id": "flag", "type": "number-input", "configs": [
                    {"id": "c-flag-name", "key": "name", "value": "flag"},
                    {"id": "c-flag-val", "key": "value", "value": ""},
                    {"id": "c-flag-input", "key": "onInputEvents",
                     "value": {"debounce": 0, "events": []}},
                ]},
                {"id": "step2", "type": "step", "configs": [
                    {"id": "c-step-name", "key": "name", "value": "step-two"},
                    {"id": "c-step-vis", "key": "visible", "value": False},
                ]},
            ]},
    }


def _run(plan, *extra, queue=None):
    sess = FakeSession(queue=queue or [FakeResp(200, _form()), FakeResp(200, {})])
    out = main.dispatch("form-set-element-chains",
                        ["--id", "F1", "--plan", json.dumps(plan), *extra],
                        client_builder=_builder(sess))
    return out, sess


def _put_events(sess, element_id, key):
    put = sess.calls[-1]
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    el = next(e for e in put["json"]["Data"]["elements"] if e["id"] == element_id)
    return next(c for c in el["configs"] if c["key"] == key)["value"]["events"]


def _path(element_id, config_id):
    return f"{ROOT}.{FIELDS_NS}.{element_id}.{config_id}"


def test_keeps_verbatim_builds_map_from_names_and_drops_the_rest():
    plan = {"chains": [{"element": "validate", "on": "click", "events": [
        {"keep": "ev-js1"},
        {"map": {"set": {"Input2.disabled": True, "step-two.visible": True, "@isPF": False},
                 "when": [{"field": "flag", "op": "EQUALS", "value": "1"},
                          {"variable": "isPF", "op": "is_true"}]}},
        {"js": "c()"},
    ]}]}
    out, sess = _run(plan)
    events = _put_events(sess, "btn", "onClickEvents")
    assert [e["action"] for e in events] == ["RUN_JAVASCRIPT", "MAP_FORM_DATA", "RUN_JAVASCRIPT"]
    assert events[0] == {"id": "ev-js1", "type": "CLICK", "action": "RUN_JAVASCRIPT",
                         "config": {"code": "a()"}}
    cfg = events[1]["config"]
    assert cfg["mapping"] == [
        {"id": 0, "left": _path("inp", "c-inp-dis"), "right": "true"},
        {"id": 1, "left": _path("step2", "c-step-vis"), "right": "true"},
        {"id": 2, "left": "var-pf", "right": "false"},
    ]
    assert cfg["areConditionsConfigured"] is True
    c0, c1 = cfg["conditions"]
    # a field operand addresses the element's VALUE config; the first condition links with AND
    assert c0["leftOperator"]["value"] == _path("flag", "c-flag-val")
    assert (c0["operator"], c0["rightOperator"]["value"], c0["logicOperator"]) == ("EQUALS", "1", 1)
    assert c0["operandsAsListOptional"] is True
    assert c1["leftOperator"]["value"] == "var-pf"
    assert (c1["operator"], c1["logicOperator"], c1["operandsAsListOptional"]) == ("IS_TRUE", 0, False)
    assert events[1]["type"] == "CLICK" and events[2]["config"] == {"code": "c()"}
    report = out["chains"][0]
    assert report["kept"] == ["ev-js1"] and report["dropped"] == ["ev-map", "ev-js2"]
    assert report["events"][1]["set"] == {"Input2.disabled": "true", "step-two.visible": "true",
                                          "@isPF": "false"}


def test_unconditional_map_carries_no_conditions_key_and_any_means_or():
    plan = {"chains": [{"element": "flag", "on": "input", "events": [
        {"map": {"set": {"step-two.visible": True}}},
        {"map": {"set": {"Input2.disabled": False}, "match": "any",
                 "when": [{"field": "Input2.disabled", "op": "IS_TRUE"},
                          {"field": "flag", "op": "IS_EMPTY"}]}},
    ]}]}
    _, sess = _run(plan)
    events = _put_events(sess, "flag", "onInputEvents")
    assert events[0]["type"] == "INPUT"
    assert set(events[0]["config"]) == {"mapping"}
    conds = events[1]["config"]["conditions"]
    assert conds[0]["leftOperator"]["value"] == _path("inp", "c-inp-dis")
    assert [c["logicOperator"] for c in conds] == [2, 0]
    # the designer's flag follows the operator: IS_TRUE false, IS_EMPTY true - on a field too
    assert [c["operandsAsListOptional"] for c in conds] == [False, True]


def test_several_elements_land_in_one_put():
    plan = {"chains": [
        {"element": "validate", "on": "click", "events": [{"keep": "ev-js2"}]},
        {"element": "flag", "on": "input", "events": [{"js": "go()"}]},
    ]}
    out, sess = _run(plan)
    assert [c["method"] for c in sess.calls] == ["GET", "PUT"]
    assert [e["id"] for e in _put_events(sess, "btn", "onClickEvents")] == ["ev-js2"]
    assert _put_events(sess, "flag", "onInputEvents")[0]["config"]["code"] == "go()"
    assert out["updated"] is True and out["elements"] == 4


def test_dry_run_reports_names_and_does_not_write():
    plan = {"chains": [{"element": "validate", "on": "click", "events": [
        {"map": {"set": {"step-two.visible": True},
                 "when": [{"field": "flag", "op": "EQUALS", "value": 1}]}}]}]}
    out, sess = _run(plan, "--dry-run", queue=[FakeResp(200, _form())])
    assert out["dry_run"] is True
    assert [c["method"] for c in sess.calls] == ["GET"]
    assert out["chains"][0]["events"][0]["when"] == ["flag.value EQUALS '1'"]


@pytest.mark.parametrize("event, needle", [
    ({"map": {"set": {"Input2.visibility": True}}}, "no 'visibility' config"),
    ({"map": {"set": {"Nope.visible": True}}}, "not an element"),
    ({"map": {"set": {"@nope": True}}}, "not a form variable"),
    ({"map": {"set": {"Input2.disabled": True},
              "when": [{"field": "flag", "op": "ROUGHLY"}]}}, "is not one of"),
    ({"map": {"set": {"Input2.disabled": True}, "match": "some",
              "when": [{"field": "flag", "op": "IS_TRUE"}]}}, "match must be"),
    ({"keep": "ev-missing"}, "no event 'ev-missing'"),
    ({"js": "  "}, "empty JavaScript"),
    ({"teleport": 1}, "unknown event kind"),
])
def test_unresolvable_plans_are_refused_before_any_write(event, needle):
    plan = {"chains": [{"element": "validate", "on": "click", "events": [event]}]}
    sess = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(errors.UsageError) as e:
        main.dispatch("form-set-element-chains", ["--id", "F1", "--plan", json.dumps(plan)],
                      client_builder=_builder(sess))
    assert needle in str(e.value)
    assert all(c["method"] == "GET" for c in sess.calls)


def test_same_element_trigger_twice_is_refused():
    plan = {"chains": [
        {"element": "validate", "on": "click", "events": [{"keep": "ev-js1"}]},
        {"element": "btn", "on": "click", "events": [{"keep": "ev-js2"}]},
    ]}
    sess = FakeSession(queue=[FakeResp(200, _form())])
    with pytest.raises(errors.UsageError, match="appears twice"):
        main.dispatch("form-set-element-chains", ["--id", "F1", "--plan", json.dumps(plan)],
                      client_builder=_builder(sess))


def test_js_file_resolves_relative_to_the_plan_file(tmp_path):
    (tmp_path / "go.js").write_text("go();\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"chains": [
        {"element": "flag", "on": "input", "events": [{"js_file": "go.js"}]}]}), encoding="utf-8")
    sess = FakeSession(queue=[FakeResp(200, _form()), FakeResp(200, {})])
    main.dispatch("form-set-element-chains", ["--id", "F1", "--plan-file", str(plan_file)],
                  client_builder=_builder(sess))
    assert _put_events(sess, "flag", "onInputEvents")[0]["config"]["code"] == "go();\n"


def test_is_true_on_a_string_default_variable_is_reported_but_not_refused():
    form = _form()
    form["data"]["variables"].append({"name": "isPJ", "id": "var-pj", "defaultValue": "False"})
    plan = {"chains": [{"element": "validate", "on": "click", "events": [
        {"map": {"set": {"step-two.visible": True},
                 "when": [{"variable": "isPJ", "op": "IS_TRUE"}]}}]}]}
    sess = FakeSession(queue=[FakeResp(200, form)])
    out = main.dispatch("form-set-element-chains",
                        ["--id", "F1", "--plan", json.dumps(plan), "--dry-run"],
                        client_builder=_builder(sess))
    assert len(out["warnings"]) == 1 and "isPJ IS_TRUE" in out["warnings"][0]
    # a variable without a string default raises nothing
    plan["chains"][0]["events"][0]["map"]["when"] = [{"variable": "isPF", "op": "IS_TRUE"}]
    sess = FakeSession(queue=[FakeResp(200, _form())])
    out = main.dispatch("form-set-element-chains",
                        ["--id", "F1", "--plan", json.dumps(plan), "--dry-run"],
                        client_builder=_builder(sess))
    assert "warnings" not in out
