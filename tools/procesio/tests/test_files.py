"""file-download action: header-based GET /api/File/download, --from-run derivation."""
from __future__ import annotations

import json

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
PDF = b"%PDF-1.4 fake brief bytes"


def _builder(session):
    return lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session)


def test_file_download_sets_headers_and_writes_file(tmp_path):
    sess = FakeSession(queue=[FakeResp(200, content=PDF, headers={
        "content-type": "application/pdf",
        "content-disposition": 'attachment; filename="brief.pdf"'})])
    out = main.dispatch("file-download", [
        "--workspace-id", "WS1",
        "--file-path", "flow/flow-F/flow-instance-I/variable-V/FID",
        "--variable-id", "V1", "--instance-id", "I1", "--flow-template-id", "FT1",
        "--out", str(tmp_path)], client_builder=_builder(sess))
    call = sess.calls[0]
    assert call["method"] == "GET" and call["url"].endswith("/api/File/download")
    assert call["params"] == {"isArchived": "false"}
    h = call["headers"]
    assert h["uploadFilePath"] == "flow/flow-F/flow-instance-I/variable-V/FID"
    assert h["variableId"] == "V1" and h["instanceId"] == "I1"
    assert h["flowTemplateId"] == "FT1" and h["workspaceId"] == "WS1"
    assert out == {"downloaded": True, "path": str(tmp_path / "brief.pdf"),
                   "size": len(PDF), "mimeType": "application/pdf", "name": "brief.pdf"}
    assert (tmp_path / "brief.pdf").read_bytes() == PDF


def test_file_download_from_run_derives_ids(tmp_path):
    run = tmp_path / "run.json"
    run.write_text(json.dumps({"result": {"instanceId": "INST", "variable": {"briefPdf": {
        "name": "b.pdf", "size": "5",
        "path": "flow/flow-11111111-1111-1111-1111-111111111111/"
                "flow-instance-22222222-2222-2222-2222-222222222222/"
                "variable-33333333-3333-3333-3333-333333333333/FID"}}}}), encoding="utf-8")
    sess = FakeSession(queue=[FakeResp(200, content=PDF, headers={"content-type": "application/pdf"})])
    out = main.dispatch("file-download", [
        "--workspace-id", "WS1", "--from-run", str(run), "--out", str(tmp_path / "x.pdf")],
        client_builder=_builder(sess))
    h = sess.calls[0]["headers"]
    assert h["flowTemplateId"] == "11111111-1111-1111-1111-111111111111"
    assert h["instanceId"] == "INST"                                      # result.instanceId wins
    assert h["variableId"] == "33333333-3333-3333-3333-333333333333"
    assert out["downloaded"] is True and out["path"] == str(tmp_path / "x.pdf")


def test_file_download_missing_ids_is_usage_error():
    sess = FakeSession()
    with pytest.raises(errors.UsageError):
        main.dispatch("file-download", ["--workspace-id", "WS1", "--file-path", "p"],
                      client_builder=_builder(sess))


def test_file_download_http_error_raises(tmp_path):
    sess = FakeSession(queue=[FakeResp(400, content=b'"Object reference not set"')])
    with pytest.raises(errors.ProcesioAPIError):
        main.dispatch("file-download", [
            "--workspace-id", "WS1", "--file-path", "p", "--variable-id", "V",
            "--instance-id", "I", "--flow-template-id", "F", "--out", str(tmp_path)],
            client_builder=_builder(sess))
