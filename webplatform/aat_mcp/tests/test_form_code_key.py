"""The passphrase of a form's code reaches the procesio tool of a turn.

A form's CSS and JavaScript are encrypted with a passphrase that belongs to the installation.
No credential of a user carries it, and a tool of a turn inherits nothing from the container,
so the bridge is the only place that can hand it over. These tests hold three things: the tool
gets it when the deployment has one, nothing is added when it has none, and the tool resolves
what the bridge wrote.
"""
import json

import pytest

import bridge
import turn_credentials

PASSPHRASE = "installation-passphrase"


class _Manifest:
    name = "procesio"


def _profile_secrets(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(bridge._FORM_CODE_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(bridge._FORM_CODE_KEY_ENV, value)
    secrets: dict = {}
    key = turn_credentials.ProcesioKey(key="k", value="v", workspace_id="ws-1")
    bridge._procesio_profile(_Manifest(), key, secrets)
    return secrets


def test_the_tool_gets_the_passphrase_beside_its_profile(monkeypatch):
    secrets = _profile_secrets(monkeypatch, PASSPHRASE)
    assert set(secrets) == {"procesio"}
    assert secrets["procesio"]["form-code-key"] == PASSPHRASE
    assert secrets["procesio"]["default-profile"] == "platform"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_a_deployment_without_the_passphrase_adds_nothing(monkeypatch, value):
    secrets = _profile_secrets(monkeypatch, value)
    assert "form-code-key" not in secrets["procesio"]


def test_surrounding_whitespace_is_not_part_of_the_passphrase(monkeypatch):
    """A secret store often adds a line end. One stray character makes a blob the web app
    cannot open, and the form then shows blank with no error."""
    secrets = _profile_secrets(monkeypatch, f"  {PASSPHRASE}\n")
    assert secrets["procesio"]["form-code-key"] == PASSPHRASE


def test_a_turn_carries_it_to_the_procesio_tool(monkeypatch):
    monkeypatch.setenv(bridge._FORM_CODE_KEY_ENV, PASSPHRASE)
    key = turn_credentials.ProcesioKey(key="k", value="v", workspace_id="ws-1")
    monkeypatch.setattr(bridge.turn_credentials, "fetch_key", lambda token: key)
    env = bridge._turn_env("tool", "procesio", "turn-token")
    assert env["AAT_CREDS_BACKEND"] == "env"
    assert json.loads(env["AAT_SECRETS_JSON"])["procesio"]["form-code-key"] == PASSPHRASE


def test_the_tool_resolves_what_the_bridge_wrote(monkeypatch, tmp_path):
    """The bridge writes the bare name. The tool reads that name for its default environment
    only, and a turn runs on the default one, so the two have to agree."""
    from tools._lib import creds
    from tools.procesio import form_code_keys

    secrets = _profile_secrets(monkeypatch, PASSPHRASE)
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path))
    monkeypatch.setenv("AAT_CREDS_BACKEND", "env")
    monkeypatch.setenv("AAT_SECRETS_JSON", json.dumps(secrets))
    creds.reset_backend()
    try:
        assert form_code_keys.key_for(None) == PASSPHRASE
    finally:
        creds.reset_backend()
