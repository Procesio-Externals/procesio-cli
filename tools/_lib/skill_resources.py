"""Safe indexing and retrieval for bundled Agent Skill resources."""
from __future__ import annotations

import mimetypes
from pathlib import Path, PurePosixPath
from typing import Any

RESOURCE_CATEGORIES = ("references", "scripts", "assets")
MAX_TEXT_BYTES = 512_000


class SkillResourceError(ValueError):
    code = "invalid_skill_resource"


class SkillResourceNotFound(SkillResourceError):
    code = "skill_resource_not_found"


class SkillResourceNotText(SkillResourceError):
    code = "skill_resource_not_text"


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    if path.suffix.lower() in {".md", ".markdown"}:
        return "text/markdown"
    return "text/plain"


def _resource_paths(root: Path, category: str) -> list[Path]:
    folder = root / category
    if not folder.is_dir():
        return []
    paths: list[Path] = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        try:
            resolved = path.resolve(strict=True)
        except (FileNotFoundError, OSError):
            continue
        if root != resolved and root not in resolved.parents:
            continue
        paths.append(path)
    return sorted(paths)


def resource_index(root: Path) -> dict[str, Any]:
    """Return a bounded metadata index without loading resource contents."""
    root = root.resolve()
    categories: dict[str, list[str]] = {}
    resources: list[dict[str, Any]] = []
    for category in RESOURCE_CATEGORIES:
        paths = _resource_paths(root, category)
        rels = [path.relative_to(root).as_posix() for path in paths]
        categories[category] = rels
        for path, rel in zip(paths, rels):
            resources.append({
                "path": rel,
                "category": category,
                "size": path.stat().st_size,
                "media_type": _media_type(path),
            })
    return {**categories, "resources": resources}


def _requested_path(requested: str) -> PurePosixPath:
    value = str(requested or "").strip().replace("\\", "/")
    if not value:
        raise SkillResourceError("resource path is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise SkillResourceError("resource path must stay inside the skill")
    if len(path.parts) < 2 or path.parts[0] not in RESOURCE_CATEGORIES:
        allowed = ", ".join(f"{item}/" for item in RESOURCE_CATEGORIES)
        raise SkillResourceError(f"resource path must start with one of: {allowed}")
    return path


def read_text_resource(root: Path, requested: str,
                       max_bytes: int = MAX_TEXT_BYTES) -> dict[str, Any]:
    """Read one UTF-8 resource, rejecting traversal, symlink escape, and huge files."""
    relative = _requested_path(requested)
    if "\x00" in str(relative):
        raise SkillResourceError("resource path contains a null byte")
    try:
        root_resolved = root.resolve()
        candidate = root_resolved.joinpath(*relative.parts)
        resolved = candidate.resolve(strict=True)
        if root_resolved != resolved and root_resolved not in resolved.parents:
            raise SkillResourceError("resource resolves outside the skill root")
        if not resolved.is_file():
            raise SkillResourceNotFound(f"resource is not a file: {relative.as_posix()}")
        size = resolved.stat().st_size
        if size > max_bytes:
            raise SkillResourceError(
                f"resource is {size} bytes; maximum retrievable size is {max_bytes}"
            )
        content = resolved.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SkillResourceNotFound(f"resource not found: {relative.as_posix()}") from exc
    except UnicodeDecodeError as exc:
        raise SkillResourceNotText(
            f"resource is not UTF-8 text: {relative.as_posix()}"
        ) from exc
    except OSError as exc:
        # OS messages may contain absolute installation paths; never emit them.
        raise SkillResourceError("resource could not be read") from exc
    return {
        "path": relative.as_posix(),
        "category": relative.parts[0],
        "size": size,
        "media_type": _media_type(resolved),
        "content": content,
    }
