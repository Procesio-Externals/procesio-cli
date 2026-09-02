"""Generate the platform usage guide FROM the notes, so it cannot drift from them.

The notes hold several hundred sections across twenty files, and the ones a builder
must know before touching the platform are marked in them with a `⚠`. That marker is
the authors' own signal for "this is a rule, not background", and it is what this reads.

Why generated rather than written. The same knowledge has to reach two audiences: us,
in this repo, and whoever clones the public one. A second document restating the rules
would create two copies of every sentence, and the copy is the one that goes stale: the
note gets corrected during the work that corrects the behaviour, and nobody remembers
the summary. So the guide carries the RULE LINE and a pointer, never the explanation.
The explanation stays in the note, one copy, and the guide is regenerated. Nothing here
is authored by hand, exactly like SKILL.md and the capability router.

It lands in the tool's own folder, so the publication plan carries it to the public repo
with everything else under `tools/procesio/` - no plan entry, no second maintenance path.

Deterministic on purpose: no clock, no counts that shift with an unrelated edit, stable
ordering. A generated file that changes when nothing changed is one people stop reading
diffs for.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from tools.procesio.actiondef import ActionDef

TOOL_DIR = Path(__file__).resolve().parents[1]
GUIDE_NAME = "PROCESIO-USAGE-GUIDE.md"

# Generated or navigational, not sources of rules.
SKIP = {GUIDE_NAME, "SKILL.md", "README.md"}

# A note file's topic, for grouping. Anything unlisted falls back to a prettified
# filename, so a new note appears in the guide without touching this map.
TOPICS = {
    "PROCESIO-API-NOTES.md": "The API, and what its answers actually mean",
    "PROCESIO-API-CORRECTIONS.md": "Readings that turned out to be wrong",
    "PROCESIO-SQL-ACTIONS-NOTES.md": "SQL actions",
    "PROCESIO-RESOURCE-MODEL-NOTES.md": "Building resources: processes, forms, documents",
    "PROCESIO-PYTHON-ACTION-NOTES.md": "The Python action",
    "PROCESIO-NODE-MODULE-WHITELIST.md": "The Node action and its libraries",
    "PROCESIO-SEND-EMAIL-NOTES.md": "Send Email",
    "PROCESIO-FORM-SUBMISSION-NOTES.md": "Form submission",
    "PROCESIO-FE-VALIDATION-NOTES.md": "Designer-side validation",
    "PROCESIO-FORM-API-HANG-NOTE.md": "Forms: a call that never returns",
    "PROCESIO-METERING-NOTES.md": "Metering and consumption",
    "PROCESIO-AUTH-NOTES.md": "Authentication",
    "PROCESIO-ENVIRONMENTS-NOTES.md": "Environments",
    "PROCESIO-CUSTOM-ACTION-NOTES.md": "Custom actions",
    "PROCESIO-CARD-BUILD-NOTES.md": "Building a card",
    "PROCESIO-RECONCILIATION-PATTERNS.md": "Reconciling state",
    "PROCESIO-DOCS-FIX-REPORT.md": "Corrections sent to the documentation",
    "PHASE4-E2E-NOTES.md": "End-to-end build, from a real one",
    "DTO-SUBTOOLS-NOTE.md": "The DTO builders",
}

_HEADING = re.compile(r"^(#{2,4})\s+(.*)$")
_MD_NOISE = re.compile(r"[`*_]")


def _clean(text: str) -> str:
    """A rule as one readable line: markers, emphasis and trailing dates removed."""
    t = text.replace("⚠", " ").strip()
    t = _MD_NOISE.sub("", t)
    # A trailing provenance stamp is evidence for the note, noise in an index:
    # (verified 2026-06-24), (live 31/08/2026), (2026-08-24) all go.
    t = re.sub(r"\s*\((?:live|verified|measured|seen|confirmed)?[ ,-]*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\)\s*$", "", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    # Removing the marker can leave "( bites parsers)" or " ,".
    t = re.sub(r"\(\s+", "(", t)
    t = re.sub(r"\s+([),;:])", r"\1", t)
    return t.strip(" .:-")


def _anchor(heading: str) -> str:
    """GitHub's heading slug, so a link lands on the section itself."""
    s = _clean(heading).lower()
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s+", "-", s).strip("-")


