"""Pytest fixtures + hyphen-safe module loading for the connector-builder agent.

The agent dir name has a hyphen, so its own modules (knowledge, context,
handlers.*, main) are imported by BARE name at runtime with the agent root on
sys.path. Under pytest those bare names collide across hyphenated dirs, so — like
the hyphenated tools — we load THIS agent's modules under unique ``cba_*`` aliases
via importlib, registering the bare names only TRANSIENTLY during load, then
restore. Shared agent libs (``agents._lib.*``) are a normal package and import
directly.

NOTE: no tests/__init__.py here; every test file has a unique ``test_cba_*``
basename to avoid pytest rootdir import collisions.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

AGENT_ROOT = Path(__file__).resolve().parents[1]          # agents/connector-builder
FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]      # repo root

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

_BARE_NAMES = (
    "knowledge", "context",
    "handlers", "handlers.status", "handlers.guidance",
    "handlers.nextstep", "handlers.checklist", "main",
)
_MISSING = object()
_saved_bare = {n: sys.modules.get(n, _MISSING) for n in _BARE_NAMES}


def _load(bare_name: str, relpath: str) -> ModuleType:
    path = AGENT_ROOT / relpath
    spec = importlib.util.spec_from_file_location(bare_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[bare_name] = mod
    spec.loader.exec_module(mod)
    sys.modules["cba_" + bare_name.replace(".", "_")] = mod
    return mod


knowledge = _load("knowledge", "knowledge.py")
context = _load("context", "context.py")

_handlers_pkg = ModuleType("handlers")
_handlers_pkg.__path__ = [str(AGENT_ROOT / "handlers")]  # type: ignore[attr-defined]
sys.modules["handlers"] = _handlers_pkg
sys.modules["cba_handlers"] = _handlers_pkg
status = _load("handlers.status", "handlers/status.py")
guidance = _load("handlers.guidance", "handlers/guidance.py")
nextstep = _load("handlers.nextstep", "handlers/nextstep.py")
checklist = _load("handlers.checklist", "handlers/checklist.py")

main = _load("main", "main.py")

sys.modules["cba_main"] = main
sys.modules["cba_knowledge"] = knowledge

_agent_root_str = str(AGENT_ROOT)
sys.path[:] = [p for p in sys.path if p != _agent_root_str]
for _bn, _prev in _saved_bare.items():
    if _prev is _MISSING:
        sys.modules.pop(_bn, None)
    else:
        sys.modules[_bn] = _prev


class FakeContext:
    """Records tool invocations and returns canned responses keyed by
    (tool, action)."""

    def __init__(self, responses=None):
        self.calls: list[tuple] = []
        self.responses = responses or {}

    def invoke(self, tool, action, *args):
        self.calls.append((tool, action, args))
        return self.responses.get((tool, action), {})


@pytest.fixture
def cba_main():
    return main


@pytest.fixture
def fake_context():
    return FakeContext()
