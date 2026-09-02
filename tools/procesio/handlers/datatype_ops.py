"""Full data-model (DataType) lifecycle actions beyond create/edit.

Mirrors how the PROCESIO UI works with data models (HAR-verified, see the
`procesio-datatype-create` memory note):

  - `datatype-create` / `datatype-edit` (dto_actions) build a model attribute-by-attribute
    via POST /api/dataTypes/attribute/{id} — the path that COMPILES attributes into the
    runtime model and keeps referenced sub-models REUSABLE in other models.
  - `datatype-create` with `fromJson` infers a model from a JSON sample; its nested inner
    models are created PRIVATE (NOT reusable in other models) until promoted.
  - `datatype-change-to-public` promotes a private inner model to PUBLIC (reusable).
  - `datatype-clone` clones an inner model.
  - `datatype-add-attribute` / `-edit-attribute` / `-delete-attribute` operate on one attr.
  - `datatype-get` / `datatype-delete` read / remove a model.

JSON in / JSON out; impure (live client). The v1.19 surface is /api/DataTypes/*.
"""
from __future__ import annotations

import argparse
import re

from tools.procesio.actiondef import ActionDef
from tools.procesio.dto import refdata
from tools.procesio.errors import UsageError
from tools.procesio.handlers.common import add_profile_arg

_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                   r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _bool_opt(s) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")


def _resolve_data_type(client, value: str) -> str:
    """Resolve a data-type reference to its id: a primitive name (string/integer/…),
    an existing model name (looked up live), or a guid (used as-is)."""
    v = (value or "").strip()
    if not v:
        raise UsageError("--data-type is required")
    if _GUID.match(v):
        return v
    try:
        return refdata.primitive_type_id(v)
    except KeyError:
        pass
    r = client.get("/api/DataTypes", {"pageNumber": 1, "pageItemCount": 1000,
                                      "includeProcesioEntries": True, "includeExternalEntries": True})
    items = r.get("pageItems") if isinstance(r, dict) else r
    for it in items or []:
        if (it.get("name") or it.get("Name") or "").strip().lower() == v.lower():
            return it.get("id") or it.get("Id")
    raise UsageError(f"unknown data type {value!r} (not a primitive, a guid, or an existing model name)")


def _attr_summary(model: dict) -> list:
    return [{"id": a.get("id"), "name": a.get("name"), "dataTypeId": a.get("dataTypeId"),
             "isList": a.get("isList"), "isDataModel": a.get("isDataModel"),
             "inlinedChildren": len(a.get("attributes") or [])}
            for a in (model.get("attributes") or [])]


# -- model get / delete -------------------------------------------------------

def get_datatype(client, args) -> dict:
    return {"result": client.get(f"/api/DataTypes/{args.id}")}


def delete_datatype(client, args) -> dict:
    client.request("DELETE", f"/api/DataTypes/{args.id}")
    return {"deleted": True, "id": args.id}


# -- attribute add / edit / delete -------------------------------------------

def _store_built_on_model(client, model_id: str):
    """Best-effort: the id of a data store whose data-model IS `model_id`, else None.

    B-048 cluster 4a reported that adding an attribute to such a model DESTROYS the store
    (both POSTs return ok, then columns read `[]` and rows go unreadable). Re-tested on a
    real from-data-model store (2026-09) it did NOT reproduce, so the caller only WARNS on a
    match, never refuses. The store's own data-model id (a from-data-model store gets a COPY
    model, distinct from the source) is what matches here — verified live against
    `GET /api/DataStore/{id}/data-model`. Fail-OPEN: any read error/unknown shape -> None,
    so a transient hiccup never even warns.
    """
    try:
        listing = client.get("/api/DataStore") or {}
    except Exception:  # noqa: BLE001 - advisory guard, never fatal
        return None
    stores = listing if isinstance(listing, list) else (
        listing.get("data") or listing.get("pageItems") or listing.get("items") or [])
    for s in stores if isinstance(stores, list) else []:
        sid = (s.get("id") or s.get("dataStoreId")) if isinstance(s, dict) else None
        if not sid:
            continue
        try:
            dm = client.get(f"/api/DataStore/{sid}/data-model") or {}
        except Exception:  # noqa: BLE001
            continue
        mid = dm.get("id") or dm.get("dataTypeId") or (dm.get("dataModel") or {}).get("id")
        if mid and str(mid) == str(model_id):
            return sid
    return None


