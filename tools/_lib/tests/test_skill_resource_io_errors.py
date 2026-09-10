"""Filesystem failures must not escape the resource JSON boundary."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools._lib.skill_resources import SkillResourceError, read_text_resource

ROOT = Path(__file__).resolve().parents[3]


def test_cli_overlong_resource_path_has_sanitized_json_error():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/get-skill.py'), 'procesio-expert',
         '--resource', 'references/' + 'x' * 256],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
    assert result.stderr == ''
    error = json.loads(result.stdout)['error']
    assert error['code'] == 'invalid_skill_resource'
    assert str(ROOT) not in result.stdout


@pytest.mark.parametrize('operation', ['resolve', 'stat', 'read_text'])
def test_filesystem_error_is_translated_without_private_path(tmp_path, monkeypatch, operation):
    (tmp_path / 'references').mkdir()
    (tmp_path / 'references/guide.md').write_text('example', encoding='utf-8')

    def denied(*args, **kwargs):
        raise PermissionError('private installation path must not reach output')

    monkeypatch.setattr(Path, operation, denied)
    with pytest.raises(SkillResourceError) as caught:
        read_text_resource(tmp_path, 'references/guide.md')
    assert 'private installation' not in str(caught.value)
