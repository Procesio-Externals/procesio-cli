"""Regenerate the form shell's default theme from ui-builder's own `getDefaultTheme()`.

The theme a form carries is whatever the designer saved when the form was created: the
array `getDefaultTheme()` returns in `src/js/model/config/theme.ts` of the ui-builder the
DESIGNER pins. The builder starts every API-built form from `data_shell.json`, and
`_apply_theme` only changes variables that already exist there, so a shell older than the
designer silently drops every override of a newer variable (seen 2026-11: 69 variables and
five groups missing, among them all of Document Signing).

`theme.ts` is TypeScript with helper functions, spreads and enum members, so it is not
parsed here: it is RUN with Node (`--experimental-transform-types`, Node 22.7+), with the
two enums it imports inlined from the same tag. The output is exactly the designer's array.

    python -m tools.procesio.dto.form.sync_theme --source <dir> --tag v0.194.0 [--write]

`--source` is a directory holding `src/js/model/config/theme.ts`,
`src/js/model/config/index.ts` and `src/js/model/element/index.ts` of that tag
(`procesio-release ui-builder-sync` extracts them from the clone and calls `evaluate`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DIR = Path(__file__).resolve().parent
SHELL = DIR / "data_shell.json"
SOURCE_NOTE = DIR / "theme_source.json"

THEME_TS = "src/js/model/config/theme.ts"
CONFIG_TS = "src/js/model/config/index.ts"
ELEMENT_TS = "src/js/model/element/index.ts"


class ThemeSyncError(RuntimeError):
    pass


def _enum_block(text: str, name: str) -> str:
    m = re.search(r"export enum " + name + r"\s*\{.*?\n\}", text, re.S)
    if not m:
        raise ThemeSyncError(f"enum {name} not found")
    return m.group(0)


def evaluate(theme_ts: str, config_ts: str, element_ts: str) -> list:
    """The array `getDefaultTheme()` returns, evaluated by Node."""
    node = shutil.which("node")
    if not node:
        raise ThemeSyncError("node is not on PATH (Node 22.7+ is needed to run theme.ts)")
    body = re.sub(r"^import .*?;\s*$", "", theme_ts.replace("\r\n", "\n"), flags=re.M)
    src = "\n".join([_enum_block(config_ts, "ElementConfigType"),
                     _enum_block(element_ts, "ElementType"),
                     "type OptionValue = any;", body,
                     "console.log(JSON.stringify(getDefaultTheme()));"])
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "theme.mts"
        script.write_text(src, encoding="utf-8")
        r = subprocess.run([node, "--experimental-transform-types", "--no-warnings", str(script)],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise ThemeSyncError(f"node could not evaluate theme.ts: {r.stderr.strip()[:800]}")
    theme = json.loads(r.stdout)
    if not isinstance(theme, list) or not all(isinstance(g, dict) and "label" in g for g in theme):
        raise ThemeSyncError("getDefaultTheme() did not return a list of groups")
    return theme


def css_variables(theme: list) -> set[str]:
    """Every cssVariable a theme defines; a {light, dark} group counts its light side."""
    out: set[str] = set()
    for g in theme or []:
        props = g.get("properties")
        if isinstance(props, dict):
            props = props.get("light") or []
        out |= {p["cssVariable"] for p in props or [] if isinstance(p, dict) and p.get("cssVariable")}
    return out


def write(theme: list, tag: str, theme_ts: str) -> dict:
    """Replace the shell's theme (only that key) and record where it came from."""
    shell = json.loads(SHELL.read_text(encoding="utf-8"))
    before = css_variables(shell.get("theme"))
    shell["theme"] = theme
    SHELL.write_text(json.dumps(shell, ensure_ascii=False), encoding="utf-8", newline="\n")
    note = {"ui_builder": tag, "file": THEME_TS,
            "sha256": hashlib.sha256(theme_ts.replace("\r\n", "\n").encode("utf-8")).hexdigest(),
            "groups": [g["label"] for g in theme], "variables": len(css_variables(theme))}
    SOURCE_NOTE.write_text(json.dumps(note, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8", newline="\n")
    after = css_variables(theme)
    return {**note, "added": sorted(after - before), "removed": sorted(before - after)}


def source_tag() -> str | None:
    """The ui-builder tag the shell theme was generated from, if recorded."""
    try:
        return json.loads(SOURCE_NOTE.read_text(encoding="utf-8")).get("ui_builder")
    except (OSError, ValueError):
        return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, help="directory holding the three ui-builder files")
    p.add_argument("--tag", required=True, help="the ui-builder tag they come from, e.g. v0.194.0")
    p.add_argument("--write", action="store_true", help="write data_shell.json and theme_source.json")
    a = p.parse_args(argv)
    src = Path(a.source)
    texts = [(src / f).read_text(encoding="utf-8") for f in (THEME_TS, CONFIG_TS, ELEMENT_TS)]
    theme = evaluate(*texts)
    if a.write:
        out = write(theme, a.tag, texts[0])
    else:
        shell = css_variables(json.loads(SHELL.read_text(encoding="utf-8")).get("theme"))
        new = css_variables(theme)
        out = {"ui_builder": a.tag, "groups": len(theme), "variables": len(new),
               "added": sorted(new - shell), "removed": sorted(shell - new), "written": False}
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