def add_attribute(client, args) -> dict:
    """Add ONE attribute via POST /api/dataTypes/attribute/{id} — the only path that
    COMPILES the attribute into the runtime model (and inlines a referenced child model
    + links its parentIds). --data-type accepts a primitive name, an existing model name,
    or a guid; --is-list makes it a list of that type.

    WARNS (non-blocking) when the model backs a data store: B-048 cluster 4a reported that
    such an add DESTROYS the store, but re-testing on a real from-data-model store (2026-09)
    did NOT reproduce it — the store kept its columns and rows — so this is a caution, not a
    refusal. --force suppresses the warning."""
    warning = None
    if not getattr(args, "force", False):
        store = _store_built_on_model(client, args.id)
        if store:
            warning = (
                f"model {args.id} backs data store {store}. B-048 cluster 4a reported that "
                f"adding an attribute to a store-backing model DESTROYS the store (columns "
                f"read [], rows unreadable), but a real from-data-model store re-tested "
                f"2026-09 SURVIVED this exact add, so treat it as a caution rather than a "
                f"certainty: re-read the store (datastore-get / get-rows) and confirm its "
                f"columns and rows afterwards. --force suppresses this warning.")
    dtid = _resolve_data_type(client, args.data_type)
    payload = {"id": None, "name": args.name,
               "displayName": args.display_name or args.name, "dataTypeId": dtid,
               "isList": bool(args.is_list), "jsonProperty": args.json_property or args.name,
               "parentDataTypeId": args.id}
    if args.hidden:
        payload["hidden"] = True
    if args.public:
        payload["isPublic"] = True
    client.post(f"/api/DataTypes/attribute/{args.id}", payload)
    model = client.get(f"/api/DataTypes/{args.id}")
    out = {"added": True, "model": args.id, "attribute": args.name,
           "attributes": _attr_summary(model)}
    if warning:
        out["warning"] = warning
    return out


def edit_attribute(client, args) -> dict:
    """Edit an existing attribute via PUT /api/dataTypes/attribute/{id} (full object).
    --attribute is the attribute id or its current name; only the flags you pass change."""
    model = client.get(f"/api/DataTypes/{args.id}")
    attr = next((a for a in (model.get("attributes") or [])
                 if a.get("id") == args.attribute
                 or (a.get("name") or "").lower() == str(args.attribute).lower()), None)
    if not attr:
        raise UsageError(f"model {args.id} has no attribute {args.attribute!r}")
    if args.name:
        attr["name"] = args.name
    if args.display_name:
        attr["displayName"] = args.display_name
    if args.data_type:
        attr["dataTypeId"] = _resolve_data_type(client, args.data_type)
    if args.is_list is not None:
        attr["isList"] = bool(args.is_list)
    if args.json_property:
        attr["jsonProperty"] = args.json_property
    if args.hidden is not None:
        attr["hidden"] = bool(args.hidden)
    if args.public is not None:
        attr["isPublic"] = bool(args.public)
    client.put(f"/api/DataTypes/attribute/{args.id}", attr)
    return {"edited": True, "model": args.id, "attribute": attr.get("name"),
            "attributes": _attr_summary(client.get(f"/api/DataTypes/{args.id}"))}


def delete_attribute(client, args) -> dict:
    model = client.get(f"/api/DataTypes/{args.id}")
    attr = next((a for a in (model.get("attributes") or [])
                 if a.get("id") == args.attribute
                 or (a.get("name") or "").lower() == str(args.attribute).lower()), None)
    if not attr:
        raise UsageError(f"model {args.id} has no attribute {args.attribute!r}")
    client.request("DELETE", f"/api/DataTypes/attribute/{args.id}/{attr.get('id')}")
    return {"deleted": True, "model": args.id, "attribute": attr.get("name")}


# -- promote private inner model / clone -------------------------------------

