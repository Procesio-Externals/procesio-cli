from __future__ import annotations

from types import SimpleNamespace

import pytest

import bridge
from tools._lib.skill_resources import SkillResourceError


def test_get_skill_exposes_index_and_resource_read(monkeypatch, tmp_path):
    root = tmp_path / "demo"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: demo\ndescription: demo\n---\n# Demo\n")
    (root / "references" / "guide.md").write_text("guide", encoding="utf-8")
    monkeypatch.setattr(bridge.registry, "get_skill",
                        lambda name: SimpleNamespace(name=name, path=root))
    skill = bridge.get_skill("demo")
    assert skill["resources"]["references"] == ["references/guide.md"]
    resource = bridge.get_skill_resource("demo", "references/guide.md")
    assert resource["resource"]["content"] == "guide"
    with pytest.raises(SkillResourceError):
        bridge.get_skill_resource("demo", "../outside")
