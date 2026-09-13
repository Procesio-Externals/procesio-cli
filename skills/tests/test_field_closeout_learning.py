"""Development-corpus and instruction retention checks, not behavior/runtime proof."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / 'skills'
CORPUS = SKILLS / 'evals/field-closeout-development-v1.json'


def test_review_addendum_is_separate_and_fixed():
    path = SKILLS / 'evals/field-closeout-correction-development-v1.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        'b155396ca27300bd535e8da33bf32eb4ab4a4d73d6c30a30682c8b7130ff4dc8'
    )
    suite = json.loads(path.read_text(encoding='utf-8'))
    assert suite['evidence_role'] == 'development_only_not_holdout'
    assert suite['rubric_contract'] == 'fixed-jury-rubric-v2'
    assert len(suite['cases']) == 1
    case = suite['cases'][0]
    for name in ('behavioral.json', 'field-boundary-development-v1.json',
                 'field-closeout-development-v1.json'):
        other = json.loads((SKILLS / 'evals' / name).read_text(encoding='utf-8'))
        assert case['id'] not in {item['id'] for item in other['cases']}
    assert case['expected_skill'] == 'procesio-cli'
    rubric = case['expected_output']
    assert rubric['rubric_version'] == 1
    assert len(rubric['criteria']) == 4
    assert len({c['id'] for c in rubric['criteria']}) == 4
    for criterion in rubric['criteria']:
        assert criterion['required'] is True
        assert criterion['description'].startswith('Pass only when')


def body(relative):
    return ' '.join((SKILLS / relative).read_text(encoding='utf-8').split())


def test_closeout_development_contract_is_frozen_and_separate():
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == (
        '566e18324c29eade65bf4a81044da1ae23306721d98a501ea29d585b7c49ac92'
    )
    suite = json.loads(CORPUS.read_text(encoding='utf-8'))
    assert suite['evidence_role'] == 'development_only_not_holdout'
    assert suite['rubric_contract'] == 'fixed-jury-rubric-v2'
    cases = suite['cases']
    ids = {case['id'] for case in cases}
    assert len(ids) == len(cases) == 7
    assert {'positive', 'pressure', 'negative', 'missing-context'} <= {
        case['kind'] for case in cases
    }
    for name in ('behavioral.json', 'field-boundary-development-v1.json'):
        other = json.loads((SKILLS / 'evals' / name).read_text(encoding='utf-8'))
        assert not ids & {case['id'] for case in other['cases']}
    assert not re.search(
        r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|Sentinel|scratchpad/',
        CORPUS.read_text(encoding='utf-8'),
    )
    for case in cases:
        assert (SKILLS / case['expected_skill'] / 'SKILL.md').is_file()
        rubric = case['expected_output']
        assert rubric['rubric_version'] == 1
        criteria = rubric['criteria']
        assert 2 <= len(criteria) <= 8
        assert len({criterion['id'] for criterion in criteria}) == len(criteria)
        for criterion in criteria:
            assert re.fullmatch(r'[a-z][a-z0-9]*(?:_[a-z0-9]+)+', criterion['id'])
            assert criterion['required'] is True
            assert criterion['description'].startswith('Pass only when')


def test_safety_obligation_is_not_success_dependent():
    field = body('agent-skill-engineer/references/field-gate-standard.md')
    for term in ('safety containment', 'evidence-destroying cleanup',
                 'independently of business-output decoding', 'existing approval',
                 'does not pass the business gate'):
        assert term in field
    for path in ('agent-skill-engineer/SKILL.md',
                 'agent-skill-engineer/references/evaluation-standard.md'):
        text = body(path)
        assert 'clean up only after' not in text
        assert 'approved safety containment' in text
    lifecycle = body('procesio-cli/references/process-lifecycle.md')
    assert 'does not depend on successful output decoding' in lifecycle
    assert 'separate approval' in lifecycle
    assert 'evidence-destroying cleanup' in lifecycle
    for name in ('form-e2e.md', 'schedules-webhooks.md'):
        adjacent = body('procesio-cli/references/' + name)
        assert 'separate approval' in adjacent
        assert 'must not wait for successful output decoding' in adjacent
        assert 'references/process-lifecycle.md' in adjacent


def test_comparison_rule_preserves_semantics_and_original_evidence():
    text = body('procesio-cli/references/operation-contract.md')
    for term in ('identity, authored semantics and representation',
                 'versioned source contract', 'untouched original',
                 'exact field paths', 'error bindings', 'Boolean/integer',
                 'new attributable result'):
        assert term in text


def test_observation_repair_does_not_require_reexecution():
    text = body('agent-skill-engineer/references/field-gate-standard.md')
    for term in ('existing attributable evidence', 'does not by itself establish',
                 'valid observation of a missing required effect',
                 'missing observation boundary', 'null is not zero'):
        assert term in text


def test_diagnostic_stop_delivers_without_promoting_acceptance():
    text = body('procesio-cli/references/operation-contract.md')
    for term in ('smallest observation', 'stop condition', 'responsible owner',
                 'clearly scoped artifact', 'not retroactive acceptance'):
        assert term in text


def test_generalization_requires_transfer_and_boundary_control():
    text = body('agent-skill-engineer/references/field-gate-standard.md')
    for term in ('different domain', 'counterexample', 'must not apply',
                 'development cases', 'not transfer-performance evidence'):
        assert term in text
