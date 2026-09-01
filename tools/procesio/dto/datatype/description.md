# Data Model (DataType) sub-tool

Full lifecycle for a PROCESIO **custom data model** — a named set of typed attributes
referenced by process variables, documents, webhooks, forms, and data stores.

## Actions

| Action | What |
|---|---|
| `datatype-create` | Build a model from a config (attribute-by-attribute, **or** `fromJson`). |
| `datatype-edit` | Desired-state edit: rename + add/replace/remove attributes. |
| `datatype-get` | `GET /api/DataTypes/{id}` — model + attributes. |
| `datatype-delete` | Delete a model. |
| `datatype-add-attribute` | Add ONE attribute (`--id --name --data-type [--is-list --hidden --public …]`). |
| `datatype-edit-attribute` | Edit ONE attribute (`--id --attribute` + fields to change). |
| `datatype-delete-attribute` | Remove ONE attribute. |
| `datatype-change-to-public` | Promote a **private** inner model (from `fromJson`) to **public**. |
| `datatype-clone` | Clone an inner model. |

(Raw 1:1 endpoints — `post-datatypes`, `post-datatypes-attribute-by-rootdatatypeid`,
`post-datatypes-private`, `post-datatypes-generate-file`, etc. — are also auto-exposed.)

## Config (`datatype-create` / `datatype-edit`)

```json
{
  "name": "OrderResult", "displayName": "Order Result", "isPublic": true,
  "attributes": [
    {"name": "orderId", "type": "guid"},
    {"name": "total", "type": "double"},
    {"name": "lines", "type": "string", "isList": true},
    {"name": "customer", "model": "CustomerModel"},
    {"name": "items", "model": "OrderLine", "isList": true},
    {"name": "meta", "attributes": [{"name": "source", "type": "string", "hidden": true}]}
  ]
}
```

Each attribute is exactly one of:
- **primitive** — `type` ∈ `boolean integer float double string datetime json object guid`
  (aliases: `bool int long number text str uuid date-time`); `isList:true` for an array.
- **model reference** — `model`: another data model by **name** (resolved live) or id →
  a nested-model field (`isList:true` for a list-of-model, e.g. a document repeating table).
- **inline nested object** — `attributes`: a brand-new sub-model defined inline.

Per-attribute options: `displayName`, `jsonProperty`, `isList`, `hidden`, `isPublic`.

**Data Model from JSON:** instead of `attributes`, pass `"fromJson": {…sample JSON…}`; the
model (incl. nested objects/lists) is inferred via `/api/DataTypes/generate`.

## How it works on the wire (HAR-verified — this is the load-bearing detail)

**Create = EMPTY model first, then EACH attribute via the attribute endpoint.** The UI (and
now this tool) does NOT put attributes in the create POST:
1. `POST /api/DataTypes` body `{name, displayName, content: null, isPublic}` → `{id}`.
2. For EACH attribute: `POST /api/dataTypes/attribute/{modelId}` body
   `{id:null, displayName, name, dataTypeId, isList, jsonProperty, parentDataTypeId}`.

A **model-reference** attribute (`dataTypeId` = another model's id) added this way makes the
server **auto-inline that child's whole attribute tree into the parent AND link the child's
`parentIds`**, and COMPILE it. Attributes placed in the create POST's `Content` instead show
up in `GET /api/DataTypes/{id}` but are **NEVER compiled into the runtime model** — a document
binding the model then renders every cell **"Unknown"** and Generate Document throws *"Unable
to find attribute &lt;id&gt;"*. (This cost ~10 debugging rounds; see the
`procesio-datatype-create` memory note.) Inline nested children are created as their own empty
model first, then referenced.

**Edit:** `PUT /api/DataTypes` renames only (ignores attributes/parentIds); attributes are
reconciled via `POST` (add — compiles), `PUT /api/dataTypes/attribute/{id}` (full object,
change), `DELETE /api/dataTypes/attribute/{id}/{attrId}` (remove).

## Public vs private models — REUSABILITY (important)

- **Attribute-by-attribute** (`datatype-create` with `attributes`): a `model:` reference points
  at an existing model, which **stays reusable** in other models.
- **`fromJson`**: the inferred nested inner models are created **PRIVATE — they cannot be
  reused in other data models.** Promote one with `datatype-change-to-public`
  (`--root-id <root model> --id <inner model>`) to make it reusable; `datatype-clone` clones an
  inner model. (`POST /api/dataTypes/changeToPublic|clone` body `{rootDataTypeId, dataTypeId}`.)

## Gotchas
- `IsProcesio`/`IsPrimaryType` true is rejected on update; always false for custom models.
- Primitive type ids are stable platform constants, bundled in `dto/data/platform_types.json`.
- `searchName` filters need ≥ 3 chars to take effect (server-side).
- `--data-type` on attribute actions accepts a primitive name, an existing model name, or a guid.
