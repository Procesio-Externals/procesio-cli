"""--brief on <component>-create / <component>-edit: an outline in place of the object.

The whole DTO of a real process or form runs to tens of kilobytes. A caller whose answer is
limited in size then gets none of it, and loses the validation report beside it. These tests
hold what the outline keeps, that it stays short however large the object is, that all four
answers honour the flag, and that an answer without the flag is what it was.
"""
from __future__ import annotations

import argparse
import json

from tools.procesio import main
from tools.procesio.dto import framework
from tools.procesio.dto.process import builder as pb
from tools.procesio.handlers import dto_actions
from tools.procesio.handlers.dto_actions import _outline


def _action(index: int) -> dict:
    return {"Id": f"a{index}", "ActionName": f"Step {index}", "Ports": [{"Id": "p"}] * 2,
            "Parameters": [{"Name": "Body", "Value": "x" * 300}],
            "CustomData": {"x": 1, "y": 2, "note": "n" * 200}}


def _process(actions: int = 3) -> dict:
    return {"Id": "P1", "Title": "Greet", "Active": True, "Description": "d" * 500,
            "Variables": [{"Id": "v1", "Name": "name"}, {"Id": "v2", "Name": "greeting"}],
            "Actions": [_action(i) for i in range(actions)], "Webhooks": [], "CanvasData": None}


# --- the outline ---------------------------------------------------------------------------

def test_short_fields_stay_and_a_list_gives_its_count_and_the_names_of_its_items():
    out = _outline(_process())
    assert out["Id"] == "P1" and out["Title"] == "Greet" and out["Active"] is True
    assert out["Variables"] == {"count": 2, "names": ["name", "greeting"]}
    assert out["Actions"] == {"count": 3, "names": ["Step 0", "Step 1", "Step 2"]}
    assert out["Webhooks"] == {"count": 0} and out["CanvasData"] is None


def test_long_text_is_described_not_printed():
    assert _outline(_process())["Description"] == {"text_chars": 500}


def test_a_form_element_is_named_by_its_name_config():
    form = {"Id": "F1", "Name": "Order", "Data": {"code": "E" * 5000, "elements": [
        {"id": "e1", "type": "input", "configs": [{"key": "label", "value": "First name"},
                                                  {"key": "name", "value": "firstName"}]},
        {"id": "e2", "type": "button", "configs": [{"key": "name", "value": "submit"}]}]}}
    out = _outline(form)
    assert out["Data"]["elements"] == {"count": 2, "names": ["firstName", "submit"]}
    assert out["Data"]["code"] == {"text_chars": 5000}


def test_the_outline_reaches_a_list_under_a_wrapper_and_stops_below_it():
    """A fetched process comes back under `flow`, one level down. Below the depth, an object
    is only counted."""
    out = _outline({"flow": {"actions": [_action(0)], "meta": {"a": {"b": {"c": 1}}}}})
    assert out["flow"]["actions"] == {"count": 1, "names": ["Step 0"]}
    assert out["flow"]["meta"] == {"a": {"keys": 1}}


def test_a_long_list_names_the_first_hundred_and_counts_the_rest():
    out = _outline(_process(actions=130))["Actions"]
    assert out["count"] == 130 and len(out["names"]) == dto_actions.MAX_NAMES
    assert out["names_not_listed"] == 30


def test_the_outline_does_not_grow_with_the_object_the_way_the_object_does():
    big = _process(actions=400)
    assert len(json.dumps(big)) > 200_000
    assert len(json.dumps(_outline(big))) < 3_000


# --- the four answers ------------------------------------------------------------------------

class _NoNetwork:
    def __getattr__(self, _):
        raise AssertionError("a dry run must not touch the network")


def _datatype_args(*extra):
    defn = main.ACTIONS["datatype-create"]
    parser = argparse.ArgumentParser()
    defn.add_args(parser)
    config = {"name": "M", "attributes": [{"name": "a", "type": "string"}]}
    return defn, parser.parse_args(["--config", json.dumps(config), *extra])


def test_a_create_dry_run_with_brief_returns_the_outline_and_no_dto():
    defn, args = _datatype_args("--dry-run", "--brief")
    out = defn.func(_NoNetwork(), args)
    assert out["dry_run"] is True and "dto" not in out
    assert out["summary"]["Content"]["Name"] == "M"
    assert "validation" in out


def test_a_create_dry_run_without_brief_is_what_it_was():
    defn, args = _datatype_args("--dry-run")
    out = defn.func(_NoNetwork(), args)
    assert out["dto"]["Content"]["Name"] == "M" and "summary" not in out


class _Client:
    def __init__(self, stored):
        self._stored = stored
        self.requests = []

    def request(self, method, path, body=None):
        self.requests.append((method, path))
        return {"id": "P1"}

    def get(self, path, query=None):
        return self._stored

    def put(self, path, body=None, query=None):
        return {}

    def post(self, path, body=None, query=None):
        return {"raw_text": ""}


def _component(**over) -> framework.Component:
    base = dict(name="process", description="", dir=pb.DIR,
                build=lambda config, ctx: _process(), create_endpoint=("POST", "/x"),
                get_path="/x/{id}", extract_id=lambda resp, dto: resp.get("id"))
    return framework.Component(**{**base, **over})


def _args(**over) -> argparse.Namespace:
    base = dict(id="P1", config=json.dumps({"title": "t", "actions": []}), config_file=None,
                dry_run=False, brief=True, force=False, no_types=False, allow_remove=False)
    return argparse.Namespace(**{**base, **over})


def test_a_real_create_with_brief_keeps_the_id_and_outlines_what_was_stored():
    client = _Client({"flow": _process(actions=5)})
    out = dto_actions._make_create(_component())(client, _args())
    assert out["created"] is True and out["id"] == "P1" and "result" not in out
    assert out["summary"]["flow"]["Actions"]["count"] == 5
    assert client.requests == [("POST", "/x")]


def test_a_real_create_without_brief_returns_the_stored_resource():
    stored = {"flow": _process()}
    out = dto_actions._make_create(_component())(_Client(stored), _args(brief=False))
    assert out["result"] == stored and "summary" not in out


def test_an_edit_dry_run_with_brief_returns_the_outline_and_no_dto():
    out = dto_actions._make_edit(_component())(_Client({}), _args(dry_run=True))
    assert out["dry_run"] is True and out["edit"] is True and "dto" not in out
    assert out["summary"]["Actions"]["count"] == 3


def test_a_real_edit_with_brief_outlines_what_the_edit_returned():
    component = _component(edit=lambda client, rid, config, ctx: {"flow": _process(actions=4)})
    out = dto_actions._make_edit(component)(_Client({}), _args())
    assert out["edited"] is True and out["id"] == "P1" and "result" not in out
    assert out["summary"]["flow"]["Actions"]["names"] == ["Step 0", "Step 1", "Step 2", "Step 3"]


def test_an_action_called_without_the_attribute_answers_as_before():
    """Code that builds the arguments by hand predates the flag. It must keep working."""
    args = _args(dry_run=True)
    del args.brief
    out = dto_actions._make_edit(_component())(_Client({}), args)
    assert "dto" in out and "summary" not in out
