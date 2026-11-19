"""node-edit-batch: several node-parameter changes, one validation and one save.

The single-change writers validate and save the whole process for each change. These tests
pin what the batch adds: the changes mean the same as the single ones, the tail runs once,
and a list that cannot be applied whole writes nothing.

The validate, lint and save tail is stubbed, as in the other handler tests here: it has its
own tests, and these are about what reaches it.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools.procesio.errors import DocumentationMissing, UsageError
from tools.procesio.handlers import nodeparams

ENDPOINT, BODY = "prop-endpoint", "prop-body"
RATES_PURPOSE = "Reads the exchange rates of the given year from the provider."
MAIL_PURPOSE = "Tells the customer that the rates are in."
PROCESS_PURPOSE = "Fetches the yearly rates and mails the customer."
# "The texts that are there are still right", for every node and for the process.
CONFIRMED = json.dumps({"action": True, "area": True, "process": True})


def _flow():
    return {
        "id": "p1", "title": "Rates", "description": PROCESS_PURPOSE,
        "variables": [{"id": "var-year", "name": "year", "type": 20},
                      {"id": "var-name", "name": "customerName", "type": 20},
                      {"id": "var-mail", "name": "customerEmail", "type": 20}],
        "actions": [
            {"id": "act-1", "actionName": "Get rates", "actionTemplateName": "Call API",
             "parameters": [{"tabPropertyId": ENDPOINT, "value": "https://old.example/x<%0%>.xml",
                             "variable": [{"id": 0, "variableId": "var-year", "attribute": None}]}],
             "customData": {"description": RATES_PURPOSE, "configuration": [{"settings": [
                 {"id": "side", "type": "side-pannel", "label": "Configure Request", "value": [
                     {"id": ENDPOINT, "label": "Endpoint", "value": "https://old.example/x.xml"}]}]}]}},
            {"id": "act-2", "actionName": "Send mail", "actionTemplateName": "Send Email",
             "parameters": [{"tabPropertyId": BODY, "value": "Hello <%name%>, write to <%mail%>",
                             "variable": []}],
             "customData": {"description": MAIL_PURPOSE, "configuration": [{"settings": [
                 {"id": "side", "type": "side-pannel", "label": "Configure", "value": [
                     {"id": BODY, "label": "Body", "value": "Hello"}]}]}]}},
        ],
    }


@pytest.fixture
def tail(monkeypatch):
    """The shared tail, counted. `flow` is the process the client serves."""
    seen = SimpleNamespace(flow=_flow(), validated=0, saved=[], gets=0)

    class Client:
        def get(self, path, *a, **k):
            seen.gets += 1
            return seen.flow

    def validate(client, flow):
        seen.validated += 1
        return True, None

    def save(client, flow, *, flow_id, valid, layout=None):
        seen.saved.append(json.loads(json.dumps(flow)))
        return {"isValid": True, "stamped": bool(valid), "layout": "kept"}

    monkeypatch.setattr(nodeparams, "_validate", validate)
    monkeypatch.setattr(nodeparams, "_lint", lambda client, flow: [])
    monkeypatch.setattr(nodeparams, "run_fe_validation",
                        lambda client, flow: {"clean": True, "errors": [], "warnings": [],
                                              "error_count": 0, "warning_count": 0})
    monkeypatch.setattr(nodeparams, "save_flow", save)
    monkeypatch.setattr(nodeparams, "normalize_designer_layer", lambda flow: {"synced": 0})
    seen.client = Client()
    return seen


def _args(changes=None, *, raw=None, **more):
    base = {"id": "p1", "changes": json.dumps(changes) if changes is not None else raw,
            "changes_file": None, "dry_run": False,
            "doc": CONFIRMED, "doc_file": None, "allow_undocumented": False}
    base.update(more)
    return SimpleNamespace(**base)


CHANGES = [
    {"op": "set", "node": "Get rates", "property": "Endpoint",
     "value": "https://new.example/x<%0%>.xml"},
    {"op": "replace-text", "node": "Send mail", "find": "Hello", "replace": "Dear"},
    {"op": "bind", "node": "Send mail", "property": "Body",
     "find": "<%name%>", "replace": "<%0%>", "bind": ["0=customerName"]},
]


def test_several_changes_on_several_nodes_cost_one_validation_and_one_save(tail):
    changes = [CHANGES[0], CHANGES[1]]
    res = nodeparams.node_edit_batch(tail.client, _args(changes))
    assert res["put"] is True and res["changed"] == 2
    assert tail.validated == 1 and len(tail.saved) == 1
    saved = {a["actionName"]: a["parameters"][0] for a in tail.saved[0]["actions"]}
    assert saved["Get rates"]["value"] == "https://new.example/x<%0%>.xml"
    assert saved["Send mail"]["value"] == "Dear <%name%>, write to <%mail%>"


def test_each_change_is_reported_with_its_position(tail):
    res = nodeparams.node_edit_batch(tail.client, _args([CHANGES[0], CHANGES[1]]))
    assert [(c["index"], c["op"], c["node"]) for c in res["changes"]] == [
        (0, "set", "Get rates"), (1, "replace-text", "Send mail")]
    # the literal stands in the runtime parameter and in its designer copy
    assert res["changes"][1]["replacements"] == 2


def test_a_change_sees_what_the_changes_before_it_did(tail):
    """Applied in order to one copy: the second replace finds the text the first one wrote."""
    changes = [{"op": "replace-text", "node": "Send mail", "find": "Hello", "replace": "Dear"},
               {"op": "replace-text", "node": "Send mail", "find": "Dear", "replace": "Hi"}]
    nodeparams.node_edit_batch(tail.client, _args(changes))
    assert tail.saved[0]["actions"][1]["parameters"][0]["value"].startswith("Hi <%name%>")


def test_one_bind_takes_every_placeholder_of_the_value(tail):
    """The edit that no single call through MCP could make: two placeholders, two bindings."""
    changes = [{"op": "replace-text", "node": "Send mail", "find": "<%name%>", "replace": "<%0%>",
                "allow_binding_change": True},
               {"op": "bind", "node": "Send mail", "property": "Body",
                "find": "<%mail%>", "replace": "<%1%>",
                "bind": ["0=customerName", "1=customerEmail"]}]
    nodeparams.node_edit_batch(tail.client, _args(changes))
    param = tail.saved[0]["actions"][1]["parameters"][0]
    assert param["value"] == "Hello <%0%>, write to <%1%>"
    assert [v["variableId"] for v in param["variable"]] == ["var-name", "var-mail"]


def test_a_change_that_cannot_be_applied_refuses_the_whole_list(tail):
    changes = [CHANGES[0], {"op": "set", "node": "No such node", "property": "Endpoint", "value": "x"}]
    with pytest.raises(UsageError) as err:
        nodeparams.node_edit_batch(tail.client, _args(changes))
    text = str(err.value)
    assert "change 1" in text and "No such node" in text and "Nothing was written" in text
    assert tail.validated == 0 and tail.saved == []


@pytest.mark.parametrize("change, says", [
    ({"op": "delete", "node": "Get rates"}, "'op' must be one of"),
    ({"op": "set", "property": "Endpoint", "value": "x"}, "set needs 'node'"),
    ({"op": "set", "node": "Get rates", "value": "x"}, "set needs 'property'"),
    ({"op": "set", "node": "Get rates", "property": "Endpoint"}, "set needs 'value'"),
    ({"op": "set", "node": "Get rates", "property": "Endpoint", "value": 5}, "must be text"),
    ({"op": "set", "node": "Get rates", "property": "Nope", "value": "x"}, "property not found"),
    ({"op": "set", "node": "Get rates", "property": "Endpoint", "value": "https://x"},
     "placeholder"),
    ({"op": "bind", "node": "Send mail", "property": "Body", "bind": "0"}, "INDEX=variable"),
    ({"op": "bind", "node": "Send mail", "property": "Body", "bind": [1]}, "list of INDEX=variable"),
    ({"op": "bind", "node": "Send mail", "property": "Body", "bind": ["0=ghost"]}, "not found"),
    ({"op": "replace-text", "node": "Send mail", "find": "absent", "replace": "x"}, "not present"),
    ({"op": "replace-text", "node": "Send mail", "find": "Hello", "replace": "x", "expect": 5},
     "expected 5 replacements, found 2"),
    ({"op": "replace-text", "node": "Send mail", "find": "<%name%>", "replace": "x"},
     "allow_binding_change"),
    ("not an object", "must be a JSON object"),
])
def test_a_wrong_change_says_what_is_wrong_with_it(tail, change, says):
    with pytest.raises(UsageError) as err:
        nodeparams.node_edit_batch(tail.client, _args([change]))
    assert says in str(err.value) and "change 0" in str(err.value)
    assert tail.saved == []


@pytest.mark.parametrize("raw", ["{}", "[]", '"text"'])
def test_the_changes_must_be_a_list_with_something_in_it(tail, raw):
    with pytest.raises(UsageError, match="JSON list"):
        nodeparams.node_edit_batch(tail.client, _args(raw=raw))
    assert tail.gets == 0      # refused before the process is read


def test_a_dry_run_validates_and_does_not_save(tail):
    res = nodeparams.node_edit_batch(tail.client, _args(CHANGES[:2], dry_run=True))
    assert res["put"] is False and res["dry_run"] is True
    assert tail.validated == 1 and tail.saved == []


def test_a_list_that_changes_nothing_is_not_validated_or_saved(tail):
    same = [{"op": "set", "node": "Get rates", "property": "Endpoint",
             "value": "https://old.example/x<%0%>.xml"}]
    res = nodeparams.node_edit_batch(tail.client, _args(same))
    assert res["put"] is False and res["changed"] == 0 and "nothing to PUT" in res["note"]
    assert tail.validated == 0 and tail.saved == []


def test_a_flow_the_validator_rejects_is_not_saved(tail, monkeypatch):
    monkeypatch.setattr(nodeparams, "_validate", lambda client, flow: (False, ["bad"]))
    res = nodeparams.node_edit_batch(tail.client, _args(CHANGES[:2]))
    assert res["put"] is False and res["errors"] == ["bad"] and tail.saved == []


def test_the_changes_can_come_from_a_file(tail, tmp_path):
    path = tmp_path / "changes.json"
    path.write_text(json.dumps(CHANGES[:1]), encoding="utf-8")
    res = nodeparams.node_edit_batch(tail.client, _args(None, changes_file=str(path)))
    assert res["changed"] == 1
    with pytest.raises(UsageError, match="not both"):
        nodeparams.node_edit_batch(tail.client, _args(CHANGES[:1], changes_file=str(path)))


def test_the_single_writers_parse_bindings_as_before():
    """The binding parsers moved into functions the batch shares. Same input, same errors."""
    flow = _flow()
    assert nodeparams._variable_bindings(flow, "p1", ["0=year", " 1 = customerName "]) == {
        0: "var-year", 1: "var-name"}
    with pytest.raises(UsageError, match="--bind index must be an integer, got: x"):
        nodeparams._variable_bindings(flow, "p1", ["x=year"])
    with pytest.raises(UsageError, match="at least one --bind"):
        nodeparams._variable_bindings(flow, "p1", [])
    assert nodeparams._attribute_bindings(None, flow, ["0=year"]) == {
        0: {"variableId": "var-year", "attributeId": None}}
    with pytest.raises(UsageError, match="unknown variable 'ghost'"):
        nodeparams._attribute_bindings(None, flow, ["0=ghost"])


def test_a_refusal_names_the_key_of_a_change_not_the_flag_of_the_single_writer(tail):
    """The single writers say "Pass --allow-binding-change". The batch has no such flag: the
    same permission is a key of the change, and a caller told to pass the flag cannot."""
    drops_the_placeholder = [{"op": "set", "node": "Get rates", "property": "Endpoint",
                              "value": "https://new.example/x.xml"}]
    with pytest.raises(UsageError) as err:
        nodeparams.node_edit_batch(tail.client, _args(drops_the_placeholder))
    assert "'allow_binding_change'" in str(err.value)
    assert "--" not in str(err.value)

    allowed = [{**drops_the_placeholder[0], "allow_binding_change": True}]
    assert nodeparams.node_edit_batch(tail.client, _args(allowed))["changed"] == 1


@pytest.mark.parametrize("written, read", [
    ("Pass --allow-binding-change only when variable[] is rewritten", "Pass 'allow_binding_change' only when variable[] is rewritten"),
    ("--bind index must be an integer, got: x", "'bind' index must be an integer, got: x"),
    ("--find text is not present", "'find' text is not present"),
    ("the value keeps <%0%> -- and nothing else", "the value keeps <%0%> -- and nothing else"),
    ("no flag here", "no flag here"),
])
def test_a_flag_in_a_message_reads_as_a_key(written, read):
    assert nodeparams._as_keys(written) == read


# --- documentation: every node a change alters, and the process ----------------------------
#
# Every surgical writer asks for the documentation its change can make untrue (docwrite.py).
# The batch asks for the same, per node, and lists everything that is missing in one answer.

def test_without_documentation_the_list_is_refused_and_every_gap_is_named_once(tail):
    with pytest.raises(DocumentationMissing) as err:
        nodeparams.node_edit_batch(tail.client, _args(CHANGES[:2], doc=None))
    text, report = str(err.value), err.value.report
    assert "'Get rates'" in text and "'Send mail'" in text and "--doc with process" in text
    assert tail.validated == 0 and tail.saved == []
    assert [(f["node"], f["doc_key"]) for f in report["findings"]] == [
        ("Get rates", "action"), ("Get rates", "process"), ("Send mail", "action")]
    assert report["documented"] is False and len(report["nodes"]) == 2


def test_a_change_carries_the_documentation_of_its_node(tail):
    changes = [{**CHANGES[0], "doc": {"action": "Reads the rates from the new provider."}},
               {**CHANGES[1], "doc": {"action": True}}]
    res = nodeparams.node_edit_batch(tail.client, _args(changes, doc=json.dumps({"process": True})))
    saved = {a["actionName"]: a["customData"]["description"] for a in tail.saved[0]["actions"]}
    assert saved == {"Get rates": "Reads the rates from the new provider.", "Send mail": MAIL_PURPOSE}
    assert res["documentation"]["documented"] is True
    assert [n["node"] for n in res["documentation"]["nodes"]] == ["Get rates", "Send mail"]


def test_what_doc_gives_stands_for_every_node_whose_change_gives_none(tail):
    changes = [{**CHANGES[0], "doc": {"action": "Reads the rates from the new provider."}}, CHANGES[1]]
    shared = json.dumps({"action": True, "process": "Fetches the rates and greets the customer."})
    nodeparams.node_edit_batch(tail.client, _args(changes, doc=shared))
    flow = tail.saved[0]
    assert flow["description"] == "Fetches the rates and greets the customer."
    assert flow["actions"][0]["customData"]["description"] == "Reads the rates from the new provider."
    assert flow["actions"][1]["customData"]["description"] == MAIL_PURPOSE


def test_two_changes_of_one_node_ask_for_its_documentation_once(tail):
    changes = [{"op": "replace-text", "node": "Send mail", "find": "Hello", "replace": "Dear",
                "doc": {"action": "Greets the customer formally."}},
               {"op": "replace-text", "node": "Send mail", "find": "write to", "replace": "mail"}]
    res = nodeparams.node_edit_batch(tail.client, _args(changes, doc=json.dumps({"process": True})))
    assert len(res["documentation"]["nodes"]) == 1
    assert tail.saved[0]["actions"][1]["customData"]["description"] == "Greets the customer formally."


def test_a_dry_run_reports_what_is_missing_and_does_not_refuse(tail):
    res = nodeparams.node_edit_batch(tail.client, _args(CHANGES[:2], doc=None, dry_run=True))
    assert res["dry_run"] is True and res["documentation"]["documented"] is False
    assert tail.saved == []


def test_allow_undocumented_saves_and_still_reports_the_gaps(tail):
    res = nodeparams.node_edit_batch(tail.client, _args(CHANGES[:2], doc=None, allow_undocumented=True))
    assert res["put"] is True and res["documentation"]["documented"] is False
    assert len(tail.saved) == 1


def test_a_change_s_doc_that_is_not_an_object_is_refused(tail):
    with pytest.raises(UsageError, match="change 0: 'doc' must be a JSON object"):
        nodeparams.node_edit_batch(tail.client, _args([{**CHANGES[0], "doc": "a purpose"}]))
    assert tail.saved == []


def test_each_node_s_area_text_is_kept_when_several_areas_change(tail):
    """The area shapes are rebuilt for every node. Rebuilt from the first copy each time, the
    second node would undo the text the first one set for its area."""
    from tools.procesio.layout import areas
    from tools.procesio.tests.test_selfdoc import _built, _camel, _config

    flow = _camel(_built(_config(5))[0])
    tail.flow = flow
    by_name = {a["actionName"]: a for a in flow["actions"]}

    def change(name, purpose, area_text):
        prop = next(p for p in by_name[name]["parameters"] if isinstance(p.get("value"), str) and p["value"])
        return {"op": "set", "node": name, "property": prop["tabPropertyId"], "value": "a fixed label",
                "allow_binding_change": True, "doc": {"action": purpose, "area": {"text": area_text}}}

    changes = [change("a1", "Stamps a fixed label on the first record.", "Cleans and stamps the name."),
               change("a5", "Stamps a fixed label on the last record.", "Stores the stamped form.")]
    nodeparams.node_edit_batch(tail.client, _args(changes, doc=json.dumps({"process": True})))

    saved = tail.saved[0]
    texts = {g["title"]: g["text"]
             for g in areas.groups_from_shapes(saved["actions"], saved["canvasData"]["shapes"])}
    assert texts == {"Prepare": "Cleans and stamps the name.", "Finish": "Stores the stamped form."}


def test_the_manifest_publishes_the_shape_of_a_change():
    schema = nodeparams.ACTIONS["node-edit-batch"].arg_schemas["changes"]
    assert schema["items"]["properties"]["op"]["enum"] == list(nodeparams.BATCH_OPS)
    assert schema["items"]["required"] == ["op", "node"]


def test_every_writer_holds_the_process_lock_and_the_reader_does_not():
    for name, defn in nodeparams.ACTIONS.items():
        wrapped = hasattr(defn.func, "__wrapped__")
        assert wrapped is (name != "node-params"), name
