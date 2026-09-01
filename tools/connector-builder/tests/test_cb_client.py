"""Auth-resolution + client behaviour tests (no network)."""
from __future__ import annotations

import pytest

import cb_client as client
import cb_errors as errors


@pytest.fixture(autouse=True)
def _clear_auth_env(monkeypatch):
    for k in ("CONNECTOR_BUILDER_AUTH", "CONNECTOR_BUILDER_API_KEY",
              "CONNECTOR_BUILDER_USERNAME", "CONNECTOR_BUILDER_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


def _set_creds(monkeypatch, mapping):
    monkeypatch.setattr(client, "_cred", lambda name: mapping.get(name))


def test_apikey_mode_default_when_key_present(monkeypatch):
    _set_creds(monkeypatch, {"api-key": "acb_abc"})
    assert client.resolve_token() == "acb_abc"


def test_userpass_mode_when_only_userpass(monkeypatch):
    _set_creds(monkeypatch, {"username": "u@e", "password": "pw"})
    monkeypatch.setattr(client, "login", lambda u, p: f"jwt:{u}:{p}")
    assert client.resolve_token() == "jwt:u@e:pw"


def test_explicit_userpass_overrides_apikey(monkeypatch):
    monkeypatch.setenv("CONNECTOR_BUILDER_AUTH", "userpass")
    _set_creds(monkeypatch, {"api-key": "acb_abc", "username": "u", "password": "p"})
    monkeypatch.setattr(client, "login", lambda u, p: "jwt-tok")
    assert client.resolve_token() == "jwt-tok"


def test_no_credential_raises(monkeypatch):
    _set_creds(monkeypatch, {})
    with pytest.raises(errors.CredentialError):
        client.resolve_token()


def test_apikey_mode_without_key_raises(monkeypatch):
    monkeypatch.setenv("CONNECTOR_BUILDER_AUTH", "apikey")
    _set_creds(monkeypatch, {"username": "u", "password": "p"})
    with pytest.raises(errors.CredentialError):
        client.resolve_token()


def test_bearer_header_shape():
    c = client.ConnectorBuilderClient(token="acb_xyz")
    h = c._headers()
    assert h["Authorization"] == "Bearer acb_xyz"
    assert h["Accept"] == "application/json"


def test_base_url_env_override(monkeypatch):
    monkeypatch.setenv("CONNECTOR_BUILDER_BASE_URL", "https://local/api/")
    assert client.get_base_url() == "https://local/api"


class _Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body
        self.headers = {}
        self.content = b"{}"
        self.text = "{}"

    def json(self):
        return self._body


def test_request_raises_apierror_on_4xx(monkeypatch):
    c = client.ConnectorBuilderClient(token="t")

    class _S:
        def request(self, *a, **k):
            return _Resp(404, {"detail": "nope"})

    c._s = _S()
    with pytest.raises(errors.ApiError) as ei:
        c.get("/builds/x")
    assert ei.value.status_code == 404
