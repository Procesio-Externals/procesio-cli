"""Generate a per-tool SKILL.md - the agent's instruction manual - from tool.yaml.

WHY
---
Borrowed from CLI-Anything, which ships a generated `SKILL.md` beside every CLI so
an agent can read how to drive it. We had no equivalent: a tool advertises itself
through one hand-written line in the Capability Router plus a README written for
humans. That line is enough to CHOOSE a tool and not enough to USE one - the agent
then falls back to `--help`, which for a big tool costs more context than the task.

The point of generating it is drift: a hand-written manual goes stale the first
time an action is added, and a stale manual is worse than none because the agent
trusts it. This one is derived from the manifest, which is already the source of
truth (Hard rule 3), so it cannot disagree with the code.

Usage:
  python scripts/build-tool-skill.py <tool> [--out PATH] [--stdout] [--check]

  --check exits 1 if the file on disk differs from what would be generated, so CI
  or a test can fail on a stale skill instead of shipping one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools._lib import manifest as M  # noqa: E402

MAX_DESC = 160


def _group_of(action_name: str) -> str:
    return action_name.split("-", 1)[0]


def _one_line(text: str, limit: int = MAX_DESC) -> str:
    """First sentence, collapsed - an agent scanning a table needs the verb, not
    the essay. The full description stays in the manifest."""
    flat = " ".join((text or "").split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def _required_args(action) -> list[str]:
    return [a.name for a in action.args if getattr(a, "required", False)]


def render(tool: M.ToolManifest) -> str:
    """The SKILL.md body. Frontmatter first so a skill loader can index it."""
    actions = list(tool.actions)
    groups: dict[str, list] = {}
    for a in actions:
        groups.setdefault(_group_of(a.name), []).append(a)
    grouped = len(groups) > 1 and len(actions) > 12

    routing = tool.routing
    primary = getattr(routing, "primary_action", None) if routing else None
    example = getattr(routing, "example", None) if routing else None

    out: list[str] = []
    out.append("---")
    out.append(f"name: {tool.name}")
    out.append(f"description: {_one_line(tool.description, 400)}")
    out.append("---")
    out.append("")
    out.append(f"# {tool.name}")
    out.append("")
    out.append(" ".join((tool.description or "").split()))
    out.append("")

    out.append("## How to call it")
    out.append("")
    out.append("```bash")
    out.append(f"python scripts/run-tool.py {tool.name} <action> [--args]")
    if example:
        out.append(f"# e.g. {example}")
    out.append("```")
    out.append("")
    out.append("One JSON object on stdout for success; `{\"error\": {\"code\", "
               "\"message\", \"details\"}}` and a non-zero exit on failure. "
               "Progress and logs go to stderr only.")
    out.append("")
    if primary:
        out.append(f"**Start with `{primary}`.**")
        out.append("")

    if tool.secrets:
        out.append("## Credentials")
        out.append("")
        out.append("Stored in the OS credential store, never in files. Missing ones "
                   "are reported by `python scripts/list-tools.py`.")
        out.append("")
        for s in tool.secrets:
            out.append(f"- `agents-and-tools:{tool.name}:{s.name}`"
                       + (f" — {_one_line(s.description)}" if s.description else ""))
        out.append("")

    out.append("## Actions")
    out.append("")
    if grouped:
        for group in sorted(groups):
            out.append(f"### {group}")
            out.append("")
            out.append("| action | required args | what it does |")
            out.append("|---|---|---|")
            for a in sorted(groups[group], key=lambda x: x.name):
                req = ", ".join(f"`--{n}`" for n in _required_args(a)) or "—"
                out.append(f"| `{a.name}` | {req} | {_one_line(a.description)} |")
            out.append("")
    else:
        out.append("| action | required args | what it does |")
        out.append("|---|---|---|")
        for a in sorted(actions, key=lambda x: x.name):
            req = ", ".join(f"`--{n}`" for n in _required_args(a)) or "—"
            out.append(f"| `{a.name}` | {req} | {_one_line(a.description)} |")
        out.append("")

    out.append("---")
    out.append("")
    out.append(f"Generated from `tools/{tool.name}/tool.yaml` by "
               "`scripts/build-tool-skill.py`. Do not edit by hand — change the "
               "manifest and regenerate.")
    out.append("")
    return "\n".join(out)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("tool", help="tool name as it appears in list-tools")
    p.add_argument("--out", help="output path (default: tools/<tool>/SKILL.md)")
    p.add_argument("--stdout", action="store_true", help="print instead of writing")
    p.add_argument("--check", action="store_true",
                   help="exit 1 if the file on disk is stale")
    args = p.parse_args()

    # Load by directory, skipping siblings that fail to parse: one broken manifest
    # elsewhere in tools/ must not stop us generating this tool's skill.
    tools: dict[str, M.ToolManifest] = {}
    for manifest_path in sorted((REPO / "tools").glob("*/tool.yaml")):
        if manifest_path.parent.name.startswith("_"):
            continue
        try:
            m = M.load_tool(manifest_path)
        except Exception as exc:  # noqa: BLE001
            if manifest_path.parent.name == args.tool:
                sys.exit(f"{args.tool}: manifest failed to load: {exc}")
            continue
        tools[m.name] = m
    if args.tool not in tools:
        sys.exit(f"unknown tool: {args.tool}. Known: {', '.join(sorted(tools))}")
    tool = tools[args.tool]
    body = render(tool)

    if args.stdout:
        print(body)
        return

    # Write beside the manifest, NOT at tools/<name>/: a manifest name and its
    # directory can differ (tools/google_mail/ declares name google-mail), so
    # deriving the path from the name misses every such tool.
    dest = Path(args.out) if args.out else (tool.path / "SKILL.md")
    if args.check:
        current = dest.read_text(encoding="utf-8") if dest.exists() else ""
        if current != body:
            sys.exit(f"STALE: {dest} differs from the manifest. Regenerate it.")
        print(f"up to date: {dest}")
        return
    dest.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {dest} ({len(body)} bytes, {len(tool.actions)} actions)")


if __name__ == "__main__":
    main()
