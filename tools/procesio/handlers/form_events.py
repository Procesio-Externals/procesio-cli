"""Surgical read/write of ONE element's event list on a live form.

Companion to form_code.py, and it exists for the same reason: `form-edit` is a
DESIRED-STATE editor that rebuilds the whole DTO from a config, so using it to
wire a single button or upload on a large hand-authored form means re-declaring
every element or losing them. These actions do a read-modify-write on the LIVE
DTO and touch ONLY the target element's event config.

The event model (see PROCESIO-RESOURCE-MODEL-NOTES.md): each element carries
per-trigger configs — `onClickEvents`, `onInputEvents`, `onStepChangeEvents`,
`onPaginationChangedEvents` — whose value is `{debounce, events:[…]}`. A fresh
element has the key present with a `null` value, which is what "no handler" looks
like; it is not an error and not a missing field.

The trap this action exists to prevent: in a RUN_PROCESS `inputMap`/`outputMap`
the PROCESS VARIABLE GUID belongs on the LEFT and the form value-path on the
right. A variable NAME on the left is accepted by the API but the designer then
renders raw guids and the launch 400s, so names are resolved to guids here and an
unknown name fails before anything is written.
"""
from __future__ import annotations

import argparse
import json
import uuid

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body

# Trigger -> (config key, event type) comes from the DTO builder's own maps, which
# were verified against the ui-builder source. Re-deriving them here would let the
# two drift, and a wrong event type is silently accepted by the API.
from tools.procesio.dto.form.builder import _EVENT_KEY, _EVENT_TYPE  # noqa: E402

ACTIONS_ALLOWED = ("RUN_PROCESS", "RUN_JAVASCRIPT", "RUN_DATA_STORE_OPERATION")

# EventAction.RUN_DATA_STORE_OPERATION (ui-builder model/config/events/index.ts): a
# form element triggers a Data Store operation, the same way RUN_PROCESS triggers a
# process. config = EventRunDataStoreOperationConfig {dataStoreId, operation, inputMap,
# outputMap, filters?, areFiltersConfigured?}. operation = DataStoreOperation
# READ/ADD/UPDATE/DELETE; filters apply to every op except ADD
# (dataStoreOperationSupportsFilters). The operation wire encoding (string vs numeric)
# must be re-verified live — pass a numeric operation via --config if the platform
# rejects the name. See PROCESIO-RESOURCE-MODEL-NOTES.md.
_DATA_STORE_OPS = ("READ", "ADD", "UPDATE", "DELETE")


def _normalize_op(raw):
    """Accept an operation as a DataStoreOperation name (case-insensitive) or a raw
    value; return the name upper-cased, or the value unchanged if not a known name."""
    if isinstance(raw, str):
        up = raw.strip().upper()
        return up if up in _DATA_STORE_OPS else raw.strip()
    return raw


def _resolve_trigger(on: str) -> tuple[str, str]:
    key = on.strip()
    friendly = key.lower().replace("-", "").replace("_", "")
    if friendly in _EVENT_KEY:
        return _EVENT_KEY[friendly], _EVENT_TYPE[friendly]
    raise UsageError(
        f"unknown trigger {on!r}; use one of {', '.join(sorted(_EVENT_KEY))}")


def _cfg(element: dict, key: str):
    for c in element.get("configs") or []:
        if c.get("key") == key:
            return c
    return None


def _find_element(elements: list, ref: str) -> dict:
    """Match by element id first, then by its `name` config (what the designer shows)."""
    for e in elements:
        if e.get("id") == ref:
            return e
    hits = []
    for e in elements:
        c = _cfg(e, "name")
        if c and str(c.get("value") or "").strip() == ref:
            hits.append(e)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise UsageError(f"no element with id or name {ref!r} on this form")
    raise UsageError(f"{len(hits)} elements are named {ref!r}; pass the element id instead")


