"""Tests for rename-actions (bulk-relabel a live process's canvas nodes).

The client is faked — no network. Both DTO casings are exercised: a PascalCase export
and the camelCase live DTO must rename identically."""
from __future__ import annotations

from argparse import Namespace

import pytest

from tools.procesio.errors import UsageError
from tools.procesio.handlers import process_naming as pn


def _flow_pascal():
    return {"Id": "P", "Title": "Demo", "Actions": [
        {"Id": "aaaa1111", "ActionName": "Node", "ActionTemplateName": "Node",
         "CustomData": {"name": "Node", "icon": "icon-nodejs"},
         "Ports": [{"SourceId": "aaaa1111", "DestinationId": "bbbb2222", "Type": 0}]},
        {"Id": "bbbb2222", "ActionName": "Node", "ActionTemplateName": "Node",
         "CustomData": {"name": "Node", "icon": "icon-nodejs"}, "Ports": []},
    ]}


def _flow_camel():
    return {"id": "P", "title": "Demo", "actions": [
        {"id": "aaaa1111", "actionName": "Node", "actionTemplateName": "Node",
         "customData": {"name": "Node"}, "ports": []},
        {"id": "bbbb2222", "actionName": "Call API", "actionTemplateName": "Call API",
         "customData": {"name": "Call API"}, "ports": []},
    ]}


class FakeClient:
    def __init__(self, flow):
        self.workspace_id = "ws-1"
        self.profile = {}                      # unbound -> production designer host
        self._flow = flow
        self.posts = []
        self.puts = []

    def get(self, path, query=None):
        assert path.startswith("/api/Projects/")
        return {"flow": self._flow}

    def post(self, path, body=None, query=None):
        self.posts.append((path, body))
        return {"raw_text": ""}

    def put(self, path, body=None, query=None):
        self.puts.append((path, body))
        return {}


def _args(**kw):
    base = dict(id="P", workspace_id="ws-1", profile=None, map=None, map_file=None,
                no_validate=False, dry_run=False, force=False)
    base.update(kw)
    return Namespace(**base)


# -- apply_names (pure) -------------------------------------------------------

def test_sets_both_action_name_and_custom_data_name():
    flow, changes, unknown, ambiguous = pn.apply_names(
        _flow_pascal(), {"aaaa1111": "Mapează nume"})
    assert (unknown, ambiguous) == ([], [])
    a = flow["Actions"][0]
    assert a["ActionName"] == "Mapează nume"
    assert a["CustomData"]["name"] == "Mapează nume"
    assert changes == [{"id": "aaaa1111", "template": "Node",
                        "from": "Node", "to": "Mapează nume"}]


def test_camel_case_live_dto_renames_the_same_way():
    flow, changes, _, _ = pn.apply_names(_flow_camel(), {"bbbb2222": "OCR AI"})
    a = flow["actions"][1]
    assert a["actionName"] == "OCR AI"
    assert a["customData"]["name"] == "OCR AI"
    assert len(changes) == 1


def test_does_not_mutate_the_input_flow():
    original = _flow_pascal()
    pn.apply_names(original, {"aaaa1111": "Changed"})
    assert original["Actions"][0]["ActionName"] == "Node"
    assert original["Actions"][0]["CustomData"]["name"] == "Node"


def test_untargeted_actions_are_left_alone():
    flow, changes, _, _ = pn.apply_names(_flow_pascal(), {"aaaa1111": "Only me"})
    assert flow["Actions"][1]["ActionName"] == "Node"
    assert [c["id"] for c in changes] == ["aaaa1111"]


def test_ports_and_wiring_survive_a_rename():
    flow, _, _, _ = pn.apply_names(_flow_pascal(), {"aaaa1111": "X", "bbbb2222": "Y"})
    assert flow["Actions"][0]["Ports"] == [
        {"SourceId": "aaaa1111", "DestinationId": "bbbb2222", "Type": 0}]


def test_a_name_already_in_place_is_not_reported_as_a_change():
    _, changes, _, _ = pn.apply_names(_flow_pascal(), {"aaaa1111": "Node"})
    assert changes == []


def test_unique_id_prefix_resolves():
    _, changes, unknown, ambiguous = pn.apply_names(_flow_pascal(), {"aaaa": "Prefixed"})
    assert (unknown, ambiguous) == ([], [])
    assert changes[0]["id"] == "aaaa1111"


def test_ambiguous_prefix_is_reported_not_guessed():
    flow = _flow_pascal()
    flow["Actions"][1]["Id"] = "aaaa9999"      # now "aaaa" matches two actions
    new, changes, unknown, ambiguous = pn.apply_names(flow, {"aaaa": "Which one?"})
    assert ambiguous == ["aaaa"]
    assert changes == []


def test_unknown_id_is_reported():
    _, changes, unknown, _ = pn.apply_names(_flow_pascal(), {"zzzz": "Nope"})
    assert unknown == ["zzzz"]
    assert changes == []


# -- rename_actions (handler) -------------------------------------------------

def test_dry_run_does_not_save():
    c = FakeClient(_flow_camel())
    out = pn.rename_actions(c, _args(map='{"aaaa1111": "Extrage nume"}', dry_run=True))["result"]
    assert out["saved"] is False and out["dry_run"] is True
    assert out["renamed_count"] == 1
    assert c.puts == [] and c.posts == []


def test_validates_then_saves():
    c = FakeClient(_flow_camel())
    out = pn.rename_actions(c, _args(map='{"aaaa1111": "Extrage nume"}'))["result"]
    assert out["validated"] is True and out["saved"] is True
    assert c.posts[0][0] == "/api/Projects/validate"
    assert c.puts[0][0] == "/api/Projects"
    assert c.puts[0][1]["actions"][0]["actionName"] == "Extrage nume"
    assert out["designer_url"].endswith("/designer/P#ws-1")


def test_no_validate_skips_the_gate():
    c = FakeClient(_flow_camel())
    pn.rename_actions(c, _args(map='{"aaaa1111": "X"}', no_validate=True))
    assert c.posts == [] and len(c.puts) == 1


def test_map_file_is_accepted(tmp_path):
    f = tmp_path / "names.json"
    f.write_text('{"bbbb2222": "OCR AI — CI"}', encoding="utf-8")
    c = FakeClient(_flow_camel())
    out = pn.rename_actions(c, _args(map_file=str(f)))["result"]
    assert out["renamed"][0]["to"] == "OCR AI — CI"


def test_map_and_map_file_are_mutually_exclusive(tmp_path):
    c = FakeClient(_flow_camel())
    with pytest.raises(UsageError, match="exactly one"):
        pn.rename_actions(c, _args(map='{"a": "b"}', map_file=str(tmp_path / "x.json")))
    with pytest.raises(UsageError, match="exactly one"):
        pn.rename_actions(c, _args())


def test_blank_name_is_rejected():
    c = FakeClient(_flow_camel())
    with pytest.raises(UsageError, match="non-empty string"):
        pn.rename_actions(c, _args(map='{"aaaa1111": "   "}'))


def test_unknown_id_aborts_before_saving():
    c = FakeClient(_flow_camel())
    with pytest.raises(UsageError, match="no action in process"):
        pn.rename_actions(c, _args(map='{"nope": "X"}'))
    assert c.puts == []


def test_ambiguous_prefix_aborts_before_saving():
    flow = _flow_camel()
    flow["actions"][1]["id"] = "aaaa9999"
    c = FakeClient(flow)
    with pytest.raises(UsageError, match="ambiguous id prefix"):
        pn.rename_actions(c, _args(map='{"aaaa": "X"}'))
    assert c.puts == []
