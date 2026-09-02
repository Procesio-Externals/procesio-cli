"""flow-lint: replicate the designer's client-side "Process Errors" checks on a live flow.

Why this exists: POST /api/Projects/validate only validates the RUNTIME layer (parameters) and
returns EMPTY even when the designer refuses to SAVE. The designer's "Process Errors" panel is a
separate CLIENT-SIDE check of the DESIGNER layer (customData) with NO server endpoint. This lint
replicates that designer check so a flow can be verified offline / in CI.

Checks (per action, against the DESIGNER customData layer):
  1. SIDEPANEL_ID  — a Call/Trigger Subprocess node whose "Subprocess Configuration" side-pannel
     setting id != the CURRENT template's id. PROCESIO bumped the template's side-pannel id over
     time; nodes built against an older template keep the old id, so the designer can't find the
     mapping and reports EVERY required input as "missing". THE most common cause of the phantom
     "Mapping of required subprocess variable (X) is missing." (Networky: 1da555da / 15af8b81 vs
     current 5456caf0 for Call, 8540605e for Trigger.)
  2. REQ_INPUT_UNMAPPED — a required target input (type 10, isRequired) with no process-inputs row.
  3. OUTPUT_NOT_TYPE30 — a process-outputs row mapping a target var that is NOT an output (type 30).
     A subprocess only exposes type-30 vars as outputs; mapping a type-20 internal var => the
     designer flags "Check data mapping."
  4. EXECQUERY_NO_OUTPUT — an Execute Query whose Output subsection is null. The designer requires it.
  5. CODE_ERROR_SCOPE / CODE_UNDECLARED — Node code binding an isError variable (an action's
     error-port output, shown in the "Error" tab, never free-initialized) or an undeclared var.
  6. missing_error_variable — variableErrorId set to a non-existent variable.
  7. CUSTOMDATA_PLACEHOLDER — a DESIGNER setting value still holding a runtime `<%N%>` placeholder. The
     customData layer mirrors each Parameter EXCEPT a variable ref is the raw variableId (GUID) there, not
     the positional `<%N%>`. A `<%N%>` left in a customData value = the param->customData mirror was skipped
     (hand-rolled flow edits bypassing the builder's _apply_values_to_config) -> the designer can't resolve
     the token and paints it RED. (Caught three times in review before the rule was written down.)

Born 2026-07-05; rebuilt 2026-07-06 after runtime-only versions repeatedly reported false "clean".
"""
from __future__ import annotations

import argparse
import re

from tools.procesio.actiondef import ActionDef
from tools.procesio.handlers.common import add_profile_arg

CODE_PID = "1e6a5523-2091-6c4c-94ac-c7984074673d"
NULL_GUID = "00000000-0000-0000-0000-000000000000"
_SUB_TEMPLATES = ("Call Subprocess", "Trigger Subprocess")
OUTPUT_TYPE = 30  # subprocess variables exposed as outputs
# built-in scalar datatypes share this prefix; the only object among them is ...1221 (any/Object).
# An Execute Query Output is a SQL result SET -> must be a list<Object>: isList=True and the element
# type an Object (the generic ...1221 OR any custom DataModel, whose GUID does NOT share this prefix).
_PRIM_PREFIX = "0317bfee-b2f5-4bde-bfe8-1212"
_GENERIC_OBJECT = "0317bfee-b2f5-4bde-bfe8-121212121221"
# The DESIGNER customData mirrors each Parameter EXCEPT a variable ref is the raw variableId there,
# while the runtime Parameter uses a <%N%> positional placeholder. A <%N%> left in a customData setting
# value means the param->customData mirror was skipped (hand-rolled edits) -> the designer can't resolve
# the token and paints it red ("still red <%0%>"). The builder's _apply_values_to_config does this
# transform; this lint catches nodes that bypassed it.
_PLACEHOLDER_RE = re.compile(r"<%\d+%>")


