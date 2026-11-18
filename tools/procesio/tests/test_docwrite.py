"""The documentation contract of the surgical writers (node-*, sql-convert, variable-*), the
per-area `groups` of process-edit, and the local baseline that catches changes made by hand."""
from __future__ import annotations

import copy

import pytest

from tools.procesio.dto.process import baseline, docwrite
from tools.procesio.errors import DocumentationMissing
from tools.procesio.layout import areas
from tools.procesio.tests.test_selfdoc import _built, _camel, _codes, _config, _edit, _strip_docs


def _flow(n=5):
    dto, _ = _built(_config(n))
    return _camel(dto)


def _id(flow, name):
    return next(a["id"] for a in flow["actions"] if a["actionName"] == name)


def _act(flow, name):
    return next(a for a in flow["actions"] if a["actionName"] == name)


def _groups(flow):
    names = {a["id"]: a["actionName"] for a in flow["actions"]}
    return {g["title"]: (g["text"], sorted(names[m] for m in g["members"]))
            for g in areas.groups_from_shapes(flow["actions"], flow["canvasData"]["shapes"])}


def _behaviour(flow, name="a2"):
    after = copy.deepcopy(flow)
    p = next(p for p in _act(after, name)["parameters"] if p.get("value"))
    p["value"], p["variable"] = "a fixed label", []
    return after


# -- behaviour change ---------------------------------------------------------------------

def test_a_changed_action_asks_for_its_purpose_its_area_and_the_process():
    before = _flow()
    after = _behaviour(before)
    with pytest.raises(DocumentationMissing) as ei:
        docwrite.apply(before, after, {"kind": "behaviour", "node": _id(before, "a2")}, {})
    assert {f["code"] for f in ei.value.report["findings"]} == {
        "ACTION_DESCRIPTION_REQUIRED", "AREA_REVIEW_REQUIRED", "PROCESS_REVIEW_REQUIRED"}
    rep = docwrite.apply(before, after, {"kind": "behaviour", "node": _id(before, "a2")},
                         {"action": "stamps a fixed label", "area": True, "process": True})
    assert rep["documented"]
    assert _act(after, "a2")["customData"]["description"] == "stamps a fixed label"
    assert after["description"] == before["description"]
    assert _groups(after) == _groups(before)


def test_true_confirms_only_a_purpose_that_exists():
    before = _flow()
    _act(before, "a2")["customData"].pop("description")
    after = _behaviour(before)
    with pytest.raises(DocumentationMissing) as ei:
        docwrite.apply(before, after, {"kind": "behaviour", "node": _id(before, "a2")},
                       {"action": True, "area": True, "process": True})
    assert [f["code"] for f in ei.value.report["findings"]] == ["ACTION_DESCRIPTION_REQUIRED"]


def test_an_area_text_and_the_process_purpose_can_be_restated():
    before = _flow()
    after = _behaviour(before)
    docwrite.apply(before, after, {"kind": "behaviour", "node": _id(before, "a2")},
                   {"action": "stamps a fixed label", "area": {"text": "Cleans the name and stamps it."},
                    "process": "Normalises and stamps a name."})
    assert _groups(after)["Prepare"][0] == "Cleans the name and stamps it."
    assert after["description"] == "Normalises and stamps a name."


def test_a_dry_run_reports_and_allow_saves_anyway():
    before = _flow()
    rep = docwrite.apply(before, _behaviour(before), {"kind": "behaviour", "node": _id(before, "a2")}, {},
                         enforce=False)
    assert not rep["documented"] and len(rep["findings"]) == 3
    rep = docwrite.apply(before, _behaviour(before), {"kind": "behaviour", "node": _id(before, "a2")}, {},
                         allow=True)
    assert not rep["documented"]


# -- insert -------------------------------------------------------------------------------

def _inserted(before, title=None):
    after = copy.deepcopy(before)
    new = copy.deepcopy(_act(after, "a5"))
    new.update(id="00000000-0000-0000-0000-00000000new1", actionName="a6", ports=[])
    new["customData"] = dict(new["customData"], name="a6",
                             position={"x": 720.0, "y": 260.0})     # free canvas (node-insert re-tidies)
    new["customData"].pop("description", None)
    after["actions"].append(new)
    return after, new["id"]


def test_an_inserted_action_needs_a_purpose_an_area_and_the_process():
    before = _flow()
    after, nid = _inserted(before)
    with pytest.raises(DocumentationMissing) as ei:
        docwrite.apply(before, after, {"kind": "insert", "node": nid}, {})
    assert {f["code"] for f in ei.value.report["findings"]} == {
        "ACTION_DESCRIPTION_REQUIRED", "AREA_REQUIRED", "PROCESS_REVIEW_REQUIRED"}
    docwrite.apply(before, after, {"kind": "insert", "node": nid},
                   {"action": "keeps a lower-case copy", "area": {"title": "Finish"}, "process": True})
    assert _groups(after)["Finish"][1] == ["a4", "a5", "a6"]


