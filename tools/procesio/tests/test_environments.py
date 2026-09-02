"""Environments: registry, default switching, credential binding, URL resolution.

The autouse _isolate_userdata fixture (conftest) pins the registry to a temp dir,
so every test starts from the built-in presets with the default = Internal-PROD.
"""
from __future__ import annotations

import argparse

import pytest

from tools.procesio import config, environments as E
from tools.procesio.client import ProcesioClient
from tools.procesio.errors import UsageError
from tools.procesio.handlers import environment_admin as EA
from tools.procesio.tests.conftest import FakeResp, FakeSession


# -- built-ins & defaults ---------------------------------------------------

def test_builtin_presets_present():
    names = set(E.all_environments())
    assert {"Internal-PROD", "Internal-QA", "Internal-DEV"} <= names


def test_default_is_prod_on_fresh_registry():
    assert E.get_default() == "Internal-PROD"


def test_prod_urls_match_historical_defaults():
    prod = E.get("Internal-PROD")
    assert prod["web_base"] == config.DEFAULT_WEB_BASE
    assert prod["app_base"] == config.DEFAULT_APP_BASE
    assert prod["forms_base"] == config.DEFAULT_FORMS_BASE


@pytest.mark.parametrize("name,web,app,forms", [
    ("Internal-QA", "https://webapi-qa.procesio.app",
     "https://qa.procesio.app", "https://forms-qa.procesio.app"),
    ("Internal-DEV", "https://webapi-dev.procesio.app",
     "https://dev.procesio.app", "https://forms-dev.procesio.app"),
])
def test_qa_dev_urls(name, web, app, forms):
    env = E.get(name)
    assert env["web_base"] == web
    assert env["app_base"] == app
    assert env["forms_base"] == forms


# -- resolution precedence --------------------------------------------------

def test_resolve_unbound_is_prod():
    assert E.resolve(None, {"type": "apikey"})["name"] == "Internal-PROD"


def test_resolve_uses_credential_binding():
    assert E.resolve(None, {"environment": "Internal-DEV"})["name"] == "Internal-DEV"


def test_explicit_name_beats_binding():
    got = E.resolve("Internal-QA", {"environment": "Internal-DEV"})
    assert got["name"] == "Internal-QA"


def test_default_pointer_beats_prod_fallback():
    E.set_default("Internal-QA")
    assert E.resolve(None, {"type": "apikey"})["name"] == "Internal-QA"


def test_case_insensitive_lookup():
    assert E.canonical_name("internal-qa") == "Internal-QA"
    assert E.resolve("INTERNAL-DEV", None)["name"] == "Internal-DEV"


def test_unknown_environment_raises():
    with pytest.raises(UsageError):
        E.get("Nope-PROD")


# -- add / set / remove -----------------------------------------------------

def test_add_client_environment_and_switch():
    entry = E.add("Delgaz-PROD", web_base="https://webapi.delgaz.example",
                  app_base="https://delgaz.example",
                  forms_base="https://forms.delgaz.example")
    assert entry["client"] == "Delgaz" and entry["env"] == "PROD"
    assert entry["builtin"] is False
    E.set_default("Delgaz-PROD")
    assert E.get_default() == "Delgaz-PROD"
    assert E.resolve(None, None)["web_base"] == "https://webapi.delgaz.example"


def test_add_trailing_slash_stripped():
    entry = E.add("X-PROD", web_base="https://a/", app_base="https://b/",
                  forms_base="https://c/")
    assert entry["web_base"] == "https://a"
    assert entry["app_base"] == "https://b"


def test_add_requires_all_three_urls():
    with pytest.raises(UsageError):
        E.add("Y-PROD", web_base="https://a", app_base="", forms_base="https://c")


def test_add_rejects_bad_name():
    with pytest.raises(UsageError):
        E.add("has space", web_base="https://a", app_base="https://b",
              forms_base="https://c")


def test_user_entry_overrides_builtin_url():
    E.add("Internal-QA", web_base="https://moved-qa.example",
          app_base="https://qa.moved.example",
          forms_base="https://forms.moved.example")
    assert E.get("Internal-QA")["web_base"] == "https://moved-qa.example"
    # still flagged builtin (name is a built-in) but URL is the override
    assert E.get("Internal-QA")["builtin"] is True


