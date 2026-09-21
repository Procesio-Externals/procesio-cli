"""Rewrite the ORDERED event chains of several elements on a live form, in one save.

`form-set-element-event` appends or swaps ONE event of ONE action type. A behaviour change on a
multi-step form is rarely that small: a button's chain is an ordered mix of RUN_JAVASCRIPT,
RUN_PROCESS and MAP_FORM_DATA blocks, and the ORDER is the behaviour. Moving a MAP, adding a
condition to it or spreading one decision across several elements means restating whole chains,
and on a form with hundreds of hand-built elements that must still be surgical and atomic, not
a desired-state rebuild.

A PLAN lists, for each (element, trigger), the new chain in order:

    {"chains": [{"element": "<name or id>", "on": "click",
                 "events": [{"keep": "<existing event id>"},
                            {"map": {"set": {"Input2.disabled": true, "@isPF": true},
                                     "when": [{"field": "flag.value", "op": "EQUALS", "value": "1"},
                                              {"variable": "isPF", "op": "IS_TRUE"}],
                                     "match": "all"}},
                            {"js": "<code>"} | {"js_file": "<path>"},
                            {"raw": {<a complete event>}}]}]}

* `keep` re-uses an existing event of that element and trigger VERBATIM, id included, so a large
  script is never re-sent or re-typed.
* A `map` target is `<element>.<configKey>` (resolved to {root}.{FIELDS_NS}.{elementId}.{configId})
  or `@<formVariable>` (the variable id). A condition operand is `field` (`<element>` for its value,
  `<element>.<configKey>` for any other config) or `variable`. `match` is `all` (AND) or `any` (OR).
* Every name, config key, variable, operator and kept id is resolved BEFORE anything is written.
  A wrong path is otherwise saved without an error and the block silently does nothing.
* Events not listed in a chain are dropped, and the result names them.
* All chains land in ONE GET -> PUT behind the concurrency guard.

Wire shapes were copied from MAP_FORM_DATA blocks the designer itself wrote (verified on a live
form): an unconditional block's config is `{"mapping": [...]}`, while a conditional one adds
`conditions` + `areConditionsConfigured: true`. A condition's `logicOperator` links it to the NEXT
condition (1 = AND, 2 = OR, 0 on the last). `operandsAsListOptional` follows the operator (see
_LIST_OPTIONAL_OPS). Mapping values are strings: booleans become "true"/"false".
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import uuid

from tools.procesio import formlint
from tools.procesio.actiondef import ActionDef
from tools.procesio.dto.form import fieldpath
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_force_arg, add_profile_arg, guard_unchanged
from tools.procesio.handlers.form_code import _fetch, build_put_body
from tools.procesio.handlers.form_events import _cfg, _find_element, _resolve_trigger

# Every operator seen in real form/process conditions (counted across exported workspaces).
OPERATORS = (
    "EQUALS", "DOES_NOT_EQUAL", "CONTAINS", "DOES_NOT_CONTAIN", "IS_EMPTY", "IS_NOT_EMPTY",
    "IS_TRUE", "IS_FALSE", "GREATER_THAN", "GREATER_THAN_OR_EQUAL_TO", "LESS_THAN",
    "LESS_THAN_OR_EQUAL_TO", "BELONGS", "DOES_NOT_BELONG",
)
_LOGIC = {"all": 1, "and": 1, "any": 2, "or": 2}
# The designer sets `operandsAsListOptional` by OPERATOR, not by operand kind: counted over every
# condition of a large production form, it is true for exactly these four and false for
# CONTAINS / DOES_NOT_CONTAIN / IS_TRUE / IS_FALSE, on fields and variables alike.
_LIST_OPTIONAL_OPS = {"EQUALS", "DOES_NOT_EQUAL", "IS_EMPTY", "IS_NOT_EMPTY"}


def _operand(value) -> dict:
    return {"variable": "", "attribute": {"id": "", "nextAttribute": None}, "value": value}


def _as_string(value) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return ""
    return str(value)


class _Resolver:
    """Names -> ids for one live form: element configs and form variables."""

    def __init__(self, form: dict):
        self.live = fieldpath.LiveForm(form)
        data = form.get("data") or {}
        self.variables = {v.get("name"): v.get("id") for v in data.get("variables") or []
                          if v.get("name") and v.get("id")}

    def variable(self, name: str, where: str) -> str:
        vid = self.variables.get(name)
        if not vid:
            raise UsageError(f"{where}: {name!r} is not a form variable; known: "
                             f"{', '.join(sorted(self.variables)) or '(none)'}")
        return vid

    def target(self, ref: str, where: str) -> str:
        """`@var` -> variable id; `<element>.<key>` -> config path (split on the LAST dot, so an
        element name may itself contain dots)."""
        ref = str(ref).strip()
        if ref.startswith("@"):
            return self.variable(ref[1:], where)
        if "." not in ref:
            raise UsageError(f"{where}: {ref!r} must be '<element>.<configKey>' or '@<variable>'")
        el, key = ref.rsplit(".", 1)
        try:
            return self.live.config_path(el, key)
        except UsageError as e:
            raise UsageError(f"{where}: {e}") from e

    def field(self, ref: str, where: str) -> str:
        """A condition's field operand: `<element>` means its value, `<element>.<key>` any config."""
        ref = str(ref).strip()
        try:
            if ref in self.live.by_name or ref in self.live.by_id:
                el = self.live.element(ref)
                return self.live.config_path(ref, fieldpath.value_key(el.get("type")))
            el, key = ref.rsplit(".", 1) if "." in ref else (ref, "value")
            return self.live.config_path(el, key)
        except UsageError as e:
            raise UsageError(f"{where}: {e}") from e


