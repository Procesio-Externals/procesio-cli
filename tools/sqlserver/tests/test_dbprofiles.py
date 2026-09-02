"""Tests for the shared ProfileStore (tools/_lib/dbprofiles.py). No real
Credential Manager: creds.has/get_optional are stubbed via a dict."""
from __future__ import annotations

import json

import pytest

from tools._lib import dbprofiles
from tools._lib.dbprofiles import AuthRequiredError, ProfileError, ProfileStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A ProfileStore backed by a tmp file and an in-memory credential map."""
    vault: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(dbprofiles.creds, "has",
                        lambda tool, name: (tool, name) in vault)
    monkeypatch.setattr(dbprofiles.creds, "get_optional",
                        lambda tool, name: vault.get((tool, name)))
    s = ProfileStore("sqlserver", tmp_path / "profiles.json")
    s._vault = vault            # tests can poke a password in
    return s


def test_empty_store_lists_nothing(store):
    assert store.names() == []
    assert store.list_public() == []


def test_add_and_get_profile(store):
    view = store.add("default", {"server": "h", "database": "d", "username": "u"})
    assert view["name"] == "default"
    assert view["server"] == "h"
    assert view["has_password"] is False
    assert store.names() == ["default"]
    blob = store.get("default")
    assert blob["database"] == "d"


def test_add_strips_password_field(store):
    store.add("p", {"server": "h", "database": "d", "password": "LEAK", "pwd": "LEAK2"})
    raw = json.loads((store.path).read_text(encoding="utf-8"))
    assert "password" not in raw["p"]
    assert "pwd" not in raw["p"]
    assert "LEAK" not in json.dumps(raw)


def test_add_duplicate_without_overwrite_raises(store):
    store.add("default", {"server": "h", "database": "d"})
    with pytest.raises(ProfileError):
        store.add("default", {"server": "h2", "database": "d2"})


def test_add_overwrite_replaces(store):
    store.add("default", {"server": "h", "database": "d"})
    store.add("default", {"server": "h2", "database": "d2"}, overwrite=True)
    assert store.get("default")["server"] == "h2"


def test_get_unknown_raises(store):
    with pytest.raises(ProfileError):
        store.get("ghost")


def test_remove_profile(store):
    store.add("a", {"server": "h", "database": "d"})
    store.remove("a")
    assert store.names() == []
    with pytest.raises(ProfileError):
        store.remove("a")


def test_password_missing_raises_auth_required(store):
    store.add("default", {"server": "h", "database": "d"})
    with pytest.raises(AuthRequiredError):
        store.password("default")


def test_password_present_is_returned(store):
    store.add("default", {"server": "h", "database": "d"})
    store._vault[("sqlserver", "default")] = "s3cr3t"
    assert store.password("default") == "s3cr3t"
    assert store.public_view("default")["has_password"] is True


def test_public_view_never_contains_password(store):
    store.add("default", {"server": "h", "database": "d"})
    store._vault[("sqlserver", "default")] = "s3cr3t"
    view = store.public_view("default")
    assert "s3cr3t" not in json.dumps(view)
    assert "password" not in view
