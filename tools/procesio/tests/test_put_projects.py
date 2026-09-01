"""put-projects: empty-body echo hardening (O4) — warns that an empty success can lie."""
from __future__ import annotations

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(session):
    return lambda prof: ProcesioClient(
        profile={"type": "apikey", "key": "N", "value": "V"}, name="t", session=session)


def test_empty_body_put_warns_and_reports_meta():
    # 200 with an empty body -> _parse_body yields {"raw_text": ""} (the O4 shape).
    sess = FakeSession(queue=[FakeResp(200, None, text="")])
    out = main.dispatch("put-projects", ["--body", '{"id": "X", "name": "n"}'],
                        client_builder=_builder(sess))
    assert "warning" in out
    assert "empty" in out["warning"].lower() and "verify" in out["warning"].lower()
    assert out["http"]["status"] == 200
    assert out["http"]["body_len"] == 0


def test_non_empty_body_put_has_no_warning():
    body_text = '{"id": "X"}'
    sess = FakeSession(queue=[FakeResp(200, {"id": "X"}, text=body_text)])
    out = main.dispatch("put-projects", ["--body", '{"id": "X"}'],
                        client_builder=_builder(sess))
    assert "warning" not in out
    assert out["http"]["status"] == 200
    assert out["http"]["body_len"] == len(body_text)


def test_put_projects_dry_run_composes_without_sending():
    sess = FakeSession()
    out = main.dispatch("put-projects", ["--body", '{"id": "X"}', "--dry-run"],
                        client_builder=_builder(sess))
    assert out["dry_run"] is True
    assert out["method"] == "PUT" and out["path"] == "/api/Projects"
    assert sess.calls == []
