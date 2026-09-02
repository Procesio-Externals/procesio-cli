"""Multi-credential profile store: CRUD, default resolution, secret hygiene."""
from __future__ import annotations

import argparse
import json

import pytest

from tools.procesio import profiles
from tools.procesio.errors import AuthError, UsageError


def test_save_and_get_roundtrip(store):
    profiles.save_profile("p", {"type": "apikey", "key": "K", "value": "V"})
    blob = profiles.get_profile("p")
    assert blob["key"] == "K" and blob["value"] == "V"
    assert "p" in profiles.profile_names()


def test_first_profile_becomes_default(store):
    profiles.save_profile("first", {"type": "apikey", "key": "K", "value": "V"})
    assert profiles.get_default() == "first"
    profiles.save_profile("second", {"type": "apikey", "key": "K", "value": "V"})
    assert profiles.get_default() == "first"  # adding more doesn't change default


def test_index_has_no_secret_values(store):
    profiles.save_profile("p", {"type": "apikey", "key": "K", "value": "TOPSECRET",
                                "workspace": "w"})
    raw_index = store.get("procesio", "credentials")
    assert "TOPSECRET" not in raw_index
    assert json.loads(raw_index)[0]["name"] == "p"


def test_public_view_redacts_secrets(store):
    profiles.save_profile("p", {"type": "userpass", "username": "u@example.com",
                                "password": "PW"})
    view = profiles.public_view(profiles.get_profile("p"), "p")
    assert view["username"] == "u@example.com"
    assert "password" not in view
    assert view["has_password"] is True


def test_resolve_explicit_default_and_single(store):
    with pytest.raises(UsageError):
        profiles.resolve(None)  # nothing stored, ambiguous
    profiles.save_profile("only", {"type": "apikey", "key": "K", "value": "V"})
    name, _ = profiles.resolve(None)
    assert name == "only"
    profiles.save_profile("other", {"type": "apikey", "key": "K", "value": "V"})
    profiles.set_default("other")
    assert profiles.resolve(None)[0] == "other"
    assert profiles.resolve("only")[0] == "only"


def test_remove_fixes_default(store):
    profiles.save_profile("a", {"type": "apikey", "key": "K", "value": "V"})
    profiles.save_profile("b", {"type": "apikey", "key": "K", "value": "V"})
    profiles.set_default("a")
    profiles.remove_profile("a")
    assert "a" not in profiles.profile_names()
    assert profiles.get_default() == "b"  # default moved to a survivor


def test_get_missing_profile_raises(store):
    with pytest.raises(AuthError):
        profiles.get_profile("nope")


def test_token_cache_roundtrip(store):
    profiles.set_token_cache("p", {"access_token": "T", "expires_at": 123})
    assert profiles.get_token_cache("p")["access_token"] == "T"
    profiles.clear_token_cache("p")
    assert profiles.get_token_cache("p") is None


# -- add-credential secret hygiene ------------------------------------------

def test_apikey_secrets_are_prompted_when_flags_are_omitted(monkeypatch):
    """A key passed as --key/--value lands in shell history and every process
    listing, which defeats storing it in the credential manager at all. Omitting
    the flag on a TTY must prompt instead of erroring."""
    from tools.procesio.handlers import profile_admin

    monkeypatch.setattr(profile_admin.sys.stdin, "isatty", lambda: True)
    asked = []

    def fake_getpass(prompt):
        asked.append(prompt)
        return {"API key NAME: ": "KN", "API key VALUE: ": "KV"}[prompt]

    monkeypatch.setattr(profile_admin.getpass, "getpass", fake_getpass)
    saved = {}
    monkeypatch.setattr(profile_admin.profiles, "save_profile",
                        lambda n, b: saved.update({"name": n, "blob": b}))
    monkeypatch.setattr(profile_admin.profiles, "get_default", lambda: None)

    args = argparse.Namespace(
        name="p", type="apikey", key=None, value=None, workspace_id=None,
        workspace=None, username=None, password=None, realm=None, client_id=None,
        web_base=None, auth_base=None, make_default=False)
    out = profile_admin.add_credential(args)

    assert asked == ["API key NAME: ", "API key VALUE: "]
    assert saved["blob"]["key"] == "KN" and saved["blob"]["value"] == "KV"
    # The returned view must never carry the secret back out.
    assert "KV" not in json.dumps(out)


def test_omitted_secret_without_a_tty_is_a_usage_error(monkeypatch):
    """CI / tool-to-tool callers still pass the flag; failing loudly beats hanging
    on a getpass prompt nobody can answer."""
    from tools.procesio.handlers import profile_admin

    monkeypatch.setattr(profile_admin.sys.stdin, "isatty", lambda: False)
    args = argparse.Namespace(
        name="p", type="apikey", key=None, value=None, workspace_id=None,
        workspace=None, username=None, password=None, realm=None, client_id=None,
        web_base=None, auth_base=None, make_default=False)
    with pytest.raises(UsageError, match="--key"):
        profile_admin.add_credential(args)
