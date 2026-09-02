"""Tests for the offline flow graph reader (tools/procesio/flowmodel)."""
from __future__ import annotations

import copy
import glob
import json
import os

import pytest

from tools.procesio.flowmodel import read_bundle, read_flow

EXPORTS = os.path.join(os.path.dirname(__file__), "..", "docs_info", "Exports")


def _synthetic_flow():
    """A minimal PascalCase flow: Start -> A -> Decisional -(err)-> Stop2, A in a For Each,
    plus a Call Subprocess and a credential-using action."""
    return {
        "Id": "flow-1", "Title": "Synthetic",
        "Variables": [
            {"Id": "v1", "Name": "items", "Type": 1, "DataType": "dt-list",
             "IsList": True, "IsRequired": True},
        ],
        "Webhooks": [{"WebhookId": "wh-1", "WebhookVariables": []}],
        "Actions": [
            {"Id": "start", "ActionTemplateName": "Start", "ParentId": None,
             "CustomData": {"type": "circle", "position": {"x": 0, "y": 0}},
             "Ports": [{"SourceId": "start", "DestinationId": "fe", "Type": 0}]},
            {"Id": "fe", "ActionTemplateName": "For Each", "ParentId": None,
             "CustomData": {"type": "area", "name": "For Each",
                            "position": {"x": 100, "y": 0},
                            "areaSize": {"width": 400, "height": 200}},
             "Ports": [{"SourceId": "fe", "DestinationId": "a", "Type": 0}]},
            {"Id": "a", "ActionTemplateName": "Map Data", "ParentId": "fe",
             "CustomData": {"type": "square", "position": {"x": 150, "y": 50}},
             "Ports": [{"SourceId": "a", "DestinationId": "sub", "Type": 0}]},
            {"Id": "sub", "ActionTemplateName": "Call Subprocess", "ParentId": None,
             "CustomData": {"type": "square", "position": {"x": 600, "y": 0},
                            "configuration": [{"settings": [
                                {"label": "Select Subprocess", "type": "flow-list",
                                 "value": "target-flow"}]}]},
             "Ports": [{"SourceId": "sub", "DestinationId": "q", "Type": 0}]},
            {"Id": "q", "ActionTemplateName": "Execute Query", "ParentId": None,
             "CustomData": {"type": "square", "position": {"x": 700, "y": 0},
                            "configuration": [{"settings": [
                                {"label": "Select Database Server", "type": "credentials",
                                 "credentialsTemplateId": "tmpl-1", "value": "cred-gid-1"}]}]},
             "Ports": [{"SourceId": "q", "DestinationId": "stop", "Type": 0},
                       {"SourceId": "q", "DestinationId": "stop2", "Type": 1}]},
            {"Id": "stop", "ActionTemplateName": "Stop", "ParentId": None,
             "CustomData": {"type": "circle", "position": {"x": 800, "y": 0}}, "Ports": []},
            {"Id": "stop2", "ActionTemplateName": "Stop", "ParentId": None,
             "CustomData": {"type": "circle", "position": {"x": 800, "y": 100}}, "Ports": []},
        ],
    }


def test_basic_parse():
    g = read_flow(_synthetic_flow())
    assert g.flow_id == "flow-1" and g.title == "Synthetic"
    assert len(g.nodes) == 7
    assert g.start_id == "start"
    assert sorted(g.stop_ids) == ["stop", "stop2"]
    # edges: start->fe, fe->a, a->sub, sub->q, q->stop, q->stop2(err) = 6, one error
    assert len(g.edges) == 6
    assert any(e.is_error for e in g.edges)
    assert sum(1 for e in g.edges if e.type == 1) == 1


def test_shape_inherited_not_inferred():
    g = read_flow(_synthetic_flow())
    by_id = {n.id: n for n in g.nodes}
    assert by_id["fe"].shape == "area"
    assert by_id["q"].shape == "square"
    assert by_id["start"].shape == "circle"


def test_container_groups_foreach_children():
    g = read_flow(_synthetic_flow())
    assert len(g.containers) == 1
    c = g.containers[0]
    assert c.id == "fe" and c.kind == "foreach"
    assert c.children == ["a"]


def test_subprocess_and_credentials():
    g = read_flow(_synthetic_flow())
    assert len(g.subprocess_calls) == 1
    sc = g.subprocess_calls[0]
    assert sc.target_flow_id == "target-flow" and sc.kind == "call"
    assert g.resources["credentials"] == ["cred-gid-1"]
    assert g.resources["webhooks"] == ["wh-1"]


def test_variables_contract():
    g = read_flow(_synthetic_flow())
    assert len(g.variables) == 1
    v = g.variables[0]
    assert v.name == "items" and v.is_list and v.is_required


def _to_camel(obj):
    """Recursively lowercase the first letter of every dict key (PascalCase -> camelCase)."""
    if isinstance(obj, dict):
        return {(k[:1].lower() + k[1:]): _to_camel(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_camel(v) for v in obj]
    return obj


def test_case_insensitive_camel_equals_pascal():
    pascal = _synthetic_flow()
    camel = _to_camel(copy.deepcopy(pascal))
    gp = read_flow(pascal).to_dict()
    gc = read_flow(camel).to_dict()
    assert gp == gc


def test_reader_is_pure():
    flow = _synthetic_flow()
    snapshot = copy.deepcopy(flow)
    read_flow(flow)
    assert flow == snapshot  # input unchanged


def test_json_string_source():
    g = read_flow(json.dumps(_synthetic_flow()))
    assert g.flow_id == "flow-1"


def test_multiflow_bundle_requires_flow_id():
    bundle = {"Flows": [_synthetic_flow(), {**_synthetic_flow(), "Id": "flow-2"}]}
    with pytest.raises(ValueError):
        read_flow(bundle)
    # explicit id resolves
    assert read_flow(bundle, flow_id="flow-2").flow_id == "flow-2"


def test_read_bundle_resource_map():
    bundle = {"Flows": [_synthetic_flow()]}
    out = read_bundle(bundle)
    assert "flow-1" in out["flows"]
    assert out["process_edges"] == [{"source": "flow-1", "target": "target-flow", "kind": "call"}]


@pytest.mark.parametrize("path", sorted(glob.glob(os.path.join(EXPORTS, "*.procesio")))[:4])
def test_real_exports_parse(path):
    """Every flow in a few real bundles parses; node/edge counts match a naive recount."""
    bundle = json.load(open(path, encoding="utf-8"))
    flows = bundle.get("Flows") or []
    if not flows:
        pytest.skip("no flows in this bundle")
    for f in flows:
        g = read_flow(f)
        assert len(g.nodes) == len(f.get("Actions") or [])
        naive_edges = sum(len(a.get("Ports") or []) for a in (f.get("Actions") or []))
        assert len(g.edges) == naive_edges
