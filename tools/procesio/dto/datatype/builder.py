"""Data Model (DataType) builder — PURE config -> CreateDataTypeDto.

Verified against POST /api/DataTypes (the server assigns the real model/attribute
ids, ignoring ours; it derives each attribute's type from DataTypeId). See
description.md. Edit is desired-state: PUT renames the model, then attributes are
reconciled (add new / delete removed / replace changed) via the attribute
endpoints — DataType edit cannot change attributes in a single PUT.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from tools.procesio.dto import refdata
from tools.procesio.dto.framework import Component

DIR = Path(__file__).resolve().parent


def _new_id() -> str:
    return str(uuid.uuid4())


def _attribute(a: dict, parent_id: str, ctx: dict) -> dict:
    """Expand one config attribute into a DataAttributeDto. Recursive for inline
    nested objects."""
    nid = ctx.get("new_id") or _new_id
    name = a["name"]
    disp = a.get("displayName") or name
    is_list = bool(a.get("isList", False))
    aid = nid()
    node = {
        "Id": aid, "ParentDataTypeId": parent_id, "Name": name, "DisplayName": disp,
        "DataTypeName": None, "IsPrimaryType": False, "IsProcesio": False,
        "IsPublic": bool(a.get("isPublic", False)), "Type": 1, "IsList": is_list,
        "jsonProperty": a.get("jsonProperty") or name, "hidden": bool(a.get("hidden", False)),
        "Attributes": [],
    }
    if "attributes" in a:                       # inline nested object -> sub data model
        node["DataTypeId"] = nid()
        node["IsDataModel"] = True
        node["CsharpCorrespondent"] = 0
        node["Attributes"] = [_attribute(x, node["Id"], ctx) for x in a["attributes"]]
    elif "model" in a:                          # reference an existing data model
        ref = a["model"].strip()
        node["DataTypeId"] = (ctx.get("models", {}).get(ref.lower()) or ref)
        node["IsDataModel"] = True
        node["CsharpCorrespondent"] = 0
    else:                                       # primitive
        node["DataTypeId"] = refdata.primitive_type_id(a["type"])
        node["IsDataModel"] = False
        node["CsharpCorrespondent"] = refdata.csharp_correspondent(a["type"])
    return node


def build(config: dict, ctx: dict) -> dict:
    """config -> CreateDataTypeDto (the POST /api/DataTypes body)."""
    nid = ctx.get("new_id") or _new_id
    name = config["name"]
    disp = config.get("displayName") or name
    public = bool(config.get("isPublic", True))
    # platform trick: Data Model from JSON — `fromJson` infers the model server-side
    # (prepare_ctx calls POST /api/DataTypes/generate); we wrap it as the Content.
    if ctx.get("generated_content"):
        content = dict(ctx["generated_content"])
        content.update({"Name": name, "DisplayName": disp, "IsDataModel": True,
                        "IsPrimaryType": False, "IsProcesio": False, "IsPublic": public,
                        "CsharpCorrespondent": 0, "Type": 1})
        return {"Name": name, "DisplayName": disp, "IsPublic": public, "Content": content}
    model_id = nid()
    content = {
        "Id": model_id, "Name": name, "DisplayName": disp,
        "IsDataModel": True, "IsPrimaryType": False, "IsProcesio": False,
        "IsPublic": public, "CsharpCorrespondent": 0, "Type": 1, "ParentIds": [],
        "Attributes": [_attribute(a, model_id, ctx) for a in config.get("attributes", [])],
    }
    return {"Name": name, "DisplayName": disp, "IsPublic": public, "Content": content}


# -- live id resolution for `model` references (impure, runs in the handler) ----

def prepare_ctx(client, config: dict) -> dict:
    """Resolve any `model: <name>` references to live data-model ids in the active
    workspace, so the pure build step can stay offline."""
    out: dict = {}
    fj = config.get("fromJson")
    if fj is not None:                          # Data Model from JSON (platform trick)
        content = fj if isinstance(fj, str) else json.dumps(fj)
        gen = client.post("/api/DataTypes/generate",
                          {"Name": config["name"], "DisplayName": config.get("displayName") or config["name"],
                           "Content": content})
        out["generated_content"] = gen
        return out
    refs = _collect_model_refs(config)
    if not refs:
        return {"models": {}}
    models: dict[str, str] = {}
    r = client.get("/api/DataTypes", {"addProperties": False, "pageNumber": 1,
                                      "pageItemCount": 500, "includeProcesioEntries": True,
                                      "includeExternalEntries": True})
    items = r.get("pageItems") if isinstance(r, dict) else r
    for it in (items or []):
        nm = (it.get("name") or it.get("Name") or "").strip().lower()
        if nm:
            models[nm] = it.get("id") or it.get("Id")
    return {"models": models}


def _collect_model_refs(config: dict) -> set[str]:
    found: set[str] = set()

    def walk(attrs):
        for a in attrs or []:
            if "model" in a:
                found.add(a["model"].strip().lower())
            if "attributes" in a:
                walk(a["attributes"])
    walk(config.get("attributes", []))
    # An id reference (a guid) needn't be resolved; only names do, but resolving
    # all is harmless — the builder falls back to the literal when not found.
    return found


def _add_one_attribute(client, parent_id: str, a: dict) -> None:
    """Add ONE attribute to a model via POST /api/DataTypes/attribute/{parentId} — the
    SAME minimal call the PROCESIO UI makes (HAR-verified). For a model-REFERENCE
    attribute (dataTypeId = another model's id) the server auto-inlines that model's
    whole attribute tree into the parent AND compiles it. For an inline NEW sub-model
    (the config used `attributes:`), create the sub-model first (empty + its own
    attributes) then reference it by id — the UI never inlines a brand-new model in one
    call. The minimal payload the UI sends: {id, displayName, name, dataTypeId, isList,
    jsonProperty, parentDataTypeId}; the server derives isDataModel/type/etc."""
    data_type_id = a.get("DataTypeId")
    if a.get("IsDataModel") and a.get("Attributes"):   # inline NEW sub-model -> create first
        sub = client.post("/api/DataTypes", {
            "name": a.get("Name"), "displayName": a.get("DisplayName") or a.get("Name"),
            "content": None, "isPublic": True})
        sub_id = sub.get("id") or sub.get("Id")
        for child in a.get("Attributes") or []:
            _add_one_attribute(client, sub_id, child)
        data_type_id = sub_id
    payload = {
        "id": None, "displayName": a.get("DisplayName") or a.get("Name"),
        "name": a.get("Name"), "dataTypeId": data_type_id,
        "isList": bool(a.get("IsList")), "jsonProperty": a.get("jsonProperty") or a.get("Name"),
        "parentDataTypeId": parent_id}
    if a.get("hidden"):
        payload["hidden"] = True
    if a.get("IsPublic"):
        payload["isPublic"] = True
    client.post(f"/api/DataTypes/attribute/{parent_id}", payload)


def _create(client, dto, ctx):
    """Create a data model exactly the way the PROCESIO UI does (HAR-verified): POST an
    EMPTY model (content:null), then add EVERY attribute one-by-one via the attribute
    endpoint. Attributes placed in the initial POST /api/DataTypes `Content` show up in
    GET but are NEVER compiled into the runtime model — so documents binding the model
    render "Unknown" and Generate Document throws "Unable to find attribute <id>". The
    attribute endpoint is what compiles them (and inlines referenced child models). The
    Data-Model-from-JSON path (generated_content) keeps the single POST — there the
    server infers and creates the nested private models itself."""
    if ctx.get("generated_content"):
        return client.post("/api/DataTypes", dto)
    content = (dto.get("Content") if isinstance(dto, dict) else None) or {}
    resp = client.post("/api/DataTypes", {
        "name": dto.get("Name"), "displayName": dto.get("DisplayName"),
        "content": None, "isPublic": dto.get("IsPublic", True)})
    model_id = (resp.get("id") or resp.get("Id")) if isinstance(resp, dict) else None
    for a in content.get("Attributes") or []:
        _add_one_attribute(client, model_id, a)
    return resp


def _extract_id(resp, dto):
    if isinstance(resp, dict):
        return resp.get("id") or resp.get("Id")
    return None


# -- desired-state edit: PUT rename + reconcile attributes ---------------------

def _edit(client, resource_id, config: dict, ctx: dict):
    name = config["name"]
    disp = config.get("displayName") or name
    # 1) top-level rename / displayName
    client.put("/api/DataTypes", {"Id": resource_id, "Name": name, "DisplayName": disp})
    # 2) reconcile attributes against current
    current = client.get(f"/api/DataTypes/{resource_id}")
    cur_attrs = {(a.get("name") or "").lower(): a for a in (current.get("attributes") or [])}
    want = {a["name"].lower(): a for a in config.get("attributes", [])}
    # delete removed
    for nm, a in cur_attrs.items():
        if nm not in want:
            client.delete(f"/api/DataTypes/attribute/{resource_id}/{a.get('id')}")
    # add new / replace changed
    for nm, a in want.items():
        built = _attribute(a, resource_id, ctx)
        if nm not in cur_attrs:
            _add_one_attribute(client, resource_id, built)  # compiles + inlines model refs
        else:
            cur = cur_attrs[nm]
            same = (cur.get("dataTypeId") == built["DataTypeId"]
                    and bool(cur.get("isList")) == built["IsList"])
            if not same:
                built["Id"] = cur.get("id")
                client.put(f"/api/DataTypes/attribute/{resource_id}", built)
    return client.get(f"/api/DataTypes/{resource_id}")


COMPONENT = Component(
    name="datatype",
    description="PROCESIO data model (DataType): a named set of typed attributes.",
    dir=DIR,
    build=build,
    create_endpoint=("POST", "/api/DataTypes"),
    create=_create,   # add model-reference attrs via the attribute endpoint -> parentIds back-link
    get_path="/api/DataTypes/{id}",
    extract_id=_extract_id,
    prepare_ctx=prepare_ctx,
    edit=_edit,
)
