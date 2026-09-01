"""PARITY TESTS — the builder's output must match the STRUCTURE of real PROCESIO exports.

Why this file exists: every form bug we've hit (enum values, event types, RUN_PROCESS map
orientation) shared one shape — the builder produced a DTO that PASSED schema/dry-run
validation but did NOT match what the real platform produces, so it only failed when a human
opened the form in the designer / ran it. The real `.procesio` exports under
docs_info/Exports are the platform's own ground truth: the exact shape a *working* form has.

Each invariant below is checked TWICE:
  (a) it actually holds across the real exports  -> proves the invariant is real, and
  (b) the builder's output satisfies the same invariant -> catches divergence pre-ship.

DISCIPLINE: whenever the builder learns to emit a new construct (a new event kind, a new
container wiring, a new mapping...), add a reality-derived invariant here. That is the
mechanism that removes the need for manual UI testing of structural correctness.
"""
import glob
import json
import os
import re
import uuid
from pathlib import Path

import pytest

from tools.procesio.dto.form import builder

EXPORTS = Path(__file__).resolve().parents[1] / "docs_info" / "Exports"

# The reality-side invariants are calibrated against the platform's own exports.
# That corpus is not carried into every distribution of this tool (a .procesio
# export names real processes and serializes credentials inline), so those tests
# SKIP where it is absent rather than failing, while the builder-side invariants
# run everywhere. Skipping is the honest outcome: without ground truth there is
# nothing to calibrate against, and a vacuous pass would be worse than no test.
requires_corpus = pytest.mark.skipif(
    not sorted(EXPORTS.glob("*.procesio")),
    reason="no .procesio export corpus in this checkout")
_GUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _is_guid(v):
    return isinstance(v, str) and bool(_GUID.match(v))


def _form_datas():
    for p in glob.glob(str(EXPORTS / "*.procesio")):
        dd = json.loads(Path(p).read_text(encoding="utf-8"))
        for fm in dd.get("Forms") or []:
            v = fm.get("Data")
            v = json.loads(v) if isinstance(v, str) else v
            if isinstance(v, dict):
                yield os.path.basename(p), v


def _iter_events(data):
    for el in data.get("elements") or []:
        for c in el.get("configs") or []:
            v = c.get("value")
            if isinstance(v, dict) and isinstance(v.get("events"), list):
                for ev in v["events"]:
                    yield el, c.get("key"), v, ev


def _build_run_process_form():
    """Build a form whose button runs a process with one input + one output map, with the
    process variables 'resolved' (as prepare_ctx would do live)."""
    pid = str(uuid.uuid4())
    in_var, out_var = str(uuid.uuid4()), str(uuid.uuid4())
    ctx = {"new_id": lambda: str(uuid.uuid4()),
           "process_vars": {pid: {"inText": in_var, "outText": out_var}}}
    cfg = {"name": "P", "elements": [
        {"type": "input", "label": "A", "name": "fieldA"},
        {"type": "input", "label": "B", "name": "fieldB"},
        {"type": "button", "label": "Run", "name": "runBtn", "events": [
            {"on": "click", "do": "process", "processId": pid, "syncRun": True,
             "inputs": [{"to": "inText", "from": "fieldA"}],
             "outputs": [{"to": "fieldB", "from": "outText"}]}]}]}
    dto = builder.build(cfg, ctx)
    btn = next(e for e in dto["Data"]["elements"]
               if any(c.get("value") == "runBtn" for c in e["configs"]))
    cfg_ev = next(c["value"] for c in btn["configs"] if c["key"] == "onClickEvents")
    return cfg_ev["events"][0]["config"], in_var, out_var


# ---------- invariant 1: RUN_PROCESS map orientation (the bug we just fixed) ----------
def _seg_count(v):
    return v.count(".") + 1 if isinstance(v, str) else 0


