"""Pure, offline reader: a PROCESIO flow/export → a canonical node/edge graph model.

The substrate the canvas layout tool, inspect-flow, and audit build on. See
tools/procesio/PROCESIO-RESOURCE-MODEL-NOTES.md §1 for the model it parses.
"""
from tools.procesio.flowmodel.model import (
    Container, Edge, FlowGraph, Node, SubprocessCall, VarRef,
)
from tools.procesio.flowmodel.reader import read_bundle, read_flow

__all__ = [
    "FlowGraph", "Node", "Edge", "Container", "VarRef", "SubprocessCall",
    "read_flow", "read_bundle",
]
