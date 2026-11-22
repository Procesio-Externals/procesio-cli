"""Surgical read/write of ONE element's event list on a live form.

Companion to form_code.py, and it exists for the same reason: `form-edit` is a
DESIRED-STATE editor that rebuilds the whole DTO from a config, so using it to
wire a single button or upload on a large hand-authored form means re-declaring
every element or losing them. These actions do a read-modify-write on the LIVE
DTO and touch ONLY the target element's event config.

The event model (see PROCESIO-RESOURCE-MODEL-NOTES.md): each element carries
per-trigger configs — `onClickEvents`, `onInputEvents`, `onStepChangeEvents`,
`onPaginationChangedEvents` — whose value is `{debounce, events:[…]}` (the runtime also
accepts a bare list of events; both are read, `{debounce, events}` is written). A fresh
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
import copy
import json
import uuid

from tools.procesio.actiondef import ActionDef
from tools.procesio.client import VARIABLES_ONLY
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body

# Trigger -> (config key, event type) comes from the DTO builder's own maps, which
# were verified against the ui-builder source. Re-deriving them here would let the
# two drift, and a wrong event type is silently accepted by the API.
from tools.procesio.dto.form.builder import _EVENT_KEY, _EVENT_TYPE, _golden  # noqa: E402

# The value-path rule itself is shared with the builder, so the action that CHECKS a path and
# the one that WRITES one cannot disagree.
from tools.procesio.dto.form import fieldpath, queries as form_queries  # noqa: E402

ACTIONS_ALLOWED = ("RUN_PROCESS", "RUN_JAVASCRIPT", "RUN_DATA_STORE_OPERATION")

# EventAction.RUN_DATA_STORE_OPERATION (ui-builder model/config/events/index.ts): a
# form element triggers a Data Store operation, the same way RUN_PROCESS triggers a
# process. config = EventRunDataStoreOperationConfig {dataStoreId, operation, inputMap,
# outputMap, filters?, areFiltersConfigured?}. operation = DataStoreOperation
# READ/ADD/UPDATE/DELETE; filters apply to every op except ADD
# (dataStoreOperationSupportsFilters). The operation wire encoding (string vs numeric)
# must be re-verified live — pass a numeric operation via --config if the platform
# rejects the name. See PROCESIO-RESOURCE-MODEL-NOTES.md.
_DATA_STORE_OPS = ("READ", "ADD", "UPDATE", "DELETE", "QUERY")


def _query_config(ev_config: dict, form: dict) -> dict:
    """Operation QUERY runs one of the form's saved queries instead of addressing a Data
    Store: `queryId` (or `query`, a name) is resolved against the live form, the inputMap
    must name parameters exactly as the query declares them, and the config takes the
    designer's shape - no Data Store, no filters."""
    query = form_queries.resolve(form.get("queries") or [],
                                 ev_config.get("queryId") or ev_config.get("query"))
    inputs = ev_config.get("inputMap") or []
    form_queries.check_parameter_names(
        query, [row.get("left") for row in inputs if isinstance(row, dict)])
    return {"dataStoreId": None, "operation": "QUERY", "inputMap": inputs,
            "outputMap": ev_config.get("outputMap") or [], "filters": [],
            "queryId": query["id"]}


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


def _slot_data(value) -> dict:
    """A trigger slot's value as `{debounce, events}`.

    The runtime accepts two shapes: `{debounce, events:[...]}` (what the designer and this
    tool write) and a bare list of events (ui-builder trigger.ts::getTriggersDataByKey wraps
    it with the default debounce). A slot written by hand through form-update is often the
    bare list, so reading it as a dict crashed. null still means "no handler"."""
    if isinstance(value, list):
        return {"debounce": 0, "events": value}
    return value if isinstance(value, dict) else {}


def _cfg(element: dict, key: str):
    for c in element.get("configs") or []:
        if c.get("key") == key:
            return c
    return None


