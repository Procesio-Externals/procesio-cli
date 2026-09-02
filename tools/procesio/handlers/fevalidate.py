"""Front-end (designer-layer) process validation — live action + the save gate.

This is the impure (client-facing) layer over flowmodel.fevalidation (pure). It:
  * gathers the datatype catalog + subprocess-variable resolver from the live API,
  * runs the pure FE validator (the designer "Process Errors" checks),
  * exposes `process-fe-validate` (validate a live process by id),
  * provides `pre_save_validate()` — the gate every process save runs: FE first, then
    the BE validator (POST /api/Projects/validate), blocking the save on either unless
    --force is passed.

Why a gate: POST /api/Projects/validate only checks the RUNTIME layer and returns EMPTY
even when the designer would REFUSE to save. Running the FE checks here means a
tool-driven save is held to the SAME bar as a human clicking Save in the designer —
without a conscious decision each time (CLAUDE.md: verify before done).
"""
from __future__ import annotations

import argparse

from tools.procesio.actiondef import ActionDef
from tools.procesio.errors import ProcesioAPIError, ValidationBlocked
from tools.procesio.flowmodel import fevalidation as fv
from tools.procesio.handlers.common import add_profile_arg

_SUB_TEMPLATES = ("Call Subprocess", "Trigger Subprocess")


# -- gather live context for the pure validator -------------------------------

def _load_datatypes(client) -> list[dict]:
    try:
        r = client.get("/api/DataTypes", {"pageNumber": 1, "pageItemCount": 1000,
                                          "includeProcesioEntries": True,
                                          "includeExternalEntries": True})
    except Exception:  # noqa: BLE001 - the type layer is best-effort / non-blocking
        return []
    items = r.get("pageItems") if isinstance(r, dict) else r
    return items or []


def _subprocess_resolver(client):
    """target_vars_of(flow_id) -> {var_id: var_dict}, cached, network-tolerant."""
    cache: dict = {}

    def resolve(fid: str) -> dict:
        if fid not in cache:
            try:
                r = client.get(f"/api/Projects/{fid}")
                f = r.get("flow", r) if isinstance(r, dict) else r
                cache[fid] = {v["id"]: v for v in (f.get("variables") or [])}
            except Exception:  # noqa: BLE001 - unreadable target: can't assert its contract
                cache[fid] = {}
        return cache[fid]

    return resolve


def run_fe_validation(client, flow: dict, *, include_types: bool = True,
                      with_datatypes: bool = True) -> dict:
    """Run the pure FE validator against a flow DTO, gathering live context. Returns a
    report: {clean, error_count, warning_count, errors, warnings}."""
    flow = flow.get("flow", flow) if isinstance(flow, dict) else flow
    datatypes = _load_datatypes(client) if (include_types and with_datatypes) else None
    resolver = _subprocess_resolver(client)
    all_w = fv.validate_flow(flow, datatypes=datatypes, target_vars_of=resolver,
                             include_types=include_types)
    all_w.extend(_flowlint_extras(client, flow, resolver))
    errs, warns = fv.split_severity(all_w)
    return {"clean": not errs, "error_count": len(errs), "warning_count": len(warns),
            "errors": errs, "warnings": warns}


# flow-lint (handlers/flowlint.py) covers three designer save-blockers that are NOT in the
# FE reference file: a stale subprocess side-pannel id, an Execute-Query with a null/bad
# Output, and Node code binding an error-scope/undeclared variable. Fold ONLY those unique
# checks into the gate (the subprocess-mapping ones overlap fevalidation's checkSubprocess,
# so they're excluded to avoid double-reporting). Best-effort: a flow-lint infra hiccup must
# never break a legitimate save, so any failure yields no extra findings.
_FLOWLINT_UNIQUE = {
    "SIDEPANEL_ID", "EXECQUERY_NO_OUTPUT", "EXECQUERY_OUTPUT_UNDECLARED",
    "EXECQUERY_OUTPUT_TYPE", "CODE_ERROR_SCOPE", "CODE_UNDECLARED", "missing_error_variable",
}


def _flowlint_extras(client, flow: dict, resolver) -> list[dict]:
    try:
        from tools.procesio.handlers import flowlint
        tmpl_sp = flowlint._template_sidepanel_ids(client)
        problems = flowlint.lint_flow_dto(flow, tmpl_sp, resolver)
    except Exception:  # noqa: BLE001 - extras are best-effort; never block a save on them
        return []
    out: list[dict] = []
    for p in problems:
        if p.get("kind") not in _FLOWLINT_UNIQUE:
            continue
        name = p.get("action")
        out.append({"severity": "error", "code": p["kind"], "text": p.get("detail", ""),
                    "badges": [name] if name else [], "actionId": None, "action": name})
    return out


