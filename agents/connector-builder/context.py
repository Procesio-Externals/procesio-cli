"""Runtime context for the connector-builder agent.

Stateless: the only thing context-actions need is a tool invoker so they can
drive the `connector-builder` and `procesio` tools (tests replace it with a
fake). The agent has no secret of its own — readiness comes from the tools it
drives.
"""
from __future__ import annotations

from agents._lib import toolrunner


class ConnectorBuilderContext:
    def __init__(self, invoke=None):
        self.invoke = invoke or toolrunner.invoke

    @classmethod
    def create(cls, invoke=None) -> "ConnectorBuilderContext":
        return cls(invoke=invoke)
