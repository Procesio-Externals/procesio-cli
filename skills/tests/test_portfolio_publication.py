"""Extraction identity and explicit non-qualification, using only local sources."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / 'skills'
PACKAGES = {'procesio-cli', 'procesio-platform-advisor', 'sql-server-optimizer',
            'procesio-cli-maintainer', 'agent-skill-engineer'}
spec = importlib.util.spec_from_file_location('portfolio_governance', ROOT / 'scripts/check-skill-governance.py')
assert spec and spec.loader
governance = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = governance
spec.loader.exec_module(governance)


def test_packaged_source_identity_is_exact_not_release_evidence():
    manifest = json.loads((SKILLS / 'evals/portfolio-package-fingerprints.json').read_text(encoding="utf-8"))
    assert manifest['evidence_role'] == 'source_identity_not_qualification'
    assert {p.parent.name for p in SKILLS.glob('*/SKILL.md')} == PACKAGES
    actual = {}
    for name in sorted(PACKAGES):
        for path in sorted((SKILLS / name).rglob('*')):
            assert not path.is_symlink()
            if not path.is_file() or '__pycache__' in path.parts or path.suffix in {'.pyc', '.pyo'}:
                continue
            actual[path.relative_to(SKILLS).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == manifest['files']


def test_extraction_is_explicitly_not_historical_qualification():
    path = SKILLS / 'evals/gates.json'
    ledger = json.loads(path.read_text(encoding="utf-8"))
    assert ledger['evidence_role'] == 'standalone_portfolio_extraction_not_historical_release'
    assert ledger['release_eligible'] is False
    gate = next(row for row in ledger['gates'] if row['id'] == 5)
    assert gate['status'] == 'blocked'
    assert 'evaluated_candidate_commit' not in gate
    assert governance.check_skills(SKILLS) == []
    assert governance.check_status(path, repo_root=ROOT, skills_root=SKILLS) == []
    findings = governance.check_status(path, require_release_eligible=True,
                                       repo_root=ROOT, skills_root=SKILLS)
    assert 'release-blocked' in {row['code'] for row in findings}
    assert 'invalid-release-binding' in {row['code'] for row in findings}


def test_optional_mcp_features_and_projection_fail_closed():
    entry = (SKILLS / 'procesio-cli/SKILL.md').read_text(encoding="utf-8")
    schedule = (SKILLS / 'procesio-cli/references/schedules-webhooks.md').read_text(encoding="utf-8")
    assert 'optional' in entry.lower()
    assert 'Do not call the unconfirmed MCP path as a preview' in entry
    assert 'before either' in entry.lower()
    assert 'If absent, stop' in schedule
    assert 'stop' in schedule.lower()


def test_sql_and_optimizer_limits_are_visible_before_use():
    context = (SKILLS / 'sql-server-optimizer/references/db-context.md').read_text(encoding="utf-8")
    tables = (SKILLS / 'sql-server-optimizer/scripts/export-tables.sql').read_text(encoding="utf-8")
    meta = (SKILLS / 'agent-skill-engineer/SKILL.md').read_text(encoding="utf-8")
    assert 'Before running an exporter or requesting its output, obtain explicit approval' in context
    assert 'DECLARE @p_IncludeServerTriggers BIT = 0;' in tables
    assert "IF @p_IncludeServerTriggers = 1 AND HAS_PERMS_BY_NAME(NULL, NULL, 'CONTROL SERVER') = 1" in tables
    assert 'one-shot' in meta
    assert 'resubmission' in meta
