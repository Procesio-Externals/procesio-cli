from __future__ import annotations

from pathlib import Path

import pytest

from tools._lib.skill_resources import (
    SkillResourceError,
    SkillResourceNotFound,
    SkillResourceNotText,
    read_text_resource,
    resource_index,
)


def test_index_lists_metadata_without_loading_contents(tmp_path):
    root = tmp_path / "skill"
    (root / "references").mkdir(parents=True)
    (root / "references" / "guide.md").write_text("hello", encoding="utf-8")
    index = resource_index(root)
    assert index["references"] == ["references/guide.md"]
    assert index["resources"][0]["size"] == 5
    assert index["resources"][0]["media_type"] == "text/markdown"


def test_read_text_resource_returns_content_and_metadata(tmp_path):
    root = tmp_path / "skill"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts" / "check.py").write_text("print('ok')\n", encoding="utf-8")
    item = read_text_resource(root, "scripts/check.py")
    assert item["content"] == "print('ok')\n"
    assert item["category"] == "scripts"


@pytest.mark.parametrize("path", ["../secret", "references/../../secret", "/etc/passwd", "SKILL.md"])
def test_traversal_and_non_resource_paths_are_rejected(tmp_path, path):
    with pytest.raises(SkillResourceError):
        read_text_resource(tmp_path, path)


def test_missing_resource_has_specific_error(tmp_path):
    with pytest.raises(SkillResourceNotFound):
        read_text_resource(tmp_path, "references/missing.md")


def test_binary_resource_is_not_decoded_as_text(tmp_path):
    root = tmp_path / "skill"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "image.bin").write_bytes(b"\xff\xfe")
    with pytest.raises(SkillResourceNotText):
        read_text_resource(root, "assets/image.bin")


def test_symlink_escape_is_rejected_when_supported(tmp_path):
    root = tmp_path / "skill"
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (root / "references").mkdir(parents=True)
    link = root / "references" / "outside.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    with pytest.raises(SkillResourceError):
        read_text_resource(root, "references/outside.md")


def test_size_limit_and_index_does_not_read_content(tmp_path, monkeypatch):
    from tools._lib.skill_resources import MAX_TEXT_BYTES

    folder = tmp_path / "references"
    folder.mkdir()
    file = folder / "large.md"
    file.write_bytes(b"x" * MAX_TEXT_BYTES)
    assert read_text_resource(tmp_path, "references/large.md")["size"] == MAX_TEXT_BYTES
    file.write_bytes(b"x" * (MAX_TEXT_BYTES + 1))
    def no_read(*args, **kwargs):
        raise AssertionError("index/oversized retrieval must not read contents")
    monkeypatch.setattr(Path, "read_text", no_read)
    assert resource_index(tmp_path)["resources"][0]["size"] == MAX_TEXT_BYTES + 1
    with pytest.raises(SkillResourceError, match="maximum retrievable size"):
        read_text_resource(tmp_path, "references/large.md")


@pytest.mark.parametrize("path", ["", "references/..\\..\\outside", "C:/outside", "assets"])
def test_additional_invalid_paths(tmp_path, path):
    with pytest.raises(SkillResourceError):
        read_text_resource(tmp_path, path)


def test_index_excludes_symlink_escape_and_read_rejects_directory(tmp_path):
    root = tmp_path / "skill"
    (root / "references").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "guide.md").write_text("outside", encoding="utf-8")
    try:
        (root / "assets").symlink_to(outside, target_is_directory=True)
        (root / "references" / "escape.md").symlink_to(outside / "guide.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    assert resource_index(root)["resources"] == []
    with pytest.raises(SkillResourceError, match="outside"):
        read_text_resource(root, "assets/guide.md")
    (root / "references" / "folder").mkdir()
    with pytest.raises(SkillResourceNotFound):
        read_text_resource(root, "references/folder")