def _process_vars(client, process_id: str) -> dict:
    """{variable name: the variable DTO}. The whole DTO, not just the id, because a map row also
    has to know whether the variable is a LIST - see _is_list_of."""
    body = client.get(f"/api/Projects/{process_id}")
    if isinstance(body, dict) and "flow" not in body and isinstance(body.get("result"), dict):
        body = body["result"]
    flow = body.get("flow") if isinstance(body, dict) else None
    src = flow if isinstance(flow, dict) else (body if isinstance(body, dict) else {})
    return {v.get("name"): v for v in (src.get("variables") or []) if v.get("name")}


def _path_of(side):
    """The attribute chain a caller supplied on this side, if any.

    A model-typed process variable is mapped one ATTRIBUTE at a time, and the
    chain lives in the row's `path`. Rebuilding the slot without carrying it over
    silently maps the whole object into a single text field instead.
    """
    return side.get("path") if isinstance(side, dict) else None


def _slot(value, is_left: bool, path=None, is_list: bool = False) -> dict:
    """One side of a map row, in the shape the DESIGNER writes.

    Verified against a live form: each side is an OBJECT, not a bare string —
    `{"value": …, "isList": …, "path": …}` — and the two sides differ, the
    process side carrying `path: {}` and the form side `path: null`. Writing bare
    strings produces a row the API accepts but the designer cannot render.

    `isList` is NOT cosmetic: a list-valued variable mapped with `isList: false` binds the whole
    result set into a single scalar slot, so the form receives nothing and there is no error to
    read. It is taken from the caller when given, else from the process variable being mapped.
    """
    if isinstance(value, dict) and "value" in value:
        return value                                  # already in wire shape
    default = {} if is_left else None
    return {"value": value, "isList": bool(is_list),
            "path": default if path is None else path}


def _is_list_of(side, variable: dict | None) -> bool:
    """Whether this side of a map row carries a LIST.

    A caller that states `isList` wins — it may be mapping one attribute out of a list. Otherwise
    the process variable's own `isList` decides, which is what the designer would have written.
    """
    if isinstance(side, dict) and "isList" in side:
        return bool(side["isList"])
    return bool((variable or {}).get("isList"))


def _plain(value):
    return value.get("value") if isinstance(value, dict) else value


def _resolve_maps(config: dict, client) -> dict:
    """Turn any process-variable NAME on the left of a map into its GUID, and put
    both sides into the designer's object shape."""
    pid = config.get("processId")
    if not pid:
        raise UsageError("RUN_PROCESS config needs a 'processId'")
    names = _process_vars(client, pid)
    by_id = {v.get("id"): v for v in names.values() if v.get("id")}
    out = dict(config)
    for side in ("inputMap", "outputMap"):
        rows = out.get(side) or []
        fixed = []
        for i, row in enumerate(rows):
            row = dict(row)
            left = _plain(row.get("left"))
            if left in by_id:
                variable = by_id[left]                # already a guid
            elif left in names:
                variable = names[left]
                left = variable.get("id")
            else:
                raise UsageError(
                    f"{side}: {left!r} is neither a variable id nor a variable name on "
                    f"process {pid}. Known variables: {', '.join(sorted(names)) or '(none)'}")
            # Both sides of a row describe the SAME value, so one list-ness governs the pair: the
            # form variable on the right holds whatever the process variable on the left produced.
            is_list = _is_list_of(row.get("left"), variable) or _is_list_of(row.get("right"), variable)
            row["left"] = _slot(left, True, _path_of(row.get("left")), is_list)
            row["right"] = _slot(_plain(row.get("right")), False,
                                 _path_of(row.get("right")), is_list)
            row["id"] = row.get("id", i)
            fixed.append(row)
        out[side] = fixed
    return out


