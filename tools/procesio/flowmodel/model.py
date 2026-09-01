"""Canonical, JSON-ready graph model for a PROCESIO flow.

Plain dataclasses so Python consumers (the layout adapter, inspect-flow) get typed
objects, and `to_dict()` yields the JSON the `read-flow-graph` action emits. Pure data,
no behavior beyond serialization.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Node:
    id: str
    template: str | None
    shape: str | None          # "square" | "diamond" | "circle" | "area" (action-dictated)
    icon: str | None
    position: dict              # {"x": float, "y": float}
    size: dict                 # {"w": float, "h": float}
    parent_id: str | None
    input_ports: int | None
    output_ports: int | None
    disabled: bool = False


@dataclass
class Edge:
    source: str
    dest: str
    type: int                  # 0 = normal flow edge, 1 = error-port edge
    is_default: bool = False    # the decisional's Default branch (port.data.isDefault=='default')

    @property
    def is_error(self) -> bool:
        return self.type == 1


@dataclass
class Container:
    id: str                    # the For-Each area node id
    kind: str                  # "foreach"
    children: list[str] = field(default_factory=list)
    size: dict = field(default_factory=dict)


@dataclass
class VarRef:
    id: str
    name: str | None
    type: int | None
    data_type: str | None
    is_list: bool = False
    is_required: bool = False
    is_error: bool = False


@dataclass
class SubprocessCall:
    action_id: str
    target_flow_id: str | None
    kind: str                  # "call" | "trigger"


@dataclass
class FlowGraph:
    flow_id: str | None
    title: str | None
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    containers: list[Container] = field(default_factory=list)
    variables: list[VarRef] = field(default_factory=list)
    subprocess_calls: list[SubprocessCall] = field(default_factory=list)
    resources: dict = field(default_factory=lambda: {"credentials": [], "webhooks": [], "documents": []})
    start_id: str | None = None
    stop_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        # surface the convenience flag on edges
        for e_in, e_out in zip(self.edges, d["edges"]):
            e_out["is_error"] = e_in.is_error
        return d
