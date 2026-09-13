from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "procesio-cli"
PLAYBOOKS = {
    "process-lifecycle.md",
    "process-debugging.md",
    "form-e2e.md",
    "connector-lifecycle.md",
    "transport-environments.md",
    "schedules-webhooks.md",
    "documents-files.md",
    "data-verification.md",
    "credentials-admin.md",
}
REQUIRED_HEADINGS = {
    "## Goal",
    "## Preconditions",
    "## Inspect",
    "## Preview and approval",
    "## Execute",
    "## Verify",
    "## Recovery and cleanup",
    "## Evidence",
}


def test_all_prioritized_playbooks_exist_and_are_linked():
    skill_text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    for name in PLAYBOOKS:
        path = SKILL / "references" / name
        assert path.is_file(), name
        assert f"`references/{name}`" in skill_text, name


def test_each_playbook_has_the_operational_contract():
    for name in PLAYBOOKS:
        text = (SKILL / "references" / name).read_text(encoding="utf-8")
        headings = {line.strip() for line in text.splitlines() if line.startswith("## ")}
        assert REQUIRED_HEADINGS <= headings, name
        assert "verify" in text.lower()
        assert "evidence" in text.lower()
        assert any(term in text.lower() for term in ("approval", "read-only", "mutation"))


def test_playbooks_do_not_duplicate_the_action_catalog():
    for name in PLAYBOOKS:
        text = (SKILL / "references" / name).read_text(encoding="utf-8")
        assert len(text.splitlines()) < 120, name