def _template_slot(el_type: str, key: str):
    """(index, config) of `key` in the element type's golden template, or (None, None)."""
    try:
        template = _golden(str(el_type))
    except UsageError:
        return None, None
    for i, c in enumerate(template.get("configs") or []):
        if c.get("key") == key:
            return i, c
    return None, None


def _backfill_slot(element: dict, key: str) -> dict:
    """Add a missing trigger slot to `element`, the way the runtime does on load.

    An element saved before a trigger existed (every approval control saved before ~Sep
    2025 has no onBefore*/onAfter* slots) carries no config for it. The form runtime
    back-fills missing configs from the element template on every load
    (ui-builder utils/formBuilder/elements.ts::actualizeElements) and the designer persists
    them on its next save, so an absent slot means "old element", not "cannot raise this
    trigger". Only when the TEMPLATE lacks the key is the trigger really unavailable.
    """
    index, template = _template_slot(element.get("type"), key)
    configs = element.setdefault("configs", [])
    if template is None:
        raise UsageError(
            f"element type {element.get('type')!r} has no {key!r} config, so it cannot raise "
            f"that trigger; available: "
            f"{', '.join(c.get('key', '') for c in configs if 'vent' in c.get('key', ''))}")
    slot = copy.deepcopy(template)
    slot["id"] = str(uuid.uuid4())
    slot["value"] = None
    configs.insert(min(index, len(configs)), slot)
    return slot


def _cfg_text(element: dict, key: str) -> str:
    c = _cfg(element, key)
    return str(c.get("value") or "").strip() if c else ""


def _find_element(elements: list, ref: str) -> dict:
    """Match by element id first, then by its `name` config (what the designer shows), then by
    its `id` config.

    The `id` config is the DOM id the element carries on the page, so it is the handle a caller
    holds after reading the form's script or markup, where the `name` never appears. The name is
    tried first because field paths and event maps are built from it. A new element of a type
    starts with that type's default DOM id, so several may share one: that is refused, never
    guessed.
    """
    for e in elements:
        if e.get("id") == ref:
            return e
    named = [e for e in elements if _cfg_text(e, "name") == ref]
    if len(named) == 1:
        return named[0]
    if named:
        raise UsageError(f"{len(named)} elements are named {ref!r}; pass the element id instead")
    by_dom_id = [e for e in elements if _cfg_text(e, "id") == ref]
    if len(by_dom_id) == 1:
        return by_dom_id[0]
    if by_dom_id:
        names = ", ".join(repr(_cfg_text(e, "name") or e.get("id")) for e in by_dom_id[:8])
        raise UsageError(
            f"{len(by_dom_id)} elements carry the DOM id {ref!r} in their `id` config ({names}); "
            f"pass the element's name or its element id instead")
    known = ", ".join(sorted(n for n in (_cfg_text(e, "name") for e in elements) if n)[:20])
    raise UsageError(
        f"no element with id, name or DOM id {ref!r} on this form. An id that a script or the "
        f"markup of a label creates is not a form element. Element names here: {known or 'none'}")


def _process_vars(client, process_id: str) -> dict:
    """{variable name: the variable DTO}. The whole DTO, not just the id, because a map row also
    has to know whether the variable is a LIST - see _is_list_of."""
    body = client.get(f"/api/Projects/{process_id}", VARIABLES_ONLY)
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


