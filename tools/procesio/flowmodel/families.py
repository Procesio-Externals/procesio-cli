"""Action-family classification (shared by inspect-flow and catalog --by-family).

Loads the curated dto/data/action_families.json. An action not in the map is "other".
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "dto" / "data" / "action_families.json"


@lru_cache(maxsize=1)
def _table() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def families() -> list[str]:
    return list(_table().get("families", []))


def classify(name: str | None) -> str:
    if not name:
        return "other"
    entry = _table().get("actions", {}).get(name.strip())
    return entry["family"] if entry else "other"


def describe(name: str | None) -> str | None:
    if not name:
        return None
    entry = _table().get("actions", {}).get(name.strip())
    return entry["desc"] if entry else None
