"""form-code-key per environment: one key per installation, never borrowed.

The platform encrypts a form's Data.code with a key that is the same on every workspace
of an installation and not guaranteed to match on another. A blob written with the
wrong installation's key is one the renderer cannot open, so the form goes blank. These
pin the lookup: the environment's own key first, the legacy bare key only for the
default environment, and otherwise an error that names the secret to store.
"""
from __future__ import annotations

import pytest

from tools.procesio import form_code_keys
from tools.procesio.dto.form import builder as fb
from tools.procesio.dto.form import code_cipher
from tools.procesio.errors import UsageError
from tools.procesio.handlers import form_code


@pytest.fixture
def store(monkeypatch):
    """A fake Credential Manager for the procesio tool, with Internal-PROD as default."""
    secrets: dict[str, str] = {}
    monkeypatch.setattr("tools._lib.creds.get_optional",
                        lambda tool, name: secrets.get(name) if tool == "procesio" else None)
    monkeypatch.setattr("tools.procesio.environments.get_default", lambda: "Internal-PROD")
    known = {"internal-prod": "Internal-PROD", "internal-qa": "Internal-QA"}
    monkeypatch.setattr("tools.procesio.environments.canonical_name",
                        lambda name: known.get(str(name).lower()))
    return secrets


class _Client:
    def __init__(self, env_name):
        self.env = {"name": env_name}


def test_secret_name_carries_the_environment():
    assert form_code_keys.secret_name("Internal-QA") == "form-code-key@Internal-QA"


def test_the_default_environment_still_reads_the_legacy_key(store):
    store["form-code-key"] = "L"
    assert form_code_keys.key_for(None) == "L"
    assert form_code_keys.key_for("Internal-PROD") == "L"
    assert form_code_keys.key_for("internal-prod") == "L"     # names are canonicalised


def test_an_environment_key_wins_over_the_legacy_one(store):
    store["form-code-key"] = "L"
    store["form-code-key@Internal-PROD"] = "P"
    assert form_code_keys.key_for("Internal-PROD") == "P"


def test_another_environment_uses_its_own_key(store):
    store["form-code-key"] = "L"
    store["form-code-key@Internal-QA"] = "Q"
    assert form_code_keys.key_for("Internal-QA") == "Q"


def test_another_environment_never_borrows_the_default_key(store):
    """The one rule that keeps a form from going blank: no silent fallback."""
    store["form-code-key"] = "L"
    with pytest.raises(UsageError) as e:
        form_code_keys.key_for("Internal-QA")
    message = str(e.value)
    assert "set-credential.py procesio form-code-key@Internal-QA" in message
    assert "never used for another installation" in message


def test_form_get_and_set_code_use_the_clients_environment(store):
    store["form-code-key"] = "L"
    store["form-code-key@Internal-QA"] = "Q"
    assert form_code._code_key(_Client("Internal-QA")) == "Q"
    assert form_code._code_key(_Client("Internal-PROD")) == "L"


def test_form_create_encrypts_with_the_environments_key(store):
    store["form-code-key@Internal-QA"] = "Q"
    blob = fb._build_code({"css": "a{color:red}"}, {"form_code_env": "Internal-QA"})
    assert code_cipher.decrypt_code(blob, "Q")["CSS"] == "a{color:red}"


def test_form_create_refuses_to_encrypt_with_another_installations_key(store):
    store["form-code-key"] = "L"
    with pytest.raises(UsageError):
        fb._build_code({"css": "a{}"}, {"form_code_env": "Internal-QA"})


def test_the_form_context_records_the_environment():
    ctx = fb._prepare_ctx(_Client("Internal-QA"), {"name": "F", "elements": []})
    assert ctx == {"form_code_env": "Internal-QA"}