def _resolve_maps(config: dict, client, form: dict | None = None) -> dict:
    """Turn a map's two sides into the designer's object shape, resolving BOTH.

    Left is a process variable: a NAME becomes its GUID. Right is a form field, and it used
    to pass through untouched — which is why every caller that guessed the value-path format
    wrote a row the platform accepted, the designer rendered, and the control silently
    ignored. With `form` given, the right side is resolved the same way as the left: a field
    NAME is built into its value path, a path is CHECKED against the live form, and anything
    else is refused before a single byte is written.
    """
    pid = config.get("processId")
    if not pid:
        raise UsageError("RUN_PROCESS config needs a 'processId'")
    names = _process_vars(client, pid)
    live = fieldpath.LiveForm(form) if form is not None else None
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
            right = _plain(row.get("right"))
            if live is not None:
                right = live.resolve(right, f"{side} row {i}")
            row["left"] = _slot(left, True, _path_of(row.get("left")), is_list)
            # a form VARIABLE side carries `path: {}` like the process side (as the designer saves it)
            rpath = {} if live is not None and live.is_variable(right) and _path_of(row.get("right")) is None \
                else _path_of(row.get("right"))
            row["right"] = _slot(right, False, rpath, is_list)
            row["id"] = row.get("id", i)
            fixed.append(row)
        out[side] = fixed
    return out


def _typed(value) -> str:
    """A typed value as the designer stores it on the right of a Data Store row: text."""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return "" if value is None else str(value)


def _is_plain_literal(text: str) -> bool:
    """A number or a boolean: text nobody meant as a field name, so not worth reporting."""
    text = text.strip().lower()
    if text in ("true", "false"):
        return True
    try:
        float(text)
    except ValueError:
        return False
    return True


def _check_filter_paths(filters, live: fieldpath.LiveForm, where: str = "filter") -> None:
    """A filter's right side is a typed value or a form value path, in the same text. Names
    are not resolved here (a filter value that equals a field's name is a value); a path is
    checked, because a wrong one is compared as text and matches no row."""
    for i, cond in enumerate(filters or []):
        if not isinstance(cond, dict):
            continue
        for side in ("rightOperator", "auxOperator"):
            operand = cond.get(side)
            if isinstance(operand, dict):
                live.check_embedded(operand.get("value"), f"{where} {i} {side}")
        if isinstance(cond.get("value"), list):
            _check_filter_paths(cond["value"], live, f"{where} {i} group")