def _conditions(when: list, match: str, res: _Resolver, where: str) -> list:
    logic = _LOGIC.get(str(match or "all").lower())
    if logic is None:
        raise UsageError(f"{where}: match must be 'all' or 'any', not {match!r}")
    out = []
    for i, c in enumerate(when):
        if not isinstance(c, dict):
            raise UsageError(f"{where}: condition {i} must be an object")
        op = str(c.get("op") or "").strip().upper()
        if op not in OPERATORS:
            raise UsageError(f"{where}: condition {i} op {c.get('op')!r} is not one of "
                             f"{', '.join(OPERATORS)}")
        if "variable" in c:
            left = res.variable(c["variable"], f"{where} condition {i}")
        elif "field" in c:
            left = res.field(c["field"], f"{where} condition {i}")
        else:
            raise UsageError(f"{where}: condition {i} needs 'field' or 'variable'")
        out.append({
            "id": i, "uid": str(uuid.uuid4()), "operator": op,
            "leftOperator": _operand(left),
            "rightOperator": _operand(_as_string(c.get("value", ""))),
            "auxOperator": _operand(""),
            "logicOperator": logic if i < len(when) - 1 else 0,
            "value": None,
            "rightOperandAsListRequired": False,
            "operandsAsListOptional": op in _LIST_OPTIONAL_OPS,
        })
    return out


def _map_event(spec: dict, event_type: str, res: _Resolver, where: str) -> dict:
    sets = spec.get("set")
    if not isinstance(sets, dict) or not sets:
        raise UsageError(f"{where}: a map needs a non-empty 'set' object")
    mapping = [{"id": i, "left": res.target(k, f"{where} set {k!r}"), "right": _as_string(v)}
               for i, (k, v) in enumerate(sets.items())]
    config: dict = {"mapping": mapping}
    when = spec.get("when") or []
    if when:
        config["conditions"] = _conditions(when, spec.get("match", "all"), res, where)
        config["areConditionsConfigured"] = True
    return {"id": str(uuid.uuid4()), "type": event_type, "action": "MAP_FORM_DATA",
            "config": config}


def _js_event(code: str, event_type: str, where: str) -> dict:
    if not isinstance(code, str) or not code.strip():
        raise UsageError(f"{where}: empty JavaScript")
    return {"id": str(uuid.uuid4()), "type": event_type, "action": "RUN_JAVASCRIPT",
            "config": {"code": code}}


def _summary(ev: dict, live: fieldpath.LiveForm, variables: dict) -> dict:
    """A human-readable line per event, so a dry run can be reviewed without reading guids."""
    ids_to_var = {v: k for k, v in variables.items()}
    by_cfg = {}
    for el in live.elements:
        name = fieldpath._name_of(el) or el.get("id")
        for c in el.get("configs") or []:
            by_cfg[(str(el.get("id")), str(c.get("id")))] = f"{name}.{c.get('key')}"

    def name_of(path):
        if path in ids_to_var:
            return "@" + ids_to_var[path]
        parts = str(path).split(".")
        if len(parts) == fieldpath.SEGMENTS:
            return by_cfg.get((parts[2], parts[3]), path)
        return path

    out = {"id": ev.get("id"), "action": ev.get("action")}
    cfg = ev.get("config") or {}
    if ev.get("action") == "MAP_FORM_DATA":
        out["set"] = {name_of(m.get("left")): m.get("right") for m in cfg.get("mapping") or []}
        conds = cfg.get("conditions") or []
        if conds:
            out["when"] = [f"{name_of(c['leftOperator'].get('value'))} {c.get('operator')} "
                           f"{c['rightOperator'].get('value')!r}" for c in conds]
    elif ev.get("action") == "RUN_JAVASCRIPT":
        code = cfg.get("code") or ""
        out["js"] = f"{len(code)} chars: " + code.strip().splitlines()[0][:90] if code.strip() else ""
    elif ev.get("action") == "RUN_PROCESS":
        out["processId"] = cfg.get("processId")
    return out


def _load_plan(args) -> dict:
    raw = args.plan
    base = os.getcwd()
    if args.plan_file:
        with open(args.plan_file, encoding="utf-8") as f:
            raw = f.read()
        base = os.path.dirname(os.path.abspath(args.plan_file))
    if not raw:
        raise UsageError("provide --plan '<json>' or --plan-file <path>")
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"the plan must be valid JSON: {e}") from e
    if not isinstance(plan, dict) or not isinstance(plan.get("chains"), list) or not plan["chains"]:
        raise UsageError("the plan must be an object with a non-empty 'chains' list")
    plan["_base"] = base
    return plan


