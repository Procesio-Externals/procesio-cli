"""Tier-4 ergonomics: inspect-flow, action families, form optionsSource + chainConfig."""
from __future__ import annotations

import itertools

from tools.procesio.flowmodel import families
from tools.procesio.flowmodel.inspect import inspect


def _flow():
    return {
        "Id": "f1", "Title": "Sample",
        "Variables": [{"Id": "v1", "Name": "items", "Type": 10, "IsRequired": True}],
        "Actions": [
            {"Id": "start", "ActionTemplateName": "Start",
             "CustomData": {"type": "circle"},
             "Ports": [{"SourceId": "start", "DestinationId": "fe", "Type": 0}]},
            {"Id": "fe", "ActionTemplateName": "For Each",
             "CustomData": {"type": "area", "name": "For Each"},
             "Ports": [{"SourceId": "fe", "DestinationId": "api", "Type": 0}]},
            {"Id": "api", "ActionTemplateName": "Call API", "ParentId": "fe",
             "CustomData": {"type": "square"},
             "Ports": [{"SourceId": "api", "DestinationId": "d", "Type": 0}]},
            {"Id": "d", "ActionTemplateName": "Decisional",
             "CustomData": {"type": "diamond"},
             "Ports": [{"SourceId": "d", "DestinationId": "stop", "Type": 0},
                       {"SourceId": "d", "DestinationId": "stop2", "Type": 0}]},
            {"Id": "stop", "ActionTemplateName": "Stop", "CustomData": {"type": "circle"}, "Ports": []},
            {"Id": "stop2", "ActionTemplateName": "Stop", "CustomData": {"type": "circle"}, "Ports": []},
        ],
    }


def test_families_classify():
    assert families.classify("Call API") == "integration"
    assert families.classify("Node") == "scripting"
    assert families.classify("For Each") == "control"
    assert families.classify("Totally Unknown Action") == "other"
    assert families.describe("Call API")


def test_inspect_counts_and_families():
    r = inspect(_flow())
    assert r["counts"]["actions"] == 6
    assert r["counts"]["decisionals"] == 1
    assert r["counts"]["stops"] == 2
    assert r["counts"]["foreach"] == 1
    assert r["action_families"].get("integration") == 1
    assert r["action_families"].get("control")  # start/stop/foreach/decisional


def test_inspect_branches():
    r = inspect(_flow())
    assert len(r["branches"]) == 1
    assert r["branches"][0]["cases"] == 2


def test_inspect_smells():
    codes = {s["code"] for s in inspect(_flow())["smells"]}
    # Call API inside a For Each, with no error port -> two smells fire
    assert "no_error_port" in codes
    assert "slow_in_loop" in codes
    assert "required_inputs" in codes


def test_inspect_variables_contract():
    r = inspect(_flow())
    assert r["variables"]["inputs"] == ["items"]
    assert r["variables"]["required"] == ["items"]


# -- form builder optionsSource + chainConfig --------------------------------

def _form_ctx():
    cnt = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}


def _configs(el):
    return {c.get("key"): c.get("value") for c in el.get("configs", [])}


def _select(elements, name=None):
    return next(e for e in elements if e.get("type") == "select")


def test_form_options_source_json():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "select", "label": "Pick",
         "optionsSource": {"type": "json", "value": [{"label": "A", "value": "a"}]}}]}
    els = fb.build(cfg, _form_ctx())["Data"]["elements"]
    c = _configs(_select(els))
    assert c["sourceType"] == "JSON"
    assert c["sourceValue"] == [{"label": "A", "value": "a"}]


def test_form_options_source_url():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "select", "label": "Pick",
         "optionsSource": {"type": "url", "value": "https://x/opts"}}]}
    els = fb.build(cfg, _form_ctx())["Data"]["elements"]
    c = _configs(_select(els))
    assert c["sourceType"] == "URL"
    assert c["sourceValue"] == "https://x/opts"


def test_form_static_options_unchanged():
    from tools.procesio.dto.form import builder as fb
    cfg = {"name": "F", "elements": [
        {"type": "select", "label": "Pick", "options": ["A", "B"]}]}
    els = fb.build(cfg, _form_ctx())["Data"]["elements"]
    assert _configs(_select(els))["sourceType"] == "static-list"


def test_form_chainconfig_emitted_only_when_present():
    from tools.procesio.dto.form import builder as fb
    base = {"name": "F", "elements": [{"type": "paragraph", "label": "hi"}]}
    assert "chainConfig" not in fb.build(base, _form_ctx())["Data"]
    chained = {**base, "chainConfig": {"columns": [{"forms": ["a"]}]}}
    data = fb.build(chained, _form_ctx())["Data"]
    assert data["chainConfig"] == {"columns": [{"forms": ["a"]}]}
