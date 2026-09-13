from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "skills" / "procesio-cli" / "references" / "process-lifecycle.md"


def test_process_lifecycle_requires_one_representative_execution():
    text = PLAYBOOK.read_text(encoding="utf-8")
    lower = text.lower()

    assert "exactly once" in lower
    assert "one execution path only" in lower
    assert "do not also call `run-process`" in lower
    assert "verify --run" in lower
    assert "status alone is not proof of the expected output value" in lower


def test_process_lifecycle_uses_known_instance_id_without_relisting():
    text = PLAYBOOK.read_text(encoding="utf-8").lower()

    assert "call `get-instance-output` directly" in text
    assert "do not add `list-instances` as routine confirmation" in text
    assert "missing id, timeout/unknown outcome, or reconciliation" in text