def _resolve_ds_maps(config: dict, form: dict) -> tuple:
    """Resolve the form side of a Data Store event -> (config, typed values, warnings).

    The right side of a row is text, and the form runtime reads as a form value only a chain
    of ids that starts at the form's data model. Any other text is sent as written. So a field
    NAME, or a path built from names, was saved without complaint and then written into the
    Data Store as the value itself, or refused by a typed column with no word about the map.
    Here an input's right side is resolved to the id path (a field name, `@variable`,
    `Element.config`, instance.currentUser.id), a path is checked against the live form, and
    what is left is a typed value, reported so a misspelled field name cannot pass unseen.
    `value` in place of `right` states a typed value outright. An output's right side is
    always a place on the form; a list of rows goes to the source of a table's dynamic row.
    """
    live = fieldpath.LiveForm(form)
    out = dict(config)
    typed, warnings = [], []
    reads = str(out.get("operation") or "").upper() in ("READ", "QUERY")

    inputs = []
    for i, row in enumerate(out.get("inputMap") or []):
        if not isinstance(row, dict):
            raise UsageError(f"inputMap row {i} must be an object {{left, right}}")
        row = dict(row)
        where = f"inputMap row {i} ({_plain(row.get('left'))!r})"
        if "value" in row:
            literal = row.pop("value")
            if row.get("right") not in (None, ""):
                raise UsageError(f"{where}: give `right` (a form value) or `value` (a typed "
                                 f"value), not both")
            row["right"] = _typed(literal)
        elif isinstance(row.get("right"), str):
            row["right"], kind = live.resolve_input(row["right"], where)
            if kind == "typed" and not _is_plain_literal(row["right"]):
                typed.append({"left": _plain(row.get("left")), "value": row["right"]})
        else:
            row["right"] = _typed(row.get("right"))
        row.setdefault("id", i)
        inputs.append(row)
    out["inputMap"] = inputs

    outputs = []
    for i, row in enumerate(out.get("outputMap") or []):
        if not isinstance(row, dict):
            raise UsageError(f"outputMap row {i} must be an object {{left, right}}")
        row = dict(row)
        left, right = _plain(row.get("left")), row.get("right")
        where = f"outputMap row {i} ({left!r})"
        if right in (None, ""):
            row["right"] = ""                     # an output the designer lists and leaves unmapped
        elif not isinstance(right, str):
            raise UsageError(f"{where}: the right side is a form field (its name) or a value "
                             f"path, not {right!r}")
        elif left == "rows" and reads:
            row["right"], found = live.resolve_rows_target(right, where)
            warnings.extend(found)
        else:
            row["right"] = live.resolve(right.strip(), where)
        row.setdefault("id", i)
        outputs.append(row)
    out["outputMap"] = outputs

    _check_filter_paths(out.get("filters"), live)
    return out, typed, warnings


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

    typed_values, map_warnings = [], []
    if action == "RUN_PROCESS":
        # `form` is the live DTO fetched above: passing it is what lets the form side of each
        # row be resolved and checked, not merely copied.
        ev_config = _resolve_maps(ev_config, client, form)   # fails loudly before any write
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
        if _normalize_op(ev_config.get("operation")) == "QUERY":
            ev_config = _query_config(ev_config, form)
        elif not ev_config.get("dataStoreId"):
            raise UsageError("RUN_DATA_STORE_OPERATION needs a dataStoreId "
                             "(--data-store-id or in --config)")
        if ev_config.get("operation") in (None, ""):
            raise UsageError("RUN_DATA_STORE_OPERATION needs an operation "
                             "(--operation READ|ADD|UPDATE|DELETE or in --config)")
        ev_config.setdefault("inputMap", [])
        ev_config.setdefault("outputMap", [])
        # Filters apply to every operation except ADD (dataStoreOperationSupportsFilters).
        if str(ev_config.get("operation")).upper() not in ("ADD", "QUERY"):
            ev_config.setdefault("filters", [])
            ev_config.setdefault("areFiltersConfigured", bool(ev_config.get("filters")))
        # fails loudly before any write, as the RUN_PROCESS branch does
        ev_config, typed_values, map_warnings = _resolve_ds_maps(ev_config, form)
    elif not ev_config.get("code"):
        raise UsageError("RUN_JAVASCRIPT config needs a 'code' string")

    slot = _cfg(element, cfg_key)
    backfilled = []
    if slot is None:
        slot = _backfill_slot(element, cfg_key)     # refuses when the type has no such slot
        backfilled.append(cfg_key)

    current = _slot_data(slot.get("value"))
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
        "backfilled": backfilled,
    }
    if warning:
        result["warning"] = warning
    if action == "RUN_JAVASCRIPT":
        # the script is saved whatever it holds, and a mistake in it shows no error on the form
        from tools.procesio import formlint
        where = f"the {cfg_key} script of {args.element!r}"
        script_warnings = (formlint.lint_form_code_runtime(None, ev_config.get("code"), where)
                           + formlint.lint_form_code_sandbox(ev_config.get("code"), where))
        if script_warnings:
            result["warnings"] = script_warnings
    if backfilled:
        result["note"] = (
            f"{args.element!r} was saved before its {', '.join(backfilled)} slot existed, so the "
            f"slot was added from the element template (the form runtime and designer do the "
            f"same on load/save); every other config is unchanged.")
    if typed_values:
        result["typed_values"] = typed_values
        result["typed_values_note"] = (
            "These right sides name no field, variable or path of this form, so the form sends "
            "each one as written, as a typed value. To send a form value instead, pass the "
            "field's name.")
    if map_warnings:
        result["warnings"] = map_warnings
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
            out[k] = _slot_data(c.get("value")).get("events") or []
    result = {"id": args.id, "element": args.element, "elementId": element.get("id"),
              "type": element.get("type")}
    scripts = [(k, (ev.get("config") or {}).get("code")) for k, events in out.items()
               for ev in events if isinstance(ev, dict) and ev.get("action") == "RUN_JAVASCRIPT"]
    if scripts:
        # before `events`: a caller that keeps only the start of a long answer still gets it
        from tools.procesio import formlint
        result["note"] = formlint.SANDBOX_NOTE
        warnings = []
        for key, code in scripts:
            for w in formlint.lint_form_code_sandbox(code, f"the {key} script of {args.element!r}"):
                if w not in warnings:
                    warnings.append(w)
        if warnings:
            result["warnings"] = warnings
    return {**result, "events": out}


