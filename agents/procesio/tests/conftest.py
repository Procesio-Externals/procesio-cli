"""Fixtures for the PROCESIO agent tests. Zero live calls: the tool invoker is a
recording fake, Credential Manager is never touched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))


@pytest.fixture(autouse=True)
def _no_keyring(monkeypatch):
    from tools._lib import creds
    monkeypatch.setattr(creds, "get_optional", lambda tool, name: None)
    monkeypatch.setattr(creds, "has", lambda tool, name: False)


class FakeInvoke:
    """Drop-in for toolrunner.invoke: __call__(tool, action, *args) -> dict.

    Map an action name to the dict it should return, or to a ToolError instance
    to simulate a tool failure. Records every call for assertions.
    """

    def __init__(self):
        self.calls: list[tuple[str, str, list]] = []
        self._map: dict[str, object] = {}

    def set(self, action: str, value) -> "FakeInvoke":
        self._map[action] = value
        return self

    def __call__(self, tool: str, action: str, *args):
        self.calls.append((tool, action, list(args)))
        v = self._map.get(action, {})
        if isinstance(v, Exception):
            raise v
        return v


@pytest.fixture
def fake_invoke():
    return FakeInvoke()


def flow(actions, *, title="T", description="") -> dict:
    """Build a get-process style envelope around a flow with these actions."""
    return {"result": {"flow": {
        "Title": title, "Description": description, "Actions": actions}}}


def action(template, *, params=None, settings=None, name=None) -> dict:
    a = {"ActionName": name or template, "ActionTemplateName": template,
         "Parameters": params or []}
    if settings is not None:
        a["CustomData"] = {"configuration": [{"settings": settings}]}
    return a
