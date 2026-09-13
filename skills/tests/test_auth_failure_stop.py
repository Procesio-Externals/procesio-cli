"""The operational skill must not encourage endpoint exploration after auth fails."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "procesio-cli"


def test_credentials_playbook_stops_after_failed_check_auth():
    text = (SKILL / "references" / "credentials-admin.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "authentication hard stop" in lowered
    assert "authenticated: false" in lowered
    assert "stop all remote procesio calls" in lowered
    assert "show-credential" in lowered
    assert "key handle" in lowered and "api key value" in lowered
    assert "configured but not confirmed" in lowered


def test_main_skill_treats_failed_readiness_as_a_stop_condition():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8").lower()
    assert "authenticated: false" in text
    assert "mode" in text
    assert "stop" in text