def collect(tool_dir: Path | None = None) -> tuple[list[dict], list[str]]:
    """One entry per SECTION that carries a ⚠, plus the notes that carry none.

    Section-level, not marker-level, and that is the whole design. A first version
    emitted one entry per marker and produced fragments: a section often carries
    several ⚠ paragraphs continuing one argument, so the list filled with half
    sentences that mean nothing away from the paragraph above them, and several
    entries pointed at the same anchor.

    A section is the unit a reader navigates to, its heading is a complete statement,
    and it de-duplicates by construction. The marker count still says how much evidence
    sits under an entry, so it is carried rather than shown as separate rows.

    The second return value is the notes with no marked section at all. The convention
    is applied in only some files today, and a guide that silently omitted the rest
    would read as though they hold nothing worth knowing.
    """
    root = tool_dir or TOOL_DIR
    out: list[dict] = []
    unmarked: list[str] = []
    for path in sorted(root.glob("*.md")):
        if path.name in SKIP:
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
        sections: list[dict] = []
        cur: dict | None = None
        for i, raw in enumerate(lines, start=1):
            head = _HEADING.match(raw)
            if head:
                cur = {"file": path.name, "line": i, "rule": _clean(head.group(2)),
                       "anchor": _anchor(head.group(2)),
                       "marks": 1 if "⚠" in raw else 0}
                sections.append(cur)
                continue
            if cur is not None and "⚠" in raw:
                cur["marks"] += 1
        marked = [s for s in sections if s["marks"] and len(s["rule"]) >= 4]
        if marked:
            out.extend(marked)
        else:
            unmarked.append(path.name)
    return out, unmarked


def render(items: list[dict], unmarked: list[str]) -> str:
    by_file: dict[str, list[dict]] = {}
    for it in items:
        by_file.setdefault(it["file"], []).append(it)

    L: list[str] = []
    L.append("# Using PROCESIO: the rules that are not obvious")
    L.append("")
    L.append("**Generated from the notes in this folder. Do not edit by hand.**")
    L.append("Regenerate with `python scripts/run-tool.py procesio usage-guide`.")
    L.append("")
    L.append("Every rule below was learned by losing time to it against the live platform,")
    L.append("and they share a shape: the call succeeds, the status says finished, nothing")
    L.append("is logged, and the thing you asked for did not happen. That is what makes")
    L.append("them expensive. There is no error to search for, so you look in the wrong")
    L.append("place.")
    L.append("")
    L.append("None of these is a defect report. Each is the platform doing something")
    L.append("defensible that reads as a failure until you know the rule.")
    L.append("")
    L.append("This page carries the rule and a pointer. The reasoning, the measurement and")
    L.append("the worked example stay in the note it points at, one copy, so a correction")
    L.append("lands in exactly one place and this page follows on the next build.")
    L.append("")
    L.append(f"**{len(items)} rules across {len(by_file)} notes.**")
    L.append("")

    for name in sorted(by_file, key=lambda n: (-len(by_file[n]), n)):
        L.append(f"## {TOPICS.get(name, name.replace('.md', '').replace('-', ' ').title())}")
        L.append("")
        L.append(f"Source: [`{name}`]({name})")
        L.append("")
        for it in by_file[name]:
            target = f"{name}#{it['anchor']}" if it["anchor"] else name
            L.append(f"- [{it['rule']}]({target})")
        L.append("")

    if unmarked:
        L.append("## Notes not yet indexed here")
        L.append("")
        L.append("These carry rules too. They are absent because the `⚠` convention has not")
        L.append("been applied to them yet, not because they hold nothing. Marking a rule in")
        L.append("one of them adds it here on the next build; read them directly meanwhile.")
        L.append("")
        for name in sorted(unmarked):
            L.append(f"- [`{name}`]({name})")
        L.append("")
    return "\n".join(L).rstrip() + "\n"


def usage_guide(args) -> dict:
    items, unmarked = collect()
    text = render(items, unmarked)
    out = Path(args.out) if getattr(args, "out", None) else TOOL_DIR / GUIDE_NAME
    current = out.read_text(encoding="utf-8") if out.exists() else ""
    stale = current != text
    payload = {
        "action": "usage-guide",
        "rules": len(items),
        "notes_with_rules": len({i["file"] for i in items}),
        "notes_not_yet_marked": unmarked,
        "path": str(out),
        "stale": stale,
    }
    if getattr(args, "check", False):
        payload["wrote"] = False
        if stale:
            payload["hint"] = ("out of date - run `procesio usage-guide` to regenerate "
                               "(a note changed, or a new one was added)")
        return payload
    # newline="" keeps LF: this file is published, and a CRLF rewrite would show the
    # whole guide as modified in the public repo's first diff.
    out.write_text(text, encoding="utf-8", newline="")
    payload["wrote"] = True
    payload["bytes"] = out.stat().st_size
    return payload


def _args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--check", action="store_true",
                   help="Report whether the guide is out of date; write nothing.")
    p.add_argument("--out", help="Write somewhere other than the tool folder.")


ACTIONS = {
    "usage-guide": ActionDef(
        func=usage_guide, add_args=_args, needs_client=False,
        description="Regenerate PROCESIO-USAGE-GUIDE.md from the rules the notes in this "
                    "folder mark with a warning sign (offline, deterministic). The guide "
                    "carries the rule and a link; the explanation stays in the note, so "
                    "there is one copy of every fact. It ships to the public repo with "
                    "the rest of the folder. --check reports staleness without writing.",
    ),
}
