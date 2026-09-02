#!/usr/bin/env python3
"""Scan tracked files for live-credential formats.

Backs Hard rule 1 ("No secrets in files. Ever.") with a mechanical check.
Runs as a CLI (pre-commit hook) and as an importable module (pytest guard).

Two properties matter more than the pattern list:

1. **Windowed reads.** A single-line 30 MB JSON export is normal here
   (a .procesio export is one enormous line). A scanner that reads by line,
   or that skips lines over some length, silently reports "clean" on exactly
   the files most likely to carry a secret. This reads fixed-size chunks with
   an overlap wider than the longest credential we match, so a token straddling
   a chunk boundary is still found.

2. **Shape classification before reporting.** Most `Bearer <x>` occurrences in
   a workflow export are GUIDs - variable references, not secrets. Classifying
   by shape (guid / placeholder / jwt / opaque-high-entropy) is what keeps the
   signal usable; without it the true positives drown.

Never emits a credential value. A finding is identified by sha256 prefix,
length and Shannon entropy, which is enough to match it against a vault entry
or to confirm a rotation without ever moving the secret itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parent.parent

# Read 4 MB at a time, overlapping by 64 KB. The overlap must exceed the
# longest single token we can match (a long JWT); 64 KB is far above that.
CHUNK_BYTES = 4 * 1024 * 1024
OVERLAP_BYTES = 64 * 1024

# Entropy floor for calling an opaque string a credential, in bits/char.
# Hex-only tokens sit near 4.0, base64url near 5.5; English prose and
# dotted identifiers sit well below 3.2.
MIN_ENTROPY = 3.2
MIN_OPAQUE_LEN = 20

GUID_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)

# Substrings that mark a value as a documentation placeholder rather than a
# live credential. Compared case-insensitively.
PLACEHOLDER_MARKERS = (
    "xxxx", "your", "example", "placeholder", "changeme", "redacted",
    "sample", "dummy", "insert", "replace", "<", ">", "{{", "}}", "...",
    "abc123", "todo", "notarealkey", "scrubbed",
)

# Each rule: (name, compiled pattern, needs_entropy_check)
# Patterns are byte patterns - we scan bytes so we never have to guess an
# encoding on a 30 MB file.
RULES: list[tuple[str, re.Pattern[bytes], bool]] = [
    ("google-api-key", re.compile(rb"AIza[0-9A-Za-z_\-]{35}"), False),
    ("openai-key", re.compile(rb"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"), True),
    ("github-pat", re.compile(rb"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,}"), False),
    ("github-fine-grained-pat", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{22,}"), False),
    ("slack-token", re.compile(rb"\bxox[abposr]-[A-Za-z0-9\-]{10,}"), False),
    ("aws-access-key-id", re.compile(rb"\bAKIA[0-9A-Z]{16}\b"), False),
    ("sendgrid-key", re.compile(rb"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}"), False),
    (
        "jwt",
        re.compile(rb"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),
        False,
    ),
    (
        "private-key-pem",
        re.compile(rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        False,
    ),
    ("twilio-account-sid", re.compile(rb"\bAC[0-9a-f]{32}\b"), False),
    ("twilio-api-key", re.compile(rb"\bSK[0-9a-f]{32}\b"), False),
    ("stripe-key", re.compile(rb"\b[rs]k_(?:live|test)_[A-Za-z0-9]{20,}"), False),
    # Authorization headers. These fire constantly on GUID variable
    # references, so the shape classifier below does the real work.
    (
        "http-authorization",
        re.compile(rb"(?:Bearer|Basic)\s+([A-Za-z0-9_\-\.=+/]{20,})"),
        True,
    ),
]

# Rules whose match is an identifier rather than a usable secret on its own.
# Still reported, at lower severity, because they name the account to rotate.
IDENTIFIER_ONLY = {"twilio-account-sid", "aws-access-key-id"}


def shannon_entropy(data: str) -> float:
    """Bits of entropy per character."""
    if not data:
        return 0.0
    counts = Counter(data)
    total = len(data)
    return -sum(
        (c / total) * math.log2(c / total) for c in counts.values()
    )


def fingerprint(value: str) -> str:
    """Stable, non-reversible id for a secret. Safe to print, log and commit."""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]


def classify(value: str) -> str:
    """Shape of a candidate: guid | placeholder | jwt | opaque | low-entropy."""
    stripped = value.strip().strip("\"'")
    if GUID_RE.match(stripped):
        return "guid"
    lowered = stripped.lower()
    if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
        return "placeholder"
    if len(set(stripped)) <= 2:
        return "placeholder"
    if stripped.startswith("eyJ") and stripped.count(".") >= 2:
        return "jwt"
    if len(stripped) < MIN_OPAQUE_LEN:
        return "low-entropy"
    if shannon_entropy(stripped) < MIN_ENTROPY:
        return "low-entropy"
    return "opaque"


@dataclass
class Finding:
    path: str
    rule: str
    shape: str
    fingerprint: str
    length: int
    entropy: float
    offset: int
    severity: str

    def render(self) -> str:
        return (
            f"  {self.severity:<10} {self.rule:<24} shape={self.shape:<11} "
            f"sha256:{self.fingerprint}  len={self.length:<4} "
            f"entropy={self.entropy:.2f}  @byte {self.offset}"
        )


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def scan_bytes(blob: bytes, path: str, base_offset: int = 0) -> list[Finding]:
    """Apply every rule to one chunk of bytes."""
    findings: list[Finding] = []
    for rule_name, pattern, entropy_gated in RULES:
        for match in pattern.finditer(blob):
            # Group 1 when the rule captures the value separately
            # (Authorization headers), else the whole match.
            raw = match.group(1) if pattern.groups else match.group(0)
            value = _decode(raw)
            shape = classify(value)

            if shape in ("guid", "placeholder", "low-entropy"):
                # A GUID after Bearer is a PROCESIO variable reference; a
                # placeholder is documentation. Neither is a secret.
                if entropy_gated or shape != "low-entropy":
                    continue

            if rule_name == "private-key-pem":
                severity = "CRITICAL"
            elif rule_name in IDENTIFIER_ONLY:
                severity = "INFO"
            else:
                severity = "CRITICAL"

            findings.append(
                Finding(
                    path=path,
                    rule=rule_name,
                    shape=shape,
                    fingerprint=fingerprint(value),
                    length=len(value),
                    entropy=round(shannon_entropy(value), 2),
                    offset=base_offset + match.start(),
                    severity=severity,
                )
            )
    return findings


def scan_file(path: Path, display: str | None = None) -> list[Finding]:
    """Scan one file with overlapping windows.

    Never reads the whole file into memory and never splits on newlines, so a
    30 MB single-line JSON export is scanned exactly like any other file.
    """
    display = display or str(path)
    findings: list[Finding] = []
    seen: set[tuple[str, str, str]] = set()

    try:
        size = path.stat().st_size
    except OSError:
        return findings
    if size == 0:
        return findings

    with path.open("rb") as handle:
        offset = 0
        carry = b""
        carry_offset = 0
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            window = carry + chunk
            window_offset = carry_offset if carry else offset
            for finding in scan_bytes(window, display, window_offset):
                # The overlap means a token near a boundary is matched twice.
                key = (finding.rule, finding.fingerprint, str(finding.offset))
                dedup = (finding.rule, finding.fingerprint, "")
                if dedup in seen:
                    continue
                seen.add(dedup)
                findings.append(finding)
            offset += len(chunk)
            carry = window[-OVERLAP_BYTES:]
            carry_offset = offset - len(carry)
    return findings


def detect_vcs(root: Path) -> list[str]:
    """Which version-control systems govern this working copy.

    This repo is deliberately dual-VCS - one team consumes it over Git, the
    other over SVN - so "what gets published" has two answers, and a scanner
    that knows only one of them is inoperative for the other team. That was
    the bug: an SVN-only checkout has no `.git`, `git ls-files` exited 128,
    and the guard raised instead of guarding.

    Both are returned when both are present (the mirror host holds both
    working copies). The union is scanned rather than either alone: a file
    versioned on only one side still reaches that side's team.

    `.git` is matched as a path, not a directory - a worktree or submodule
    checkout carries a `.git` *file* pointing at the real git dir.
    """
    found: list[str] = []
    if (root / ".git").exists():
        found.append("git")
    if (root / ".svn").is_dir():
        found.append("svn")
    return found


class NoVersionControl(RuntimeError):
    """Raised when the scan scope cannot be determined from the working copy."""


def _decode_nul_list(payload: bytes) -> list[str]:
    return [name.decode("utf-8") for name in payload.split(b"\0") if name]


def _run_vcs(cmd: list[str], root: Path) -> bytes:
    """Run a VCS query, turning a non-zero exit into a legible failure.

    A CalledProcessError from deep inside the guard reads as "the scanner is
    broken"; for a check whose whole job is to refuse to pass silently, the
    failure has to say which command failed and in which working copy.
    """
    result = subprocess.run(cmd, cwd=root, capture_output=True)
    if result.returncode != 0:
        raise NoVersionControl(
            f"{' '.join(cmd[:2])} failed in {root} (exit {result.returncode}): "
            + (result.stderr.decode("utf-8", "replace").strip() or "no stderr")
        )
    return result.stdout


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------

def _git_tracked(root: Path) -> list[str]:
    return _decode_nul_list(_run_vcs(["git", "ls-files", "-z"], root))


def _git_changed(root: Path) -> list[str]:
    return _decode_nul_list(
        _run_vcs(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"],
            root,
        )
    )


# --------------------------------------------------------------------------
# svn
# --------------------------------------------------------------------------

# `svn status` item kinds that are NOT part of what a commit publishes.
# Everything else is scanned, including kinds not listed here: for a guard,
# an unrecognised state must fall through to "scan it", never to "skip it".
SVN_UNPUBLISHED = frozenset(
    {"unversioned", "ignored", "external", "missing", "deleted", "none"}
)

# Item kinds that represent a local change - the SVN answer to "staged".
SVN_LOCAL_CHANGE = frozenset({"added", "modified", "replaced", "conflicted", "merged"})


def _svn_status_entries(root: Path, verbose: bool) -> list[tuple[str, str]]:
    """(path, item-kind) for every entry `svn status` reports.

    `--xml` rather than the columnar default: the plain output is fixed-width
    and positional, which mis-parses a path containing spaces - and this tree
    has them. `svn status` is a working-copy operation and needs no network,
    unlike `svn list -R`, which queries the repository and would make the
    guard fail offline and hang a pre-commit hook.
    """
    cmd = ["svn", "status", "--xml", "--no-ignore"]
    if verbose:
        cmd.append("--verbose")
    payload = _run_vcs(cmd, root)

    entries: list[tuple[str, str]] = []
    for entry in ElementTree.fromstring(payload).iter("entry"):
        path = entry.get("path")
        if not path or path == ".":
            continue
        status = entry.find("wc-status")
        item = status.get("item", "") if status is not None else ""
        entries.append((path, item))
    return entries


def _svn_versioned(root: Path) -> list[str]:
    """Every file SVN has under version control in this working copy."""
    return [
        path
        for path, item in _svn_status_entries(root, verbose=True)
        if item not in SVN_UNPUBLISHED
    ]


def _svn_changed(root: Path) -> list[str]:
    """Locally changed files - what `svn commit` would send.

    SVN has no index, so nothing is literally "staged"; the closest honest
    equivalent is the set of local modifications.
    """
    return [
        path
        for path, item in _svn_status_entries(root, verbose=False)
        if item in SVN_LOCAL_CHANGE
    ]


# --------------------------------------------------------------------------
# backend-agnostic entry points
# --------------------------------------------------------------------------

# backend -> (full-scope enumerator, local-change enumerator)
_ENUMERATORS = {
    "git": (_git_tracked, _git_changed),
    "svn": (_svn_versioned, _svn_changed),
}


def _collect(root: Path, index: int) -> list[Path]:
    backends = detect_vcs(root)
    if not backends:
        raise NoVersionControl(
            f"no .git or .svn in {root} - cannot determine which files are "
            "published, and a secret scan over an unknown scope proves nothing"
        )
    names: set[str] = set()
    for backend in backends:
        names.update(_ENUMERATORS[backend][index](root))
    return sorted({(root / name) for name in names}, key=str)


def tracked_files(root: Path) -> list[Path]:
    """Every file this working copy publishes, so the guard covers exactly that.

    Git or SVN, or the union of both when the machine holds both.

    Files only. `git ls-files` never names a directory, but `svn status -v`
    reports one entry per versioned directory too, and counting those as
    "scanned" overstates the guard's coverage by a fifth of the tree.
    """
    return [p for p in _collect(root, 0) if p.is_file()]


def staged_files(root: Path) -> list[Path]:
    """Files a commit from here would carry - the pre-commit hook's scope."""
    return [p for p in _collect(root, 1) if p.is_file()]


