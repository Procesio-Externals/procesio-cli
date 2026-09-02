"""Read the bundled PROCESIO endpoint index (data/endpoints.json).

The index is generated from the live Web-API Swagger (v1.19) at build time and
shipped with the tool so `list-endpoints` works offline and deterministically.
Each entry: {method, path, tag, summary, params, body}.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "endpoints.json"


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


def all_endpoints() -> list[dict]:
    return list(_load().get("endpoints", []))


def meta() -> dict:
    d = _load()
    return {k: d[k] for k in ("source", "openapi", "version", "count") if k in d}


def tags() -> list[str]:
    return sorted({e["tag"] for e in all_endpoints()})


def find(filter_text: str | None = None, tag: str | None = None,
         method: str | None = None) -> list[dict]:
    out = all_endpoints()
    if tag:
        tl = tag.lower()
        out = [e for e in out if e["tag"].lower() == tl]
    if method:
        ml = method.upper()
        out = [e for e in out if e["method"] == ml]
    if filter_text:
        ft = filter_text.lower()
        out = [
            e for e in out
            if ft in e["path"].lower()
            or ft in e["tag"].lower()
            or ft in (e.get("summary") or "").lower()
        ]
    return out
