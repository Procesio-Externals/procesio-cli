"""Encrypt/decrypt a form's `Data.code` blob (the "Switch to code" CSS + JavaScript).

PROVEN against real exports (2026-06-25): `Data.code` is `JSON.stringify({JAVASCRIPT,
CSS})` encrypted with CryptoJS `AES.encrypt(text, passphrase)` — i.e. OpenSSL-compatible
AES-256-CBC, key+IV derived from the passphrase + an 8-byte random salt via EVP_BytesToKey
(MD5, 1 iteration), output = base64("Salted__" + salt + ciphertext). The passphrase is a
static key stored in Credential Manager (agents-and-tools:procesio/form-code-key) — it is
NEVER hard-coded here. Decrypting any real export's `code` with that key yields
`{"JAVASCRIPT": "...", "CSS": "..."}`.

The frontend (ui-builder) only holds `code` as a plaintext `{JAVASCRIPT, CSS}` object and
injects the JS as a RUN_JAVASCRIPT form event at render; the host webapp does the AES step
before POST/PUT /api/FormTemplate. There is no plaintext-CSS/JS field on the DTO, so to set
global form CSS/JS server-side we must produce this exact encrypted blob.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_MAGIC = b"Salted__"


def _evp_bytes_to_key(passphrase: bytes, salt: bytes, key_len: int = 32, iv_len: int = 16):
    """OpenSSL EVP_BytesToKey (MD5, 1 iteration) — CryptoJS's default KDF."""
    d = b""
    prev = b""
    while len(d) < key_len + iv_len:
        prev = hashlib.md5(prev + passphrase + salt).digest()
        d += prev
    return d[:key_len], d[key_len:key_len + iv_len]


def encrypt_code(javascript: str, css: str, key: str, salt: bytes | None = None) -> str:
    """Build the encrypted `Data.code` blob from JS + CSS strings.

    Plaintext mirrors the frontend exactly: JSON `{"JAVASCRIPT":...,"CSS":...}` (that key
    order, JSON.stringify-compact). `salt` is random by default (as CryptoJS does); pass a
    fixed salt only for deterministic tests.
    """
    plaintext = json.dumps({"JAVASCRIPT": javascript or "", "CSS": css or ""},
                           separators=(",", ":"), ensure_ascii=False)
    salt = salt if salt is not None else os.urandom(8)
    k, iv = _evp_bytes_to_key(key.encode("utf-8"), salt)
    data = plaintext.encode("utf-8")
    pad = 16 - (len(data) % 16)
    data += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(k), modes.CBC(iv)).encryptor()
    ct = enc.update(data) + enc.finalize()
    return base64.b64encode(_MAGIC + salt + ct).decode("ascii")


def decrypt_code(blob: str, key: str) -> dict:
    """Inverse of encrypt_code: encrypted blob -> {"JAVASCRIPT": ..., "CSS": ...}.

    Raises ValueError for a wrong key or a corrupt blob. CBC with a wrong key does not
    fail by itself: it yields random bytes, and now and then those strip as "padding",
    decode as UTF-8 and even parse as JSON (a lone digit is valid JSON). So the padding
    is checked in full and the result must be a JSON object, or a wrong key could pass
    as a form with odd code.
    """
    raw = base64.b64decode(blob)
    if raw[:8] != _MAGIC:
        raise ValueError("not a CryptoJS 'Salted__' blob")
    salt, ct = raw[8:16], raw[16:]
    if not ct or len(ct) % 16:
        raise ValueError("ciphertext is not a whole number of AES blocks")
    k, iv = _evp_bytes_to_key(key.encode("utf-8"), salt)
    dec = Cipher(algorithms.AES(k), modes.CBC(iv)).decryptor()
    pt = dec.update(ct) + dec.finalize()
    pad = pt[-1]
    if not 1 <= pad <= 16 or pt[-pad:] != bytes([pad]) * pad:
        raise ValueError("bad PKCS#7 padding (wrong key or corrupt blob)")
    try:
        doc = json.loads(pt[:-pad].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"decrypted bytes are not JSON (wrong key or corrupt blob): {e}") from e
    if not isinstance(doc, dict):
        raise ValueError(f"decrypted JSON is a {type(doc).__name__}, not an object "
                         f"(wrong key or corrupt blob)")
    return doc
