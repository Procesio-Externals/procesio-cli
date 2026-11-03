"""Document-signing form element: the design lint and the template-document upload.

The element (ui-builder `document-signing`, live in prod since user-playground v1.116.0 /
form-runtime v1.32.0) keeps its signers and spots as plain configs that the server stores
without checking; these tests pin the traps the lint reports and the upload's contract.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from tools.procesio import formlint
from tools.procesio.dto.form import sync_from_mock
from tools.procesio.errors import UsageError
from tools.procesio.handlers import form_signing


def _golden():
    return json.loads((sync_from_mock.ELEMENTS / "document-signing.json").read_text(encoding="utf-8"))


def _element(signers, spots, document=""):
    el = _golden()
    el["id"] = "el-1"
    for c in el["configs"]:
        if c["key"] == "templateSigners":
            c["value"] = signers
        elif c["key"] == "templateSpots":
            c["value"] = spots
        elif c["key"] == "document":
            c["value"] = document
        elif c["key"] == "name":
            c["value"] = "Contract"
    return el


def _spot(sid, party, stype="SIGNATURE", **kw):
    s = {"spotId": sid, "partyId": party, "page": 1, "x": 0.1, "y": 0.8, "w": 0.22,
         "h": 0.08, "type": stype, "required": stype == "SIGNATURE"}
    s.update(kw)
    return s


def _lint(el):
    return formlint.lint_document_signing({"elements": [el]})


def test_a_clean_filler_design_has_no_warnings():
    el = _element([{"id": "f", "kind": "FILLER"}], [_spot("s1", "f")])
    assert _lint(el) == []


def test_a_spot_for_an_unknown_party_and_a_signer_without_signature():
    el = _element([{"id": "f", "kind": "FILLER"}],
                  [_spot("s1", "ghost"), _spot("s2", "f", "PRINTED_NAME", h=0.03)])
    out = " | ".join(_lint(el))
    assert "spot 's1' names party 'ghost'" in out
    assert "signers ['f'] have no SIGNATURE spot" in out


def test_member_needs_user_two_fillers_and_private_form():
    el = _element([{"id": "a", "kind": "FILLER"}, {"id": "b", "kind": "FILLER"},
                   {"id": "m", "kind": "MEMBER"}],
                  [_spot("1", "a"), _spot("2", "b"), _spot("3", "m")])
    out = " | ".join(_lint(el))
    assert "MEMBER signer 'm' needs the userId" in out
    assert "at most one FILLER" in out
    assert "keeps the form private" in out


def test_geometry_off_the_page_and_bad_type():
    el = _element([{"id": "f", "kind": "FILLER"}],
                  [_spot("s1", "f", x=0.9, w=0.22), _spot("s2", "f", "STAMP", page=0)])
    out = " | ".join(_lint(el))
    assert "must fit on it" in out
    assert "type 'STAMP'" in out
    assert "1-based integer" in out


def test_inline_pdf_is_flagged():
    el = _element([{"id": "f", "kind": "FILLER"}], [_spot("s1", "f")],
                  document={"src": "data:application/pdf;base64,AAAA", "name": "c.pdf"})
    assert any("inline in the form" in w for w in _lint(el))


def test_lint_runs_inside_lint_form_data():
    el = _element([{"id": "f", "kind": "FILLER"}], [])
    assert any("no SIGNATURE spot" in w for w in formlint.lint_form_data({"elements": [el]}))


# -- form-signing-upload-document ---------------------------------------------------

class _Client:
    def __init__(self, form):
        self.form = form
        self.multipart = []
        self.puts = []

    def get(self, path, *a, **k):
        assert path == "/api/FormTemplate/form-1"
        return json.loads(json.dumps(self.form))

    def request_multipart(self, path, *, files, query=None, headers=None):
        self.multipart.append((path, files))
        return {"fileId": "file-9", "name": files["package"][0], "pageCount": 2}

    def put(self, path, body, *a, **k):
        self.puts.append((path, body))
        return {}


def _form():
    return {"id": "form-1", "name": "F", "updatedOn": "t1",
            "data": {"elements": [_element([{"id": "f", "kind": "FILLER"}], [_spot("s1", "f")])]}}


def _pdf(tmp_path, data=b"%PDF-1.7\n%test\n"):
    p = tmp_path / "contract.pdf"
    p.write_bytes(data)
    return str(p)


def _args(**kw):
    base = dict(form_id="form-1", file=None, element=None, dry_run=False, force=True)
    base.update(kw)
    return SimpleNamespace(**base)


def test_upload_sends_multipart_with_the_form_id(tmp_path):
    c = _Client(_form())
    out = form_signing.upload_document(c, _args(file=_pdf(tmp_path)))
    path, files = c.multipart[0]
    assert path == "/api/form/signing/template-document"
    assert files["package"][0] == "contract.pdf" and files["package"][2] == "application/pdf"
    assert files["formTemplateId"] == (None, "form-1")
    assert out["document"]["fileId"] == "file-9" and not c.puts


def test_upload_with_element_points_document_at_the_stored_file(tmp_path):
    c = _Client(_form())
    out = form_signing.upload_document(c, _args(file=_pdf(tmp_path), element="Contract"))
    assert out["set"] == {"document": {"fileId": "file-9", "name": "contract.pdf"}}
    assert out["previous"] == {"document": ""}
    _path, body = c.puts[0]
    doc = next(cfg for cfg in body["Data"]["elements"][0]["configs"] if cfg["key"] == "document")
    assert doc["value"] == {"fileId": "file-9", "name": "contract.pdf"}
    assert doc["id"] == next(cfg for cfg in _golden()["configs"] if cfg["key"] == "document")["id"]


def test_upload_refuses_a_non_pdf_and_an_oversized_file(tmp_path):
    with pytest.raises(UsageError, match="not a PDF"):
        form_signing.upload_document(_Client(_form()), _args(file=_pdf(tmp_path, b"PK\x03\x04")))
    big = b"%PDF" + b"0" * (form_signing.MAX_SIGNING_DOCUMENT_MB * 1048576)
    with pytest.raises(UsageError, match="at most 10 MB"):
        form_signing.upload_document(_Client(_form()), _args(file=_pdf(tmp_path, big)))


def test_dry_run_uploads_nothing(tmp_path):
    c = _Client(_form())
    out = form_signing.upload_document(c, _args(file=_pdf(tmp_path), element="Contract",
                                                dry_run=True))
    assert out["dry_run"] is True and out["element"] == "el-1"
    assert not c.multipart and not c.puts
