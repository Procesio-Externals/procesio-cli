"""Read-only correspondence check for a Gate 5 commit and current skill bytes.

Historical fingerprints cover the entire committed skills subtree, exactly as the
series launcher exports it. Live correspondence covers published packages and the
behavioral/threshold contract, excluding the ledger (which must record new proof).
This verifies content identity, not the authenticity or quality of a test verdict.
Release targets must be clean source exports: bytecode/cache artifacts are rejected,
not silently ignored. Never delete a possibly active developer cache to pass a gate.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path, PurePosixPath


EXPERIMENT_FILES = {"evals/behavioral.json", "evals/gate5-thresholds.json"}


def _finding(code: str, message: str) -> list[dict[str, str]]:
    return [{"skill": "<repository>", "code": code, "message": message}]


def _git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode:
        # Git diagnostics may include machine-local paths; never echo raw output.
        raise ValueError("evaluated Git commit/tree is unavailable")
    return result.stdout


def _snapshot(repo: Path, commit: str) -> dict[str, bytes]:
    if _git(repo, "cat-file", "-t", commit).strip() != b"commit":
        raise ValueError("evaluated identity must be a commit, not a tree or tag")
    entries = _git(repo, "ls-tree", "-r", "-z", commit, "--", "skills").split(b"\0")
    files: dict[str, bytes] = {}
    for entry in filter(None, entries):
        metadata, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        path = PurePosixPath(raw_path.decode("utf-8"))
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("evaluated skills tree contains an unsupported entry")
        if path.is_absolute() or ".." in path.parts or path.parts[0] != "skills":
            raise ValueError("evaluated tree contains an unsafe path")
        files[path.relative_to("skills").as_posix()] = _git(repo, "cat-file", "blob", oid)
    if not files:
        raise ValueError("evaluated skills tree is empty")
    return files


def _digest(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    # Match sorted(Path.rglob()) in the frozen series launcher, not raw string
    # ordering: a directory's children sort before a similarly prefixed sibling.
    for name in sorted(files, key=PurePosixPath):
        digest.update(name.encode("utf-8") + b"\0" + files[name] + b"\0")
    return digest.hexdigest()


def _packages(files: dict[str, bytes]) -> set[str]:
    return {name.split("/")[0] for name in files
            if len(PurePosixPath(name).parts) == 2 and name.endswith("/SKILL.md")}


def _projection(files: dict[str, bytes]) -> dict[str, bytes]:
    packages = _packages(files)
    return {name: data for name, data in files.items()
            if name.split("/")[0] in packages or name in EXPERIMENT_FILES}


def _live(root: Path) -> dict[str, bytes]:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("current skill root is missing or symlinked")
    files: dict[str, bytes] = {}
    for folder in root.iterdir():
        if folder.is_symlink():
            raise ValueError("current skills contain a symlinked directory")
        if not folder.is_dir() or not (folder / "SKILL.md").exists():
            continue
        for path in folder.rglob("*"):
            rel = path.relative_to(root)
            if path.is_symlink():
                raise ValueError("current skill package contains a symlink")
            if "__pycache__" in rel.parts or path.suffix.lower() in {".pyc", ".pyo"}:
                raise ValueError("release binding requires a clean source export without bytecode")
            if path.is_file():
                files[rel.as_posix()] = path.read_bytes()
    for name in EXPERIMENT_FILES:
        path = root / name
        if path.parent.is_symlink() or path.is_symlink():
            raise ValueError("current experiment contract contains a symlink")
        if path.is_file():
            files[name] = path.read_bytes()
    return files


def check_release_binding(repo_root: Path, skills_root: Path, commit: object,
                          fingerprint: object) -> list[dict[str, str]]:
    if (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)
            or not isinstance(fingerprint, str)
            or not re.fullmatch(r"[0-9a-f]{64}", fingerprint)):
        return _finding("invalid-release-binding", "Gate 5 needs an exact commit and SHA-256 fingerprint")
    try:
        frozen = _snapshot(repo_root, commit)
    except (OSError, ValueError, UnicodeError):
        return _finding("unavailable-release-snapshot", "Cannot read a safe evaluated skills tree")
    if _digest(frozen) != fingerprint:
        return _finding("release-snapshot-mismatch", "Recorded fingerprint does not match evaluated Git tree")
    try:
        live = _live(skills_root)
    except (OSError, ValueError):
        return _finding("unsafe-release-content", "Require readable source packages without symlinks or bytecode/cache artifacts; use a clean export")
    expected = _projection(frozen)
    if not _packages(expected) or _packages(live) != _packages(expected) or live != expected:
        changed = sum(live.get(name) != expected.get(name) for name in live.keys() | expected.keys())
        return _finding("release-content-drift", f"Current packages/experiment differ from evaluated content ({changed} paths)")
    return []
