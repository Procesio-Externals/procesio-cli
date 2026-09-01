"""form-get-code / form-set-code: surgical read-modify-write of Data.code.

The invariant worth guarding is that restyling a form NEVER rewrites its content:
the PUT body must carry the element tree, theme and data model through untouched,
with `Data.code` the only changed field. A desired-state rebuild would silently
drop hand-authored elements, which is exactly what these actions exist to avoid.
"""
from __future__ import annotations

import pytest

from tools.procesio import main
from tools.procesio.client import ProcesioClient
from tools.procesio.dto.form import code_cipher
from tools.procesio.errors import UsageError
from tools.procesio.tests.conftest import FakeResp, FakeSession

APIKEY = {"type": "apikey", "key": "N", "value": "V"}
KEY = "test-passphrase"


def _call(action, argv, session):
    return main.dispatch(
        action, argv,
        client_builder=lambda prof: ProcesioClient(profile=APIKEY, name="t", session=session))


@pytest.fixture(autouse=True)
def _stub_key(monkeypatch):
    monkeypatch.setattr("tools.procesio.handlers.form_code._code_key", lambda: KEY)


def _form(code: str = "") -> dict:
    return {
        "id": "F1", "name": "Some form", "isPrivate": False, "type": 1, "status": 1,
        "state": True, "assignees": [], "customUrl": None,
        "data": {"code": code, "elements": [{"id": "e1", "type": "input"}],
                 "theme": [{"label": "Colors"}], "dataModel": {"id": "dm"},
                 "browserTitle": "T"},
    }


def test_get_code_decrypts_and_writes_files(tmp_path):
    blob = code_cipher.encrypt_code("var a=1;", ".x{color:red}", KEY)
    s = FakeSession(queue=[FakeResp(200, _form(blob))])
    css_out, js_out = tmp_path / "a.css", tmp_path / "a.js"
    out = _call("form-get-code",
                ["--id", "F1", "--css-out", str(css_out), "--js-out", str(js_out)], s)
    assert out["css"] == ".x{color:red}" and out["javascript"] == "var a=1;"
    assert css_out.read_text(encoding="utf-8") == ".x{color:red}"
    assert js_out.read_text(encoding="utf-8") == "var a=1;"


def test_get_code_on_empty_blob_is_not_an_error():
    s = FakeSession(queue=[FakeResp(200, _form(""))])
    out = _call("form-get-code", ["--id", "F1"], s)
    assert out["css"] == "" and out["javascript"] == ""


def test_null_css_and_js_are_treated_as_absent_not_as_an_error():
    """A form that never used "Switch to code" carries {"JAVASCRIPT":null,"CSS":null} —
    the designer's initial state, not a corrupt blob. Seen on a real 134-element form."""
    import json as _json
    from tools.procesio.dto.form import code_cipher as cc
    nulls = _json.dumps({"JAVASCRIPT": None, "CSS": None}, separators=(",", ":"))
    salt = b"\x00" * 8
    k, iv = cc._evp_bytes_to_key(KEY.encode(), salt)
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    import base64 as _b64
    data = nulls.encode()
    pad = 16 - (len(data) % 16)
    enc = Cipher(algorithms.AES(k), modes.CBC(iv)).encryptor()
    blob = _b64.b64encode(b"Salted__" + salt + enc.update(data + bytes([pad]) * pad)
                          + enc.finalize()).decode()

    s = FakeSession(queue=[FakeResp(200, _form(blob))])
    out = _call("form-get-code", ["--id", "F1"], s)
    assert out["css"] == "" and out["javascript"] == ""

    # ...and setting only CSS over it must not blow up on the null JS side.
    s = FakeSession(queue=[FakeResp(200, _form(blob)), FakeResp(200, {})])
    out = _call("form-set-code", ["--id", "F1", "--css", ".x{}"], s)
    assert out["updated"] is True and out["javascript_bytes"] == 0
    assert cc.decrypt_code(s.calls[1]["json"]["Data"]["code"], KEY) == {
        "JAVASCRIPT": "", "CSS": ".x{}"}


