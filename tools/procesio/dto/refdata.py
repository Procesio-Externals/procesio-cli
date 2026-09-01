"""Bundled platform reference data + lookups for the DTO builders.

The builders are PURE (config -> DTO, no network). Anything they need from the
platform that is *stable* (primitive data-type ids, procesio built-in models)
ships bundled in data/platform_types.json so a build needs no live calls. Live,
workspace-specific ids (a credential template, an existing data model referenced
by a webhook, an action template's properties) are resolved by the handler and
passed into the builder as `ctx`, keeping the builder side-effect free.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent / "data" / "platform_types.json"

# PrimaryDataType enum (Domain/Enums) — the value carried as CsharpCorrespondent.
CSHARP = {
    "boolean": 10, "integer": 20, "float": 30, "double": 40, "string": 50,
    "date": 60, "relationship": 70, "time": 80, "datetime": 90, "guid": 100,
    "uri": 110, "json": 120, "credentials": 130, "object": 140,
}


@lru_cache(maxsize=1)
def platform_types() -> dict:
    return json.loads(_DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _primitive_by_name() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in platform_types().get("primary", []):
        if d.get("name"):
            out[d["name"].strip().lower()] = d
    return out


@lru_cache(maxsize=1)
def _procesio_by_name() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for d in platform_types().get("procesio", []):
        if d.get("name"):
            out[d["name"].strip().lower()] = d
    return out


# Friendly aliases -> the platform's primitive type name.
_ALIAS = {
    "bool": "boolean", "int": "integer", "long": "integer", "number": "double",
    "text": "string", "str": "string", "datetime": "datetime", "date-time": "datetime",
    "uuid": "guid",
}


def primitive_type_id(name: str) -> str:
    """Map a primitive type name (case-insensitive, with aliases) to its stable
    platform DataType id. Raises KeyError for an unknown type."""
    key = (name or "").strip().lower()
    key = _ALIAS.get(key, key)
    prim = _primitive_by_name()
    if key in prim:
        return prim[key]["id"]
    raise KeyError(
        f"unknown primitive type {name!r}; known: {sorted(prim)} (aliases: {sorted(_ALIAS)})"
    )


def primitive_names() -> list[str]:
    """The accepted primitive type names (for schema enums)."""
    return sorted(set(_primitive_by_name()) | set(_ALIAS))


def csharp_correspondent(name: str) -> int:
    key = (name or "").strip().lower()
    key = _ALIAS.get(key, key)
    return CSHARP.get(key, 0)


def procesio_model_id(name: str) -> str:
    """Id of a procesio built-in data model (e.g. 'FileDataModel')."""
    by = _procesio_by_name()
    key = (name or "").strip().lower()
    if key in by:
        return by[key]["id"]
    raise KeyError(f"unknown procesio model {name!r}; known: {sorted(by)}")
