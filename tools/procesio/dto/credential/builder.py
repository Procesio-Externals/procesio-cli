"""Credential builder — PURE config -> CredentialsDto.

A credential instance is a saved set of property values for a credential template
(connection type). The builder resolves the template (gtid/gtpid + property ids,
fetched live in prepare_ctx) and maps config `properties: {label: value}` to
`properties: [{id, value}]`. Select/radio option *names* are resolved to their
option value (guid) automatically.

API (verified live 2026-06-24):
  - Create: POST /api/Credentials {gtid, gtpid, name, properties[]} -> {id}
  - Get:    GET  /api/Credentials/{id}
  - Edit:   PUT  /api/Credentials {gid: id, ...}
  - Validate@source: POST /api/Credentials/test (live connection probe)
"""
from __future__ import annotations

from pathlib import Path

from tools.procesio.dto.framework import Component
from tools.procesio.errors import UsageError

DIR = Path(__file__).resolve().parent


def _property_index(template: dict) -> dict:
    out: dict[str, dict] = {}
    for p in template.get("properties") or []:
        if p.get("label"):
            out.setdefault(p["label"].strip().lower(), p)
        if p.get("id"):
            out[p["id"]] = p
    return out


_GUIDISH = 32          # a guid without dashes is 32 hex chars; with dashes, 36


def _looks_guid(v) -> bool:
    s = str(v or "").strip()
    return len(s) >= _GUIDISH and s.count("-") >= 4


def _resolve_option(prop: dict, value):
    """Map an option property's value to the option **guid** the engine expects.

    Accepts the option `name` ("GET"), its `be_value` ("Get"), or the guid itself.

    RAISES on an unmatched value when the property's options are guid-valued. This
    is deliberate: PROCESIO stores whatever string you send, the credential saves
    fine, and then EVERY Call API run using it dies at runtime with
    ``Error while building input model: Unrecognized Guid format.`` — blamed on the
    Call API action, not the credential, which sends you hunting in the wrong place.
    (Cost hours on 2026-07-30 with ``"Method": "POST"``; POST is not even an option —
    the credential Method is only used by the /test probe, Call API carries its own
    Verb.) Non-guid option sets (checkbox-style "true"/"false") still pass through,
    so nothing that worked before breaks.
    """
    opts = prop.get("options")
    if not (isinstance(opts, list) and opts) or not isinstance(value, str):
        return value
    want = value.strip().lower()
    for key in ("name", "be_value", "value"):
        for o in opts:
            if str(o.get(key, "")).strip().lower() == want:
                return o.get("value")
    if any(_looks_guid(o.get("value")) for o in opts):
        allowed = [o.get("name") for o in opts if o.get("name")]
        raise UsageError(
            f"credential property {prop.get('label')!r}: {value!r} is not one of its "
            f"options {allowed}. This property is an option list valued by GUID — "
            f"sending a raw string saves fine but makes every Call API run using this "
            f"credential fail at runtime with 'Unrecognized Guid format'. Pass an "
            f"option name (or its guid). Note: a REST credential's 'Method' is only "
            f"used by the connection test; the Call API action carries its own 'Verb'."
        )
    return value


def build(config: dict, ctx: dict) -> dict:
    template = ctx.get("template")
    if not template:
        raise UsageError("credential build needs the resolved template in ctx "
                         "(prepare_ctx fetches /api/Credentials/types)")
    pidx = _property_index(template)
    props = []
    for label, value in (config.get("properties") or {}).items():
        prop = pidx.get(str(label).strip().lower()) or pidx.get(label)
        if not prop:
            known = sorted({p["label"] for p in template.get("properties") or [] if p.get("label")})
            raise UsageError(f"credential template {template.get('name')!r} has no "
                             f"property {label!r}; known: {known}")
        props.append({"id": prop["id"], "value": _resolve_option(prop, value)})
    dto = {
        "gid": config.get("id"),
        "gtid": template.get("gid"),
        "gtpid": template.get("pid"),
        "name": config["name"],
        "tname": template.get("name"),
        "type": template.get("type"),
        # status is the "validated" flag in the manager list. prepare_ctx runs the
        # /test probe and sets ctx["validated"] so a passing credential persists as
        # validated (functionally identical to not-validated, but cleaner).
        "status": bool(ctx.get("validated", False)),
        "description": config.get("description", ""),
        "properties": props,
    }
    return dto


def _test_ok(res) -> bool:
    """Did POST /api/Credentials/test succeed? Response: {isSuccess, statusCode, ...}."""
    if not isinstance(res, dict):
        return False
    if str(res.get("isSuccess")).strip().lower() == "true":
        return True
    try:
        return 200 <= int(res.get("statusCode")) < 300
    except (TypeError, ValueError):
        return False


def prepare_ctx(client, config: dict) -> dict:
    """Resolve the named credential template to its full definition (gid/pid +
    property ids/options) and run the /test probe so a passing credential is saved
    as **validated** (set ctx["validated"]; build maps it to the status flag). The
    test uses the credential's own `Test endpoint` / test-parameters — those are for
    validation only and do NOT flow to the action, so the action still needs its own
    request params."""
    want = (config.get("template") or "").strip().lower()
    if not want:
        raise UsageError("config.template is required (a credential type name, e.g. 'REST API')")
    types = client.get("/api/Credentials/types")
    for t in types or []:
        if (t.get("name") or "").strip().lower() == want:
            validated = False
            try:                                  # probe so it can persist as validated
                res = client.post("/api/Credentials/test", build(config, {"template": t}))
                validated = _test_ok(res)
            except Exception:  # noqa: BLE001 - never block a create on the probe
                validated = False
            return {"template": t, "validated": validated}
    names = sorted((t.get("name") or "") for t in (types or []))
    raise UsageError(f"unknown credential template {config.get('template')!r}; known: {names}")


def _extract_id(resp, dto):
    if isinstance(resp, dict):
        return resp.get("id") or resp.get("Id") or resp.get("gid")
    return None


def _validate(client, dto, ctx):
    """POST /api/Credentials/test — a live connection probe. Returns the raw
    result; shape is server-defined."""
    try:
        res = client.post("/api/Credentials/test", dto)
        return {"tested": True, "result": res}
    except Exception as e:  # noqa: BLE001 - report, don't abort the create
        return {"tested": False, "error": str(e)[:300]}


def _edit(client, resource_id, config, ctx):
    dto = build({**config, "id": resource_id}, ctx)
    client.put("/api/Credentials", dto)
    return client.get(f"/api/Credentials/{resource_id}")


COMPONENT = Component(
    name="credential",
    description="PROCESIO credential instance: saved values for a connection template.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/Credentials"),
    get_path="/api/Credentials/{id}",
    extract_id=_extract_id,
    prepare_ctx=prepare_ctx,
    validate=_validate,
    edit=_edit,
)
