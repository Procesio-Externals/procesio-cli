from __future__ import annotations

from pathlib import Path

import registry


def _write_skill(root: Path, name: str, body: str = "# Demo\n") -> Path:
    skill_root = root / name
    skill_root.mkdir(parents=True)
    skill_md = skill_root / "SKILL.md"
    skill_md.write_text(
        "---\n"
        f"name: {name}\n"
        "description: Use when testing registry skill behavior.\n"
        "version: 1.0.0\n"
        "tier: template\n"
        "owner: test-owner\n"
        "last_verified: 2026-09-03\n"
        "baseline_version: abc123\n"
        "eval_suite: evals/evals.json\n"
        "source_policy: static\n"
        "routing:\n"
        "  triggers: [test registry skills]\n"
        "  primary_action: test\n"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return skill_md


def test_registry_exposes_governance_metadata(monkeypatch, tmp_path):
    _write_skill(tmp_path, "demo")
    monkeypatch.setattr(registry, "SKILLS_DIR", tmp_path)
    entries = registry.list_skills()
    assert entries == [{
        "name": "demo",
        "description": "Use when testing registry skill behavior.",
        "version": "1.0.0",
        "tier": "template",
        "path": str(tmp_path / "demo"),
        "routing": {"triggers": ["test registry skills"],
                    "primary_action": "test", "example": ""},
        "owner": "test-owner",
        "last_verified": "2026-09-03",
        "baseline_version": "abc123",
        "eval_suite": "evals/evals.json",
        "source_policy": "static",
        "readiness": "ready",
        "ready": True,
    }]



def test_metadata_does_not_activate_integrity_policy(monkeypatch, tmp_path):
    # Metadata references need not be installed to remain discoverable.
    _write_skill(tmp_path, "demo", "Read `references/missing.md`.\n")
    monkeypatch.setattr(registry, "SKILLS_DIR", tmp_path)
    assert registry.list_skills()[0]["ready"] is True
    assert registry.get_skill("demo").eval_suite == "evals/evals.json"


def test_legacy_defaults_and_folder_warning(monkeypatch, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo\nlicense: Apache-2.0\n---\n# Demo\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(registry, "SKILLS_DIR", tmp_path)
    entry = registry.list_skills()[0]
    assert entry["ready"] is True
    assert entry["warning"] == "folder 'folder' != skill name 'demo'"
    assert entry["owner"] is None and entry["last_verified"] is None
    assert registry.get_skill("demo").version == "0.1.0"
