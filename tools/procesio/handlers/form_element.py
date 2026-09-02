"""Surgical read/write of ONE element's plain configs on a live form.

Third member of the surgical family, after form_code.py (Data.code) and
form_events.py (one element's event handlers), and it exists for the same reason:
`form-edit` is a DESIRED-STATE editor that rebuilds the whole DTO from a config,
so using it to change one paragraph's HTML on a large hand-authored form means
re-declaring every element or losing them.

What this pair covers that the other two do not: the SEMANTIC configs — `label`,
`placeholder`, `required`, `regex`, `visible`, `tooltip`, `info-text`,
`defaultValue`. Content and per-field rules belong in the DTO, not in the
form-level JS layer: a paragraph rewritten from JavaScript is invisible in the
designer, has to be re-applied on every render, and fights the runtime's own
MutationObserver.

Two invariants this handler holds, both load-bearing (see FORM-DEV-GUIDE/01):

1. **It only ever overwrites configs that already exist.** Adding a config key
   would also require a matching data-model attribute whose id equals the new
   config's id; without it the process designer renders raw guids and values
   never flow. Refusing the write is the honest failure — silently creating a
   half-wired config is not.
2. **Config ids are preserved.** The data-model mirror addresses each attribute
   by the element's own config id, so a fresh id on a rewritten config breaks
   every value path that points at it.

`form-set-element-config` always returns the PREVIOUS value of every config it
touched, so an overwrite is recoverable from the tool output alone.
"""
from __future__ import annotations

import argparse
import json

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body
from tools.procesio.handlers.form_events import _cfg, _find_element

# Event configs are a different shape (`{debounce, events:[…]}`) with their own
# resolution rules — process-variable names to guids, one event per trigger. They
# go through form-set-element-event, which knows those rules; routing them here
# would let a caller write a mapping row the designer cannot render.
def _is_event_key(key: str) -> bool:
    return key.startswith("on") and key.endswith("Events")


def _parse_value(raw: str):
    """JSON first, plain string as the fallback.

    `--set required=true` should store the boolean, and `--set label=<p>Hi</p>`
    the string. Trying JSON first and falling back covers both without asking the
    caller to quote every scalar.
    """
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _split_assignment(item: str, label: str) -> tuple[str, str]:
    if "=" not in item:
        raise UsageError(f"--{label} expects key=value, got {item!r}")
    key, _, value = item.partition("=")
    key = key.strip()
    if not key:
        raise UsageError(f"--{label} expects a config key before '=', got {item!r}")
    return key, value


# -- actions -----------------------------------------------------------------

def get_element(client, args) -> dict:
    form = _fetch(client, args.id)
    elements = form["data"].get("elements") or []
    el = _find_element(elements, args.element)
    configs = el.get("configs") or []
    wanted = set(args.key or [])
    return {
        "form_id": args.id,
        "element_id": el.get("id"),
        "type": el.get("type"),
        "parent_id": el.get("parentId"),
        "section": el.get("section"),
        "configs": {
            c.get("key"): c.get("value")
            for c in configs
            if not wanted or c.get("key") in wanted
        },
        "config_keys": [c.get("key") for c in configs],
    }


def set_element_config(client, args) -> dict:
    updates: dict[str, object] = {}
    for item in args.set or []:
        key, raw = _split_assignment(item, "set")
        updates[key] = _parse_value(raw)
    for item in args.set_file or []:
        key, path = _split_assignment(item, "set-file")
        with open(path, encoding="utf-8") as f:
            updates[key] = f.read()
    if not updates:
        raise UsageError("nothing to set: pass --set key=value and/or --set-file key=path")

    bad = sorted(k for k in updates if _is_event_key(k))
    if bad:
        raise UsageError(
            f"{', '.join(bad)} are event configs; wire them with form-set-element-event, "
            f"which resolves process-variable names to guids and enforces one event per trigger")

    form = _fetch(client, args.id)
    elements = form["data"].get("elements") or []
    el = _find_element(elements, args.element)

    # Refuse BEFORE writing anything: a config this element does not carry has no
    # data-model attribute behind it, and creating one here would wire it only
    # half-way (see the module docstring).
    missing = sorted(k for k in updates if _cfg(el, k) is None)
    if missing:
        raise UsageError(
            f"element {args.element!r} has no config {', '.join(missing)}; "
            f"it carries {', '.join(c.get('key') for c in el.get('configs') or [])}")

    previous = {}
    for key, value in updates.items():
        c = _cfg(el, key)
        previous[key] = c.get("value")
        c["value"] = value          # the config's own id is preserved

    result = {
        "form_id": args.id,
        "element_id": el.get("id"),
        "type": el.get("type"),
        "set": updates,
        "previous": previous,
        "elements": len(elements),
    }
    if args.dry_run:
        return {"dry_run": True, **result}

    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    client.put("/api/FormTemplate", build_put_body(form, data=form["data"]))
    return {"updated": True, "concurrency": guard, **result}


def _get_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--element", required=True,
                   help="element id, or its `name` config as the designer shows it")
    p.add_argument("--key", action="append",
                   help="only return this config key (repeatable; default: all)")


def _set_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--element", required=True,
                   help="element id, or its `name` config as the designer shows it")
    p.add_argument("--set", action="append",
                   help="key=value to write (repeatable); the value is parsed as JSON "
                        "when it parses, otherwise stored as a plain string. A value that "
                        "LOOKS like JSON (true/42/[..]) is stored as that type — for a "
                        "literal string that looks like JSON, use --set-file (always a string)")
    p.add_argument("--set-file", dest="set_file", action="append",
                   help="key=path to write a config's value from a file (repeatable) — "
                        "for long HTML labels")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="report the change (and the previous values) without writing")
    add_force_arg(p)


ACTIONS = {
    "form-get-element": ActionDef(
        func=get_element, add_args=_get_args, needs_client=True,
        description="Read one element's configs from a live form (id or name).",
    ),
    "form-set-element-config": ActionDef(
        func=set_element_config, add_args=_set_args, needs_client=True,
        description="Set one element's plain configs in place (surgical: only that "
                    "element's config values change, ids preserved; returns the previous "
                    "values). Event configs go through form-set-element-event.",
    ),
}
