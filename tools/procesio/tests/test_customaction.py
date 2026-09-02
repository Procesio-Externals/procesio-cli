"""customaction sub-tool: upload (.nupkg multipart), delete, list."""
from __future__ import annotations

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
NUPKG = b"PK\x03\x04 fake nupkg bytes"


def _builder(session):
    return lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session)


def test_upload_posts_nupkg_as_multipart_package(tmp_path):
    pkg = tmp_path / "MyConnector.1.0.0.nupkg"
    pkg.write_bytes(NUPKG)
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEWID"})])
    out = main.dispatch("customaction-upload", ["--workspace-id", "WS1", "--file", str(pkg)],
                        client_builder=_builder(sess))
    call = sess.calls[0]
    assert call["method"] == "POST" and call["url"].endswith("/api/actions")
    assert call["headers"]["workspaceid"] == "WS1"
    assert "Content-Type" not in call["headers"]          # requests writes the multipart boundary
    field = call["files"]["package"]
    assert field == ("MyConnector.1.0.0.nupkg", NUPKG, "application/x-compressed")
    # The backend takes the designer display name off the `name` header, so an
    # upload with no --action-name still has to carry one (the package stem).
    assert call["headers"]["name"] == "MyConnector.1.0.0"
    assert out == {"uploaded": True, "id": "NEWID",
                   "name": "MyConnector.1.0.0.nupkg",
                   "actionName": "MyConnector.1.0.0", "bytes": len(NUPKG)}


def test_upload_action_name_sets_display_name_header(tmp_path):
    pkg = tmp_path / "MyConnector.1.0.0.nupkg"
    pkg.write_bytes(NUPKG)
    sess = FakeSession(queue=[FakeResp(200, {"id": "X"})])
    main.dispatch("customaction-upload",
                  ["--workspace-id", "WS1", "--file", str(pkg),
                   "--action-name", "Prelude", "--icon-path", "icons/prelude.svg"],
                  client_builder=_builder(sess))
    assert sess.calls[0]["headers"]["name"] == "Prelude"
    assert sess.calls[0]["headers"]["path"] == "icons/prelude.svg"


def test_upload_name_override(tmp_path):
    pkg = tmp_path / "raw.nupkg"
    pkg.write_bytes(NUPKG)
    sess = FakeSession(queue=[FakeResp(200, {"id": "X"})])
    main.dispatch("customaction-upload",
                  ["--workspace-id", "WS1", "--file", str(pkg), "--name", "Pretty.1.0.0.nupkg"],
                  client_builder=_builder(sess))
    assert sess.calls[0]["files"]["package"][0] == "Pretty.1.0.0.nupkg"


def test_upload_missing_file_is_usage_error():
    sess = FakeSession()
    with pytest.raises(errors.UsageError):
        main.dispatch("customaction-upload", ["--workspace-id", "WS1", "--file", "/no/such.nupkg"],
                      client_builder=_builder(sess))


def test_delete_calls_delete_endpoint():
    sess = FakeSession(queue=[FakeResp(200, {})])
    out = main.dispatch("customaction-delete", ["--workspace-id", "WS1", "--id", "AID"],
                        client_builder=_builder(sess))
    assert sess.calls[0]["method"] == "DELETE"
    assert sess.calls[0]["url"].endswith("/api/actions/AID")
    assert out == {"deleted": True, "id": "AID"}


def test_list_custom_only_uses_iscustom_filter():
    sess = FakeSession(queue=[FakeResp(200, {"actions": [
        {"actionId": "A1", "name": "My CA", "description": "d",
         "inputPorts": 1, "outputPorts": 1, "isProcesioAction": False}]})])
    out = main.dispatch("customaction-list", ["--workspace-id", "WS1"],
                        client_builder=_builder(sess))
    call = sess.calls[0]
    assert call["url"].endswith("/api/Actions/node")
    assert call["params"] == {"getFullAction": "true", "isCustom": "true"}
    assert out["count"] == 1
    assert out["actions"][0] == {"actionId": "A1", "name": "My CA", "description": "d",
                                 "inputPorts": 1, "outputPorts": 1, "isCustom": True}


def test_list_all_uses_full_catalog():
    sess = FakeSession(queue=[FakeResp(200, {"actions": [
        {"actionId": "X", "name": "builtin", "isProcesioAction": True}]})])
    out = main.dispatch("customaction-list", ["--workspace-id", "WS1", "--all"],
                        client_builder=_builder(sess))
    assert sess.calls[0]["url"].endswith("/api/Actions")
    assert out["count"] == 1 and out["actions"][0]["isCustom"] is False