def test_set_code_puts_full_dto_and_changes_only_code():
    original = _form(code_cipher.encrypt_code("old();", ".old{}", KEY))
    s = FakeSession(queue=[FakeResp(200, original), FakeResp(200, {})])
    out = _call("form-set-code", ["--id", "F1", "--css", ".new{}", "--javascript", "neu();"], s)

    assert s.calls[0]["method"] == "GET"
    put = s.calls[1]
    assert put["method"] == "PUT" and put["url"].endswith("/api/FormTemplate")
    body = put["json"]
    # PascalCase envelope, mapped from the camelCase GET.
    assert body["Id"] == "F1" and body["Name"] == "Some form" and body["State"] is True
    # Everything except `code` survives byte-identical.
    assert body["Data"]["elements"] == original["data"]["elements"]
    assert body["Data"]["theme"] == original["data"]["theme"]
    assert body["Data"]["dataModel"] == original["data"]["dataModel"]
    assert code_cipher.decrypt_code(body["Data"]["code"], KEY) == {
        "JAVASCRIPT": "neu();", "CSS": ".new{}"}
    # The overwritten code comes back, so the change is recoverable from the output.
    assert out["previous"] == {"css": ".old{}", "javascript": "old();"}
    assert out["updated"] is True


def test_set_code_preserves_the_side_not_passed():
    s = FakeSession(queue=[
        FakeResp(200, _form(code_cipher.encrypt_code("keep();", ".keep{}", KEY))),
        FakeResp(200, {})])
    _call("form-set-code", ["--id", "F1", "--css", ".only-css{}"], s)
    assert code_cipher.decrypt_code(s.calls[1]["json"]["Data"]["code"], KEY) == {
        "JAVASCRIPT": "keep();", "CSS": ".only-css{}"}


def test_set_code_dry_run_sends_no_write():
    s = FakeSession(queue=[FakeResp(200, _form(""))])
    out = _call("form-set-code", ["--id", "F1", "--css", ".x{}", "--dry-run"], s)
    assert out["dry_run"] is True and len(s.calls) == 1
    assert all(c["method"] == "GET" for c in s.calls)


def test_set_code_reads_from_files(tmp_path):
    css = tmp_path / "f.css"
    css.write_text(".from-file{}", encoding="utf-8")
    s = FakeSession(queue=[FakeResp(200, _form("")), FakeResp(200, {})])
    _call("form-set-code", ["--id", "F1", "--css-file", str(css)], s)
    assert code_cipher.decrypt_code(s.calls[1]["json"]["Data"]["code"], KEY)["CSS"] == ".from-file{}"


def test_set_code_requires_something_to_set():
    s = FakeSession(queue=[])
    with pytest.raises(UsageError):
        _call("form-set-code", ["--id", "F1"], s)


def test_inline_and_file_for_the_same_side_is_rejected(tmp_path):
    f = tmp_path / "f.css"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(UsageError):
        _call("form-set-code",
              ["--id", "F1", "--css", ".a{}", "--css-file", str(f)], FakeSession(queue=[]))


def test_wrong_key_fails_loudly_rather_than_overwriting():
    s = FakeSession(queue=[FakeResp(200, _form(code_cipher.encrypt_code("j", "c", "OTHER-KEY")))])
    with pytest.raises(UsageError, match="does not match"):
        _call("form-set-code", ["--id", "F1", "--css", ".x{}"], s)
    assert all(c["method"] == "GET" for c in s.calls)


def test_put_keys_track_the_form_builder_top_level_shape():
    """The surgical PUT rebuilds the FormTemplate DTO from _PUT_KEYS (all the surgical
    handlers share this one list). If the form BUILDER ever grows a new top-level field,
    a surgical write would silently drop it — so lock the two together: the builder's
    top-level keys, minus Data, must be exactly _PUT_KEYS."""
    import itertools
    import json as _json

    from tools.procesio.dto.form import builder as fb
    from tools.procesio.handlers.form_code import _PUT_KEYS

    cnt = itertools.count(1)
    ctx = {"new_id": lambda: f"00000000-0000-0000-0000-{next(cnt):012d}"}
    cfg = _json.loads((fb.DIR / "fixtures" / "reg.config.json").read_text(encoding="utf-8"))
    dto = fb.build(cfg, ctx)
    assert set(dto) - {"Data"} == set(_PUT_KEYS)
