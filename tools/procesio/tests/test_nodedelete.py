"""Deleting one node from a live flow and healing the graph behind it (flowmodel/nodeparam).

A dead node is not free: it still runs, still consumes an execution, and still fails into whatever
error variable it was given, so a flow whose SQL contract moved on quietly throws on every run. The
designer removes such a node and reconnects its neighbours in one gesture; over the API the edge
healing has to be done explicitly, and getting it wrong strands the tail of the flow.
"""
from __future__ import annotations

import copy

import pytest

from tools.procesio.flowmodel import nodeparam as np


FLOW_ID = "flow-1"


def _port(source: str, dest: str) -> dict:
    return {"id": f"port-{source}-{dest}", "flowId": FLOW_ID, "sourceId": source,
            "destinationId": dest, "type": 0, "state": 1, "data": {}, "errors": {}, "config": {}}


def _linear_flow() -> dict:
    """Start -> Query -> Node -> Stop, plus the all-zeros entry edge the designer writes."""
    return {
        "id": FLOW_ID,
        "actions": [
            {"id": "start", "actionName": "Start", "actionTemplateName": "Start",
             "ports": [_port("start", "query"),
                       _port("00000000-0000-0000-0000-000000000000", "start")]},
            {"id": "query", "actionName": "sp_GetAvailableSlots", "actionTemplateName": "Execute Query",
             "ports": [_port("query", "node")]},
            {"id": "node", "actionName": "Node", "actionTemplateName": "Node",
             "ports": [_port("node", "stop")]},
            {"id": "stop", "actionName": "Stop", "actionTemplateName": "Stop", "ports": []},
        ],
        "variables": [],
    }


def _ids(flow: dict) -> list[str]:
    return [a["id"] for a in flow["actions"]]


def _edges(flow: dict) -> set[tuple[str, str]]:
    return {(p["sourceId"], p["destinationId"]) for a in flow["actions"] for p in a.get("ports") or []}


def test_deleting_a_middle_node_reconnects_its_predecessor_to_its_successor():
    flow = _linear_flow()

    changed, msg = np.delete_node(flow, np.find_node(flow, "Node"))

    assert changed is True
    assert "Node" in msg
    assert _ids(flow) == ["start", "query", "stop"]
    assert ("query", "stop") in _edges(flow), "the tail of the flow must stay reachable"
    assert not any(dest == "node" for _, dest in _edges(flow))


def test_the_healed_edge_keeps_the_flow_id_so_the_designer_can_render_it():
    flow = _linear_flow()
    np.delete_node(flow, np.find_node(flow, "Node"))

    healed = next(p for a in flow["actions"] for p in a.get("ports") or []
                  if (p["sourceId"], p["destinationId"]) == ("query", "stop"))
    assert healed["flowId"] == FLOW_ID
    assert healed["type"] == 0


def test_deleting_a_tail_node_just_drops_the_edge_into_it():
    flow = _linear_flow()
    # make Node the last action: Start -> Query -> Node
    node = np.find_node(flow, "Node")
    node["ports"] = []

    changed, _ = np.delete_node(flow, node)

    assert changed is True
    assert _ids(flow) == ["start", "query", "stop"]
    assert not any(dest == "node" for _, dest in _edges(flow))
    assert ("query", "stop") not in _edges(flow), "a tail node has no successor to reconnect to"


def test_a_predecessor_that_already_reaches_the_successor_does_not_get_a_duplicate_edge():
    flow = _linear_flow()
    query = np.find_node(flow, "sp_GetAvailableSlots")
    query["ports"].append(_port("query", "stop"))

    np.delete_node(flow, np.find_node(flow, "Node"))

    edges = [(p["sourceId"], p["destinationId"]) for a in flow["actions"] for p in a.get("ports") or []]
    assert edges.count(("query", "stop")) == 1


def test_healing_never_creates_a_self_loop():
    flow = _linear_flow()
    node = np.find_node(flow, "Node")
    node["ports"] = [_port("node", "query")]      # Node loops back to its own predecessor

    np.delete_node(flow, node)

    assert not any(src == dest for src, dest in _edges(flow))


def test_start_and_stop_are_refused():
    for key in ("Start", "Stop"):
        flow = _linear_flow()
        before = copy.deepcopy(flow)
        changed, msg = np.delete_node(flow, np.find_node(flow, key))
        assert changed is False
        assert "Start" in msg or "Stop" in msg
        assert flow == before


def test_a_branching_node_is_refused_rather_than_guessed():
    flow = _linear_flow()
    node = np.find_node(flow, "Node")
    node["ports"] = [_port("node", "stop"), _port("node", "query")]
    before = copy.deepcopy(flow)

    changed, msg = np.delete_node(flow, node)

    assert changed is False
    assert "more than one" in msg
    assert flow == before, "a refused delete must not half-rewire the graph"


def test_deleting_a_node_that_is_not_in_the_flow_is_refused():
    flow = _linear_flow()
    stranger = {"id": "ghost", "actionName": "Ghost", "actionTemplateName": "Node", "ports": []}
    changed, msg = np.delete_node(flow, stranger)
    assert changed is False
    assert "not in" in msg


def test_variables_are_left_alone_because_another_node_may_still_read_them():
    flow = _linear_flow()
    flow["variables"] = [{"id": "v1", "name": "availableSlots"}]

    np.delete_node(flow, np.find_node(flow, "Node"))

    assert flow["variables"] == [{"id": "v1", "name": "availableSlots"}]


@pytest.mark.parametrize("key", ["node", "Node"])
def test_find_node_accepts_either_the_id_or_the_action_name(key):
    flow = _linear_flow()
    assert np.find_node(flow, key)["id"] == "node"
