"""Form-level CSS/JS (encrypted Data.code) + per-component styling.

Scheme verified live against real exports (2026-06-25): Data.code is JSON {JAVASCRIPT,CSS}
encrypted CryptoJS-style (AES-256-CBC, EVP_BytesToKey/MD5, Salted__). Tests use an injected
key (ctx['form_code_key']) so they need no Credential Manager access.
"""
import uuid

import pytest

from tools.procesio.dto.form import builder, code_cipher
from tools.procesio.errors import UsageError

KEY = "TESTKEY123456789"


def _ctx():
    return {"new_id": lambda: str(uuid.uuid4()), "form_code_key": KEY}


# ---- cipher ---------------------------------------------------------------
def test_code_cipher_roundtrip():
    blob = code_cipher.encrypt_code("console.log(1)", "body{color:red}", KEY)
    assert blob.startswith("U2FsdGVkX1")  # base64("Salted__")
    out = code_cipher.decrypt_code(blob, KEY)
    assert out == {"JAVASCRIPT": "console.log(1)", "CSS": "body{color:red}"}


def test_code_cipher_wrong_key_fails():
    blob = code_cipher.encrypt_code("x", "y", KEY)
    with pytest.raises(ValueError):
        code_cipher.decrypt_code(blob, "WRONGKEY12345678")


def _blob_of(plaintext: bytes, key: str) -> str:
    """Encrypt raw bytes exactly as given (no padding added), the way a wrong key's
    garbage would look to decrypt_code once it is decrypted."""
    import base64

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    salt = b"\x01" * 8
    k, iv = code_cipher._evp_bytes_to_key(key.encode("utf-8"), salt)
    enc = Cipher(algorithms.AES(k), modes.CBC(iv)).encryptor()
    return base64.b64encode(b"Salted__" + salt + enc.update(plaintext) + enc.finalize()).decode()


@pytest.mark.parametrize("plaintext", [
    b"7" + bytes([15]) * 15,          # valid padding, JSON number: the CI flake
    b'"x"' + bytes([13]) * 13,        # valid padding, JSON string
    b'{"CSS":"a"}' + bytes([0]) * 5,  # padding byte 0
    b'{"CSS":"a"}' + b"\x01\x02\x03\x04\x05",  # last byte 5, the rest disagree
])
def test_code_cipher_refuses_garbage_that_a_wrong_key_can_produce(plaintext):
    """A wrong key gives random bytes; rarely they strip as padding and parse as JSON
    that is not an object. That reached form_code._decode as an int (`.get` on int) on
    one CI run in many. Every such shape must be a ValueError."""
    with pytest.raises(ValueError):
        code_cipher.decrypt_code(_blob_of(plaintext, KEY), KEY)


# ---- builder: form-level code --------------------------------------------
def test_build_sets_encrypted_code():
    dto = builder.build(
        {"name": "F", "css": "a{}", "javascript": "b()",
         "elements": [{"type": "input", "label": "X"}]}, _ctx())
    blob = dto["Data"]["code"]
    assert code_cipher.decrypt_code(blob, KEY) == {"JAVASCRIPT": "b()", "CSS": "a{}"}


def test_build_code_object_form():
    dto = builder.build(
        {"name": "F", "code": {"css": "c{}", "javascript": "d()"},
         "elements": [{"type": "input", "label": "X"}]}, _ctx())
    assert code_cipher.decrypt_code(dto["Data"]["code"], KEY)["CSS"] == "c{}"


def test_build_no_code_is_empty_string():
    dto = builder.build({"name": "F", "elements": [{"type": "input", "label": "X"}]}, _ctx())
    assert dto["Data"]["code"] == ""


# ---- builder: per-component style -----------------------------------------
def test_element_style_sets_enabled_cssproperties():
    dto = builder.build(
        {"name": "F", "elements": [
            {"type": "input", "label": "X", "style": {"--h-input": "50px"}}]}, _ctx())
    el = next(e for e in dto["Data"]["elements"] if e["type"] == "input")
    style = next(c for c in el["configs"] if c["key"] == "style")["value"]
    assert style == [{"label": "Height", "value": "50px",
                      "cssVariable": "--h-input", "type": None, "enabled": True}]


def test_element_style_unknown_var_fails_loud():
    with pytest.raises(UsageError):
        builder.build({"name": "F", "elements": [
            {"type": "input", "label": "X", "style": {"--bogus": "1"}}]}, _ctx())


