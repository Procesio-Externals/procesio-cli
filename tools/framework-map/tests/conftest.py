"""Module loading for the framework-map tool (hyphenated dir).

The dir name has a hyphen, so modules can't be imported as
``tools.framework-map.*``. The tool's own modules are already fm_-prefixed
(fm_builder / fm_strings / fm_ro_catalog), so they import cleanly by bare name
once the tool root is on sys.path and never collide with other tools. Only
main.py needs an alias (``fm_main``) to avoid clashing with other tools' main.py
during a full-suite run.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(FRAMEWORK_ROOT), str(TOOL_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, str(TOOL_ROOT / filename))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# main.py imports fm_builder, which imports fm_strings + fm_ro_catalog by name
# (resolved via TOOL_ROOT on sys.path). Load main under a unique alias.
_load("fm_main", "main.py")
