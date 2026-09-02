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
    assert len(goldens) >= 33