def test_an_inserted_action_can_open_a_new_area():
    before = _flow()
    after, nid = _inserted(before)
    with pytest.raises(DocumentationMissing) as ei:
        docwrite.apply(before, after, {"kind": "insert", "node": nid},
                       {"action": "keeps a copy", "area": {"title": "Search"}, "process": True})
    assert [f["code"] for f in ei.value.report["findings"]] == ["AREA_TEXT_REQUIRED"]
    docwrite.apply(before, after, {"kind": "insert", "node": nid},
                   {"action": "keeps a copy", "area": {"title": "Search", "text": "Feeds the search index."},
                    "process": True})
    assert _groups(after)["Search"] == ("Feeds the search index.", ["a6"])


def test_a_small_process_without_areas_needs_no_area_for_an_insert():
    before = _flow(2)
    after = copy.deepcopy(before)
    new = copy.deepcopy(_act(after, "a2"))
    new.update(id="00000000-0000-0000-0000-00000000new2", actionName="a3", ports=[])
    after["actions"].append(new)
    rep = docwrite.apply(before, after, {"kind": "insert", "node": new["id"]},
                         {"action": "a third step", "process": True})
    assert rep["documented"] and "area" not in rep["required"]


# -- delete -------------------------------------------------------------------------------

def _deleted(before, name):
    after = copy.deepcopy(before)
    gone = _id(after, name)
    after["actions"] = [a for a in after["actions"] if a["id"] != gone]
    for a in after["actions"]:
        a["ports"] = [p for p in a["ports"] if p.get("destinationId") != gone]
    return after, gone


def test_deleting_an_action_asks_whether_its_area_text_still_holds():
    before = _flow()
    after, gone = _deleted(before, "a5")
    with pytest.raises(DocumentationMissing) as ei:
        docwrite.apply(before, after, {"kind": "delete", "node": gone}, {})
    assert {f["code"] for f in ei.value.report["findings"]} == {"AREA_REVIEW_REQUIRED", "PROCESS_REVIEW_REQUIRED"}
    docwrite.apply(before, after, {"kind": "delete", "node": gone}, {"area": True, "process": True})
    assert _groups(after)["Finish"][1] == ["a4"]


def test_deleting_the_last_action_of_an_area_removes_the_area():
    before = _flow()
    after, gone = _deleted(before, "a5")
    docwrite.apply(before, after, {"kind": "delete", "node": gone}, {"area": True, "process": True})
    after2, gone2 = _deleted(after, "a4")
    rep = docwrite.apply(after, after2, {"kind": "delete", "node": gone2}, {"process": True})
    assert rep["area_removed"] == "Finish" and "Finish" not in _groups(after2)
    assert not [s for s in after2["canvasData"]["shapes"] if areas.base_title(s["title"]) == "Finish"]


# -- contract -----------------------------------------------------------------------------

def test_only_an_input_or_output_variable_asks_for_the_process_purpose():
    before = _flow()
    out_var = next(v for v in before["variables"] if v["type"] == 30)
    with pytest.raises(DocumentationMissing):
        docwrite.apply(before, copy.deepcopy(before), {"kind": "contract", "variable": out_var}, {})
    rep = docwrite.apply(before, copy.deepcopy(before), {"kind": "contract", "variable": {"type": 20}}, {})
    assert rep["documented"] and rep["required"] == []


# -- process-edit: per-area groups ---------------------------------------------------------

def test_edit_groups_remove_an_area_and_move_an_action():
    live, _ = _built(_config(5))
    cfg = _strip_docs(_config(5))
    cfg["groups"] = [{"title": "Finish", "actions": ["a3", "a4", "a5"]}]       # a3 moves out of Prepare
    with pytest.raises(DocumentationMissing) as ei:
        _edit(live, cfg)
    assert "AREA_MEMBERS_CHANGED" in {f["code"] for f in ei.value.report["findings"]}
    cfg["groups"].append({"title": "Prepare", "text": "Cleans the incoming name in two steps."})
    put, state = _edit(live, cfg)
    assert not _codes(state)
    put_flow = _camel(put)
    assert {t: m for t, (_x, m) in _groups(put_flow).items()} == {"Prepare": ["a1", "a2"],
                                                                   "Finish": ["a3", "a4", "a5"]}
    cfg2 = _strip_docs(_config(3))
    cfg2["groups"] = [{"title": "Prepare", "remove": True}]
    put2, _ = _edit(put, cfg2, _allow_remove=True, _allow_undocumented=True)
    assert "Prepare" not in _groups(_camel(put2))


# -- baseline -----------------------------------------------------------------------------

def test_a_change_made_by_hand_after_the_tool_documented_it_is_reported():
    flow = _flow()
    assert baseline.findings(flow) == []                         # no record: nothing guessed
    baseline.record(flow)
    assert baseline.findings(flow) == []
    hand = _behaviour(flow)                                      # changed in the designer
    assert [f["action"] for f in baseline.findings(hand)] == ["a2"]
    _act(hand, "a2")["customData"]["description"] = "stamps a fixed label"   # and redocumented
    assert baseline.findings(hand) == []


def test_the_reader_reports_the_baseline_only_when_asked():
    from tools.procesio.flowmodel import docs
    flow = _flow()
    baseline.record(flow)
    hand = _behaviour(flow)
    assert "ACTION_CHANGED_SINCE_DOCUMENTED" not in {f["code"] for f in docs.read(hand)["findings"]}
    assert "ACTION_CHANGED_SINCE_DOCUMENTED" in {f["code"] for f in docs.read(hand, use_baseline=True)["findings"]}
