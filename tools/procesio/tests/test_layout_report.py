"""Tests for the engine-agnostic layout verification (report.build_report / layout-report)."""
from __future__ import annotations

from tools.procesio.layout import adapter, report


def _linear_flow():
    return {"Id": "f", "Actions": [
        {"Id": "start", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "start", "DestinationId": "a", "Type": 0}]},
        {"Id": "a", "ActionTemplateName": "Map Data",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "a", "DestinationId": "stop", "Type": 0}]},
        {"Id": "stop", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}}, "Ports": []},
    ]}


def _foreach_flow():
    return {"Id": "f", "Actions": [
        {"Id": "start", "ActionTemplateName": "Start",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "start", "DestinationId": "loop", "Type": 0}]},
        {"Id": "loop", "ActionTemplateName": "For Each",
         "CustomData": {"type": "area", "name": "For Each", "position": {"x": 0, "y": 0},
                        "areaSize": {"width": 0, "height": 0, "x": 0, "y": 0}},
         "Ports": [{"SourceId": "loop", "DestinationId": "k1", "Type": 0},
                   {"SourceId": "loop", "DestinationId": "stop", "Type": 0}]},
        {"Id": "k1", "ActionTemplateName": "Map Data", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}},
         "Ports": [{"SourceId": "k1", "DestinationId": "k2", "Type": 0}]},
        {"Id": "k2", "ActionTemplateName": "Add", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 0, "y": 0}}, "Ports": []},
        {"Id": "stop", "ActionTemplateName": "Stop",
         "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}}, "Ports": []},
    ]}


def test_report_on_clean_layout():
    b = adapter.layout_flow(_linear_flow())["bundle"]
    r = report.build_report(b)
    assert r["ok"] is True and r["hard_issue_count"] == 0
    m = r["metrics"]
    assert m["nodes"] == 3 and m["edges"] == 2
    for k in ("crossings", "max_edge_px", "vertical_rows", "aspect_w_to_h", "back_edges"):
        assert k in m


def test_report_detects_overlap():
    # two leaf nodes stacked on the same point → overlap hard-issue
    flow = {"Id": "f", "Actions": [
        {"Id": "a", "CustomData": {"type": "square", "position": {"x": 100, "y": 100}}, "Ports": []},
        {"Id": "b", "CustomData": {"type": "square", "position": {"x": 110, "y": 100}}, "Ports": []},
    ]}
    r = report.build_report(flow)
    assert r["ok"] is False
    assert any(i["type"] == "overlap" for i in r["hard_issues"])


def test_report_detects_child_outside_frame_and_small_container():
    # a For-Each whose frame is tiny (0x0) with a child at (200,200) → outside + size warnings
    flow = {"Id": "f", "Actions": [
        {"Id": "loop", "CustomData": {"type": "area", "name": "For Each",
         "position": {"x": 0, "y": 0}, "areaSize": {"width": 0, "height": 0}}, "Ports": []},
        {"Id": "k1", "ParentId": "loop",
         "CustomData": {"type": "square", "position": {"x": 200, "y": 200}}, "Ports": []},
    ]}
    r = report.build_report(flow)
    assert r["ok"] is False
    assert any(i["type"] == "child_outside_frame" for i in r["hard_issues"])
    c = r["containers"][0]
    assert c["warnings"]                                  # width/height < min flagged


def test_report_engine_agnostic():
    # the SAME verification runs on either engine's output and yields the same structure
    import os
    legacy = report.build_report(adapter.layout_flow(_foreach_flow())["bundle"])
    os.environ["LAYOUT_ENGINE"] = "elk"
    try:
        elk = report.build_report(adapter.layout_flow(_foreach_flow())["bundle"])
    finally:
        os.environ.pop("LAYOUT_ENGINE", None)
    for rep_ in (legacy, elk):
        assert set(rep_) >= {"ok", "metrics", "containers", "hard_issues"}
        assert rep_["metrics"]["nodes"] == 5
        assert rep_["containers"] and rep_["containers"][0]["name"] == "For Each"