def set_element_event(client, args) -> dict:
    cfg_key, default_type = _resolve_trigger(args.on)
    action = args.action.strip().upper()
    if action not in ACTIONS_ALLOWED:
        raise UsageError(f"--action must be one of {', '.join(ACTIONS_ALLOWED)}")

    raw = args.config
    if args.config_file:
        with open(args.config_file, encoding="utf-8") as f:
            raw = f.read()
    if raw:
        try:
            ev_config = json.loads(raw)
        except json.JSONDecodeError as e:
            raise UsageError(f"--config must be valid JSON: {e}") from e
        if not isinstance(ev_config, dict):
            raise UsageError("--config must be a JSON object")
    elif action == "RUN_DATA_STORE_OPERATION":
        ev_config = {}   # may be fully specified via --data-store-id / --operation
    else:
        raise UsageError("provide --config '<json>' or --config-file <path>")

    form = _fetch(client, args.id)
    elements = form["data"].get("elements") or []
    element = _find_element(elements, args.element)

    if action == "RUN_PROCESS":
        ev_config = _resolve_maps(ev_config, client)   # fails loudly before any write
        # Backfill the canonical RUN_PROCESS config the DTO builder always emits, so a
        # hand-written minimal {processId, inputMap, outputMap} renders configured in the
        # designer and launches — the designer reads these keys and a missing
        # areConditionsConfigured/conditions leaves the event half-wired. setdefault, so a
        # caller that passes its own value always wins.
        ev_config.setdefault("syncRun", True)
        ev_config.setdefault("mapLatestTriggerOnly", False)
        ev_config.setdefault("conditions", [])
        ev_config.setdefault("areConditionsConfigured", True)
    elif action == "RUN_DATA_STORE_OPERATION":
        if getattr(args, "data_store_id", None):
            ev_config["dataStoreId"] = args.data_store_id
        if getattr(args, "operation", None):
            ev_config["operation"] = _normalize_op(args.operation)
        if not ev_config.get("dataStoreId"):
            raise UsageError("RUN_DATA_STORE_OPERATION needs a dataStoreId "
                             "(--data-store-id or in --config)")
        if ev_config.get("operation") in (None, ""):
            raise UsageError("RUN_DATA_STORE_OPERATION needs an operation "
                             "(--operation READ|ADD|UPDATE|DELETE or in --config)")
        ev_config.setdefault("inputMap", [])
        ev_config.setdefault("outputMap", [])
        # Filters apply to every operation except ADD (dataStoreOperationSupportsFilters).
        if str(ev_config.get("operation")).upper() != "ADD":
            ev_config.setdefault("filters", [])
            ev_config.setdefault("areFiltersConfigured", bool(ev_config.get("filters")))
    elif not ev_config.get("code"):
        raise UsageError("RUN_JAVASCRIPT config needs a 'code' string")

    slot = _cfg(element, cfg_key)
    if slot is None:
        raise UsageError(
            f"element {args.element!r} has no {cfg_key!r} config, so it cannot raise that "
            f"trigger; available: "
            f"{', '.join(c.get('key','') for c in element.get('configs') or [] if 'vent' in c.get('key',''))}")

    current = slot.get("value") or {}
    previous = list(current.get("events") or [])
    event = {"id": str(uuid.uuid4()),
             "type": (args.type or default_type),
             "action": action,
             "config": ev_config}

    # Three ways to combine the new event with the trigger's existing events:
    #   --replace-action ACT : replace ONLY events whose action is ACT, keeping the
    #                          others and their ORDER (the safe O8 recipe — an element
    #                          commonly carries [RUN_PROCESS, RUN_JAVASCRIPT] on one
    #                          trigger, and you rarely mean to drop the sibling).
    #   --replace            : replace ALL events (destructive) — warns when it would
    #                          discard more than one.
    #   (neither)            : append.
    replace_action = (args.replace_action or "").strip().upper() or None
    if replace_action and args.replace:
        raise UsageError(
            "pass either --replace (replace ALL events) or --replace-action <ACTION> "
            "(replace only that action's events) — not both")
    if replace_action and replace_action not in ACTIONS_ALLOWED:
        raise UsageError(f"--replace-action must be one of {', '.join(ACTIONS_ALLOWED)}")

    warning = None
    if replace_action:
        events, inserted = [], False
        for e in previous:
            if str(e.get("action") or "").upper() == replace_action:
                if not inserted:            # new event takes the first slot of its kind
                    events.append(event)
                    inserted = True
            else:
                events.append(e)            # a different action survives, in place
        if not inserted:
            events.append(event)
    elif args.replace:
        events = [event]
        if len(previous) > 1:
            discarded = ", ".join(str(e.get("action")) for e in previous)
            warning = (
                f"--replace discarded ALL {len(previous)} existing events on this "
                f"trigger ({discarded}). Elements commonly carry [RUN_PROCESS, "
                f"RUN_JAVASCRIPT] on one trigger; to replace only one action and keep "
                f"the rest (and their order), use --replace-action <ACTION> instead.")
    else:
        events = previous + [event]

    result = {
        "id": args.id, "element": args.element, "elementId": element.get("id"),
        "trigger": cfg_key, "action": action,
        "previous_events": previous, "event_count": len(events),
        "elements": len(elements),
    }
    if warning:
        result["warning"] = warning
    if args.dry_run:
        return {"dry_run": True, "event": event, **result}

    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    slot["value"] = {"debounce": current.get("debounce", 0), "events": events}
    client.put("/api/FormTemplate", build_put_body(form, data=form["data"]))
    return {"updated": True, "event": event, "concurrency": guard, **result}


