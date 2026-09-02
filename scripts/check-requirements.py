"""Check the machine-level prerequisites every tool declares in `requires:`.

`uv sync` builds the venv. It does not install a browser engine, a database driver
or a codec — and because those are imported lazily, a machine missing them still
reports every tool "ready" and passes the whole test suite. The failure surfaces
at the user's first real call, one tool at a time.

This runs each requirement's `check` command and says what is actually missing,
so a fresh install can be verified in one command instead of by incident.

  python scripts/check-requirements.py            # everything, grouped
  python scripts/check-requirements.py --tool web
  python scripts/check-requirements.py --json
  python scripts/check-requirements.py --quiet     # only what's missing

Exit code: 0 if nothing REQUIRED is missing (self-installing ones are warnings),
1 otherwise — so it can gate an onboarding run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools._lib import manifest as M  # noqa: E402

TIMEOUT = 120


def _probe(cmd: str) -> tuple[bool, str]:
    """Run a check command. Present == exit 0. Never raises.

    `{python}` in a check is replaced with THIS interpreter. A check must not
    depend on how the shell was started: writing `uv run python -c ...` reported
    Playwright's browser missing on a machine that had it, because `uv` was not on
    PATH in that context - a false alarm is as bad as a missed one."""
    if not cmd:
        return True, "no check declared"
    cmd = cmd.replace("{python}", f'"{sys.executable}"')
    try:
        p = subprocess.run(cmd, shell=True, cwd=REPO, capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"check timed out after {TIMEOUT}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"check could not run: {exc}"
    if p.returncode == 0:
        return True, ""
    tail = ((p.stderr or p.stdout) or "").strip().splitlines()
    return False, (tail[-1][:160] if tail else f"exit {p.returncode}")


def collect(only: str | None = None) -> list[dict]:
    """One row per (tool, requirement). Requirements are deduplicated per NAME
    when probing: chromium is the same chromium for all twelve tools that need
    it, and probing it twelve times just makes the run slow."""
    rows: list[dict] = []
    cache: dict[str, tuple[bool, str]] = {}
    for mp in sorted((REPO / "tools").glob("*/tool.yaml")):
        if mp.parent.name.startswith("_"):
            continue
        try:
            tool = M.load_tool(mp)
        except Exception:  # noqa: BLE001 - a broken manifest is list-tools' problem
            continue
        if only and tool.name != only:
            continue
        for req in tool.requires:
            if req.name not in cache:
                cache[req.name] = _probe(req.check)
            present, detail = cache[req.name]
            rows.append({
                "tool": tool.name, "requirement": req.name, "kind": req.kind,
                "present": present, "auto": req.auto, "detail": detail,
                "why": req.why.strip(), "install": req.install,
            })
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tool", help="check one tool only")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.add_argument("--quiet", action="store_true", help="only report what's missing")
    args = p.parse_args()

    rows = collect(args.tool)
    if args.as_json:
        print(json.dumps({"requirements": rows}, indent=1))
    missing = [r for r in rows if not r["present"]]
    blocking = [r for r in missing if not r["auto"]]

    if not args.as_json:
        by_req: dict[str, list[dict]] = {}
        for r in rows:
            by_req.setdefault(r["requirement"], []).append(r)
        for name, group in sorted(by_req.items()):
            first = group[0]
            if first["present"] and args.quiet:
                continue
            mark = "OK  " if first["present"] else ("WARN" if first["auto"] else "MISS")
            tools = ", ".join(sorted({g["tool"] for g in group}))
            print(f"[{mark}] {name} ({first['kind']}) — needed by {len(set(t['tool'] for t in group))} tool(s)")
            print(f"       {tools}")
            if not first["present"]:
                if first["detail"]:
                    print(f"       check said: {first['detail']}")
                if first["why"]:
                    print(f"       why: {' '.join(first['why'].split())}")
                if first["install"]:
                    print(f"       install: {first['install']}")
                if first["auto"]:
                    print("       (self-installing on first use — warning, not a blocker)")
            print()
        if not missing:
            print("All declared machine requirements are present.")
        elif blocking:
            print(f"{len(blocking)} blocking requirement(s) missing.")

    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
