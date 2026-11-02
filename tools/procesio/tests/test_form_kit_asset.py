"""Guards the form kit (assets/form-kit): the CSS effects gate and the composed runtime.

The JS runs in a browser, so the check here is that the pieces compose into one valid script
and carry no client data. The composed script is parsed by `node --check`, skipped when no
`node` binary is on PATH.
"""
from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "assets" / "form-kit"


def _gate():
    spec = importlib.util.spec_from_file_location("effects_gate", KIT / "effects_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FRAMES = "@keyframes pulse{to{opacity:.5}}@keyframes rise{to{opacity:1}}@keyframes kit-spin{to{opacity:1}}"


def test_a_repeating_animation_gets_a_twin_that_stops_it():
    loop, _ = _gate().gates(FRAMES + ".a{animation:pulse 2s infinite}")
    assert loop == 'html[data-kit-fx-loop="0"] .a{animation:none!important}'


def test_the_finite_part_of_a_mixed_animation_keeps_running():
    loop, _ = _gate().gates(FRAMES + ".a{animation:rise .3s both,pulse 2s infinite}")
    assert loop == 'html[data-kit-fx-loop="0"] .a{animation:rise .3s both!important}'


def test_a_loop_that_reports_progress_is_left_alone():
    loop, _ = _gate().gates(FRAMES + ".a{animation:kit-spin 1s linear infinite}")
    assert loop == ""


def test_a_finite_animation_gets_no_twin():
    loop, _ = _gate().gates(FRAMES + ".a{animation:rise .3s both}")
    assert loop == ""


def test_a_twin_stays_inside_the_media_query_of_its_source():
    loop, _ = _gate().gates(FRAMES + "@media (max-width:760px){.a{animation:pulse 2s infinite}}")
    assert loop == '@media (max-width:760px){html[data-kit-fx-loop="0"] .a{animation:none!important}}'


def test_the_lowest_tier_is_the_forms_own_reduced_motion():
    _, motion = _gate().gates("@media (prefers-reduced-motion: reduce){.a{transition:none}}")
    assert motion == 'html[data-kit-fx-motion="0"] .a{transition:none}'


def test_prefix_and_functional_names_are_the_callers():
    loop, _ = _gate().gates(FRAMES + ".a{animation:pulse 2s infinite}.b{animation:rise 1s infinite}",
                            prefix="x", functional=("rise",))
    assert loop == 'html[data-x-fx-loop="0"] .a{animation:none!important}'


def test_a_rule_on_html_keeps_the_attribute_on_html():
    loop, _ = _gate().gates(FRAMES + "html.on .a{animation:pulse 2s infinite}")
    assert loop == 'html[data-kit-fx-loop="0"].on .a{animation:none!important}'


def _composed() -> str:
    js = (KIT / "runtime.template.js").read_text(encoding="utf-8")
    assert "/*@@KIT@@*/" in js
    return js.replace("/*@@KIT@@*/", (KIT / "core.js").read_text(encoding="utf-8") + (KIT / "effects.js").read_text(encoding="utf-8"))


def test_the_pieces_compose_into_one_valid_script(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("no node on PATH")
    f = tmp_path / "form.js"
    f.write_text(_composed(), encoding="utf-8")
    r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[:600]


def test_every_function_the_runtime_calls_comes_with_the_kit():
    js = _composed()
    for name in ("make", "byId", "runOf", "propagateScope", "ensureCritical", "setAttr", "now", "toast"):
        assert re.search(r"function " + name + r"\(", js), name
    assert "var FX = " in js


def test_the_kit_stays_neutral():
    # the kit is shared and exported: tokens and text only, no client's brand or identifiers
    guid = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    for f in KIT.iterdir():
        if f.suffix not in {".js", ".css", ".py"}:
            continue
        text = f.read_text(encoding="utf-8")
        assert not re.search(r"\bmet-|\bMET\b", text), f.name
        assert not guid.search(text), f.name
        assert not re.search(r"[ăâîșțĂÂÎȘȚ]", text), f.name


def test_the_runtime_composes_from_all_three_pieces_without_a_js_engine():
    """A Python-side smoke test so the compose is exercised even where the node --check above only
    skips (a box with no node on PATH): the template keeps exactly one insertion point, both core
    and effects land in full, and nothing is dropped. It checks composition integrity, not JS
    syntax - node --check stays the syntax gate when node is present."""
    tmpl = (KIT / "runtime.template.js").read_text(encoding="utf-8")
    core = (KIT / "core.js").read_text(encoding="utf-8")
    effects = (KIT / "effects.js").read_text(encoding="utf-8")
    assert tmpl.count("/*@@KIT@@*/") == 1               # one, well-defined insertion point
    assert core.strip() and effects.strip()             # neither piece is empty or truncated to nothing
    composed = _composed()
    assert core in composed and effects in composed     # both pieces landed in full
    assert len(composed) == len(tmpl) - len("/*@@KIT@@*/") + len(core) + len(effects)
