"""Shared error handling for agents.

Mirrors the tool-side contract: every uncaught exception is classified into a
(code, message, details, exit_code) tuple that becomes the {"error": ...} JSON
envelope. ToolError from a driven tool is surfaced with its origin preserved.
"""
from __future__ import annotations

from typing import Any

from agents._lib.toolrunner import ToolError


class UsageError(Exception):
    """Bad CLI usage (unknown action, missing/invalid arg). Exit code 2."""


class AgentError(Exception):
    """Agent-level failure with an explicit error code."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def classify(exc: Exception) -> tuple[str, str, dict[str, Any], int]:
    if isinstance(exc, UsageError):
        return "usage_error", str(exc), {}, 2
    if isinstance(exc, AgentError):
        return exc.code, exc.message, exc.details, 1
    if isinstance(exc, ToolError):
        # A tool the agent drives failed. Keep its code/message and note the tool.
        details = dict(exc.details)
        details.setdefault("tool", exc.tool)
        return f"tool:{exc.code}", f"{exc.tool}: {exc.message}", details, 1
    if isinstance(exc, KeyError):
        return "not_found", str(exc), {}, 1
    return "internal_error", str(exc), {"type": type(exc).__name__}, 1
