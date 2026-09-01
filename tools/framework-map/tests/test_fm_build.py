"""Build the map from the live registry and assert its structure + invariants."""
from __future__ import annotations

from pathlib import Path

import pytest

import fm_builder

FRAMEWORK_ROOT = Path(fm_builder.__file__).resolve().parents[2]


def test_stats_only_shape():
    s = fm_builder.stats_only(FRAMEWORK_ROOT)
    for key in ("tools", "agents", "skills", "actions", "tool_actions",
                "agent_actions", "categories", "uncategorized", "ro_untranslated"):
        assert key in s
    # Deliberately not a census (">= 39 tools"): that asserted the contents of one
    # checkout rather than the behaviour of the builder, so it failed in any
    # distribution of the framework that ships a different set. What must hold is
    # that the registry produced something of each kind and that the totals agree.
    assert s["tools"] >= 1 and s["agents"] >= 1
    assert s["actions"] == s["tool_actions"] + s["agent_actions"]


def test_every_tool_is_categorized():
    # a new tool with no CAT entry falls into "Other"; keep the map curated.
    s = fm_builder.stats_only(FRAMEWORK_ROOT)
    assert s["uncategorized"] == [], f"uncategorized tools: {s['uncategorized']}"


def test_catalog_fully_translated_to_ro():
    # adding a tool/agent/skill without an RO catalog translation shows up here;
    # `framework-map check` lists exactly what to translate.
    s = fm_builder.stats_only(FRAMEWORK_ROOT)
    assert s["ro_untranslated"] == {}, f"missing RO translations: {s['ro_untranslated']}"


def test_build_html_structure():
    html, stats = fm_builder.build_html(FRAMEWORK_ROOT)
    assert html.startswith("<!DOCTYPE html>")
    assert html.rstrip().endswith("</html>")
    # both datasets embedded + language toggle present
    assert "const DATA=" in html and "const DATA_RO=" in html and "const LBL=" in html
    assert 'data-lang="ro"' in html and "lang-ro" in html
    # self-contained: no external resource references
    assert 'href="http' not in html and 'src="http' not in html
    # counts made it into the page
    assert "{:,}".format(stats["tools"]) in html


def test_no_unresolved_template_tokens():
    html, _ = fm_builder.build_html(FRAMEWORK_ROOT)
    # narrative placeholders ($svg_*, $NTOOLS, $uc1_h, $footer ...) must all be
    # substituted. ($filter can legitimately appear inside embedded manifest text.)
    import re
    body = html.split("const DATA=", 1)[0]  # ignore the embedded JSON payload
    leftover = set(re.findall(r"\$[A-Za-z_]{2,}", body))
    assert not leftover, f"unresolved template tokens: {sorted(leftover)}"


def test_marker_ids_unique_per_language():
    html, _ = fm_builder.build_html(FRAMEWORK_ROOT)
    # The arrowheads live in the architecture diagram, which is part of the
    # narrative a distribution may not ship. Where there is no diagram there is
    # nothing to assert; where there is one, the markers must be per-language or
    # the RO arrows reference a hidden EN marker and vanish.
    if "<marker" not in html:
        pytest.skip("this distribution does not ship the architecture diagram")
    assert 'id="ahg-en"' in html and 'id="ahg-ro"' in html
    assert "url(#ahg-ro)" in html and "url(#ahg-en)" in html


# -- structural + reference guards (build once, reuse) ------------------------

_CACHE: dict = {}


def _built():
    if "html" not in _CACHE:
        _CACHE["html"], _ = fm_builder.build_html(FRAMEWORK_ROOT)
        # everything before the embedded JSON payload is the real markup
        _CACHE["body"] = _CACHE["html"].split("const DATA=", 1)[0]
    return _CACHE


def test_section_and_div_tags_balanced():
    # a dropped closing tag orphans every later section (this actually happened);
    # balance is the cheapest guard that would have caught it immediately.
    body = _built()["body"]
    assert body.count("<section") == body.count("</section>"), "unbalanced <section> tags"
    assert body.count("<div") == body.count("</div>"), "unbalanced <div> tags"


def test_nav_links_resolve_to_sections():
    import re
    html = _built()["html"]
    hrefs = set(re.findall(r'<a href="#([\w-]+)"', html))
    targets = (set(re.findall(r'id="([\w-]+)"', html))
               | set(re.findall(r'data-sec="([\w-]+)"', html)))
    missing = hrefs - targets
    assert not missing, f"nav links with no matching section: {missing}"


def test_narrative_references_resolve():
    # use-case chips + the generated schedule note reference agents/tools by name
    # via data-ujump; a rename/removal must not leave a dead pointer.
    import re
    body = _built()["body"]
    refs = set(re.findall(r'data-ujump="([\w-]+)"', body))
    dump = fm_builder.compress(fm_builder.extract(FRAMEWORK_ROOT))
    real = ({t["name"] for t in dump["tools"]}
            | {a["name"] for a in dump["agents"]} | {"__none__"})
    unknown = refs - real
    assert not unknown, f"data-ujump references a non-existent capability: {unknown}"


def test_schedule_note_generated_from_yaml():
    # the 'Live today' note is derived from schedule.yaml, not hardcoded. When a
    # schedule exists it names the real target agents; the fallback is generic.
    note_en = fm_builder._schedule_note("en")
    if note_en is None:  # fresh/wiped install -> fallback path
        assert "schedule.yaml" in fm_builder._SCHED_FALLBACK["en"]
    else:
        assert note_en.startswith("<b>Live today:</b>")
        assert 'data-ujump=' in note_en
