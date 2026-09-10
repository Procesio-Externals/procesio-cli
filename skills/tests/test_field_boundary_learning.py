"""Structural retention checks + frozen development cases, NOT behavioral uplift proof."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REFS = ROOT / 'skills/procesio-cli/references'
CORPUS = ROOT / 'skills/evals/field-boundary-development-v1.json'


def text(name):
    return ' '.join((REFS / name).read_text(encoding='utf-8').split())


def test_development_cases_remain_frozen_and_separate():
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == (
        'bb0e22e34bdf262a72973958eed528aa470dc37c758c6197126fbbdd5ad72596'
    )
    suite = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert suite['evidence_role'] == 'development_only_not_holdout'
    assert suite['rubric_contract'] == 'fixed-jury-rubric-v2'
    cases = suite['cases']
    ids = {c['id'] for c in cases}
    assert len(cases) == len(ids) == 10
    historical = json.loads((ROOT / 'skills/evals/behavioral.json').read_text(encoding="utf-8"))
    assert not ids & {c['id'] for c in historical['cases']}
    assert {'positive', 'pressure', 'negative', 'missing-context'} <= {c['kind'] for c in cases}
    assert not re.search(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', CORPUS.read_text(encoding="utf-8"))
    for case in cases:
        assert (ROOT / 'skills' / case['expected_skill'] / 'SKILL.md').is_file()
        rubric = case['expected_output']
        assert rubric['rubric_version'] == 1
        criteria = rubric['criteria']
        assert 2 <= len(criteria) <= 8
        assert len({c['id'] for c in criteria}) == len(criteria)
        for c in criteria:
            assert re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)+', c['id'])
            assert c['required'] is True
            assert c['description'].startswith('Pass only when')


def test_credentials_preserve_existing_access_and_typed_identity():
    body = text('credentials-admin.md')
    for term in ['two authentication planes', 'workspace GUID', 'connection GUID',
                 '`gid`', 'not evidence of absence', 'does not prove read-only',
                 'generated', 'not invent', 'owner', 'emails or user IDs']:
        assert term in body


def test_native_proof_is_independent_and_transition_sensitive():
    body = text('data-verification.md')
    for term in ['original request', 'same intermediate', 'explicit null',
                 'concrete → null', 'null → concrete', 'false', 'zero',
                 'already null', 'typed object', 'not a universal', 'protected']:
        assert term in body


def test_debugging_does_not_repeat_shared_state_corruption():
    body = text('process-debugging.md')
    assert 'original item → intermediate variable → native mapping → persisted row' in body
    assert 'last loop iteration' in body
    assert 'same intermediate' in body


def test_graph_and_confidentiality_precede_execution():
    body = text('process-lifecycle.md')
    assert 'before freezing' in body
    assert 'input-port' in body
    assert 'Join' in body
    assert 'first persistence boundary' in body
    assert 'synthetic canary' in body
    assert 'inactive creation' in body
    assert 'downstream hashing' in body


def test_resume_and_inventory_rules_are_not_delete_and_retry():
    body = text('operation-contract.md')
    for term in ['returned page', 'unique stable IDs', 'not not-found',
                 'Approval recording', 'checkpoint eligibility', 'actual execution',
                 'one bounded next step', 'selected-phase', 'aggregate']:
        assert term in body


def test_meta_gate_compares_independent_evidence_and_separate_layers():
    body = ' '.join((ROOT / 'skills/agent-skill-engineer/references/field-gate-standard.md').read_text(encoding="utf-8").split())
    for term in ['same erroneous intermediate', 'first persistence boundary',
                 'offline assertions', 'causal skill improvement',
                 'typed-null', 'checkpoint eligibility']:
        assert term in body


def test_confidentiality_gate_is_reachable_for_exports_before_execute():
    common = text('operation-contract.md')
    assert 'Before a read, export or diagnostic fetch' in common
    assert 'references/process-lifecycle.md' in common
    transport = text('transport-environments.md')
    assert transport.index('pre-acquisition confidentiality gate') < transport.index('## Execute')
    assert 'inline secrets' in transport
    assert 'references/process-lifecycle.md' in transport
