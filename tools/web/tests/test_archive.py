"""Tests for `web archive-document`.

The capture is evidence, so the properties that matter are not "did it write a
file" but: the original is byte-identical to what the publisher served, the hash
in the header is the hash of THAT file, the extraction never silently loses the
document's text, and a date the document states about itself is reported rather
than reconciled. Each test below pins one of those.

No network: the fetch path is exercised through --file, and the stylesheet
inliner is driven with a stubbed requests module.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
if str(FRAMEWORK_ROOT) not in sys.path:
    sys.path.insert(0, str(FRAMEWORK_ROOT))

from tools.web.handlers import archive  # noqa: E402
from tools.web.errors import UsageError  # noqa: E402


class _Args:
    """Minimal stand-in for the parsed argparse namespace."""

    def __init__(self, **kw):
        defaults = dict(url=None, file=None, source_url=None, out_dir=None,
                        name=None, title=None, timeout=5, no_self_contained=True)
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)


HTML = b"""<html><head><title>Terms & Conditions | ACME</title>
<link rel="stylesheet" href="/s.css"></head>
<body><h1>Terms</h1><p>Last updated: 10 August 2021</p>
<p>Client must not resell the Technology.</p>
<script>var x=1;</script></body></html>"""


def _run(tmp_path, **kw):
    src = tmp_path / "in.html"
    src.write_bytes(kw.pop("body", HTML))
    return archive.archive_document(
        _Args(file=str(src), out_dir=str(tmp_path / "out"), name="terms", **kw))


def test_original_is_byte_identical_and_hash_matches_it(tmp_path):
    """The stored original must equal the input byte for byte, and the reported
    sha256 must be the hash of that file - not of the extraction, and not of a
    re-serialised parse tree. This is the whole basis for comparing a later
    fetch against this one."""
    res = _run(tmp_path)
    original = Path(res["files"]["original"])
    assert original.read_bytes() == HTML
    assert res["sha256"]["original"] == hashlib.sha256(HTML).hexdigest()


def test_extraction_keeps_document_text_and_drops_only_script(tmp_path):
    """Dropping a region to tidy the extraction risks dropping a clause that
    happens to sit in it, so only script/style are removed."""
    res = _run(tmp_path)
    text = Path(res["files"]["extraction"]).read_text(encoding="utf-8")
    assert "Client must not resell the Technology." in text
    assert "var x=1" not in text


def test_provenance_header_carries_source_and_hash(tmp_path):
    """An extraction that travels without its source and fetch date becomes an
    unattributable quote the first time someone pastes it into a brief."""
    res = _run(tmp_path, source_url="https://example.com/terms")
    header = Path(res["files"]["extraction"]).read_text(encoding="utf-8")[:1200]
    assert "https://example.com/terms" in header
    assert res["sha256"]["original"] in header
    assert "Fetched at (UTC)" in header


def test_title_read_from_the_document_unless_overridden(tmp_path):
    assert _run(tmp_path)["title"] == "Terms & Conditions | ACME"
    assert _run(tmp_path, title="Pinned")["title"] == "Pinned"


def test_self_contained_copy_is_written_only_when_asked(tmp_path):
    assert "self_contained" not in _run(tmp_path)["files"]


def test_date_candidates_are_reported_not_reconciled(tmp_path):
    """Two different dates on one document is a finding about the document. The
    action must surface both rather than pick one."""
    body = (b"<html><body><p>Last updated: 10 August 2021</p>"
            b"<p>Effective 19/12/2023</p></body></html>")
    res = _run(tmp_path, body=body)
    dates = [d["date"] for d in res["document_date_candidates"]]
    assert "10 August 2021" in dates
    assert "19/12/2023" in dates


def test_a_bare_date_with_no_version_context_is_not_claimed_as_the_date(tmp_path):
    """A date mentioned in passing is not the document's own date. Only dates
    near version wording are reported, so the caller is not handed a false
    'this document is dated X'."""
    body = b"<html><body><p>The contract began on 01/01/2020 in Bucharest.</p></body></html>"
    assert _run(tmp_path, body=body)["document_date_candidates"] == []


def test_pdf_is_detected_by_magic_bytes_not_extension(tmp_path):
    """A PDF served without a .pdf path or content-type must still be stored as
    a .pdf and text-extracted as one."""
    src = tmp_path / "doc.bin"
    src.write_bytes(b"%PDF-1.4\n% not a real pdf")
    res = archive.archive_document(
        _Args(file=str(src), out_dir=str(tmp_path / "out"), name="agreement"))
    assert res["kind"] == "pdf"
    assert Path(res["files"]["original"]).suffix == ".pdf"


@pytest.mark.parametrize("kw", [
    dict(),                                            # neither url nor file
    dict(url="https://x/y", file="z.html"),            # both
])
def test_exactly_one_source_is_required(tmp_path, kw):
    with pytest.raises(UsageError):
        archive.archive_document(
            _Args(out_dir=str(tmp_path), name="n", **kw))


def test_name_must_not_escape_the_out_dir(tmp_path):
    """--name becomes a folder; a path separator in it would write outside the
    collection."""
    for bad in ("../evil", "a/b", "a\\b", "  "):
        with pytest.raises(UsageError):
            archive.archive_document(
                _Args(file=str(tmp_path), out_dir=str(tmp_path), name=bad))


def test_stylesheets_are_inlined_with_urls_made_absolute(tmp_path, monkeypatch):
    """The inlined copy has to render offline, and url() inside a stylesheet is
    relative to the STYLESHEET, not the page - left alone it loses its fonts."""
    class _Resp:
        status_code = 200
        text = "body{background:url('img/bg.png')}"

    monkeypatch.setattr("requests.get", lambda *a, **k: _Resp())
    soup = archive._soup(HTML)
    assert archive._inline_stylesheets(soup, "https://example.com/terms", 5) == 1
    out = str(soup)
    assert "inlined from https://example.com/s.css" in out
    assert "url('https://example.com/img/bg.png')" in out
    assert "<link" not in out


def test_a_failing_stylesheet_degrades_but_never_aborts_the_capture(tmp_path, monkeypatch):
    """Losing a stylesheet must not cost us the document."""
    def _boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr("requests.get", _boom)
    soup = archive._soup(HTML)
    assert archive._inline_stylesheets(soup, "https://example.com/t", 5) == 0


def test_manifest_declares_every_runtime_action(tmp_path):
    """Manifest is the source of truth (Hard rule 3): an action reachable at
    runtime but absent from tool.yaml is a contract that drifted."""
    import yaml
    from tools.web import main as web_main
    manifest = yaml.safe_load((FRAMEWORK_ROOT / "tools/web/tool.yaml").read_text(encoding="utf-8"))
    declared = {a["name"] for a in manifest["actions"]}
    assert "archive-document" in declared
    assert set(web_main.ACTIONS) == declared


def test_cli_emits_one_json_object_on_stdout(tmp_path):
    """JSON in, JSON out (Hard rule 2)."""
    src = tmp_path / "in.html"
    src.write_bytes(HTML)
    proc = subprocess.run(
        [sys.executable, str(FRAMEWORK_ROOT / "scripts/run-tool.py"), "web",
         "archive-document", "--file", str(src), "--out-dir",
         str(tmp_path / "out"), "--name", "terms"],
        capture_output=True, text=True, cwd=str(FRAMEWORK_ROOT))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["name"] == "terms"
