"""End-to-end dispatch: action routing, generic request, curated actions,
list-endpoints (bundled data), profile admin, error classification."""
from __future__ import annotations

import pytest

from tools.procesio import errors, main, profiles, swagger
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


# -- routing ----------------------------------------------------------------

def test_unknown_action_raises_usage():
    with pytest.raises(errors.UsageError):
        main.dispatch("nope", [])


def test_all_actions_have_manifest_descriptions():
    assert len(main.ACTIONS) >= 20
    assert all(d.description for d in main.ACTIONS.values())


# -- generic request --------------------------------------------------------

def test_request_action_passthrough():
    sess = FakeSession(queue=[FakeResp(200, {"hello": "world"})])
    out = main.dispatch(
        "request",
        ["--method", "GET", "--path", "/api/Workspaces"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    assert out["result"] == {"hello": "world"}
    assert sess.calls[0]["url"].endswith("/api/Workspaces")


def test_request_unmangles_shell_mangled_path(capsys):
    # Git Bash rewrites '/api/FormTemplate/F1' into a Windows filesystem path;
    # the request action must recover the intended '/api/...' tail and warn.
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    mangled = "/C:/Program Files/Git/api/FormTemplate/F1"
    out = main.dispatch(
        "request", ["--method", "GET", "--path", mangled],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    assert out["result"] == {"ok": True}
    assert out["path"] == "/api/FormTemplate/F1"
    assert sess.calls[0]["url"].endswith("/api/FormTemplate/F1")
    assert "C:" not in sess.calls[0]["url"]
    assert "shell-mangled" in capsys.readouterr().err     # warning went to stderr


def test_request_collapses_double_slash_workaround():
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    out = main.dispatch(
        "request", ["--method", "GET", "--path", "//api/Workspaces"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    assert out["path"] == "/api/Workspaces"
    assert sess.calls[0]["url"].endswith("/api/Workspaces")


def test_request_leaves_clean_path_untouched(capsys):
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    main.dispatch(
        "request", ["--method", "GET", "--path", "/api/Workspaces"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    assert sess.calls[0]["url"].endswith("/api/Workspaces")
    assert capsys.readouterr().err == ""                  # no false-positive warning


def test_request_rejects_bad_method():
    with pytest.raises(errors.UsageError):
        main.dispatch(
            "request", ["--path", "/api/X", "--method", "FETCH"],
            client_builder=_builder({"type": "apikey", "key": "N", "value": "V"},
                                    FakeSession()),
        )


def test_request_rejects_bad_json_body():
    with pytest.raises(errors.UsageError):
        main.dispatch(
            "request", ["--path", "/api/X", "--method", "POST", "--body", "{bad"],
            client_builder=_builder({"type": "apikey", "key": "N", "value": "V"},
                                    FakeSession()),
        )


# -- list-endpoints (bundled, no client) ------------------------------------

def test_list_endpoints_tags_only():
    out = main.dispatch("list-endpoints", ["--tags-only"])
    tags = {t["tag"] for t in out["tags"]}
    assert "ProcessTemplate" in tags and "Workspace" in tags
    assert out["meta"]["count"] == len(swagger.all_endpoints())


def test_list_endpoints_filter():
    out = main.dispatch("list-endpoints", ["--tag", "ProcessInstance", "--filter", "run"])
    assert any(e["path"] == "/api/Projects/{id}/run" for e in out["endpoints"])


# -- curated: run-process dry-run -------------------------------------------

def test_run_process_dry_run_builds_body():
    out = main.dispatch(
        "run-process",
        ["--id", "PID", "--payload", '{"a":1}', "--synchronous", "--dry-run"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"},
                                FakeSession()),
    )
    assert out["dry_run"] is True
    assert out["path"] == "/api/Projects/PID/run"
    assert out["body"] == {"payload": {"a": 1}, "connectionid": None}
    assert out["query"]["runSynchronous"] == "true"


def test_list_processes_maps_paging():
    sess = FakeSession(queue=[FakeResp(200, [])])
    main.dispatch(
        "list-processes", ["--page", "2", "--page-size", "50", "--search", "inv"],
        client_builder=_builder({"type": "apikey", "key": "N", "value": "V"}, sess),
    )
    assert sess.calls[0]["params"] == {"pageNumber": 2, "pageItemCount": 50,
                                       "searchName": "inv"}


# -- profile admin (no client) ----------------------------------------------

def test_add_and_list_credentials(store):
    main.dispatch("add-credential",
                  ["--name", "wsA", "--type", "apikey", "--key", "K", "--value", "S",
                   "--workspace-id", "G", "--workspace", "A"])
    out = main.dispatch("list-credentials", [])
    assert out["count"] == 1
    prof = out["profiles"][0]
    assert prof["name"] == "wsA" and prof["type"] == "apikey"
    assert "value" not in prof and prof["has_value"] is True
    assert prof["is_default"] is True


def test_add_userpass_requires_fields(store):
    with pytest.raises(errors.UsageError):
        main.dispatch("add-credential", ["--name", "x", "--type", "userpass"])


def test_set_default_and_remove(store):
    main.dispatch("add-credential",
                  ["--name", "a", "--type", "apikey", "--key", "K", "--value", "S"])
    main.dispatch("add-credential",
                  ["--name", "b", "--type", "apikey", "--key", "K", "--value", "S"])
    main.dispatch("set-default", ["--name", "b"])
    assert profiles.get_default() == "b"
    out = main.dispatch("remove-credential", ["--name", "b"])
    assert out["default"] == "a"


# -- error classification ---------------------------------------------------

def test_classify_api_error_maps_407():
    err = errors.ProcesioAPIError(407, "HTTP 407", {"message": "proxy"})
    code, msg, details, exit_code = errors.classify(err)
    assert code == "proxy_auth_failed"
    assert details["status"] == 407