def test_remove_builtin_blocked():
    with pytest.raises(UsageError):
        E.remove("Internal-DEV")


def test_remove_user_env_resets_default():
    E.add("Z-PROD", web_base="https://a", app_base="https://b", forms_base="https://c",
          make_default=True)
    assert E.get_default() == "Z-PROD"
    E.remove("Z-PROD")
    assert E.get_default() == "Internal-PROD"  # falls back


def test_set_unknown_default_raises():
    with pytest.raises(UsageError):
        E.set_default("Ghost-PROD")


# -- handler surface --------------------------------------------------------

def test_set_environment_handler_reports_credentials(store):
    from tools.procesio import profiles
    profiles.save_profile("qa-key", {"type": "apikey", "key": "N", "value": "V",
                                     "environment": "Internal-QA"})
    out = EA.set_environment(argparse.Namespace(name="Internal-QA"))
    assert out["default_environment"] == "Internal-QA"
    assert out["credentials"] == ["qa-key"]


def test_list_environments_marks_default_and_creds(store):
    from tools.procesio import profiles
    profiles.save_profile("dev-key", {"type": "apikey", "key": "N", "value": "V",
                                      "environment": "Internal-DEV"})
    out = EA.list_environments(argparse.Namespace())
    by_name = {e["name"]: e for e in out["environments"]}
    assert by_name["Internal-PROD"]["is_default"] is True
    assert by_name["Internal-DEV"]["credentials"] == ["dev-key"]


# -- client URL injection ---------------------------------------------------

def _run(profile, session, environment=None):
    c = ProcesioClient(profile=profile, name="t", session=session,
                       environment=environment)
    c.get("/api/Workspaces")
    return c, session.calls[0]


def test_client_injects_bound_environment_url():
    sess = FakeSession(queue=[FakeResp(200, {})])
    _, call = _run({"type": "apikey", "key": "N", "value": "V",
                    "environment": "Internal-QA"}, sess)
    assert call["url"] == "https://webapi-qa.procesio.app/api/Workspaces"


def test_client_explicit_environment_overrides_binding():
    sess = FakeSession(queue=[FakeResp(200, {})])
    _, call = _run({"type": "apikey", "key": "N", "value": "V",
                    "environment": "Internal-QA"}, sess, environment="Internal-DEV")
    assert call["url"] == "https://webapi-dev.procesio.app/api/Workspaces"


def test_client_unbound_is_prod():
    sess = FakeSession(queue=[FakeResp(200, {})])
    _, call = _run({"type": "apikey", "key": "N", "value": "V"}, sess)
    assert call["url"] == "https://webapi.procesio.app/api/Workspaces"


def test_explicit_profile_url_override_beats_environment():
    sess = FakeSession(queue=[FakeResp(200, {})])
    _, call = _run({"type": "apikey", "key": "N", "value": "V",
                    "environment": "Internal-QA",
                    "web_base": "https://custom.example"}, sess)
    assert call["url"] == "https://custom.example/api/Workspaces"


def test_client_does_not_mutate_caller_profile():
    sess = FakeSession(queue=[FakeResp(200, {})])
    original = {"type": "apikey", "key": "N", "value": "V",
                "environment": "Internal-QA"}
    ProcesioClient(profile=original, name="t", session=sess)
    assert "web_base" not in original  # injection copied, never mutated the input


def test_userpass_login_origin_is_environment_app_host(store):
    # `store` isolates the token cache to in-memory creds, so login actually runs.
    login_resp = FakeResp(200, {"message": "ok"},
                          cookies={"__Host-procesio.access": "a.b.c"},
                          headers={"x-session-expires-at": "9999999999"})
    sess = FakeSession(queue=[login_resp, FakeResp(200, {})])
    _run({"type": "userpass", "username": "u", "password": "p",
          "environment": "Internal-QA"}, sess)
    login = sess.calls[0]
    assert login["url"] == "https://webapi-qa.procesio.app/api/authentication"
    assert login["headers"]["Origin"] == "https://qa.procesio.app"
