"""Engine-agnostic schema-mirror, diff, and migration helpers.

Shared by the `sqlserver` and `mysql` tools' `schema-extract`, `schema-diff`, and
`migrate` actions. PURE: no DB driver import, no network — every function is a
deterministic transform of its inputs, so it is fully unit-testable without a
database. The engine-specific parts (catalog queries, tracking-table SQL, apply
path) live in each tool's `schema.py`; this module is the common machinery.

Mirror layout (one file per object):
    <out>/schema/<Type>/<schema>.<name>.sql      (or <name>.sql when schema is "")
    <out>/_manifest.json                          {relpath: sha256}

A "record" is a dict: {"type": <dir label>, "schema": <str|"">, "name": <str>,
"definition": <sql text>}.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------

def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# mirror layout
# ---------------------------------------------------------------------------

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe(component: str) -> str:
    """Make one path component filesystem-safe (Windows + POSIX)."""
    s = _UNSAFE.sub("_", str(component)).strip().rstrip(".")
    return s or "_"


def mirror_relpath(obj_type: str, schema: str, name: str) -> str:
    """Deterministic POSIX relpath under the mirror root for one object."""
    stem = f"{schema}.{name}" if schema else str(name)
    return f"schema/{_safe(obj_type)}/{_safe(stem)}.sql"


def write_mirror(out_dir: str | Path, records, *, full: bool = False,
                 dry_run: bool = False) -> dict:
    """Write/update the local mirror from `records`. Incremental by default:
    only changed/new objects are written, orphaned files are removed, and a
    `_manifest.json` of relpath->sha256 tracks state. Returns a summary dict.
    """
    out = Path(out_dir)
    schema_root = out / "schema"
    manifest_path = out / "_manifest.json"

    desired: dict[str, str] = {}      # relpath -> definition text
    by_type: dict[str, int] = {}
    for r in records:
        rel = mirror_relpath(r["type"], r.get("schema", "") or "", r["name"])
        desired[rel] = r["definition"]
        by_type[r["type"]] = by_type.get(r["type"], 0) + 1

    prev: dict[str, str] = {}
    if manifest_path.exists() and not full:
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev = {}

    if full and not dry_run and schema_root.exists():
        import shutil
        shutil.rmtree(schema_root)
        prev = {}

    written = unchanged = removed = 0
    new_manifest: dict[str, str] = {}
    for rel, definition in sorted(desired.items()):
        digest = sha256_text(definition)
        new_manifest[rel] = digest
        target = out / rel
        is_same = prev.get(rel) == digest and (dry_run or target.exists())
        if is_same and not full:
            unchanged += 1
            continue
        written += 1
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(definition, encoding="utf-8")

    # remove orphans (in the old manifest but no longer desired)
    for rel in sorted(set(prev) - set(desired)):
        removed += 1
        if not dry_run:
            try:
                (out / rel).unlink()
            except OSError:
                pass

    if not dry_run:
        out.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(new_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {"out": str(out), "written": written, "unchanged": unchanged,
            "removed": removed, "total": len(desired), "by_type": by_type,
            "dry_run": dry_run, "manifest": str(manifest_path)}


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

def _mirror_files(mirror_dir: str | Path) -> dict[str, str]:
    """relpath (posix, 'schema/...') -> file text, for every .sql under schema/."""
    root = Path(mirror_dir) / "schema"
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*.sql"):
        rel = p.relative_to(Path(mirror_dir)).as_posix()
        try:
            out[rel] = p.read_text(encoding="utf-8")
        except OSError:
            out[rel] = ""
    return out


def diff_mirrors(left_dir: str | Path, right_dir: str | Path, *,
                 include_diff: bool = True) -> dict:
    """Compare two schema mirrors. added = only in right, removed = only in left,
    changed = present in both with differing content (with a unified diff)."""
    left = _mirror_files(left_dir)
    right = _mirror_files(right_dir)
    added = sorted(set(right) - set(left))
    removed = sorted(set(left) - set(right))
    changed = []
    for rel in sorted(set(left) & set(right)):
        if left[rel] != right[rel]:
            entry = {"relpath": rel}
            if include_diff:
                entry["diff"] = "".join(difflib.unified_diff(
                    left[rel].splitlines(keepends=True),
                    right[rel].splitlines(keepends=True),
                    fromfile=f"left/{rel}", tofile=f"right/{rel}"))
            changed.append(entry)
    unchanged = len(set(left) & set(right)) - len(changed)
    return {"added": added, "removed": removed, "changed": changed,
            "unchanged": unchanged,
            "identical": not added and not removed and not changed,
            "summary": {"added": len(added), "removed": len(removed),
                        "changed": len(changed)}}


# ---------------------------------------------------------------------------
# migrations
# ---------------------------------------------------------------------------

MIGRATION_FILE_RE = re.compile(r"^(\d{3,})_([a-z0-9][a-z0-9_\-]*)\.sql$", re.IGNORECASE)

_DANGER_RE = re.compile(
    r"\b(DROP\s+(TABLE|DATABASE|SCHEMA|COLUMN)|TRUNCATE\s+TABLE)\b", re.IGNORECASE)
_UNQUALIFIED_RE = re.compile(
    r"\b(UPDATE|DELETE)\b(?:(?!\bWHERE\b).)*?(;|\Z)", re.IGNORECASE | re.DOTALL)
_GO_RE = re.compile(r"^\s*GO\s*$", re.IGNORECASE)


def discover_migrations(migrations_dir: str | Path):
    """Return [(mig_id, Path)] for NNNN_<slug>.sql files, ordered by the numeric
    prefix. mig_id is the filename stem. Non-matching files are skipped (returned
    separately so the caller can warn)."""
    d = Path(migrations_dir)
    found, skipped = [], []
    if d.is_dir():
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() == ".sql":
                m = MIGRATION_FILE_RE.match(p.name)
                (found if m else skipped).append((p.stem if m else p.name, p))
    found.sort(key=lambda t: int(t[0].split("_", 1)[0]))
    return found, [name for name, _ in skipped]


def pending(applied_ids, migrations):
    """migrations = [(mig_id, path)]; return those whose id is not in applied_ids."""
    applied = set(applied_ids)
    return [(mid, p) for (mid, p) in migrations if mid not in applied]


def danger_warnings(sql: str) -> list[str]:
    out = []
    m = _DANGER_RE.search(sql)
    if m:
        out.append(f"destructive DDL: {m.group(0)}")
    if _UNQUALIFIED_RE.search(sql):
        out.append("possible UPDATE/DELETE without a WHERE clause")
    return out


def split_go_batches(sql: str) -> list[str]:
    """Split a SQL Server script on lines that are exactly `GO` (case-insensitive).
    Known limitation: a `GO` inside a string literal or block comment that sits
    alone on a line is still treated as a separator."""
    batches, cur = [], []
    for line in sql.splitlines():
        if _GO_RE.match(line):
            batch = "\n".join(cur).strip()
            if batch:
                batches.append(batch)
            cur = []
        else:
            cur.append(line)
    batch = "\n".join(cur).strip()
    if batch:
        batches.append(batch)
    return batches
