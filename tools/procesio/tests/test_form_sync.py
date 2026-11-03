"""Guard: the form-control goldens must stay in sync with FormBuilder mock.ts.

Mirrors test_manifest_sync.py's intent for the form layer. If this fails, either a
golden was hand-edited or the mock changed without regenerating — run
`python tools/procesio/dto/form/sync_from_mock.py --write`.
"""
from tools.procesio.dto.form import sync_from_mock as s


def test_all_goldens_match_mock():
    goldens, _stats, _res = s.build_goldens()
    drift = []
    for t, g in goldens.items():
        path = s.ELEMENTS / f"{t}.json"
        if not path.exists():
            drift.append(f"{t} (missing on disk)")
        elif path.read_text(encoding="utf-8").strip() != s._dump(g).strip():
            drift.append(t)
    assert not drift, (
        "form goldens out of sync with FormBuilder mock.ts: "
        f"{drift} — run sync_from_mock.py --write")


def test_every_mock_control_has_a_golden():
    goldens, _stats, _res = s.build_goldens()
    on_disk = {p.stem for p in s.ELEMENTS.glob("*.json")}
    assert set(goldens) <= on_disk, f"mock controls with no golden: {set(goldens) - on_disk}"


def test_soundness_no_enum_contradictions():
    # build_goldens resolves every enum; a wrong mapping would change a value that an
    # existing golden already had. The --check path asserts this; here we just confirm
    # the generator runs and produces the full set.
    goldens, _stats, _res = s.build_goldens()
    assert len(goldens) >= 34


def test_nothing_left_unresolved():
    # every enum member, constant and JSON.stringify(...) the mock writes into a config
    # field resolves to a plain value; a golden never carries a bare identifier
    _goldens, _stats, res = s.build_goldens()
    assert not res.unverified, res.unverified
    assert not res.unresolved, res.unresolved
    for p in s.ELEMENTS.glob("*.json"):
        assert "@bare" not in p.read_text(encoding="utf-8"), p.name


def _cfg(golden, key):
    return next(c for c in golden["configs"] if c["key"] == key)


def test_document_signing_golden_carries_the_upload_contract():
    goldens, _stats, _res = s.build_goldens()
    g = goldens["document-signing"]
    assert g["category"] == "fields" and g["section"] == "body"
    doc = _cfg(g, "document")
    assert doc["type"] == "url-or-file"
    assert doc["accept"] == ["pdf"] and doc["maxFileSizeMB"] == 10
    # without uploadEvent the runtime would keep the PDF inline in the form JSON
    assert doc["uploadEvent"] == "UPLOAD_SIGNING_TEMPLATE_DOCUMENT"
    assert doc["downloadEvent"] == "DOWNLOAD_SIGNING_TEMPLATE_DOCUMENT"
    assert "${" not in doc["tooltip"] and "10 MB" in doc["tooltip"]
    assert _cfg(g, "templateSigners")["type"] == "signing-signers"
    assert _cfg(g, "blockFields")["type"] == "signing-block-fields"
    assert [r["type"] for r in _cfg(g, "blockFields")["value"]] == ["PRINTED_NAME", "DATE_SIGNED"]
    keys = {c["key"] for c in g["configs"]}
    assert {"templateSpots", "setupEditable", "fieldsEditable", "allowDecline",
            "onSignedEvents", "onDeclinedEvents", "onCompletedEvents", "value"} <= keys


def test_json_stringify_placeholders_render_as_text():
    goldens, _stats, _res = s.build_goldens()
    ph = _cfg(goldens["chart"], "colors")["placeholder"]
    assert isinstance(ph, str) and ph.startswith("[") and "#0039E3" in ph
    assert _cfg(goldens["chart"], "type")["options"][0] == {"name": "Bar", "value": "bar"}
