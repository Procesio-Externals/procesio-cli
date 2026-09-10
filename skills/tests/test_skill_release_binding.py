"""Release claims must bind to bytes, not merely green ledger labels."""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._lib.skill_release import check_release_binding


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


@pytest.fixture
def snapshot(tmp_path):
    git(tmp_path, "init", "-q")
    package = tmp_path / "skills" / "demo"
    (package / "references").mkdir(parents=True)
    (tmp_path / "skills" / "evals").mkdir()
    for name, value in {
        "demo/SKILL.md": "---\nname: demo\n---\n# Demo\n",
        "demo/references/rule.md": "Original rule\n",
        "evals/behavioral.json": "{}\n",
        "evals/gate5-thresholds.json": "{}\n",
        "evals/gates.json": "{}\n",
    }.items():
        (tmp_path / "skills" / name).write_text(value, encoding="utf-8")
    git(tmp_path, "add", "skills")
    git(tmp_path, "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
        "commit", "-qm", "fixture")
    commit = git(tmp_path, "rev-parse", "HEAD").decode().strip()
    digest = hashlib.sha256()
    for path in sorted((tmp_path / "skills").rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(tmp_path / "skills").as_posix().encode())
            digest.update(b"\0" + path.read_bytes() + b"\0")
    return tmp_path, commit, digest.hexdigest()


def check(snapshot):
    root, commit, fingerprint = snapshot
    return check_release_binding(root, root / "skills", commit, fingerprint)


def test_matching_package_and_full_snapshot_pass(snapshot):
    assert check(snapshot) == []


@pytest.mark.parametrize("relative", ["demo/SKILL.md", "demo/references/rule.md",
                                      "evals/behavioral.json", "evals/gate5-thresholds.json"])
def test_dirty_loaded_or_experiment_bytes_fail(snapshot, relative):
    (snapshot[0] / "skills" / relative).write_text("changed", encoding="utf-8")
    assert "release-content-drift" in {row["code"] for row in check(snapshot)}


def test_added_and_deleted_package_resources_fail(snapshot):
    root = snapshot[0] / "skills" / "demo"
    (root / "references" / "rule.md").unlink()
    (root / "references" / "new.md").write_text("new")
    assert "release-content-drift" in {row["code"] for row in check(snapshot)}


def test_new_package_cannot_hide_outside_evaluated_inventory(snapshot):
    package = snapshot[0] / "skills" / "another"
    package.mkdir()
    (package / "SKILL.md").write_text("another")
    assert "release-content-drift" in {row["code"] for row in check(snapshot)}


def test_ledger_update_does_not_poison_loaded_package_binding(snapshot):
    root = snapshot[0] / "skills"
    (root / "evals" / "gates.json").write_text('{"new_evidence": true}')
    assert check(snapshot) == []


@pytest.mark.parametrize("relative", ["scripts/payload.pyc", "__pycache__/generated.pyc"])
def test_release_requires_a_clean_source_package_without_bytecode(snapshot, relative):
    path = snapshot[0] / "skills" / "demo" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"potentially executable bytes")
    assert "unsafe-release-content" in {row["code"] for row in check(snapshot)}


def test_tree_object_is_not_commit_lineage(snapshot):
    root, _, fingerprint = snapshot
    tree = git(root, "rev-parse", "HEAD^{tree}").decode().strip()
    result = check_release_binding(root, root / "skills", tree, fingerprint)
    assert "unavailable-release-snapshot" in {row["code"] for row in result}


def test_wrong_historical_full_tree_hash_fails(snapshot):
    root, commit, _ = snapshot
    result = check_release_binding(root, root / "skills", commit, "0" * 64)
    assert "release-snapshot-mismatch" in {row["code"] for row in result}


@pytest.mark.parametrize("commit,fingerprint", [(None, None), ("HEAD", "a" * 64),
                                               ("a" * 40, "bad"), (True, False)])
def test_malformed_binding_fails_closed(snapshot, commit, fingerprint):
    root = snapshot[0]
    result = check_release_binding(root, root / "skills", commit, fingerprint)
    assert "invalid-release-binding" in {row["code"] for row in result}


def test_symlink_resource_is_rejected_without_reading_target(snapshot):
    root = snapshot[0]
    outside = root / "outside.txt"
    outside.write_text("must not load")
    link = root / "skills" / "demo" / "references" / "escape.md"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    assert "unsafe-release-content" in {row["code"] for row in check(snapshot)}


def _ledger_check(snapshot, mutate=lambda ledger: None):
    import json
    import runpy

    root, commit, fingerprint = snapshot
    ledger = {"release_eligible": True, "release_blockers": [],
              "gates": [{"id": value, "status": "passed"} for value in range(7)]}
    ledger["gates"][5].update(evaluated_candidate_commit=commit,
                             evaluated_candidate_fingerprint=fingerprint)
    mutate(ledger)
    path = root / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    check_status = runpy.run_path(str(ROOT / "scripts" / "check-skill-governance.py"))["check_status"]
    return check_status(path, repo_root=root, skills_root=root / "skills")


def test_green_ledger_automatically_checks_real_content(snapshot):
    assert _ledger_check(snapshot) == []
    (snapshot[0] / "skills" / "demo" / "SKILL.md").write_text("changed")
    assert "release-content-drift" in {row["code"] for row in _ledger_check(snapshot)}


@pytest.mark.parametrize("value", ["false", 0, [], None])
def test_ledger_requires_real_boolean(snapshot, value):
    findings = _ledger_check(snapshot, lambda doc: doc.update(release_eligible=value))
    assert "invalid-gate-status" in {row["code"] for row in findings}


@pytest.mark.parametrize("value", [False, [], "0"])
def test_ledger_rejects_non_integer_gate_ids_without_crashing(snapshot, value):
    findings = _ledger_check(snapshot, lambda doc: doc["gates"][0].update(id=value))
    assert "incomplete-gate-set" in {row["code"] for row in findings}


@pytest.mark.parametrize("field,value,code", [
    ("evidence", "not-a-list", "invalid-gate-evidence"),
    ("evidence", ["../outside"], "unsafe-gate-evidence"),
    ("status", [], "invalid-gate-state"),
])
def test_malformed_evidence_and_status_fail_closed(snapshot, field, value, code):
    findings = _ledger_check(snapshot, lambda doc: doc["gates"][0].update({field: value}))
    assert code in {row["code"] for row in findings}


@pytest.mark.parametrize("evidence", ["nul\x00path", "x" * 5000], ids=["nul", "overlong"])
def test_filesystem_metadata_errors_stay_structured(snapshot, evidence):
    findings = _ledger_check(snapshot, lambda doc: doc["gates"][0].update(evidence=[evidence]))
    assert "unsafe-gate-evidence" in {row["code"] for row in findings}


def test_symlink_loop_resolution_error_stays_structured(snapshot, monkeypatch):
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        if path.name == "loop":
            raise RuntimeError("symlink loop")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    findings = _ledger_check(snapshot, lambda doc: doc["gates"][0].update(evidence=["loop"]))
    assert "unsafe-gate-evidence" in {row["code"] for row in findings}