def _is_proc_ref(v):
    # a process-variable reference: a bare GUID, or {value: <guid|"">, ...}
    if _is_guid(v):
        return True
    if isinstance(v, dict) and "value" in v:
        return _is_guid(v["value"]) or v["value"] == ""
    return False


@requires_corpus
def test_reality_run_process_left_is_never_a_form_path():
    """Calibrated to reality: across all real exports, a RUN_PROCESS map's `left` is the
    PROCESS-variable side (a GUID, sometimes wrapped as {value}) and is NEVER a form field
    value-path (4 dotted GUIDs). That is exactly the orientation our output-map bug broke."""
    proc_ref_lefts = 0
    for fn, data in _form_datas():
        for _el, _k, _grp, ev in _iter_events(data):
            if ev.get("action") != "RUN_PROCESS":
                continue
            cfg = ev.get("config") or {}
            for m in (cfg.get("inputMap") or []) + (cfg.get("outputMap") or []):
                left = m.get("left")
                assert _seg_count(left) < 3, (
                    f"{fn}: RUN_PROCESS map 'left' is a form path (should be a process var): {left!r}")
                if _is_proc_ref(left):
                    proc_ref_lefts += 1
    assert proc_ref_lefts > 0, "no real RUN_PROCESS process-var lefts found to validate against"


def test_builder_run_process_map_matches_reality():
    cfg, in_var, out_var = _build_run_process_form()
    for m in cfg["inputMap"] + cfg["outputMap"]:
        assert _is_guid(m["left"]), f"builder RUN_PROCESS map 'left' not a GUID: {m['left']!r}"
    # process variable on the LEFT (resolved to its id); form field path on the RIGHT
    assert cfg["inputMap"][0]["left"] == in_var
    assert cfg["outputMap"][0]["left"] == out_var          # <-- would fail with the old swap
    assert cfg["inputMap"][0]["right"].count(".") == 3     # form value-path = 4 segments
    assert cfg["outputMap"][0]["right"].count(".") == 3


# ---------- invariant 2: stored event object shape ----------
@requires_corpus
def test_reality_event_shape():
    n = 0
    for _fn, data in _form_datas():
        for _el, _k, grp, ev in _iter_events(data):
            assert {"id", "type", "action"} <= set(ev)
            assert "events" in grp and "debounce" in grp
            n += 1
    assert n > 0


def test_builder_event_shape():
    """Split out of the reality test: the builder half needs no corpus, and pairing
    them meant losing builder coverage wherever the corpus is absent."""
    cfg, _i, _o = _build_run_process_form()
    assert {"processId", "inputMap", "outputMap"} <= set(cfg)


# ---------- invariant 3: a DATA-FIELD's `value` config is canonical (exposed + EMIT_INPUT) ----------
# Scoped to user-data input controls (the ones whose `value` the platform's on-save compiler
# turns into the field value attribute). Non-field controls (assignee, table rows, approval,
# containers) legitimately have a different/absent value config, so they are excluded.
# NOTE: dropdown is an action MENU (items), not a value field -> excluded.
_DATA_FIELDS = {"input", "number-input", "datetime-input", "textarea", "select",
                "radiobox", "checkbox", "file-upload"}


def test_data_field_value_config_canonical_in_goldens():
    elems = Path(builder.__file__).resolve().parent / "elements"
    checked = 0
    for p in elems.glob("*.json"):
        if p.stem not in _DATA_FIELDS:
            continue
        cfgs = json.loads(p.read_text(encoding="utf-8")).get("configs", [])
        vc = next((c for c in cfgs if c.get("key") == "value"), None)
        assert vc is not None, f"{p.name}: data field must have a value config"
        assert vc.get("exposed") is True, f"{p.name}: value config must be exposed"
        assert vc.get("events") == ["EMIT_INPUT"], f"{p.name}: value events must be [EMIT_INPUT]"
        checked += 1
    assert checked >= len(_DATA_FIELDS) - 1
