"""Non-blocking safety lints for a form's Data DTO.

These encode form-build traps that the server ACCEPTS silently and that then cost
a debugging session to find (see PROCESIO-API-NOTES.md and FORM-DEV-GUIDE/08):

* **Phantom parentId** — an element whose `parentId` matches no element id renders
  on NO pane. Tab/container membership is by `parentId` = a container element's id;
  a dangling one is invisible, not an error (O6).
* **Duplicate id/name configs** — two elements sharing the designer `id` or `name`
  config collide for selectors and process mapping.
* **Patch wrapping mistake** — a form-update `--data` patch whose top-level key is
  not an existing Data field is merged in as an inert junk key; the classic case is
  wrapping the patch as `{"Data": {...}}` (O7).
* **Multiple-select without isList** — a select with `multiple=true` whose `value`
  config is not marked `isList` maps a list into a scalar.

Pure and side-effect-free: each returns a list of human-readable warning strings.
Warnings, never blockers — the caller attaches them to its result JSON.
"""
from __future__ import annotations

from typing import Any


def _elements(data: Any) -> list:
    if isinstance(data, dict):
        els = data.get("elements")
        if isinstance(els, list):
            return els
    return []


def _cfg_value(element: dict, key: str):
    for c in element.get("configs") or []:
        if isinstance(c, dict) and c.get("key") == key:
            return c.get("value")
    return None


def _cfg(element: dict, key: str):
    for c in element.get("configs") or []:
        if isinstance(c, dict) and c.get("key") == key:
            return c
    return None


def _label(element: dict) -> str:
    """Best identifier for a message: the designer name, else the element id."""
    name = _cfg_value(element, "name")
    if isinstance(name, str) and name.strip():
        return f"{name.strip()!r}"
    return f"id {element.get('id')!r}"


def lint_phantom_parent(data: Any) -> list[str]:
    els = _elements(data)
    ids = {e.get("id") for e in els if isinstance(e, dict)}
    out = []
    for e in els:
        if not isinstance(e, dict):
            continue
        pid = e.get("parentId")
        if pid not in (None, "") and pid not in ids:
            out.append(
                f"element {_label(e)} has parentId {pid!r} matching no element on the "
                f"form — it renders on NO pane (dangling container reference). Point it "
                f"at a real container/tab element id, or set parentId to null for a "
                f"top-level element.")
    return out


def lint_duplicate_configs(data: Any) -> list[str]:
    els = _elements(data)
    out = []
    for cfg_key in ("id", "name"):
        seen: dict[str, int] = {}
        for e in els:
            if not isinstance(e, dict):
                continue
            val = _cfg_value(e, cfg_key)
            if isinstance(val, str) and val.strip():
                seen[val.strip()] = seen.get(val.strip(), 0) + 1
        for val, n in seen.items():
            if n > 1:
                out.append(
                    f"{n} elements share the same {cfg_key} config {val!r}; a duplicate "
                    f"{cfg_key} collides for CSS/JS selectors and process mapping — make "
                    f"each element's {cfg_key} unique.")
    return out


def lint_multiple_select_islist(data: Any) -> list[str]:
    els = _elements(data)
    out = []
    for e in els:
        if not isinstance(e, dict):
            continue
        multiple = _cfg_value(e, "multiple")
        if multiple is True or (isinstance(multiple, str) and multiple.lower() == "true"):
            value_cfg = _cfg(e, "value") or {}
            is_list = value_cfg.get("isList") if isinstance(value_cfg, dict) else None
            if not is_list:
                out.append(
                    f"element {_label(e)} is a multiple-select (multiple=true) but its "
                    f"value config is not marked isList — a multi-value selection maps "
                    f"into a scalar. Set isList on the value config / the mapped "
                    f"data-model attribute.")
    return out


def lint_patch_keys(existing_data: Any, patch: Any) -> list[str]:
    """A form-update --data patch whose top-level key is not an existing Data field
    is added as a (probably inert) junk key. Flags the classic `{"Data": {...}}`
    wrapping mistake explicitly."""
    if not isinstance(patch, dict) or not isinstance(existing_data, dict):
        return []
    known = set(existing_data.keys())
    out = []
    for k in patch:
        if k in known:
            continue
        if k.lower() == "data":
            out.append(
                f"patch top-level key {k!r} is not a Data field — this is almost "
                f"certainly the wrapping mistake: pass the INNER fields directly (e.g. "
                f'--data \'{{"hideBranding": true}}\'), not wrapped as {{{k!r}: {{...}}}}. '
                f"As written it creates an inert junk key that changes nothing.")
        else:
            sample = ", ".join(sorted(known)[:8]) or "(none)"
            out.append(
                f"patch top-level key {k!r} is not an existing Data field — it will be "
                f"ADDED as a new key (no existing value is changed). Existing fields "
                f"include: {sample}. Check for a typo/casing mismatch.")
    return out


def lint_form_data(data: Any) -> list[str]:
    """All structural (element-level) lints for a form's Data."""
    return (lint_phantom_parent(data)
            + lint_duplicate_configs(data)
            + lint_multiple_select_islist(data))
