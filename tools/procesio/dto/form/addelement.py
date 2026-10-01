"""Add one or more controls to a LIVE form, without disturbing anything already on it.

The gap this fills: `form-create` speaks an authoring config and `form-edit` rebuilds a whole form
from one, so neither can add a control to a form that was hand-built in the designer — the two
shapes are different languages (an authoring config has no element ids at all, see
PROCESIO-API-NOTES.md "form-create takes an AUTHORING CONFIG"). Every other form action here is
surgical; adding a control was the missing verb, and without it a new admin button meant
hand-writing a stored element DTO.

What makes a splice safe rather than a rebuild: PROCESIO backs each control with a data-model
sub-model whose id IS the element id, and whose attribute ids ARE that element's own config ids
(see `_build_data_model` in builder.py). New controls therefore contribute new sub-models and touch
nothing else — which is the whole point, because a RUN_PROCESS/MAP trigger references a field by the
path `root.fields.elementId.valueAttrId`. Regenerating the live model would silently break every
mapping already on the form, so this never rebuilds it; it appends to it.

Pure: takes the form as GET returns it, returns a NEW `Data` dict. The caller validates and PUTs.
"""
from __future__ import annotations

import copy
import json
import re
import uuid

from tools.procesio.dto.form import builder
from tools.procesio.errors import UsageError


def _new_id(_ctx=None) -> str:
    return str(uuid.uuid4())


def _name_of(element: dict) -> str | None:
    for c in element.get("configs") or []:
        if c.get("key") == "name":
            return c.get("value")
    return None


def _sub_model(element: dict, fields_ns: str, ctx: dict) -> dict:
    """The `fields` sub-model for one control — element id, config ids, same as a full build.

    Mirrors `builder._build_data_model`'s per-element branch. It is duplicated rather than shared
    because that function rebuilds the WHOLE model from the shell, which is exactly what a splice
    must not do to a designer-built form.
    """
    eid = element["id"]
    name = _name_of(element) or eid
    sub = {"id": eid, "dataTypeId": eid, "name": name, "displayName": name,
           "isDataModel": True, "isList": False, "isProcesio": False,
           "isPublic": False, "parentDataTypeId": fields_ns, "jsonProperty": None,
           "attributes": []}
    for c in element.get("configs") or []:
        shape = builder._dm_shape(element, c)     # the same rule form-create applies
        if shape is None:
            continue
        sub["attributes"].append(
            builder._dm_attr(builder._attr_name(c["key"]), c.get("id") or _new_id(ctx),
                             shape[0], eid, shape[1]))
    return sub


# container type -> the config holding the ordered NAMES of the children it renders.
_LIST_CONFIG = {"tabs": "tabs", "table": "rows", "stepper": "steps"}


def unreachable_in_row(elements: list, parent_id: str | None) -> str | None:
    """Warn when a control is being placed where no process map can read it.

    A control inside a table row exists once per row, so a map reads it through the ROW - a
    five-segment path ending at the child element, via the row's `$.fields` model attribute. A row
    that was itself spliced in has no `$.fields`: this function builds a sub-model from an element's
    own configs, and there is no way to add one afterwards that the runtime will honour. The control
    then displays fine, accepts typing, and sends nothing, which looks like a broken save rather
    than a control in the wrong place.

    Returns the warning text, or None when the placement is fine.
    """
    if not parent_id:
        return None
    by_id = {e.get("id"): e for e in elements}
    node = by_id.get(parent_id)
    seen = set()
    while node is not None and node.get("id") not in seen:
        seen.add(node.get("id"))
        if node.get("type") == "dynamic-table-row":
            name = _name_of(node) or node.get("id")
            return (f"placed inside the table row {name!r}: a control there exists once per row, so "
                    f"a RUN_PROCESS map reading its own field path gets nothing. Address it through "
                    f"the row (formId.fieldsNs.rowId.$fieldsAttrId.childId), or - if that row has no "
                    f"'$.fields' attribute, which is the case for any row that was itself spliced in "
                    f"- put the control outside the row and copy the value out from the row's "
                    f"'$.item' when the panel opens.")
        node = by_id.get(node.get("parentId"))
    return None


