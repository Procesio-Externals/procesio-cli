"""Deterministic canvas auto-layout: graph → tidy positions.

`engine` is the pure layered-layout core (default); `elk_engine` is an opt-in ELK
'layered' alternative with the same I/O contract; `dispatch` picks between them via the
LAYOUT_ENGINE flag; `adapter` bridges the chosen engine to the `.procesio` export / live
flow. See todo/procesio-canvas-layout-tool.md and
agents/procesio/PROCESIO-VISUAL-ORGANIZATION.md.
"""
from tools.procesio.layout import adapter, dispatch, elk_engine, engine

__all__ = ["engine", "elk_engine", "dispatch", "adapter"]