def _common(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--element", required=True,
                   help="element id, its designer 'name' (e.g. doccipf), or its `id` config "
                        "(the DOM id the element carries on the page)")


def _set_args(p: argparse.ArgumentParser) -> None:
    _common(p)
    p.add_argument("--on", required=True,
                   help="trigger: " + " | ".join(sorted(_EVENT_KEY)) + " (case, '-' and '_' "
                        "are ignored). A slot missing from an element saved before that "
                        "trigger existed is added from the element template and reported "
                        "under `backfilled`")
    p.add_argument("--action", required=True,
                   help="RUN_PROCESS | RUN_JAVASCRIPT | RUN_DATA_STORE_OPERATION")
    p.add_argument("--config", help="event config as JSON")
    p.add_argument("--data-store-id", dest="data_store_id",
                   help="RUN_DATA_STORE_OPERATION: the target data store id")
    p.add_argument("--operation",
                   help="RUN_DATA_STORE_OPERATION: READ | ADD | UPDATE | DELETE, or QUERY to "
                        "run one of the form's saved queries (--config then carries queryId, "
                        "or query = its name, and no data store)")
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
        description="List one element's event handlers, by trigger. When one of them is a "
                    "RUN_JAVASCRIPT script, the answer carries a `note` on where the script runs "
                    "(a sandbox iframe, not the page), and `warnings` when a script works on the "
                    "DOM only through its own `document`.",
    ),
    "form-set-element-event": ActionDef(
        func=set_element_event, add_args=_set_args, needs_client=True,
        description="Wire one element's trigger to RUN_PROCESS / RUN_JAVASCRIPT / "
                    "RUN_DATA_STORE_OPERATION in place (surgical: only that element's event "
                    "config changes). In a RUN_PROCESS inputMap/outputMap BOTH sides take "
                    "NAMES: left = a process variable name, right = a form FIELD name, a form "
                    "variable (@Offer_ID), an element config (Paragraph9.label; the element by its name, id or "
                    "DOM id) or a data-model "
                    "path (instance.currentUser.email) - each "
                    "is resolved to the id/value-path the runtime needs. Do NOT hand-build "
                    "the form value path; if you pass one it is CHECKED against the live form "
                    "and refused when wrong, because a wrong path is saved without any error "
                    "and the control then launches nothing. A DataStore op takes "
                    "--data-store-id + --operation; operation QUERY runs a saved query of the "
                    "form instead (queryId or query name in --config, inputMap left = the "
                    "parameter exactly as declared, outputMap left = rows|columns|count|success). "
                    "In a DataStore op the right side takes the same NAMES and is resolved and "
                    "checked the same way; an input's right side that names nothing on the form "
                    "is kept as a typed value and listed in `typed_values` (pass `value` in "
                    "place of `right` to state a typed value), and `rows` takes a table's name "
                    "and is written to its dynamic row's source. "
                    "An element saved before the trigger "
                    "existed (e.g. an approval control from before Sep 2025, no "
                    "onBeforeApprove slot) gets the missing slot added from the element "
                    "template, listed in `backfilled`. A RUN_JAVASCRIPT script runs in a hidden "
                    "sandbox iframe, not in the page: reach the form through "
                    "window.parent.document. Returns `warnings` when the script works on the DOM "
                    "only through its own `document`.",
    ),
}
