"""Runtime context for the PROCESIO agent.

Unlike the outreach agent there is no state backend - the PROCESIO agent is
stateless. The only thing context-actions need is a tool invoker (so they can
drive the `procesio` tool), which tests replace with a fake. No secret of its
own; readiness comes from the tools it drives.
"""
from __future__ import annotations

from agents._lib import toolrunner


class ProcesioContext:
    def __init__(self, invoke=None):
        self.invoke = invoke or toolrunner.invoke

    @classmethod
    def create(cls, invoke=None) -> "ProcesioContext":
        return cls(invoke=invoke)
