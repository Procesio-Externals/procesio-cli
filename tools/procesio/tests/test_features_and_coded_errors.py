"""Optional-module flags (GET /api/Features) and PROCESIO's coded error list.

The Web API answers its own refusals as a JSON list `[{"statusCode", "value", "target"}]`;
the client wraps a non-dict body as {"body": [...]}. Before this was read, every such
refusal (a disabled feature, a signing spot error, an invalid crontab) surfaced as a bare
"HTTP 400". 1013 FEATURE_DISABLED gets its own error code because no argument fixes it.
"""
from __future__ import annotations

from types import SimpleNamespace

from tools.procesio import errors
from tools.procesio.handlers import auth_actions


def _api_error(status, items):
    return errors.ProcesioAPIError(status, f"HTTP {status}", {"body": items})


def test_coded_list_body_surfaces_value_code_and_target():
    err = _api_error(400, [{"statusCode": 715, "value": "The signature is off the page.",
                            "target": "signatureSpot"}])
    code, msg, details, exit_code = errors.classify(err)
    assert code == "invalid_argument"
    assert msg == "The signature is off the page. (code 715) [signatureSpot]"
    assert details["procesio_codes"] == [715]
    assert exit_code == 2


def test_feature_disabled_gets_its_own_code_and_hint():
    err = _api_error(400, [{"statusCode": 1013,
                            "value": "This feature is disabled on this environment.",
                            "target": "DataStore"}])
    code, msg, details, exit_code = errors.classify(err)
    assert code == "feature_disabled"
    assert "disabled on this environment" in msg and "[DataStore]" in msg
    assert details["features_disabled"] == ["DataStore"]
    assert "procesio features" in details["hint"]
    assert exit_code == 1


def test_several_items_are_joined_and_a_missing_target_is_omitted():
    err = _api_error(400, [{"statusCode": 502, "value": "Invalid request", "target": None},
                           {"statusCode": 714, "value": "Signer invalid", "target": "parties"}])
    _, msg, details, _ = errors.classify(err)
    assert msg == "Invalid request (code 502); Signer invalid (code 714) [parties]"
    assert details["procesio_codes"] == [502, 714]


def test_dict_bodies_are_unchanged():
    err = errors.ProcesioAPIError(400, "HTTP 400", {"message": "plain"})
    code, msg, details, _ = errors.classify(err)
    assert (code, msg) == ("invalid_argument", "plain")
    assert "procesio_codes" not in details


class _Client:
    def __init__(self, body):
        self.body = body
        self.env = {"name": "Client-PROD"}
        self.paths = []

    def get(self, path, *a, **k):
        self.paths.append(path)
        return self.body


def test_features_reports_disabled_modules_with_their_scope():
    c = _Client({"customActions": True, "dataStore": False, "forms": True,
                 "executionEnvironment": False})
    out = auth_actions.features(c, SimpleNamespace())
    assert c.paths == ["/api/Features"]
    assert out["environment"] == "Client-PROD"
    assert out["disabled"] == ["dataStore", "executionEnvironment"]
    assert set(out["disabled_scope"]) == {"dataStore", "executionEnvironment"}
    assert "Query Store" in out["disabled_scope"]["dataStore"]
    assert out["all_enabled"] is False


def test_features_all_on():
    c = _Client({"customActions": True, "dataStore": True, "forms": True,
                 "executionEnvironment": True})
    out = auth_actions.features(c, SimpleNamespace())
    assert out["disabled"] == [] and out["all_enabled"] is True


def test_every_api_flag_has_a_scope_line():
    # the four flags FeaturesDto carries (Web-Api v3.1.0)
    assert set(auth_actions.FEATURE_SCOPE) == {"customActions", "dataStore", "forms",
                                               "executionEnvironment"}
