"""Static instruction contracts, not evidence of model behavioral improvement."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def text(skill, resource="SKILL.md"):
    return " ".join((ROOT / "skills" / skill / resource).read_text(encoding="utf-8").split())


@pytest.mark.parametrize("skill", ["procesio-cli", "sql-server-optimizer"])
def test_skill_authoring_handoff_has_one_owner(skill):
    body = text(skill).split("## Boundary", 1)[1].split("## ", 1)[0]
    assert "`agent-skill-engineer`" in body
    assert "`procesio-cli-maintainer`" in body


def test_operational_verification_does_not_grant_execution_permission():
    body = text("procesio-cli")
    contract = text("procesio-cli", "references/operation-contract.md")
    assert "Verification is not additional execution permission" in body
    assert "CLI and MCP" in contract
    assert "explicit operator approval" in contract
    assert "Run, test, submit, enable, and trigger" in contract
    assert "Unknown outcome" in contract


def test_credential_recovery_does_not_restore_exposed_keys_or_probe_forbidden_targets():
    contract = text("procesio-cli", "references/credentials-admin.md")
    assert "Never restore a disclosed or revoked credential" in contract
    assert "preserve the incident" in contract
    assert "Never probe a forbidden workspace" in contract
    assert "separately approved" in contract


def test_sql_actual_plans_and_deployment_require_bounded_approval():
    body = text("sql-server-optimizer")
    context = text("sql-server-optimizer", "references/db-context.md")
    assert "Tuning permission is not deployment permission" in body
    assert "An actual execution plan executes the statement" in context
    assert "ROLLBACK" in context
    assert "unknown outcome" in context
    assert "explicit approval" in context


def test_advisor_distinguishes_occupied_capacity_from_ee_count():
    sizing = text("procesio-platform-advisor", "references/sizing-method.md")
    assert "mean_occupied_seconds" in sizing
    assert "verified_slots_per_EE" in sizing
    assert "steady-state" in sizing
    assert "not a peak or SLA guarantee" in sizing
    assert "do not invent an EE count" in sizing


def test_advisor_missing_sources_stays_provisional_and_non_mutating():
    body = text("procesio-platform-advisor")
    assert "If current sources are unavailable" in body
    assert "provisional" in body
    assert "separately approved operational handoff" in body


def test_maintainer_covers_secret_bearing_reads_and_scoped_release_evidence():
    contract = text("procesio-cli-maintainer", "references/change-contract.md")
    integration = text("procesio-cli-maintainer", "references/skill-authoring.md")
    assert "secret-bearing reads" in contract
    assert "redacted projection" in contract
    assert "reference or helper" in integration
    assert "evaluated package fingerprint" in integration
