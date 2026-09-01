"""Document template builder — PURE config -> DocumentTemplateDto.

A document template is reusable rich-text/HTML with `<%placeholder%>` variables,
rendered by the "Generate Document" action in a process.

API (verified live 2026-06-24):
  - Create: POST /api/DocumentTemplate (client-supplied id; returns empty)
  - Get:    GET  /api/DocumentTemplate/{id}
  - Edit:   PUT  /api/DocumentTemplate
  - Delete: DELETE /api/DocumentTemplate/{id}
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from tools.procesio.dto import refdata
from tools.procesio.dto.framework import Component

DIR = Path(__file__).resolve().parent

_ORIENTATION = {"portrait": 0, "landscape": 1}


def _new_id(ctx) -> str:
    return (ctx.get("new_id") or (lambda: str(uuid.uuid4())))()


def _esc(s: str) -> str:
    """HTML-entity-encode & < > " exactly like the PROCESIO document editor persists."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def _encode_body(body: str) -> str:
    """PROCESIO's document editor stores the body HTML-ENTITY-ENCODED and SINGLE-LINE.
    The renderer DECODES then walks the resulting DOM to substitute placeholders and to
    detect a list<model> repeating <tr> (the single <tbody><tr> whose <td>s carry
    `<%listVarId.attrId%>` is cloned once per list element). A RAW, multi-line body pushed
    via the API is never recognised by that DOM walk -> list-bound tables render every
    `<%hits.*%>` cell as "Unknown" (verified live: every working list<model> doc stores
    `&lt;%`, our raw-HTML doc was the lone exception). So mirror the editor: collapse
    whitespace around newlines to a single line, then entity-encode (placeholders
    `<%id%>` become `&lt;%id%&gt;`)."""
    return _esc(re.sub(r"\s*\n\s*", "", body or ""))


def _variable(v: dict, ctx: dict) -> dict:
    if "model" in v:
        ref = v["model"].strip()
        dt = ctx.get("models", {}).get(ref.lower()) or ref
    else:
        dt = refdata.primitive_type_id(v.get("type", "string"))
    return {
        "id": _new_id(ctx), "dataType": dt, "type": 10, "name": v["name"],
        "defaultValue": v.get("default"), "isList": bool(v.get("isList", False)),
        # Document-template variables are placeholders FILLED BY the Generate Document
        # action (destinations) — never flow inputs. Real templates store isInput:false
        # for every variable (scalar AND list). With isInput:true the designer treats a
        # list<model> var as a flat input and WON'T expand its model attributes -> the
        # repeating table can't bind those fields and renders "Unknown". So default false.
        "isInput": bool(v.get("isInput", False)), "isOutput": bool(v.get("isOutput", False)),
    }


def _resolve_body_placeholders(body: str, name_to_id: dict, var_attrs: dict) -> str:
    """The render engine resolves body placeholders by variable **id** (and for a
    repeating table over a list model, by `<%listId.attrId%>`). Authors write
    friendly names; translate `<%name%>` -> `<%id%>` and `<%listName.attrName%>` ->
    `<%listId.attrId%>` (var_attrs[listName] = {attrName: attrId})."""
    def sub(m):
        inner = m.group(1)
        head, _, rest = inner.partition(".")
        key = head.strip().lower()
        vid = name_to_id.get(key)
        if not vid:
            return m.group(0)
        if rest:
            attr_id = (var_attrs.get(key) or {}).get(rest.strip().lower(), rest)
            return f"<%{vid}.{attr_id}%>"
        return f"<%{vid}%>"
    return re.sub(r"<%([^%]+)%>", sub, body)


def build(config: dict, ctx: dict) -> dict:
    ctx = dict(ctx)
    orient = config.get("orientation", "portrait")
    orient_code = _ORIENTATION.get(str(orient).strip().lower(), orient if isinstance(orient, int) else 0)
    variables = [_variable(v, ctx) for v in config.get("variables", [])]
    name_to_id = {(c.get("name") or "").strip().lower(): v["id"]
                  for c, v in zip(config.get("variables", []), variables)}
    body = _resolve_body_placeholders(config.get("body", ""), name_to_id,
                                      ctx.get("var_attrs", {}))
    body = _encode_body(body)  # editor-format: encoded + single-line (binds list tables)
    return {
        "id": ctx.get("doc_id") or _new_id(ctx),
        "name": config["name"],
        "description": config.get("description"),
        "body": body,
        "placeholderDelimiterStart": _esc(config.get("placeholderStart", "<%")),
        "placeholderDelimiterStop": _esc(config.get("placeholderStop", "%>")),
        "documentPageSize": config.get("pageSize", "A4"),
        "documentPageOrientation": orient_code,
        "variables": variables,
    }


def prepare_ctx(client, config: dict) -> dict:
    # NOTE: list<model> repeating tables DO work (proven by the Round 12 render test in
    # PHASE4-E2E-NOTES.md) — bind `<%listVar.attr%>` in one <tr> and feed the whole list
    # in one Generate-Document mapping (destination.attribute null), with the list fed
    # via a process variable typed as the item model (isList:true) + a JSON-array
    # DefaultValue. The two requirements: (1) the editor body encoding handled by
    # _encode_body in build(); (2) the item data model must be created with ALL its
    # attributes in the initial POST /api/DataTypes — attributes added later via the
    # /api/DataTypes/attribute edit path are missing from the runtime's COMPILED model
    # and render as "Unknown" / "Unable to find attribute <id>". There is no platform
    # limit on list tables — the earlier "dead-end" warning was the stale compiled model.
    model_vars = [v for v in config.get("variables", []) if v.get("model")]
    if not model_vars:
        return {}
    models: dict[str, str] = {}
    r = client.get("/api/DataTypes", {"addProperties": False, "pageNumber": 1,
                                      "pageItemCount": 500, "includeProcesioEntries": True,
                                      "includeExternalEntries": True})
    for it in (r.get("pageItems") if isinstance(r, dict) else r) or []:
        nm = (it.get("name") or it.get("Name") or "").strip().lower()
        if nm:
            models[nm] = it.get("id") or it.get("Id")
    # for each model-typed variable, fetch its model's attribute name->id (so a body
    # table `<%varName.attrName%>` can be translated to `<%varId.attrId%>`)
    var_attrs: dict[str, dict] = {}
    for v in model_vars:
        ref = v["model"].strip()
        mid = models.get(ref.lower()) or ref
        try:
            m = client.get(f"/api/DataTypes/{mid}")
            var_attrs[(v.get("name") or "").strip().lower()] = {
                (a.get("name") or "").strip().lower(): a.get("id")
                for a in (m.get("attributes") or [])}
        except Exception:  # noqa: BLE001
            pass
    return {"models": models, "var_attrs": var_attrs}


def _extract_id(resp, dto):
    # POST returns empty; the template keeps the client-supplied id.
    if isinstance(resp, dict) and (resp.get("id") or resp.get("Id")):
        return resp.get("id") or resp.get("Id")
    return dto.get("id") if isinstance(dto, dict) else None


def _edit(client, resource_id, config, ctx):
    ctx = dict(ctx)
    ctx["doc_id"] = resource_id
    dto = build(config, ctx)
    client.put("/api/DocumentTemplate", dto)
    return client.get(f"/api/DocumentTemplate/{resource_id}")


COMPONENT = Component(
    name="document",
    description="PROCESIO document template: HTML body with <%placeholder%> variables.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/DocumentTemplate"),
    get_path="/api/DocumentTemplate/{id}",
    extract_id=_extract_id,
    prepare_ctx=prepare_ctx,
    edit=_edit,
)
