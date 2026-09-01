"""Shared fakes for the procesio test suite - zero live HTTP, zero real keyring.

* FakeCreds   - in-memory stand-in for Windows Credential Manager.
* FakeResp    - minimal response (status_code/.json()/.text).
* FakeSession - records every .request(...) and returns canned/queued responses.
"""
from __future__ import annotations

import pytest

from tools.procesio import profiles


class FakeCreds:
    def __init__(self):
        self.store: dict[str, str] = {}

    @staticmethod
    def _k(tool: str, name: str) -> str:
        return f"{tool}:{name}"

    def get_optional(self, tool, name):
        return self.store.get(self._k(tool, name))

    def get(self, tool, name):
        v = self.get_optional(tool, name)
        if v is None:
            raise KeyError(name)
        return v

    def has(self, tool, name):
        return self.get_optional(tool, name) is not None

    def set_secret(self, tool, name, value):
        self.store[self._k(tool, name)] = value

    def delete(self, tool, name):
        self.store.pop(self._k(tool, name), None)


class FakeResp:
    def __init__(self, status: int, body=None, text: str = "", cookies=None,
                 headers=None, content: bytes = b""):
        self.status_code = status
        self._body = body
        self.text = text
        self.cookies = dict(cookies or {})      # name -> value (Set-Cookie)
        self.headers = dict(headers or {})       # response headers
        self.content = content                   # raw bytes (for request_bytes)

    def json(self):
        if self._body is None:
            raise ValueError("no json body")
        return self._body


class FakeSession:
    """responder(method, url, kwargs) -> FakeResp, OR a queue of FakeResp
    consumed in order, OR a default 200 {}. Records every call (incl. form
    `data` and `json` bodies)."""

    def __init__(self, responder=None, queue=None):
        self.calls: list[dict] = []
        self.responder = responder
        self.queue = list(queue or [])

    def request(self, method, url, params=None, json=None, data=None,
                headers=None, timeout=None, files=None):
        self.calls.append({"method": method, "url": url, "params": params,
                           "json": json, "data": data, "headers": headers,
                           "timeout": timeout, "files": files})
        if self.responder:
            return self.responder(method, url, {"params": params, "json": json,
                                                "data": data, "headers": headers,
                                                "files": files})
        if self.queue:
            return self.queue.pop(0)
        return FakeResp(200, {})


@pytest.fixture(autouse=True)
def _isolate_userdata(tmp_path, monkeypatch):
    """Pin the user-data root to a per-test temp dir so the environments registry
    (config/procesio/environments.json) is empty by default — every test resolves
    the default environment to Internal-PROD (the historical production URLs) and no
    test ever reads or writes the developer's real registry."""
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path / "userdata"))
    yield


@pytest.fixture(autouse=True)
def _clear_cookie_mem_cache():
    """The userpass in-process cookie cache is module-global — clear it around
    every test so sessions don't leak between tests."""
    from tools.procesio import auth
    auth._MEM_COOKIES.clear()
    yield
    auth._MEM_COOKIES.clear()


@pytest.fixture
def store(monkeypatch):
    """In-memory credential store wired into the profiles module."""
    fake = FakeCreds()
    monkeypatch.setattr(profiles, "creds", fake)
    return fake


@pytest.fixture
def apikey_profile(store):
    profiles.save_profile("k1", {
        "type": "apikey", "key": "NAME1", "value": "SECRET1",
        "workspace_id": "ws-guid-1", "workspace": "personal",
    })
    return "k1"


@pytest.fixture
def userpass_profile(store):
    profiles.save_profile("u1", {
        "type": "userpass", "username": "u@example.com", "password": "pw",
    })
    return "u1"