def _is_guid(x) -> bool:
    return isinstance(x, str) and len(x) == 36 and x.count("-") == 4


def _walk_settings(action: dict):
    """Yield every customData.configuration setting (recursing into list-valued settings)."""
    def walk(settings):
        for s in settings or []:
            if isinstance(s, dict):
                yield s
                if isinstance(s.get("value"), list):
                    yield from walk(s["value"])
    for cf in (action.get("customData") or {}).get("configuration") or []:
        yield from walk(cf.get("settings") or [])


def _sidepanel(action: dict) -> dict | None:
    for cf in (action.get("customData") or {}).get("configuration") or []:
        for s in cf.get("settings") or []:
            if s.get("type") == "side-pannel":
                return s
    return None


def _subsection(sidepanel: dict | None, kind: str) -> list:
    for sub in (sidepanel.get("value") or []) if sidepanel else []:
        if sub.get("type") == kind:
            return sub.get("value") or []
    return []


def _execquery_output(action: dict):
    """The Execute Query Output subsection value, or the sentinel '__absent__'."""
    for cf in (action.get("customData") or {}).get("configuration") or []:
        for s in cf.get("settings") or []:
            if s.get("type") == "side-pannel":
                for sub in s.get("value") or []:
                    if str(sub.get("label")) == "Output":
                        return sub.get("value")
    return "__absent__"


def lint_flow_dto(flow: dict, template_sidepanel_ids: dict, target_vars_of) -> list[dict]:
    """Pure lint over a flow DTO.
    template_sidepanel_ids: {"Call Subprocess": id, "Trigger Subprocess": id} (current template).
    target_vars_of(flow_id) -> {var_id: var_dict} for a called subprocess (injected: no network in tests).
    """
    vmap = {v["id"]: v for v in flow.get("variables") or []}
    problems: list[dict] = []

    def add(action, kind, detail):
        problems.append({"action": action, "kind": kind, "detail": detail})

    for a in flow.get("actions") or []:
        nm = a.get("actionName")
        tmpl = a.get("actionTemplateName")

        for s in _walk_settings(a):
            val = s.get("value")
            if isinstance(val, str) and _PLACEHOLDER_RE.search(val):
                add(nm, "CUSTOMDATA_PLACEHOLDER",
                    f"designer setting '{s.get('label')}' still holds a <%N%> placeholder "
                    f"(customData must carry the variable GUID, not the runtime placeholder - the "
                    f"designer paints it red); param->customData mirror was not applied")

        if tmpl == "Node":
            cp = next((p for p in a.get("parameters") or [] if p.get("tabPropertyId") == CODE_PID), None)
            for ve in (cp.get("variable") if cp else []) or []:
                vid = ve.get("variableId")
                v = vmap.get(vid)
                if v is None:
                    add(nm, "CODE_UNDECLARED", f"code binds undeclared variable {vid}")
                elif v.get("isError"):
                    add(nm, "CODE_ERROR_SCOPE",
                        f"code binds error-scope variable '{v.get('name')}' (isError=true)")

        if tmpl == "Execute Query":
            out = _execquery_output(a)
            if out is None or out == "":
                add(nm, "EXECQUERY_NO_OUTPUT", "Execute Query Output subsection is null")
            elif out != "__absent__":
                ov = vmap.get(out)
                if ov is None:
                    add(nm, "EXECQUERY_OUTPUT_UNDECLARED", f"Output variable {out} not declared")
                else:
                    dt = ov.get("dataType") or ""
                    if (not ov.get("isList")) or (dt.startswith(_PRIM_PREFIX) and dt != _GENERIC_OBJECT):
                        add(nm, "EXECQUERY_OUTPUT_TYPE",
                            f"Output '{ov.get('name')}' must be a list<Object> (a SQL result set) - "
                            f"got isList={ov.get('isList')} dataType=...{dt[-4:]} "
                            f"(scalar/primitive -> designer 'data type mismatch')")

        ev = a.get("variableErrorId")
        if ev and ev not in vmap:
            add(nm, "missing_error_variable", f"variableErrorId {ev} not declared")

        if tmpl in _SUB_TEMPLATES:
            sp = _sidepanel(a)
            want = template_sidepanel_ids.get(tmpl)
            if want and (sp is None or sp.get("id") != want):
                add(nm, "SIDEPANEL_ID",
                    f"side-pannel id {sp.get('id') if sp else None} != current template {want} "
                    f"(designer cannot find the mapping)")
            target = next((p["value"] for p in a.get("parameters") or []
                           if _is_guid(p.get("value")) and p["value"] != NULL_GUID), None)
            if not target:
                continue
            tv = target_vars_of(target) or {}
            mapped_in = {r.get("subprocess"): r.get("process") for r in _subsection(sp, "process-inputs")}
            for vid, v in tv.items():
                if v.get("type") == 10 and v.get("isRequired"):
                    src = mapped_in.get(vid)
                    if src is None or src == "":
                        add(nm, "REQ_INPUT_UNMAPPED",
                            f"required subprocess input '{v.get('name')}' has no designer mapping")
                    else:
                        root = str(src).split(".")[0]
                        if _is_guid(root) and root not in vmap:
                            add(nm, "REQ_INPUT_DEAD_SOURCE",
                                f"input '{v.get('name')}' mapped from undeclared variable {root}")
            for r in _subsection(sp, "process-outputs"):
                ov = tv.get(r.get("subprocess"))
                if ov is not None and ov.get("type") != OUTPUT_TYPE:
                    add(nm, "OUTPUT_NOT_TYPE30",
                        f"output maps target var '{ov.get('name')}' which is type {ov.get('type')}, "
                        f"not an exposed output (type {OUTPUT_TYPE})")
    return problems