def get_element_events(client, args) -> dict:
    form = _fetch(client, args.id)
    element = _find_element(form["data"].get("elements") or [], args.element)
    out = {}
    for c in element.get("configs") or []:
        k = c.get("key") or ""
        if "vent" in k:
            out[k] = (c.get("value") or {}).get("events") or []
    return {"id": args.id, "element": args.element, "elementId": element.get("id"),
            "type": element.get("type"), "events": out}


def _common(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--element", required=True,
                   help="element id, or its designer 'name' (e.g. doccipf)")


def _set_args(p: argparse.ArgumentParser) -> None:
    _common(p)
    p.add_argument("--on", required=True,
                   help="trigger: click | input | stepChange | paginationChanged | rowAdded")
    p.add_argument("--action", required=True,
                   help="RUN_PROCESS | RUN_JAVASCRIPT | RUN_DATA_STORE_OPERATION")
    p.add_argument("--config", help="event config as JSON")
    p.add_argument("--data-store-id", dest="data_store_id",
                   help="RUN_DATA_STORE_OPERATION: the target data store id")
    p.add_argument("--operation",
                   help="RUN_DATA_STORE_OPERATION: READ | ADD | UPDATE | DELETE")
    p.add_argument("--config-file", dest="config_file", help="path to a JSON config file")
    p.add_argument("--type", help="override the event type (default follows the trigger)")
    p.add_argument("--replace", action="store_true",
                   help="replace ALL of this trigger's events instead of appending "
                        "(destructive; warns when it discards more than one)")
    p.add_argument("--replace-action", dest="replace_action",
                   help="replace only this trigger's events whose action is this "
                        "(RUN_PROCESS/RUN_JAVASCRIPT), preserving the others and order")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="build the event and report it without writing")
    add_force_arg(p)


ACTIONS = {
    "form-get-element-events": ActionDef(
        func=get_element_events, add_args=_common, needs_client=True,
        description="List one element's event handlers, by trigger.",
    ),
    "form-set-element-event": ActionDef(
        func=set_element_event, add_args=_set_args, needs_client=True,
        description="Wire one element's trigger to RUN_PROCESS / RUN_JAVASCRIPT / "
                    "RUN_DATA_STORE_OPERATION in place (surgical: only that element's event "
                    "config changes; process-variable names in inputMap/outputMap are "
                    "resolved to guids; a DataStore op takes --data-store-id + --operation).",
    ),
}