def run_be_validation(client, flow: dict) -> dict:
    """Run PROCESIO's own validator (POST /api/Projects/validate). Empty 200 => valid."""
    dto = flow.get("flow", flow) if isinstance(flow, dict) and "flow" in flow else flow
    try:
        res = client.post("/api/Projects/validate", dto)
    except ProcesioAPIError as e:
        det = e.details if isinstance(e.details, dict) else {"body": e.details}
        return {"valid": False, "errors": det.get("body", det)}
    empty = (not res) or (isinstance(res, dict)
                          and list(res.keys()) == ["raw_text"] and not res["raw_text"])
    if empty:
        return {"valid": True, "errors": []}
    errs = (res.get("errors") or res.get("validationErrors")) if isinstance(res, dict) else None
    valid = res.get("isValid") if isinstance(res, dict) else None
    return {"valid": valid if valid is not None else (not errs), "errors": errs, "result": res}


# -- the save gate ------------------------------------------------------------

def pre_save_validate(client, dto: dict, *, force: bool = False,
                      include_types: bool = True) -> dict:
    """Gate a process SAVE: FE (designer) validation first, then BE validation.

    Returns a combined report {fe, be, blocked}. Raises ValidationBlocked when there are
    blocking errors and force is False — so the caller (create/edit) aborts before the
    POST/PUT. FE-warning-only (type-mismatch) never blocks. --force bypasses everything.
    """
    fe = run_fe_validation(client, dto, include_types=include_types)
    be = run_be_validation(client, dto)
    blocked = (not fe["clean"]) or (be.get("valid") is False)
    report = {"fe": fe, "be": be, "blocked": blocked, "forced": bool(force)}
    if blocked and not force:
        n_fe = fe["error_count"]
        n_be = len(be.get("errors") or []) if be.get("valid") is False else 0
        raise ValidationBlocked(
            f"Save blocked by validation: {n_fe} designer (front-end) error(s), "
            f"{n_be} back-end error(s). Fix them, or pass --force to override.", report)
    return report


# -- the live action ----------------------------------------------------------

def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="process (project) id to validate")
    p.add_argument("--no-types", dest="no_types", action="store_true",
                   help="skip the advisory data-type-mismatch (warning) layer")
    p.add_argument("--include-be", dest="include_be", action="store_true",
                   help="also run the back-end validator (POST /api/Projects/validate)")


def process_fe_validate(client, args) -> dict:
    resp = client.get(f"/api/Projects/{args.id}")
    flow = resp.get("flow", resp) if isinstance(resp, dict) else resp
    fe = run_fe_validation(client, flow, include_types=not args.no_types)
    out = {"id": args.id, "title": flow.get("title") or flow.get("Title"),
           "clean": fe["clean"], "error_count": fe["error_count"],
           "warning_count": fe["warning_count"],
           "errors": fe["errors"], "warnings": fe["warnings"]}
    if args.include_be:
        out["backend"] = run_be_validation(client, flow)
    return out


ACTIONS = {
    "process-fe-validate": ActionDef(
        func=process_fe_validate, add_args=_args, needs_client=True,
        description="Front-end (designer-layer) 'Process Errors' validation on a live "
                    "process — the client-side check that BLOCKS designer Save but which "
                    "POST /api/Projects/validate does NOT catch: unconnected actions, "
                    "missing Start/Stop, empty node names, required-empty fields, leftover "
                    "placeholders, bad number/integer values, out-of-range limits, "
                    "duplicate/primitive-named variables, and unmapped required subprocess "
                    "inputs. clean=true when no blocking errors. Data-type mismatches are "
                    "reported as (non-blocking) warnings. This same check auto-runs before "
                    "every process-create / process-edit. Add --include-be for the BE layer."),
}


# -- saving a fetched flow ----------------------------------------------------

def save_flow(client, flow: dict, *, flow_id: str, valid: bool) -> dict:
    """PUT a flow with its validity mark stamped to `valid`, and report what the server KEPT.

    Two measured facts about the platform put this in one place rather than a bare PUT at
    each call site. Both were established against the live API, not assumed:

    * `isValid` is never computed by the back end. It stores whatever the PUT body
      carries, and defaults it to TRUE when the body omits the field. So a writer that
      passes a fetched flow straight through leaves a corrected process marked broken
      for ever, and one that drops the field marks a broken process valid.
    * The runtime validator (POST /api/Projects/validate) answers EMPTY - "valid" - for
      flows the designer refuses to save, so `valid` has to carry the FE+BE verdict the
      create/edit gate applies, never the runtime answer alone.

    The mark is stamped, never blocked on. Saving a half-built process is deliberate
    platform behaviour; the point of the mark is to say so truthfully.

    The returned `isValid` is RE-READ after the PUT, because reporting the pre-save
    measurement describes the flow that was sent rather than the one the platform kept,
    and those two genuinely differ. A read-back that fails leaves it None with a note:
    the PUT already landed, so failing the whole call here would misreport a save that
    succeeded.
    """
    flow["isValid"] = bool(valid)
    out: dict = {"stamped": bool(valid)}
    client.put("/api/Projects", flow)
    try:
        stored = client.get(f"/api/Projects/{flow_id}")
        f = stored.get("flow", stored) if isinstance(stored, dict) else stored
        out["isValid"] = f.get("isValid") if isinstance(f, dict) else None
    except Exception as e:  # noqa: BLE001 - the PUT landed; only the read-back failed
        out["isValid"] = None
        out["readback_error"] = str(e)
    return out