def _resolve_parent(elements: list, parent: str | None) -> str | None:
    if not parent:
        return None
    for el in elements:
        if el.get("id") == parent or _name_of(el) == parent:
            return el["id"]
    known = ", ".join(sorted(n for n in (_name_of(e) for e in elements) if n))
    raise UsageError(f"parent element not found: {parent!r}. Known element names: {known}")


def add_elements(form: dict, specs: list, *, parent: str | None = None) -> dict:
    """Return a NEW `Data` with `specs` (authoring-config elements) appended.

    `parent` places them inside an existing container, by element name or id; omitted, they land at
    the top level. A duplicate control NAME is refused: the designer resolves a field path back to a
    name, so two controls sharing one make every reference to it ambiguous.
    """
    if not specs:
        raise UsageError("nothing to add: pass at least one element spec")

    data = copy.deepcopy(form.get("data") or form.get("Data") or {})
    elements = data.get("elements") or []
    existing_names = {n for n in (_name_of(e) for e in elements) if n}

    parent_id = _resolve_parent(elements, parent)

    # The field-name resolver walks from the form handle variable into Data.dataModel, so the model
    # root, the field-path root and variables[0].id must be the SAME id (builder.build guards this
    # on a full build). On a splice we adopt the LIVE id rather than deriving a new one.
    handle = (data.get("variables") or [{}])[0]
    root_id = data.get("dataModel", {}).get("id") or handle.get("id")
    if not root_id:
        raise UsageError("form has no dataModel root id; refusing to guess one")

    ctx = {"form_id": form.get("id") or form.get("Id"), "dm_root_id": root_id,
           "field_paths": {}, "value_attr_ids": {}, "new_id": _new_id,
           "parent_id": parent_id}

    added: list = []
    for spec in specs:
        name = spec.get("name") or builder._field_slug(spec.get("label") or spec.get("type") or "")
        if name in existing_names:
            raise UsageError(
                f"the form already has a control named {name!r}; two controls with one name make "
                f"every field reference to it ambiguous")
        existing_names.add(name)
        builder._build_element(spec, dict(ctx), added)

    data["elements"] = elements + added

    # A container does not draw a child just because the child points at it: `tabs` lists its tab
    # NAMES and `table` lists its row names, and a spliced child that is missing from that list
    # exists, saves, lints clean, and never appears on screen. Registering it here is the whole
    # difference between a control that is there and one that only looks like it is.
    if parent_id:
        container = next((e for e in elements if e.get("id") == parent_id), None)
        if container is not None:
            key = _LIST_CONFIG.get(container.get("type"))
            if key:
                for c in container.get("configs") or []:
                    if c.get("key") == key:
                        listed = list(c.get("value") or [])
                        for el in added:
                            nm = _name_of(el)
                            if el.get("parentId") == parent_id and nm and nm not in listed:
                                listed.append(nm)
                        c["value"] = listed

    model = data.setdefault("dataModel", {"id": root_id, "name": "form", "attributes": []})
    attrs = model.setdefault("attributes", [])
    fields = next((a for a in attrs if a.get("name") == "fields"), None)
    if fields is None:
        fields = {"id": builder._FIELDS_NS, "dataTypeId": builder._FIELDS_NS, "name": "fields",
                  "displayName": "fields", "isDataModel": True, "isList": False,
                  "isProcesio": False, "isPublic": True, "parentDataTypeId": root_id,
                  "jsonProperty": None, "attributes": []}
        attrs.append(fields)
    fields.setdefault("attributes", []).extend(
        _sub_model(el, fields["id"], ctx) for el in added)

    return data


def _descendants(elements: list, root_id: str) -> list:
    """Every element under `root_id`, however deep."""
    out, frontier = [], {root_id}
    while frontier:
        kids = [e for e in elements if e.get("parentId") in frontier and e not in out]
        if not kids:
            break
        out += kids
        frontier = {k["id"] for k in kids}
    return out