def change_to_public(client, args) -> dict:
    """Promote a PRIVATE inner data model (one created by `fromJson`) to PUBLIC so it can
    be reused in other models. --root-id = the top/root model id, --id = the inner id."""
    client.post("/api/DataTypes/changeToPublic",
                {"rootDataTypeId": args.root_id, "dataTypeId": args.id})
    return {"changedToPublic": True, "rootDataTypeId": args.root_id, "dataTypeId": args.id,
            "result": client.get(f"/api/DataTypes/{args.id}")}


def clone_datatype(client, args) -> dict:
    """Clone an inner data model. --root-id = the top/root model id, --id = the inner id."""
    resp = client.post("/api/DataTypes/clone",
                       {"rootDataTypeId": args.root_id, "dataTypeId": args.id})
    return {"cloned": True, "rootDataTypeId": args.root_id, "dataTypeId": args.id, "result": resp}


# -- argparse -----------------------------------------------------------------

def _id_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="data model id")


def _add_attr_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="parent model id")
    p.add_argument("--name", required=True, help="attribute name")
    p.add_argument("--data-type", dest="data_type", required=True,
                   help="primitive name (string/integer/…), an existing model name, or a guid")
    p.add_argument("--is-list", dest="is_list", action="store_true",
                   help="attribute holds a list of the type")
    p.add_argument("--display-name", dest="display_name")
    p.add_argument("--json-property", dest="json_property", help="JSON key (defaults to name)")
    p.add_argument("--hidden", action="store_true")
    p.add_argument("--public", action="store_true", help="mark the attribute isPublic")
    p.add_argument("--force", action="store_true",
                   help="suppress the store-backing caution (B-048 cluster 4a)")


def _edit_attr_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="parent model id")
    p.add_argument("--attribute", required=True, help="attribute id or current name")
    p.add_argument("--name")
    p.add_argument("--display-name", dest="display_name")
    p.add_argument("--data-type", dest="data_type", help="new type (primitive/model/guid)")
    p.add_argument("--json-property", dest="json_property")
    p.add_argument("--is-list", dest="is_list", type=_bool_opt, default=None,
                   help="true/false (omit to leave unchanged)")
    p.add_argument("--hidden", type=_bool_opt, default=None, help="true/false")
    p.add_argument("--public", type=_bool_opt, default=None, help="isPublic true/false")


def _del_attr_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--id", required=True, help="parent model id")
    p.add_argument("--attribute", required=True, help="attribute id or current name")


def _promote_args(p: argparse.ArgumentParser) -> None:
    add_profile_arg(p)
    p.add_argument("--root-id", dest="root_id", required=True, help="root/top model id")
    p.add_argument("--id", required=True, help="inner model id to promote/clone")


ACTIONS = {
    "datatype-get": ActionDef(
        func=get_datatype, add_args=_id_args, needs_client=True,
        description="Get a data model with its attributes (GET /api/DataTypes/{id})."),
    "datatype-delete": ActionDef(
        func=delete_datatype, add_args=_id_args, needs_client=True,
        description="Delete a data model (DELETE /api/DataTypes/{id})."),
    "datatype-add-attribute": ActionDef(
        func=add_attribute, add_args=_add_attr_args, needs_client=True,
        description="Add one attribute to a model — compiles it; a model-typed attr inlines the child + keeps it reusable."),
    "datatype-edit-attribute": ActionDef(
        func=edit_attribute, add_args=_edit_attr_args, needs_client=True,
        description="Edit one attribute (PUT /api/dataTypes/attribute/{id})."),
    "datatype-delete-attribute": ActionDef(
        func=delete_attribute, add_args=_del_attr_args, needs_client=True,
        description="Delete one attribute (DELETE /api/dataTypes/attribute/{id}/{attrId})."),
    "datatype-change-to-public": ActionDef(
        func=change_to_public, add_args=_promote_args, needs_client=True,
        description="Promote a private inner model (from fromJson) to public so it's reusable (POST /api/DataTypes/changeToPublic)."),
    "datatype-clone": ActionDef(
        func=clone_datatype, add_args=_promote_args, needs_client=True,
        description="Clone an inner data model (POST /api/DataTypes/clone)."),
}
