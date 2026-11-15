"""The form shell's theme is the designer's own getDefaultTheme(), and overrides of a
variable it does not define are reported instead of dropped without a word.

Before 2026-11 the shell was 18 groups behind the designer's 23 and 69 variables short,
among them every Document Signing variable, and `theme` overrides of those were ignored.
"""
import json
import uuid

from tools.procesio.dto.form import builder, sync_theme
from tools.procesio.handlers import dto_actions  # noqa: F401  (the action wiring under test)
from tools.procesio import main


def _ctx():
    return {"new_id": lambda: str(uuid.uuid4()), "_build_warnings": []}


def _cfg(**extra):
    return {"name": "F", "elements": [{"type": "input", "label": "X"}], **extra}


def _value(dto, cssvar, mode="light"):
    for g in dto["Data"]["theme"]:
        for p in builder._group_props(g, mode):
            if p.get("cssVariable") == cssvar:
                return p["value"]
    return None


def test_the_shell_records_the_designer_tag_it_came_from():
    note = json.loads(sync_theme.SOURCE_NOTE.read_text(encoding="utf-8"))
    assert note["ui_builder"].startswith("v0.")          # the designer's (legacy) line
    shell = json.loads(sync_theme.SHELL.read_text(encoding="utf-8"))["theme"]
    assert [g["label"] for g in shell] == note["groups"]
    assert len(sync_theme.css_variables(shell)) == note["variables"]


def test_document_signing_and_dropdown_groups_are_in_the_shell():
    labels = {g["label"] for g in builder._shell()["theme"]}
    assert {"Document Signing", "Dropdown", "Column", "Step", "Tab"} <= labels


def test_an_override_of_a_newer_variable_reaches_the_form():
    dto = builder.build(_cfg(theme={"--c-signing-accent": "#123456",
                                    "pds-text-muted": "#654321"}), _ctx())
    assert _value(dto, "--c-signing-accent") == "#123456"
    assert _value(dto, "--pds-text-muted") == "#654321"   # a Colors (light side) variable


def test_theme_dark_changes_only_the_dark_side():
    dto = builder.build(_cfg(themeDark={"--c-primary": "#000000"}), _ctx())
    assert _value(dto, "--c-primary", "dark") == "#000000"
    assert _value(dto, "--c-primary", "light") != "#000000"


def test_an_unknown_variable_is_reported_not_dropped_silently():
    ctx = _ctx()
    dto = builder.build(_cfg(theme={"--c-primary": "#111111", "--not-a-var": "1px"},
                             themeDark={"--nor-this": "#000"}), ctx)
    assert _value(dto, "--c-primary") == "#111111"
    joined = " ".join(ctx["_build_warnings"])
    assert "--not-a-var" in joined and "--nor-this" in joined and "--c-primary" not in joined


def test_a_known_override_gives_no_warning():
    ctx = _ctx()
    builder.build(_cfg(theme={"--c-primary": "#111111"}), ctx)
    assert ctx["_build_warnings"] == []


def test_form_create_dry_run_returns_the_theme_warning():
    out = main.dispatch("form-create", ["--dry-run", "--config",
                                        json.dumps(_cfg(theme={"--typo-var": "1"}))],
                        client_builder=lambda prof: None)
    assert any("--typo-var" in w for w in out.get("warnings", []))
