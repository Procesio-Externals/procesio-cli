"""Single dispatch point selecting the canvas layout engine via a config flag.

The legacy engine (`engine.layout`) is the DEFAULT and is unchanged. The ELK 'layered'
engine (`elk_engine.layout`) is opt-in. Both have the identical signature, so this is a
clean either/or with no other code path aware of the choice.

Flag: the LAYOUT_ENGINE environment variable (following the env-var config precedent in
config.py). Values:
    legacy  (default) -> engine.layout
    elk               -> elk_engine.layout
Unset, blank, or any unrecognised value -> legacy. Not user-facing: no CLI arg, no UI.
"""
from __future__ import annotations

import os
import sys

from tools.procesio.layout import elk_engine, engine

LEGACY = "legacy"
ELK = "elk"
_FLAG_ENV = "LAYOUT_ENGINE"


def selected_engine() -> str:
    """The engine name the flag resolves to: 'elk' only for an explicit valid value, else
    'legacy' (unset / blank / unrecognised all fall back to legacy)."""
    val = (os.environ.get(_FLAG_ENV) or "").strip().lower()
    return ELK if val == ELK else LEGACY


def layout(nodes: list[dict], edges: list[dict], opts: dict | None = None,
           subset: list[str] | None = None) -> dict:
    """Lay out a node/edge graph with the flag-selected engine. Same signature and return
    contract as engine.layout / elk_engine.layout, so callers are engine-agnostic."""
    if selected_engine() == ELK:
        print(f"[layout] LAYOUT_ENGINE={ELK} → ELK 'layered' engine", file=sys.stderr)
        return elk_engine.layout(nodes, edges, opts=opts, subset=subset)
    return engine.layout(nodes, edges, opts=opts, subset=subset)
