"""PROCESIO polish: --workspace-id override, list-subworkspaces filter, export."""
from __future__ import annotations

import json

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


APIKEY = {"type": "apikey", "key": "N", "value": "V"}


# -- --workspace-id override -------------------------------------------------

def test_workspace_id_override_sets_header():
    sess = FakeSession(queue=[FakeResp(200, [])])
    main.dispatch("list-workspaces", ["--workspace-id", "WS-123"],
                  client_builder=_builder(APIKEY, sess))
    assert sess.calls[0]["headers"]["workspaceid"] == "WS-123"


def test_workspace_id_overrides_profile_workspace():
    sess = FakeSession(queue=[FakeResp(200, [])])
    prof = {"type": "apikey", "key": "N", "value": "V", "workspace_id": "PROFILE-WS"}
    main.dispatch("list-workspaces", ["--workspace-id", "CALL-WS"],
                  client_builder=_builder(prof, sess))
    assert sess.calls[0]["headers"]["workspaceid"] == "CALL-WS"   # call wins


# -- list-subworkspaces active-only filter -----------------------------------

_MIXED = {"pageItems": [
    {"workspace": "Active A", "id": "a", "workspaceState": "active"},
    {"workspace": "Removed B", "id": "b", "workspaceState": "removed"},
    {"workspace": "Active C", "id": "c", "workspaceState": "active"},
]}


def test_list_subworkspaces_hides_removed_by_default():
    sess = FakeSession(queue=[FakeResp(200, _MIXED)])
    out = main.dispatch("list-subworkspaces", ["--parent-id", "RING"],
                        client_builder=_builder(APIKEY, sess))
    assert out["count"] == 2
    assert {w["id"] for w in out["workspaces"]} == {"a", "c"}


def test_list_subworkspaces_include_removed():
    sess = FakeSession(queue=[FakeResp(200, _MIXED)])
    out = main.dispatch("list-subworkspaces", ["--parent-id", "RING", "--include-removed"],
                        client_builder=_builder(APIKEY, sess))
    assert out["count"] == 3


# -- export ------------------------------------------------------------------

def _export_responder(export_bytes=None):
    """Serves list endpoints for name resolution + the export POST."""
    lists = {
        "/api/DataTypes": [{"name": "lazarusDM", "id": "DM1"}],
        "/api/Projects": [{"title": "Lazarus Data process", "id": "P1"},
                          {"title": "Import excel products to pdf", "id": "P2"}],
        "/api/DocumentTemplate": [{"name": "products from Excel", "id": "DOC1"}],
        "/api/Webhooks": [], "/api/FormTemplate": [], "/api/Credentials": [],
    }

    def responder(method, url, kw):
        if url.endswith("/api/Transport/export-entities"):
            return FakeResp(200, content=export_bytes or b"{}")
        for path, rows in lists.items():
            if url.endswith(path):
                return FakeResp(200, {"pageItems": rows})
        return FakeResp(200, {"pageItems": []})
    return responder


def test_export_dry_run_resolves_names_excludes_credentials():
    sess = FakeSession(responder=_export_responder())
    out = main.dispatch(
        "export",
        ["--workspace-id", "WS", "--data-models", "lazarusDM",
         "--processes", "Lazarus Data process,Import excel products to pdf",
         "--documents", "all", "--dry-run"],
        client_builder=_builder(APIKEY, sess),
    )
    assert out["dry_run"] is True
    b = out["body"]
    assert b["dataModelIds"] == ["DM1"]
    assert b["flowIds"] == ["P1", "P2"]
    assert b["documentIds"] == ["DOC1"]
    assert b["credentialIds"] == []          # excluded by default
    assert b["exportSensitiveData"] is False


def test_export_requires_workspace_scope():
    sess = FakeSession(responder=_export_responder())
    with pytest.raises(errors.UsageError):
        main.dispatch("export", ["--data-models", "lazarusDM"],
                      client_builder=_builder(APIKEY, sess))


def test_export_nothing_selected_errors():
    sess = FakeSession(responder=_export_responder())
    with pytest.raises(errors.UsageError):
        main.dispatch("export", ["--workspace-id", "WS"],
                      client_builder=_builder(APIKEY, sess))


def test_export_unresolvable_name_errors():
    sess = FakeSession(responder=_export_responder())
    with pytest.raises(errors.UsageError):
        main.dispatch("export", ["--workspace-id", "WS", "--processes", "Nope"],
                      client_builder=_builder(APIKEY, sess))


def test_export_saves_file(tmp_path):
    bundle = json.dumps({"DataTypes": [{}], "Flows": [{}, {}], "DocumentTemplates": [{}],
                         "Credentials": [], "Webhooks": [], "Forms": []}).encode()
    sess = FakeSession(responder=_export_responder(export_bytes=bundle))
    out_path = str(tmp_path / "exp.procesio")
    out = main.dispatch(
        "export",
        ["--workspace-id", "WS", "--data-models", "lazarusDM",
         "--processes", "Lazarus Data process", "--documents", "all", "--output", out_path],
        client_builder=_builder(APIKEY, sess),
    )
    assert out["saved"] == out_path
    assert out["bytes"] == len(bundle)
    # DataStores joined the summary when data stores became selectable. It is
    # counted even at zero: a caller cannot otherwise tell a pack that carries
    # no store from one where the store was never requested, and reading the
    # second as the first is exactly the mistake that made this change
    # necessary.
    assert out["sections"] == {"DataTypes": 1, "Flows": 2, "DocumentTemplates": 1,
                               "Credentials": 0, "Webhooks": 0, "Forms": 0,
                               "DataStores": 0}
    with open(out_path, "rb") as f:
        assert f.read() == bundle
    # the export POST carried the built selection body
    post = [c for c in sess.calls if c["url"].endswith("/Transport/export-entities")][0]
    assert post["json"]["flowIds"] == ["P1"]