def set_element_chains(client, args) -> dict:
    plan = _load_plan(args)
    form = _fetch(client, args.id)
    data = form["data"]
    elements = data.get("elements") or []
    count_before = len(elements)
    res = _Resolver(form)

    staged, report, seen, warnings = [], [], set(), []
    for n, chain in enumerate(plan["chains"]):
        where = f"chains[{n}]"
        if not isinstance(chain, dict) or not chain.get("element") or not chain.get("on"):
            raise UsageError(f"{where}: needs 'element' and 'on'")
        element = _find_element(elements, str(chain["element"]))
        cfg_key, event_type = _resolve_trigger(str(chain["on"]))
        if (element.get("id"), cfg_key) in seen:
            raise UsageError(f"{where}: {chain['element']!r} {cfg_key} appears twice in the plan")
        seen.add((element.get("id"), cfg_key))
        slot = _cfg(element, cfg_key)
        if slot is None:
            raise UsageError(f"{where}: element {chain['element']!r} has no {cfg_key!r} config")
        current = slot.get("value") or {}
        previous = list(current.get("events") or [])
        by_id = {e.get("id"): e for e in previous}

        new_events, kept = [], []
        for i, spec in enumerate(chain.get("events") or []):
            w = f"{where}.events[{i}] ({chain['element']})"
            if not isinstance(spec, dict) or len(spec) != 1:
                raise UsageError(f"{w}: each event is one of keep / map / js / js_file / raw")
            kind, body = next(iter(spec.items()))
            if kind == "keep":
                if body not in by_id:
                    raise UsageError(f"{w}: no event {body!r} on this element's {cfg_key}; it has "
                                     f"{', '.join(str(k) for k in by_id) or '(none)'}")
                if body in kept:
                    raise UsageError(f"{w}: event {body!r} is kept twice")
                kept.append(body)
                new_events.append(copy.deepcopy(by_id[body]))
            elif kind == "map":
                new_events.append(_map_event(body, event_type, res, w))
            elif kind == "js":
                new_events.append(_js_event(body, event_type, w))
            elif kind == "js_file":
                path = body if os.path.isabs(body) else os.path.join(plan["_base"], body)
                with open(path, encoding="utf-8") as f:
                    new_events.append(_js_event(f.read(), event_type, w))
            elif kind == "raw":
                if not isinstance(body, dict) or not body.get("action"):
                    raise UsageError(f"{w}: raw needs a complete event object")
                ev = copy.deepcopy(body)
                ev.setdefault("id", str(uuid.uuid4()))
                ev.setdefault("type", event_type)
                new_events.append(ev)
            else:
                raise UsageError(f"{w}: unknown event kind {kind!r}")

        staged.append((slot, {"debounce": current.get("debounce", 0), "events": new_events}))
        warnings += formlint.string_boolean_conditions(
            new_events, data.get("variables"), f"{chain['element']} {cfg_key}")
        report.append({
            "element": chain["element"], "elementId": element.get("id"), "trigger": cfg_key,
            "previous": [_summary(e, res.live, res.variables) for e in previous],
            "events": [_summary(e, res.live, res.variables) for e in new_events],
            "kept": kept,
            "dropped": [e.get("id") for e in previous if e.get("id") not in kept],
        })

    result = {"id": args.id, "chains": report, "elements": count_before}
    if warnings:
        result["warnings"] = warnings
    if args.dry_run:
        return {"dry_run": True, **result}

    guard = guard_unchanged(lambda: _fetch(client, args.id), form, force=args.force)
    for slot, value in staged:
        slot["value"] = value
    if len(data.get("elements") or []) != count_before:
        raise UsageError("element count changed while staging; refusing to PUT")
    client.put("/api/FormTemplate", build_put_body(form, data=data))
    return {"updated": True, "concurrency": guard, **result}


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="form template id")
    p.add_argument("--plan", help="the chains plan as JSON (see the action description)")
    p.add_argument("--plan-file", dest="plan_file",
                   help="path to the plan JSON; js_file paths inside it resolve relative to it")
    p.add_argument("--dry-run", dest="dry_run", action="store_true",
                   help="resolve and report every chain (names, not guids) without saving")
    add_force_arg(p)


ACTIONS = {
    "form-set-element-chains": ActionDef(
        func=set_element_chains, add_args=_args, needs_client=True,
        description="Rewrite the ORDERED event chains of one or more elements on a live form in "
                    "ONE save (surgical: only the listed element triggers change). Each chain "
                    "lists its events in order: {keep: <existing event id>} re-uses an event "
                    "verbatim (large scripts are never re-sent), {map: {set: {'<element>."
                    "<configKey>': value, '@<variable>': value}, when: [{field|variable, op, "
                    "value}], match: all|any}} builds a MAP_FORM_DATA block from NAMES, {js: "
                    "code} / {js_file: path} adds a RUN_JAVASCRIPT block, {raw: event} passes an "
                    "event through. Every name, config key, variable, operator and kept id is "
                    "resolved before writing; events not listed are dropped and reported. "
                    "--dry-run prints each chain by name.",
    ),
}