def load_allowlist(root: Path) -> set[str]:
    """Fingerprints reviewed and accepted as non-secret.

    Holds fingerprints, never values - so the allowlist itself is safe to
    commit. Add an entry only after confirming the value is not live.
    """
    path = root / ".secret-scan-allowlist"
    if not path.exists():
        return set()
    entries = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.add(line)
    return entries


def _is_vcs_internal(rel: str) -> bool:
    """VCS metadata directories, which are never published content.

    `.svn` matters more than `.git` here: `.svn/pristine` holds a complete
    copy of every versioned file, so a directory scan that descends into it
    reports each finding twice and - worse - keeps reporting a secret out of
    the pristine copy after the working file has been scrubbed, which reads
    as "the scrub did not work".
    """
    # Separators are normalised because `rel` falls back to a native
    # absolute path when the target sits outside the repo root, and on
    # Windows that arrives backslash-separated.
    return any(
        part in (".git", ".svn")
        for part in rel.replace("\\", "/").split("/")
    )


def scan_paths(paths: list[Path], root: Path) -> list[Finding]:
    allowed = load_allowlist(root)
    findings: list[Finding] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = str(path)
        if rel == ".secret-scan-allowlist" or _is_vcs_internal(rel):
            continue
        for finding in scan_file(path, rel):
            if finding.fingerprint in allowed:
                continue
            findings.append(finding)
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan for live-credential formats in tracked files."
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Scan only files staged for commit (pre-commit hook mode).",
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Scan a specific file or directory (repeatable).",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    args = parser.parse_args()

    if args.path:
        targets: list[Path] = []
        for entry in args.path:
            p = Path(entry)
            if not p.is_absolute():
                p = REPO_ROOT / entry
            targets.extend(sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p])
    elif args.staged:
        targets = staged_files(REPO_ROOT)
    else:
        targets = tracked_files(REPO_ROOT)

    findings = scan_paths(targets, REPO_ROOT)
    blocking = [f for f in findings if f.severity == "CRITICAL"]

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        if not findings:
            print(f"secret-scan: clean ({len(targets)} files scanned)")
        else:
            by_path: dict[str, list[Finding]] = {}
            for f in findings:
                by_path.setdefault(f.path, []).append(f)
            print(
                f"secret-scan: {len(findings)} finding(s) in "
                f"{len(by_path)} file(s) of {len(targets)} scanned\n"
            )
            for path, group in sorted(by_path.items()):
                print(f"{path}")
                for f in sorted(group, key=lambda x: x.offset):
                    print(f.render())
                print()
            if blocking:
                print(
                    "Values are never printed. Identify a secret by its sha256 "
                    "prefix.\nRotate it at the source, scrub the file, then "
                    "re-scan. If a finding is\nconfirmed not live, add its "
                    "fingerprint to .secret-scan-allowlist."
                )

    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