def _references_to(data: dict, doomed_ids: set) -> list:
    """Where the rest of the form still points at one of `doomed_ids`.

    A field VALUE PATH carries the element id, so a RUN_PROCESS input/output map, a visibility
    condition or another control's event all show up as the id appearing outside the element
    itself. Searching by id is exact; a reference made by NAME cannot be found this way, which
    is why the report says so rather than implying the list is exhaustive.
    """
    survivors = {"elements": [e for e in (data.get("elements") or [])
                             if e.get("id") not in doomed_ids],
                 "events": data.get("events"), "variables": data.get("variables")}
    blob = json.dumps(survivors, ensure_ascii=False)
    # Matched as a WHOLE token: a field path joins ids with dots, so an id must not be found
    # merely because it is a substring of a longer one.
    return sorted(i for i in doomed_ids
                  if re.search(r"(?<![0-9A-Za-z-])%s(?![0-9A-Za-z-])" % re.escape(i), blob))


def delete_element(form: dict, element: str, *, force: bool = False) -> tuple[dict, dict]:
    """Return (a NEW `Data` without `element`, report). The mirror of `add_elements`.

    Removes the control from `Data.elements` AND its entry from the form's data model, leaving
    every other element's id and field path untouched - the property that makes a splice safe
    and is equally required here. A control that something still references is REFUSED unless
    `force`, because a dangling field path is saved without any error and the control that
    pointed at it then silently launches nothing.
    """
    data = copy.deepcopy(form.get("data") or form.get("Data") or {})
    elements = data.get("elements") or []
    target = next((e for e in elements
                   if e.get("id") == element or _name_of(e) == element), None)
    if target is None:
        known = ", ".join(sorted(n for n in (_name_of(e) for e in elements) if n)[:20])
        raise UsageError(f"no element with id or name {element!r} on this form; known: {known}")

    kids = _descendants(elements, target["id"])
    if kids and not force:
        raise UsageError(
            f"{_name_of(target) or target['id']!r} contains {len(kids)} control(s) "
            f"({', '.join(str(_name_of(k) or k['id']) for k in kids[:6])}); delete those first, "
            f"or pass --force to remove the whole subtree")

    doomed = [target] + kids
    doomed_ids = {e["id"] for e in doomed}
    refs = _references_to(data, doomed_ids)
    if refs and not force:
        raise UsageError(
            f"{_name_of(target) or target['id']!r} is still referenced by the form "
            f"({len(refs)} id reference(s) outside the control itself: an event, a process "
            f"input/output map or a visibility condition). Re-point or remove those first, or "
            f"pass --force to delete anyway and break them")

    data["elements"] = [e for e in elements if e["id"] not in doomed_ids]

    # Un-register from a container's own list, the reverse of the splice.
    for container in data["elements"]:
        key = _LIST_CONFIG.get(container.get("type"))
        if not key:
            continue
        for c in container.get("configs") or []:
            if c.get("key") == key and isinstance(c.get("value"), list):
                gone = {_name_of(e) for e in doomed}
                c["value"] = [n for n in c["value"] if n not in gone]

    # And from the data model, so the form stops advertising a field it no longer draws.
    removed_attrs = 0
    fields = next((a for a in (data.get("dataModel", {}).get("attributes") or [])
                   if a.get("name") == "fields"), None)
    if fields:
        before = len(fields.get("attributes") or [])
        fields["attributes"] = [a for a in (fields.get("attributes") or [])
                                if a.get("id") not in doomed_ids]
        removed_attrs = before - len(fields["attributes"])

    report = {
        "removed": [{"id": e["id"], "type": e.get("type"), "name": _name_of(e)} for e in doomed],
        "descendants": len(kids),
        "model_attributes_removed": removed_attrs,
        "broken_references": refs if force else [],
        "element_count": len(data["elements"]),
        "note": ("references are found by element id; one made by NAME cannot be detected that "
                 "way, so check a condition that names the control"),
    }
    return data, report