def test_element_style_on_unstylable_type_fails():
    with pytest.raises(UsageError):
        builder.build({"name": "F", "elements": [
            {"type": "heading", "label": "H", "style": {"--x": "y"}}]}, _ctx())


# ---- dynamic vs static tables ---------------------------------------------
def _table(dynamic):
    spec = {"type": "table", "name": "items", "columns": [
        {"key": "p", "label": "P", "cell": {"type": "input"}}]}
    if dynamic:
        spec["dynamic"] = True
    dto = builder.build({"name": "T", "elements": [spec]}, _ctx())
    return dto["Data"]["elements"]


def test_dynamic_table_uses_dynamic_row_with_add_remove():
    els = _table(dynamic=True)
    rows = [e for e in els if e["type"] == "dynamic-table-row"]
    assert rows, "dynamic table must emit a dynamic-table-row"
    cfg = {c["key"]: c.get("value") for c in rows[0]["configs"]}
    assert cfg.get("canAdd") is True and cfg.get("canRemove") is True


def test_static_table_uses_static_row():
    els = _table(dynamic=False)
    assert any(e["type"] == "static-table-row" for e in els)
    assert not any(e["type"] == "dynamic-table-row" for e in els)


# ---- element alignment properties -----------------------------------------

def _style_of(dto, idx=0):
    el = dto["Data"]["elements"][idx]
    return {p["cssVariable"]: p["value"]
            for p in next(c for c in el["configs"] if c["key"] == "style")["value"]}


def test_section_accepts_alignment_vars():
    dto = builder.build(
        {"name": "F", "elements": [
            {"type": "section", "label": "S",
             "style": {"--fd-section": "row", "--jc-section": "center",
                       "--ai-section": "stretch"}}]}, _ctx())
    s = _style_of(dto)
    assert s["--fd-section"] == "row" and s["--jc-section"] == "center"
    assert s["--ai-section"] == "stretch"


def test_columns_alignment_suffix():
    dto = builder.build(
        {"name": "F", "elements": [
            {"type": "columns", "label": "C",
             "style": {"--jc-column": "space-between"}}]}, _ctx())
    assert _style_of(dto)["--jc-column"] == "space-between"


def test_alignment_var_wrong_suffix_still_fails_loud():
    # --jc-section is invalid on a columns element (its suffix is 'column').
    with pytest.raises(UsageError):
        builder.build({"name": "F", "elements": [
            {"type": "columns", "label": "C", "style": {"--jc-section": "center"}}]}, _ctx())


# ---- dark theme (ModeProperties on the Colors group) ----------------------

def _colors_group(dto):
    for g in dto["Data"]["theme"]:
        if str(g.get("label", "")).strip().lower() == "colors":
            return g
    return None


def _mode_var(dto, mode, cssvar):
    for p in _colors_group(dto)["properties"][mode]:
        if p.get("cssVariable") == cssvar:
            return p["value"]
    return None


def test_dark_mode_puts_modeproperties_on_colors_group():
    dto = builder.build(
        {"name": "F", "dark": True,
         "elements": [{"type": "input", "label": "X"}]}, _ctx())
    colors = _colors_group(dto)
    # Colors group's properties becomes {light, dark}; other groups stay flat lists
    assert isinstance(colors["properties"], dict)
    assert set(colors["properties"]) == {"light", "dark"}
    assert _mode_var(dto, "dark", "--c-primary") == "#4663f5"        # DARK_PALETTE default
    others = [g for g in dto["Data"]["theme"] if str(g.get("label")).lower() != "colors"]
    assert all(isinstance(g["properties"], list) for g in others)


def test_dark_override_wins():
    dto = builder.build(
        {"name": "F", "dark": True, "themeDark": {"--c-primary": "#000000"},
         "elements": [{"type": "input", "label": "X"}]}, _ctx())
    assert _mode_var(dto, "dark", "--c-primary") == "#000000"
    # light side keeps the light default
    assert _mode_var(dto, "light", "--c-primary") != "#000000"


def test_no_dark_by_default():
    dto = builder.build({"name": "F", "elements": [{"type": "input", "label": "X"}]}, _ctx())
    assert isinstance(_colors_group(dto)["properties"], list)        # flat, no {light,dark}
    assert "themeMode" not in dto["Data"] and "themeDark" not in dto["Data"]
