"""Tests for the live process-layout actions (duplicate-process, relayout-process).

The client is faked — no network. adapter.layout_flow runs the real offline engine
(legacy by default) on a tiny flow, so the round-trip through the handler is exercised."""
from __future__ import annotations

from argparse import Namespace

import pytest

from tools.procesio.errors import UsageError
from tools.procesio.handlers import process_layout as pl


def _flow(fid="f1"):
    return {"Id": fid, "Title": "Demo", "Actions": [
        {"Id": "start", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "start", "DestinationId": "a", "Type": 0}]},
        {"Id": "a", "ActionTemplateName": "Map Data",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "a", "DestinationId": "stop", "Type": 0}]},
        {"Id": "stop", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}}, "Ports": []},
    ]}


class FakeClient:
    """Records POST/PUT calls and serves canned GET responses."""
    def __init__(self, project_lists, flow):
        self.workspace_id = "ws-1"
        self.profile = {}                      # unbound -> production designer host
        self._lists = list(project_lists)      # successive /api/Projects responses
        self._flow = flow
        self.posts = []
        self.puts = []

    def get(self, path, query=None):
        if path == "/api/Projects":
            return {"pageItems": self._lists.pop(0)}
        if path.startswith("/api/Projects/"):
            return {"flow": self._flow}
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, body=None, query=None):
        self.posts.append((path, body))
        if path.endswith("/duplicate"):
            return {"hasWebhook": False}
        if path == "/api/Projects/validate":
            return {"raw_text": ""}
        raise AssertionError(f"unexpected POST {path}")

    def put(self, path, body=None, query=None):
        self.puts.append((path, body))
        return {}


def test_duplicate_process_finds_new_copy_id():
    before = [{"id": "A"}, {"id": "B"}]
    after = [{"id": "A"}, {"id": "B"}, {"id": "C"}]  # C is the new copy
    # the two /api/Projects GETs (before, after) + the GET for the copy's title
    c = FakeClient([before, after], _flow(fid="C"))
    out = pl.duplicate_process(c, Namespace(id="A", workspace_id="ws-1", profile=None))["result"]
    assert out["copy_id"] == "C"
    assert out["source_id"] == "A"
    assert out["designer_url"].endswith("/designer/C#ws-1")
    assert out["has_webhook"] is False
    assert c.posts[0][0] == "/api/Projects/A/duplicate"


def test_duplicate_process_ambiguous_when_multiple_new():
    before = [{"id": "A"}]
    after = [{"id": "A"}, {"id": "C"}, {"id": "D"}]   # two new → cannot disambiguate
    c = FakeClient([before, after], _flow())
    out = pl.duplicate_process(c, Namespace(id="A", workspace_id="ws-1", profile=None))["result"]
    assert out["copy_id"] is None
    assert set(out["copy_candidates"]) == {"C", "D"}
    assert out["designer_url"] is None


def test_relayout_process_dry_run_does_not_save():
    c = FakeClient([], _flow())
    out = pl.relayout_process(c, Namespace(id="C", workspace_id="ws-1", profile=None,
                                           no_validate=False, dry_run=True))["result"]
    assert out["saved"] is False and out["dry_run"] is True
    assert out["nodes_moved"] >= 1
    assert out["engine"] in ("legacy", "elk")
    assert c.puts == [] and c.posts == []           # nothing persisted


def test_relayout_process_validates_then_saves():
    c = FakeClient([], _flow())
    out = pl.relayout_process(c, Namespace(id="C", workspace_id="ws-1", profile=None,
                                           no_validate=False, dry_run=False))["result"]
    assert out["saved"] is True and out["validated"] is True
    assert [p[0] for p in c.posts] == ["/api/Projects/validate"]   # validate gate ran
    assert len(c.puts) == 1 and c.puts[0][0] == "/api/Projects"    # saved via PUT
    # the PUT body carries the re-laid-out flow (same action ids, new positions)
    saved_flow = c.puts[0][1]
    assert {a["Id"] for a in saved_flow["Actions"]} == {"start", "a", "stop"}


def test_relayout_process_no_validate_skips_gate():
    c = FakeClient([], _flow())
    out = pl.relayout_process(c, Namespace(id="C", workspace_id="ws-1", profile=None,
                                           no_validate=True, dry_run=False))["result"]
    assert out["saved"] is True and out["validated"] is None
    assert c.posts == []                            # validate skipped
    assert len(c.puts) == 1


def test_relayout_process_reports_elk_engine(monkeypatch):
    monkeypatch.setenv("LAYOUT_ENGINE", "elk")
    c = FakeClient([], _flow())
    out = pl.relayout_process(c, Namespace(id="C", workspace_id="ws-1", profile=None,
                                           no_validate=True, dry_run=True))["result"]
    assert out["engine"] == "elk"
