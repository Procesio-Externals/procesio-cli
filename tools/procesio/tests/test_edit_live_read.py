"""`process-edit` must stop when it cannot read the live flow.

An edit carries the variable ids over from the live flow, by name, because forms and subprocess
calls bind a variable by GUID. The read used to sit in a `try/except: pass`, so a failed read went
on with nothing carried over: every variable got a new id, the removal gate had nothing to compare
against, and a save that still went through broke every map bound to the process, with no error.

`--dry-run` is the exception on purpose: it writes nothing, so it still previews, but it has to say
that the ids it shows are not the ones an edit would keep.
"""
from __future__ import annotations

import argparse
import itertools
import json

import pytest
import requests

from tools.procesio import errors
from tools.procesio.dto import framework
from tools.procesio.dto.process import builder as pb
from tools.procesio.errors import ProcesioAPIError
from tools.procesio.handlers import dto_actions


LIVE_VAR_ID = "11111111-1111-1111-1111-111111111111"
CONFIG = {"title": "t", "actions": [],
          "variables": [{"name": "Row", "type": "string", "direction": "input"}]}


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}", "_force": True}


class _Client:
    """Answers the live read with whatever `read` does, and records every write."""

    def __init__(self, read):
        self._read = read
        self.writes = []

    def get(self, path, query=None):
        return self._read()

    def put(self, path, body=None, query=None):
        self.writes.append(body)
        return {}

    def post(self, path, body=None, query=None):
        return {"raw_text": ""}


def _raises(exc):
    def read():
        raise exc
    return read


def _live(*names):
    flow = {"actions": [], "variables": [{"id": LIVE_VAR_ID, "name": n, "isError": False} for n in names]}
    return lambda: {"flow": flow}


def _written_id(client, name):
    return next(v["Id"] for v in client.writes[0]["Variables"] if v["Name"] == name)


@pytest.mark.parametrize("status,code", [(400, "invalid_argument"), (503, "server_error")])
def test_a_failed_read_stops_the_edit_and_keeps_its_status(status, code):
    client = _Client(_raises(ProcesioAPIError(status, f"HTTP {status}", {"body": "kept"})))

    with pytest.raises(ProcesioAPIError) as got:
        pb._edit(client, "P1", CONFIG, _ctx())

    assert got.value.status == status and got.value.details == {"body": "kept"}
    assert errors.classify(got.value)[0] == code, "the code callers branch on must not change"
    assert "could not read process P1" in str(got.value), "a bare status does not say what failed"
    assert "nothing was written" in str(got.value)
    assert client.writes == [], "nothing may be written without the live ids"


def test_a_network_failure_on_the_read_stops_the_edit_as_it_is():
    failure = requests.exceptions.ConnectionError("no route to host")
    client = _Client(_raises(failure))

    with pytest.raises(requests.exceptions.ConnectionError) as got:
        pb._edit(client, "P1", CONFIG, _ctx())

    assert got.value is failure
    assert client.writes == []


@pytest.mark.parametrize("reply", [
    None, [], {}, {"raw_text": ""}, {"flow": None}, {"flow": {"title": "no graph"}},
])
def test_a_reply_that_is_not_a_flow_stops_the_edit(reply):
    """An empty body reads as success at the HTTP layer, and would mint new ids just the same."""
    client = _Client(lambda: reply)

    with pytest.raises(ProcesioAPIError):
        pb._edit(client, "P1", CONFIG, _ctx())

    assert client.writes == []


def test_a_process_without_variables_can_still_be_edited(monkeypatch):
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)
    client = _Client(lambda: {"flow": {"actions": []}})

    pb._edit(client, "P1", CONFIG, _ctx())

    assert len(client.writes) == 1


@pytest.mark.parametrize("live_name", ["Row", "row", " ROW "])
def test_a_variable_keeps_its_id_by_name_ignoring_case(monkeypatch, live_name):
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)
    client = _Client(_live(live_name))

    pb._edit(client, "P1", CONFIG, {**_ctx(), "_allow_remove": True})

    assert _written_id(client, "Row") == LIVE_VAR_ID


def test_a_flow_wrapped_in_result_still_carries_its_ids(monkeypatch):
    """The form builder accepts this shape too, so the check must not refuse it."""
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)
    wrapped = {"result": _live("Row")()}
    client = _Client(lambda: wrapped)

    pb._edit(client, "P1", CONFIG, _ctx())

    assert _written_id(client, "Row") == LIVE_VAR_ID


def test_a_really_renamed_variable_gets_a_new_id(monkeypatch):
    monkeypatch.setattr(pb, "_save_gate", lambda *a, **k: None)
    client = _Client(_live("OldName"))

    pb._edit(client, "P1", CONFIG, {**_ctx(), "_allow_remove": True})

    assert _written_id(client, "Row") != LIVE_VAR_ID


def _preview(client):
    comp = framework.Component(
        # the real process dir, so validate_config finds a schema; the config below satisfies it
        name="process", description="", dir=pb.DIR,
        build=lambda config, ctx: {"Variables": []}, create_endpoint=("POST", "/x"), get_path="/x/{id}",
        extract_id=lambda r, d: None, edit_ctx=pb._edit_ctx)
    args = argparse.Namespace(id="P1", config=json.dumps({"title": "t", "actions": []}), config_file=None,
                              dry_run=True, force=False, no_types=False, allow_remove=False)
    return dto_actions._make_edit(comp)(client, args)


def test_the_preview_still_builds_and_says_it_could_not_read_the_live_flow():
    client = _Client(_raises(requests.exceptions.ConnectionError("no route to host")))

    out = _preview(client)

    assert out["dry_run"] is True and "dto" in out
    assert "no route to host" in out["live_read_failed"]
    assert client.writes == []


def test_the_preview_says_nothing_when_the_read_worked():
    assert "live_read_failed" not in _preview(_Client(_live("Row")))