def _args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="flow (process) id to lint")


def _template_sidepanel_ids(client) -> dict:
    acts = client.get("/api/Actions?getFullAction=true")
    if isinstance(acts, dict):
        acts = acts.get("result", acts)
        acts = acts.get("actions", acts) if isinstance(acts, dict) else acts
    out = {}
    for tn in _SUB_TEMPLATES:
        t = next((a for a in acts if a.get("name") == tn), None)
        if not t:
            continue
        sp = next((s["id"] for tab in t.get("configuration") or []
                   for s in tab.get("settings") or [] if s.get("type") == "side-pannel"), None)
        if sp:
            out[tn] = sp
    return out


def flow_lint(client, args) -> dict:
    resp = client.get(f"/api/Projects/{args.id}")
    flow = resp.get("flow", resp) if isinstance(resp, dict) else resp
    tmpl_sp = _template_sidepanel_ids(client)
    cache: dict = {}

    def target_vars_of(fid: str) -> dict:
        if fid not in cache:
            try:
                r = client.get(f"/api/Projects/{fid}")
                f = r.get("flow", r) if isinstance(r, dict) else r
                cache[fid] = {v["id"]: v for v in f.get("variables") or []}
            except Exception:  # noqa: BLE001 - unreadable target -> can't assert its contract
                cache[fid] = {}
        return cache[fid]

    problems = lint_flow_dto(flow, tmpl_sp, target_vars_of)
    return {"id": args.id, "title": flow.get("title"), "clean": not problems,
            "problem_count": len(problems), "problems": problems}


ACTIONS = {
    "flow-lint": ActionDef(
        func=flow_lint, add_args=_args, needs_client=True,
        description="Designer-layer 'Process Errors' lint on a live flow (the check that blocks "
                    "designer SAVE, which POST /Projects/validate does NOT catch): stale subprocess "
                    "side-pannel ids, unmapped/dead required subprocess inputs, subprocess outputs "
                    "mapped to non-output (non-type-30) vars, Execute Query with null Output, and Node "
                    "code binding error-scope/undeclared vars. clean=true when none."),
}
