"""The usage guide is generated FROM the notes, so it cannot drift from them.

What these pin is the reason the generator exists at all: one copy of every fact.
The guide carries a rule line and a pointer; the explanation stays in the note. A
regression here does not look like a crash, it looks like a second, slowly diverging
copy of the platform's behaviour.
"""
from __future__ import annotations

from tools.procesio.handlers import usageguide as ug


def _note(tmp_path, name, text):
    (tmp_path / name).write_text(text, encoding="utf-8")


def test_a_section_marked_once_yields_one_entry(tmp_path):
    """Section-level, not marker-level. The first version emitted one row per marker,
    so a section arguing one point across several marked paragraphs produced a list of
    half sentences all pointing at the same anchor."""
    _note(tmp_path, "A-NOTES.md", "\n".join([
        "# Title",
        "## A Node inlines the value as raw text",
        "⚠ first marked paragraph, which continues below",
        "some prose",
        "⚠ second marked paragraph of the same argument",
    ]))
    items, unmarked = ug.collect(tmp_path)
    assert len(items) == 1
    assert items[0]["rule"] == "A Node inlines the value as raw text"
    assert items[0]["marks"] == 2      # evidence is counted, not listed
    assert unmarked == []


def test_an_unmarked_section_is_not_an_entry(tmp_path):
    _note(tmp_path, "A-NOTES.md", "\n".join([
        "## Background reading with no rule in it",
        "prose",
        "## A rule worth knowing",
        "⚠ this one is marked",
    ]))
    items, _ = ug.collect(tmp_path)
    assert [i["rule"] for i in items] == ["A rule worth knowing"]


def test_a_note_with_no_marked_section_is_reported_not_dropped(tmp_path):
    """Seventeen of the twenty notes carry rules that are not marked yet. Omitting
    them silently would read as though they hold nothing worth knowing."""
    _note(tmp_path, "MARKED.md", "## Rule\n⚠ marked\n")
    _note(tmp_path, "UNMARKED.md", "## Something\nprose only\n")
    items, unmarked = ug.collect(tmp_path)
    assert [i["file"] for i in items] == ["MARKED.md"]
    assert unmarked == ["UNMARKED.md"]
    assert "UNMARKED.md" in ug.render(items, unmarked)


def test_the_generated_file_is_never_a_source(tmp_path):
    """Reading its own output back would compound every heading on each run."""
    _note(tmp_path, ug.GUIDE_NAME, "## Looks like a rule\n⚠ but this is our own output\n")
    _note(tmp_path, "REAL.md", "## Real rule\n⚠ marked\n")
    items, unmarked = ug.collect(tmp_path)
    assert [i["file"] for i in items] == ["REAL.md"]
    assert ug.GUIDE_NAME not in unmarked


def test_entries_link_to_the_section_not_the_file(tmp_path):
    """A pointer to the top of a four-thousand-line note is not a pointer."""
    _note(tmp_path, "A-NOTES.md", "## A Node's <%i%> INLINES THE VALUE\n⚠ marked\n")
    items, unmarked = ug.collect(tmp_path)
    out = ug.render(items, unmarked)
    assert "A-NOTES.md#a-nodes-i-inlines-the-value" in out


def test_render_is_deterministic(tmp_path):
    """No clock, no ordering that shifts with an unrelated edit. A generated file that
    changes when nothing changed is one people stop reading diffs for."""
    _note(tmp_path, "A-NOTES.md", "## One\n⚠ x\n## Two\n⚠ y\n")
    _note(tmp_path, "B-NOTES.md", "## Three\n⚠ z\n")
    first = ug.render(*ug.collect(tmp_path))
    second = ug.render(*ug.collect(tmp_path))
    assert first == second


def test_clean_strips_the_marker_without_leaving_its_hole(tmp_path):
    assert ug._clean("DTO casing ⚠ ( bites parsers)") == "DTO casing (bites parsers)"
    assert ug._clean("A rule (verified 2026-06-24)") == "A rule"


def test_the_live_guide_is_current():
    """The guard that makes this worth having: a note changed and nobody rebuilt."""
    items, unmarked = ug.collect()
    expected = ug.render(items, unmarked)
    on_disk = (ug.TOOL_DIR / ug.GUIDE_NAME).read_text(encoding="utf-8")
    assert on_disk == expected, (
        "PROCESIO-USAGE-GUIDE.md is stale - run "
        "`python scripts/run-tool.py procesio usage-guide`")
