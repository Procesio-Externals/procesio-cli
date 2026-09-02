"""Pytest fixtures + hyphen-safe module loading for the connector-builder tool.

The tool dir name has a hyphen, so its own modules (errors, actiondef, client,
handlers.*, main) cannot be imported as ``tools.connector-builder.*``. At runtime
main.py imports them by BARE name with the tool root on sys.path. Under pytest
those bare names collide across hyphenated tools, so — exactly like fgo-web /
quickmail-web — we load THIS tool's modules under unique ``cb_*`` aliases via
importlib, registering the bare names only TRANSIENTLY during load so each
module's intra-tool bare imports resolve to THIS tool's files, then restore.

NOTE: there is intentionally NO tests/__init__.py here and every test file has a
unique ``test_cb_*`` basename — otherwise pytest's rootdir import collides with
other hyphenated tools' identically-named test modules.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[1]          # tools/connector-builder
FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]     # repo root

if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

_BARE_NAMES = (
    "errors", "actiondef", "client",
    "handlers", "handlers.common", "handlers.auth", "handlers.builds",
    "handlers.files", "handlers.telemetry", "handlers.admin", "handlers.raw",
    "main",
)
_MISSING = object()
_saved_bare = {n: sys.modules.get(n, _MISSING) for n in _BARE_NAMES}


def _load(bare_name: str, relpath: str) -> ModuleType:
    path = TOOL_ROOT / relpath
    spec = importlib.util.spec_from_file_location(bare_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[bare_name] = mod  # transient: lets intra-tool bare imports work
    spec.loader.exec_module(mod)
    sys.modules["cb_" + bare_name.replace(".", "_")] = mod
    return mod


# Leaf modules first.
errors = _load("errors", "errors.py")
actiondef = _load("actiondef", "actiondef.py")
client = _load("client", "client.py")

_handlers_pkg = ModuleType("handlers")
_handlers_pkg.__path__ = [str(TOOL_ROOT / "handlers")]  # type: ignore[attr-defined]
sys.modules["handlers"] = _handlers_pkg
sys.modules["cb_handlers"] = _handlers_pkg
common = _load("handlers.common", "handlers/common.py")
auth = _load("handlers.auth", "handlers/auth.py")
builds = _load("handlers.builds", "handlers/builds.py")
files = _load("handlers.files", "handlers/files.py")
telemetry = _load("handlers.telemetry", "handlers/telemetry.py")
admin = _load("handlers.admin", "handlers/admin.py")
raw = _load("handlers.raw", "handlers/raw.py")

main = _load("main", "main.py")

# Friendly aliases for tests.
sys.modules["cb_main"] = main
sys.modules["cb_errors"] = errors
sys.modules["cb_client"] = client

# Strip TOOL_ROOT from sys.path so another hyphenated tool's bare imports don't
# resolve to OUR files for the rest of the session, then restore bare-name slots.
_tool_root_str = str(TOOL_ROOT)
sys.path[:] = [p for p in sys.path if p != _tool_root_str]
for _bn, _prev in _saved_bare.items():
    if _prev is _MISSING:
        sys.modules.pop(_bn, None)
    else:
        sys.modules[_bn] = _prev


class FakeClient:
    """Records calls and returns canned responses. Mirrors the
    ConnectorBuilderClient verb surface used by handlers."""

    def __init__(self, responses=None, base_url="https://example/api"):
        self.base_url = base_url
        self.calls: list[tuple] = []
        self.responses = responses or {}

    def _ret(self, key, default):
        return self.responses.get(key, default)

    def get(self, path, params=None):
        self.calls.append(("GET", path, params, None))
        return self._ret(("GET", path), {"ok": True, "path": path, "params": params})

    def post(self, path, json_body=None, params=None):
        self.calls.append(("POST", path, params, json_body))
        return self._ret(("POST", path), {"ok": True, "path": path, "body": json_body})

    def put(self, path, json_body=None):
        self.calls.append(("PUT", path, None, json_body))
        return self._ret(("PUT", path), {"ok": True, "path": path, "body": json_body})

    def patch(self, path, json_body=None):
        self.calls.append(("PATCH", path, None, json_body))
        return self._ret(("PATCH", path), {"ok": True, "path": path, "body": json_body})

    def delete(self, path, params=None):
        self.calls.append(("DELETE", path, params, None))
        return self._ret(("DELETE", path), {"ok": True, "path": path})

    def request(self, method, path, params=None, json_body=None):
        self.calls.append((method.upper(), path, params, json_body))
        return self._ret((method.upper(), path),
                         {"ok": True, "path": path, "method": method.upper()})

    def download(self, path, out_path, params=None):
        self.calls.append(("DOWNLOAD", path, params, out_path))
        return {"out": out_path, "bytes": 123, "filename": "pkg.nupkg",
                "content_type": "application/octet-stream"}


@pytest.fixture
def fake_client():
    return FakeClient()


@pytest.fixture
def cb_main():
    return main


@pytest.fixture
def cb_errors():
    return errors


@pytest.fixture
def cb_client():
    return client
