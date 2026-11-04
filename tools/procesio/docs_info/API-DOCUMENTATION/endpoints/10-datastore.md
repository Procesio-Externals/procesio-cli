# Data Store endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreRowsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreCsvController.cs`

**Data Store** is PROCESIO's user-defined dynamic data-table feature: tenants define a table (a "data store") with a typed column schema, then read/write rows in it. A data store is backed by an internal **data model** (a data type) describing its columns. Rows are exchanged as JSON dictionaries keyed by **column display name** (never by the internal column alias). Large reads/writes can be offloaded to asynchronous **CSV jobs** (import/export) that produce downloadable files.

All routes are served under the Web-Api gateway base URL. Versioning is via the optional `x-version` header (default `1.19`). Unless an endpoint is marked **Auth: Anonymous**, send a Bearer JWT (see [../01-authentication.md](../01-authentication.md)). All three controllers are PUBLIC (none carry `[SecureInternalController]`; no `internal/` route prefix).

Error responses for the Data Store controllers use `ProducesResponseType(List<ApiErrorResponse>)` (see Shared DTOs → `ApiErrorResponse`).

---

## Endpoints

### DataStoreController — `api/DataStore` (table / schema CRUD)

Controller route: `[Route("api/[controller]")]` → **`api/DataStore`**. Controller-level permission entity: `DataStoreSchema`.

---

#### `POST api/DataStore`

- **Operation:** `Create` — Create a new data store (table + column schema).
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Create` (Swagger: "Permission required: DataStoreSchema.Write")
- **Request body** (`application/json`): `DataStoreMetadataDto`
  - `Id` — `string (uuid)`, optional — ignored on create (server-generated).
  - `Name` — `string`, required — store name.
  - `Description` — `string`, optional.
  - `Columns` — array of `DataStoreColumnDefinitionDto`, optional — column schema.
  - `DataTypeId` — `string (uuid)`, optional — **forced to null by the controller on this endpoint** (the backing data type id is generated server-side). Do not send it.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
  - `500 Internal Server Error` → array of `ApiErrorResponse`

---

#### `PUT api/DataStore`

- **Operation:** `Update` — Update an existing data store (rename, description, schema-level changes).
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Update` (Swagger: "Permission required: DataStoreSchema.Update")
- **Request body** (`application/json`): `DataStoreMetadataDto`
  - Same fields as Create. `Id` identifies the store to update. `DataTypeId` is **forced to null by the controller** (retrieved server-side).
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `400` / `403 Forbidden` / `500` → array of `ApiErrorResponse`

---

#### `PATCH api/DataStore/{dataStoreId}/column`

- **Operation:** `ModifyColumn` — Modify a single column: rename, change its data type, or update its constraints.
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Update` (Swagger: "Permission required: DataStoreSchema.Update")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required — target data store.
- **Request body** (`application/json`): `DataStoreModifyColumnDto`
  - `OriginalColumn` — `object (DataStoreColumnDefinitionDto)`, required — the column as it currently exists (identifies which column to change).
  - `UpdatedColumn` — `object (DataStoreColumnDefinitionDto)`, required — the desired new column definition.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto` (updated store metadata)
  - `204 No Content` (when the operation produced no metadata payload, e.g. a no-op change)
  - `400` / `403 Forbidden` / `500` → array of `ApiErrorResponse`
- **Notes:** The edited column is matched by `OriginalColumn.ColumnId`, with the name as fallback when no id is sent; `ColumnId` is preserved across the edit, so a rename keeps the same column identity. System columns can be neither modified nor introduced, and removing `IsPrimaryKey` from the store's only primary-key column is rejected.

---

#### `DELETE api/DataStore/{id}`

- **Operation:** `Delete` — Delete a data store by id (drops the table and its backing data type).
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Delete` (Swagger: "Permission required: DataStoreSchema.Delete")
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` (empty body)
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore/{id}`

- **Operation:** `GetById` — Get a single data store's metadata (including its column schema).
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Read` (Swagger: "Permission required: DataStoreSchema.Read")
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore`

- **Operation:** `GetAll` — List data stores with pagination and optional name search.
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Read` (Swagger: "Permission required: DataStoreSchema.Read")
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
  - `searchName` — `string`, optional, default `null` — case-handled name filter. **A search term shorter than 3 characters (after trim) is ignored** (treated as no filter).
- **Responses:**
  - `200 OK` → `PageRequestResult<DataStoreMetadataResponseDto>`
  - `500` → array of `ApiErrorResponse`

---

#### `POST api/DataStore/from-data-model`

- **Operation:** `CreateFromDataModel` — Create a data store from an existing data model. First-level primitive attributes become typed columns; complex attributes become JSON columns.
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Create` (Swagger: "Permission required: DataStoreSchema.Write")
- **Request body** (`application/json`): `DataStoreFromDataModelDto`
  - `DataModelId` — `string (uuid)`, required — source data model.
  - `Name` — `string`, required — new store name.
  - `Description` — `string`, optional.
  - `PrimaryKeyAttributeIds` — array of `string (uuid)`, optional — source attribute ids to mark as primary key columns (composite PKs supported, so multiple ids allowed).
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `POST api/DataStore/from-json`

- **Operation:** `CreateFromJson` — Create a data store by inferring its column schema from a JSON payload or a JSON-returning URL. Top-level properties become typed columns.
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Create` (Swagger: "Permission required: DataStoreSchema.Write")
- **Request body** (`application/json`): `DataStoreFromJsonDto`
  - `Name` — `string`, required.
  - `Description` — `string`, optional.
  - `Content` — `string`, required — either a raw JSON string or a public HTTP/S URL that returns JSON. The resolved JSON object's top-level properties become the columns.
  - `PrimaryKeyAttributeNames` — array of `string`, optional — names of top-level JSON properties to mark as primary key columns. Matching is case-insensitive; composite PKs supported. At least one PK name must be supplied per the operation summary.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `400` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore/{dataStoreId}/data-model`

- **Operation:** `GetDataModel` — Get the internal data model (data type) that backs a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStoreSchema:Read` (Swagger: "Permission required: DataStoreSchema.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `DataModelDto` (see Shared DTOs)
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore/restricted`

- **Operation:** `GetRestrictedDataStores` — List the id and name of every data store in the resolved workspace scope, paginated. Intended for pickers (e.g. form builders) that need store names without full metadata.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None` (Swagger: "Permission required: None"). Works both signed in and logged out.
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
  - `formTemplateId` — `string (uuid)`, optional — for anonymous callers arriving through a public form: the form template whose owner scopes the request.
  - `formWorkspaceId` — `string (uuid)`, optional — for anonymous callers: the form's workspace, sent as a query param since a logged-out caller has no workspace header.
- **Responses:**
  - `200 OK` → `PageRequestResult<RestrictedDataStoreMetadataDto>` (slim `Id` + `Name` items — not the full metadata DTO)
  - `500` → array of `ApiErrorResponse`
- **Notes:** An anonymous caller must be scoped to a workspace before the query runs: `formWorkspaceId` (or the workspace header) provides the scope; when that workspace is personal, the scope comes from the owner of the **public** form template passed in `formTemplateId`. A private form template is refused, and a caller with no resolvable scope receives an **empty page**, not an error. The endpoint deliberately adds a randomized response delay so anonymous callers cannot distinguish outcomes by timing.

---

### DataStoreRowsController — `api/DataStore` (row CRUD + query)

Controller route: `[Route("api/DataStore")]`. Controller-level permission entity: `DataStoreRows`. All actions are tagged `DataStore` in Swagger.

> **Row model (read this first).** Every row is a JSON object (dictionary). Keys are **column display names**, not internal aliases — the Web-Api layer maps display names to aliases before calling the Data Store service. Values are arbitrary JSON (`object` / nullable). Primary-key columns identify rows for update/delete.

---

#### `POST api/DataStore/{dataStoreId}/rows/filter`

- **Operation:** `GetRows` — Read a page of rows, optionally narrowed by a recursive filter tree with AND/OR grouping and sorted by one or more columns.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Read` (Swagger: "Permission required: DataStoreRows.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Query params:** *(pagination stays on the query string, not in the body)*
  - `pageNumber` — `number`, required — 1-based page index; a page past the end returns the last page (paging rules in `02-conventions.md` §6).
  - `pageItemCount` — `number`, required — page size; `0` or less returns every matching row in one page.
- **Request body** (`application/json`): `DataStoreGetRowsRequestDto` — **optional**. Send no body (or an empty one) to read every row; the action is annotated `EmptyBodyBehavior.Allow`.
  - `Filter` — `DataStoreFilterGroupDto`, nullable — the recursive WHERE tree.
  - `Sort` — array of `DataStoreSortDto`, default `[]` — multi-column ORDER BY, applied in array order.
- **Responses:**
  - `200 OK` → `DataStoreViewerResponseDto` (column metadata + a `PageRequestResult` of row dictionaries)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse` — a condition whose `Operator` is `0` (`None`), at any nesting depth, is **refused** with `400 "Unsupported filter operator: None"` rather than dropped, so a filter that fails to build returns an error and not the whole table. An operator outside `0`–`20` answers `400 "Operator 'N' is not supported for column 'Y'."`.
- **Notes:** Columns are given as **display names**; Web-Api resolves them to column aliases before calling the Data Store service. This is the same expressive filter format used by the write paths (`PUT`/`DELETE`), the form-context read path, and the Process-Execution Data Store connector. In the returned rows, the `CreatedById`/`UpdatedById` values are replaced by the user's display name ("FirstName LastName") when Web-Api can resolve the stored id, falling back to the raw Guid when it cannot — but the columns stay Guid-typed in the metadata, and **filters on them must still send the Guid**, never the name.

**Example** — `Status = "Active" AND (Country = "RO" OR Country = "PL")`, newest first:

```http
POST api/DataStore/3f8a.../rows/filter?pageNumber=1&pageItemCount=50
```

```json
{
  "Filter": {
    "Id": 1,
    "Logic": 1,
    "Items": [
      {
        "Id": 2, "Type": 1, "Logic": 1,
        "Condition": { "Id": 3, "Column": "Status", "Operator": 1, "Value": "Active" }
      },
      {
        "Id": 4, "Type": 2, "Logic": 1,
        "Group": {
          "Id": 5, "Logic": 2,
          "Items": [
            { "Id": 6, "Type": 1, "Logic": 1, "Condition": { "Id": 7, "Column": "Country", "Operator": 1, "Value": "RO" } },
            { "Id": 8, "Type": 1, "Logic": 2, "Condition": { "Id": 9, "Column": "Country", "Operator": 1, "Value": "PL" } }
          ]
        }
      }
    ]
  },
  "Sort": [{ "Column": "CreatedOn", "Direction": 2 }]
}
```

---

#### `POST api/DataStore/{dataStoreId}/rows`

- **Operation:** `AddRows` — Add one or more rows to a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Create` (Swagger: "Permission required: DataStoreRows.Write")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreInsertRowsRequestDto`
  - `Rows` — array of `object` (each a dictionary of `displayName → value`), required — the rows to insert. **Every row in one batch must declare the same set of columns**: send a column explicitly with `null` rather than leaving it out of some rows. Column names are matched **case-sensitively** (`code` for a column `Code` is refused as a column that does not exist). The system columns (`CreatedOn`, `UpdatedOn`, `CreatedById`, `UpdatedById`) are set by the server and dropped from every row; a row left empty by that is skipped, and a batch with no row left answers `400 "At least one row is required."`.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto` (`{ "AffectedRows": <number> }`)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse` — a batch whose rows declare differing column sets answers `400 "All rows in a batch must have the same set of column aliases."`

---

#### `PUT api/DataStore/{dataStoreId}/rows`

- **Operation:** `UpdateRows` — Set the given values on every row the filter matches.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Update` (Swagger: "Permission required: DataStoreRows.Update")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreUpdateRowsRequestDto`
  - `Values` — `object` (dictionary `displayName → value`), required — the columns to set and their new values.
  - `Filter` — `DataStoreFilterGroupDto`, nullable in the DTO but **mandatory in practice** — selects the rows to update. A non-empty filter is required; an empty or missing filter is rejected rather than updating every row.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto`
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `DELETE api/DataStore/{dataStoreId}/rows`

- **Operation:** `DeleteRows` — Remove every row the filter matches.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Delete` (Swagger: "Permission required: DataStoreRows.Delete")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreDeleteRowsRequestDto`
  - `Filter` — `DataStoreFilterGroupDto`, nullable in the DTO but **mandatory in practice** — selects the rows to delete. A non-empty filter is required.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto`
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

### DataStoreCsvController — `api/DataStore` (CSV import/export jobs)

Controller route: `[Route("api/DataStore")]`. Controller-level permission entity: `DataStoreRows` (CSV moves row content, so it is governed by the rows entity, not the schema entity). All actions tagged `DataStore` in Swagger. CSV jobs are **asynchronous**: start a job, then poll/download by `jobId`.

---

#### `POST api/DataStore/{dataStoreId}/export-start`

- **Operation:** `StartExport` — Start an asynchronous CSV export job for a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Read` (Swagger: "Permission required: DataStoreRows.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Special headers:** `connectionId` `[FromHeader]` — `string`, optional — SignalR/connection id used to push job progress notifications back to the caller.
- **Responses:**
  - `200 OK` → `DataStoreCsvJobResponseDto` (the created job descriptor; use its `JobId` to download)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`
- **Notes:** Read-only system columns are **never** included in the export (the `includeSystemColumns` flag is hard-coded to `false`). The export runs in the background; the response only confirms the job was queued.

---

#### `GET api/DataStore/{dataStoreId}/export-download/{jobId}`

- **Operation:** `DownloadExport` — Download the CSV file produced by a completed export job.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Read` (Swagger: "Permission required: DataStoreRows.Read")
- **Path params:**
  - `{dataStoreId}` — `string (uuid)`, required.
  - `{jobId}` — `string (uuid)`, required — the export job id returned by `export-start`.
- **Responses:**
  - `200 OK` → CSV file download (`text/csv; charset=utf-8`, content type `text/csv`, returned as a `FileResult` with a server-set filename)
  - `400` / `404 Not Found` / `409 Conflict` (job not yet complete / wrong state) / `500` → array of `ApiErrorResponse`

---

#### `POST api/DataStore/{dataStoreId}/import-start`

- **Operation:** `Import` — Import CSV data into a data store (starts an asynchronous import job).
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Create` (Swagger: "Permission required: DataStoreRows.Write")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Special headers:** `connectionId` `[FromHeader]` — `string`, optional — connection id for progress notifications.
- **Request body** (`multipart/form-data`):
  - `file` — file (`IFormFile`), required — the CSV file to import. Form field name: `file`.
- **Responses:**
  - `200 OK` → `DataStoreCsvJobResponseDto` (the created import job descriptor)
  - `400` / `404 Not Found` / `413 Payload Too Large` (file exceeds the configured size limit) / `500` → array of `ApiErrorResponse`
- **Notes:** Import runs in the background. Rows that fail validation are collected and can be downloaded via `import-failures`.

---

#### `GET api/DataStore/{dataStoreId}/import-failures/{jobId}`

- **Operation:** `DownloadImportFailures` — Download a CSV of the rows that failed during a completed import job.
- **Auth:** Bearer JWT — **Permission:** `DataStoreRows:Read` (Swagger: "Permission required: DataStoreRows.Read")
- **Path params:**
  - `{dataStoreId}` — `string (uuid)`, required.
  - `{jobId}` — `string (uuid)`, required — the import job id returned by `import-start`.
- **Responses:**
  - `200 OK` → CSV file download (`text/csv; charset=utf-8`) of failed rows
  - `400` / `404 Not Found` / `409 Conflict` (job not yet complete) / `500` → array of `ApiErrorResponse`

---

## Shared DTOs

### `DataStoreColumnDefinitionDto`

A single column in a data store's schema.

- `ColumnId` — `string (uuid)`, nullable — the column's **stable identity**. Optional on requests: the server assigns a fresh Guid to any column that arrives without one. Always echoed in responses for user columns; `null` for the appended system columns. Schema update reconciliation and `PATCH .../column` match the edited column by `ColumnId` (with the name as fallback), so clients that echo the response `ColumnId` back get reliable rename/retype detection instead of a drop-and-add.
- `Name` — `string` — column display name.
- `DataTypeId` — `string (uuid)` — the data type backing this column (see Data Types).
- `IsList` — `boolean` — whether the column holds a list/array of the type.
- `IsPrimaryKey` — `boolean` — part of the (possibly composite) primary key.
- `IsRequired` — `boolean` — non-null constraint.
- `IsSystemColumn` — `boolean` — read-only system-managed column (e.g. internal id/audit columns).

### `DataStoreMetadataDto` (request)

- `Id` — `string (uuid)`, optional — store id (ignored on POST create).
- `Name` — `string`, required.
- `Description` — `string`, optional.
- `Columns` — array of `DataStoreColumnDefinitionDto`, optional.
- `DataTypeId` — `string (uuid)`, optional — forced to null by Create/Update controllers; not for client use on those endpoints.

### `DataStoreMetadataResponseDto` (response)

Extends `OwnershipAuditDto` (audit fields below are included).

- `Id` — `string (uuid)`.
- `Name` — `string`.
- `Description` — `string`.
- `Columns` — array of `DataStoreColumnDefinitionDto`.
- `DataTypeId` — `string (uuid)`, nullable.
- *(plus all `OwnershipAuditDto` fields.)*

### `DataStoreModifyColumnDto`

- `OriginalColumn` — `object (DataStoreColumnDefinitionDto)` — current column.
- `UpdatedColumn` — `object (DataStoreColumnDefinitionDto)` — desired column.

### `RestrictedDataStoreMetadataDto` (response)

Slim item returned by `GET api/DataStore/restricted` — deliberately name-only, since the endpoint also serves anonymous callers.

- `Id` — `string (uuid)`.
- `Name` — `string`.

### `DataStoreFromDataModelDto`

- `DataModelId` — `string (uuid)`, required.
- `Name` — `string`, required.
- `Description` — `string`, optional.
- `PrimaryKeyAttributeIds` — array of `string (uuid)`, optional.

### `DataStoreFromJsonDto`

- `Name` — `string`, required.
- `Description` — `string`, optional.
- `Content` — `string`, required — raw JSON or a JSON-returning HTTP/S URL.
- `PrimaryKeyAttributeNames` — array of `string`, optional — case-insensitive top-level property names to use as PKs.

### `DataStoreViewerResponseDto` (response)

Combined viewer payload returned by `POST .../rows/filter`.

- `Columns` — array of `DataStoreColumnDefinitionDto` — schema for rendering.
- `Rows` — `object (PageRequestResult<row>)` — paginated rows, where each row is an `object` (dictionary `displayName → value`, values are arbitrary JSON / nullable).

In each row, the system columns `CreatedById`/`UpdatedById` carry the user's display name ("FirstName LastName") when the stored id resolves to a known user, and the raw Guid when it does not. The column metadata still types them as Guid, and filters on them must send the Guid. The same substitution applies to the forms read path, which builds its rows the same way.

### `DataStoreInsertRowsRequestDto` (request)

- `Rows` — array of `object` (each a dictionary `displayName → value`).

### `DataStoreUpdateRowsRequestDto` (request)

- `Values` — `object` (dictionary `displayName → value`) — columns to set.
- `Filter` — `DataStoreFilterGroupDto`, nullable — selects the rows to update. Required in practice.

### `DataStoreDeleteRowsRequestDto` (request)

- `Filter` — `DataStoreFilterGroupDto`, nullable — selects the rows to delete. Required in practice.

### `DataStoreRowsAffectedDto` (response)

- `AffectedRows` — `number` — count of rows inserted/updated/deleted.

### `DataStoreGetRowsRequestDto` (request body for `POST .../rows/filter`)

Optional body. Shared by the viewer read path and the form-context read path. Pagination travels on the query string, not here.

- `Filter` — `DataStoreFilterGroupDto`, nullable — recursive WHERE tree.
- `Sort` — array of `DataStoreSortDto`, default `[]` — multi-column ORDER BY, applied in array order.

### The filter tree

Three DTOs form a recursive tree. Column names are **display names** on the wire; Web-Api resolves them to column aliases before calling the Data Store service. The ordinals below cross the wire to the Data Store service, so they must be sent as numbers.

#### `DataStoreFilterGroupDto`

- `Id` — `number` — client-assigned node id.
- `Logic` — `number (enum: LogicOperators)`, default `1` (`AND`) — how this group connects to its previous sibling.
- `Items` — array of `DataStoreFilterNodeDto`, default `[]`.

#### `DataStoreFilterNodeDto`

A node is **either** a condition **or** a nested group, selected by `Type`.

- `Id` — `number`.
- `Type` — `number (enum: DataStoreFilterNodeType)`, default `1` — `Condition=1`, `Group=2`.
- `Logic` — `number (enum: LogicOperators)`, default `1` — connects this node to the previous sibling.
- `Condition` — `DataStoreFilterConditionDto`, nullable — set when `Type=1`.
- `Group` — `DataStoreFilterGroupDto`, nullable — set when `Type=2`.

#### `DataStoreFilterConditionDto`

- `Id` — `number`.
- `Column` — `string` — column display name.
- `Operator` — `number (enum: QueryOperators)`, default `1` (`Equals`).
- `Value` — `object`, nullable — omit for unary operators (`IsNull`, `IsNotNull`, `IsTrue`, `IsFalse`); pass an array for `In`/`NotIn`; pass the lower bound for `Between`/`NotBetween`.
- `AuxValue` — `object`, nullable — the upper bound for `Between` / `NotBetween`.

#### `DataStoreSortDto`

- `Column` — `string` — column display name.
- `Direction` — `number (enum: SortDirection)`, default `1` — `Asc=1`, `Desc=2`.

### `DataStoreCsvJobResponseDto` (response)

- `JobId` — `string (uuid)` — use to download results / failures.
- `JobType` — `number (enum: DataStoreCsvJobType — Export=0, Import=10)`.
- `Status` — `number (enum: DataStoreCsvJobStatus — Queued=0, Running=10, Completed=20, CompletedWithFailures=30, Failed=40, Cancelled=50)`.
- `CreatedOn` — `string (date-time, ISO-8601)`.

### `DataAttributeDto`

One attribute (field) of a data model. Recursive (`Attributes` holds nested attributes).

- `Id` — `string (uuid)`, nullable.
- `DataTypeId` — `string (uuid)`.
- `ParentDataTypeId` — `string (uuid)`.
- `Name` — `string`.
- `DisplayName` — `string`.
- `DataTypeName` — `string`.
- `IsDataModel` — `boolean`.
- `IsPrimaryType` — `boolean`, default `false`.
- `IsProcesio` — `boolean`, default `false`.
- `IsPublic` — `boolean`, default `false`.
- `CsharpCorrespondent` — `number (enum: PrimaryDataType)` — see enum below.
- `Type` — `number (enum: DataModelTypeParam — Normal=1, Webhook=2)`, default `Normal`.
- `IsList` — `boolean`.
- `jsonProperty` — `string` (wire name; C# `JsonPropertyName`) — JSON property name mapping.
- `updatedOn` — `string (date-time, ISO-8601)` (wire name) — last update time.
- `Attributes` — array of `DataAttributeDto` — nested attributes.

### `DataModelDto` (response, also used as `CreateDataTypeDto.Content`)

Extends `BaseDataTypeDto`.

- `Attributes` — array of `DataAttributeDto`.
- `ParentIds` — array of `string (uuid)`.
- *(plus all `BaseDataTypeDto` fields below.)*

### `BaseDataTypeDto`

Extends `OwnershipAuditDto`.

- `Id` — `string (uuid)`.
- `Name` — `string`.
- `DisplayName` — `string`.
- `IsDataModel` — `boolean`.
- `IsPrimaryType` — `boolean`, default `false`.
- `IsProcesio` — `boolean`, default `false`.
- `IsPublic` — `boolean`, default `false`.
- `CsharpCorrespondent` — `number (enum: PrimaryDataType)`.
- `Type` — `number (enum: DataModelTypeParam — Normal=1, Webhook=2)`, default `Normal`.
- *(plus all `OwnershipAuditDto` fields.)*

### `OwnershipAuditDto`

Audit base for FE-facing list/detail entities. All wire names are camelCase via `[JsonProperty]`.

- `firstName` — `string` — (legacy; being replaced by `createdBy`/`updatedBy`).
- `lastName` — `string` — (legacy).
- `workspaceId` — `string (uuid)`, nullable.
- `createdBy` — `string` — "FirstName LastName" of creator.
- `updatedBy` — `string` — "FirstName LastName" of last updater.
- `createdById` — `string (uuid)`, nullable.
- `updatedById` — `string (uuid)`, nullable.
- `createdOn` — `string (date-time, ISO-8601)`, nullable.
- `updatedOn` — `string (date-time, ISO-8601)`, nullable.

### `PageRequestResult<T>` (paged response wrapper)

All wire names via `[JsonProperty]`.

- `totalItemCount` — `number` — total matching items across all pages.
- `pageNumber` — `number` — the page that came back (1-based); a page past the end is moved back to the last page.
- `pageItemCount` — `number` — the requested page size, **not** the number of items on the page (rules in `02-conventions.md` §6); count `pageItems`.
- `pageItems` — array of `T` — the page's items.

### `Pagination` (query-param trio, not a body)

Used by all paginated endpoints via `pageNumber` + `pageItemCount` query params.

- `PageNumber` — `number` — 1-based; values `<= 1` are clamped to `1`.
- `PageItemCount` — `number` — page size; values `<= 0` are clamped to `0`, which returns every item in one page.

### `ApiErrorResponse` (error item — Data Store controllers)

Data Store error responses are a JSON **array** of these objects — the controller serializes the manager's error list directly; no middleware rewraps it.

- `StatusCode` — `number` — the internal PROCESIO error code (not the HTTP status, which is on the response itself). The Data Store row endpoints answer with `502` for an invalid request (every `400` in this file, for example `[{"statusCode":502,"value":"Unsupported filter operator: None","target":"filters"}]`) and `1006` for a duplicate key (the `409` on insert). `502` here is not an HTTP 502.
- `Value` — `object` — error detail/message payload.
- `Target` — `object` — what the error refers to (field/entity); may be `null`.

### Enums

**`QueryOperators`** (numeric, used in `DataStoreFilterConditionDto.Operator`). Ordinals mirror the Data Store service enum and cross the wire:
`None=0`, `Equals=1`, `NotEquals=2`, `GreaterThan=3`, `GreaterThanOrEqual=4`, `LessThan=5`, `LessThanOrEqual=6`, `Between=7`, `NotBetween=8`, `Like=9`, `NotLike=10`, `In=11`, `NotIn=12`, `IsNull=13`, `IsNotNull=14`, `IsTrue=15`, `IsFalse=16`, `Contains=17`, `NotContains=18`, `StartsWith=19`, `EndsWith=20`.

Operator shape:

- **Unary** (no `Value`): `IsNull`, `IsNotNull`, `IsTrue`, `IsFalse`.
- **List** (`Value` is an array): `In`, `NotIn`.
- **Range** (`Value` = lower bound, `AuxValue` = upper bound): `Between`, `NotBetween`.

On text columns (the `utf8mb4_0900_ai_ci` collation of every Data Store table), matching, sorting **and primary keys** ignore **letter case and accents** but not trailing spaces: `Equals "alpha"` matches a stored `"Alpha"`, `"cafe"` matches `"café"` and `"s"` matches `"ș"`, while `"abc"` does not match `"abc "`. Ligatures and `ß` compare with their spelled-out forms (`ß` equals `ss`, `Æ` equals `AE`), and every emoji is a distinct character. An ascending sort interleaves cases rather than grouping them (`aardvark, Alpha, beta, Charlie`) and places emoji first. Inserting `"Alpha"` into a store that already holds the key `"alpha"` answers `409`.

`Json`, `Object`, Data Model and list columns are compared differently, and letter case counts there (see below).

Not every operator is legal on every column — the server validates the operator against the column's `PrimaryDataType`:

| Column type | Allowed operators |
|---|---|
| `String` | Equals, NotEquals, Contains, NotContains, StartsWith, EndsWith, Like, NotLike, In, NotIn, IsNull, IsNotNull |
| `Integer`, `Float`, `Double`, `Date`, `DateTime` | Equals, NotEquals, GreaterThan, GreaterThanOrEqual, LessThan, LessThanOrEqual, Between, NotBetween, In, NotIn, IsNull, IsNotNull |
| `Boolean` | Equals, NotEquals, In, NotIn, IsNull, IsNotNull, IsTrue, IsFalse |
| `Guid` | Equals, NotEquals, In, NotIn, IsNull, IsNotNull |
| `Object` | same as `String` (stringifiable) — but see the note below the table |
| `Json` | Equals, NotEquals, IsNull, IsNotNull |
| Data Model | Equals, NotEquals, IsNull, IsNotNull (filtered as `Json`) |
| any list column (`IsList: true`) | Equals, NotEquals, IsNull, IsNotNull (filtered as `Json`, whatever the element type) |

Any other operator answers `400 "Operator 'X' is not supported for column 'Y'."`.

On an `Object` column the text operators (`Contains`, `StartsWith`, `EndsWith`, `Like` and their negations) run on the **stored JSON text**, case-sensitively and with the stored spacing and key order described below: `Contains "a": 2` matches `{"a":2}`, `Contains "a":2` does not.

**The negative operators (`NotEquals`, `NotContains`, `NotLike`, `NotIn`) never return rows where the column is empty**, as SQL `<>` does: on a column holding `x`, `q`, `""` and null, `NotEquals "x"` returns `q` and `""` but not the null row. Add an `IsNull` condition with `OR` to include empty rows.

#### How stored values come back, per column type

These behaviours are by design and are the ones integrators get wrong:

- **`Float` is stored as a full 64-bit double — identical to `Double`.** There are no 32-bit semantics: writing `1.2345678901234567` to a `Float` column reads it back unchanged, where a real 32-bit float would return `1.2345678806304932`. The two types appear separately in `PrimaryDataType` below, which makes `Float` look like the narrower choice; it is not. Prefer `Double` for clarity.
- **`Json`, `Object`, Data Model and list columns are MySQL `JSON` columns.** The structure round-trips, but the text does not:
  - whitespace is **normalized** to one space after `:` and `,`
  - keys are **reordered**: shorter keys first, then by byte value, so upper case comes before lower case. `{"ccc":3,"a":1,"bb":2}` reads back as `{"a": 1, "bb": 2, "ccc": 3}`, and `{"aa":1,"b":2}` as `{"b": 2, "aa": 1}`. It is not alphabetical.
  - **duplicate keys are deduplicated**, and the last one wins. Sending `{"b": 1,   "a":    2, "b": 3}` reads back as `{"a": 2, "b": 3}`.
  - **numbers are rewritten**: `1.10` reads back as `1.1`, and `1e2` as `100.0`.

  Never compare the raw text, and never rely on key order.
- **Writing a `Json`, `Object` or Data Model value:**
  - an empty string `""` is stored as **null**
  - a string that holds JSON is parsed and stored as that JSON: `"{\"b\":1}"` is stored as `{"b": 1}`
  - a string that is not JSON, including a plain JSON string such as `"hello"`, is refused with `400 "Value for column 'X' must be a valid JSON value."`
  - a Data Model column accepts **any** valid JSON (`5`, `true`, `[3,1,2]`, or keys the model does not define). It is not checked against the model's attributes.
- **`Json`, `Object`, Data Model and list values are returned as JSON *strings*, not parsed structures.** A `Json` column reads back as the string `{"a": 2}`, and a list column as the string `["x", "y"]`. **The client must `JSON.parse` them.** Integers keep every digit in that string (`12345678901234567890` comes back exact), but `JSON.parse` in JavaScript rounds anything above 2^53.
- **Filtering a `Json`, Data Model or list column compares the whole value as JSON.** Only `Equals`, `NotEquals`, `IsNull` and `IsNotNull` are accepted (see the table above). `Equals` takes the complete value, sent as JSON text:
  - spacing does not matter, and numbers compare as numbers: `[ "x" , "y" ]` matches `["x","y"]`, `[1.0,2.0]` matches `[1,2]`, and `{"a":2.0}` matches `{"a":2}`
  - key order does not matter: `{"b":3,"a":2}` matches `{"a":2,"b":3}`
  - **list element order matters**: `["y","x"]` does not match `["x","y"]`
  - **letter case matters**, in keys and in values: `["X","Y"]` does not match `["x","y"]`, and `{"A":2,"b":3}` does not match `{"a":2,"b":3}`. This is unlike `String` columns.
  - the string `"2"` is not the number `2`
  - a single member never matches: `x` does not find `["x","y"]`. **There is no "list contains" filter**; keep a value you need to search on in its own scalar column.
  - `[]` matches an empty list, and a JSON `null` means `IsNull`

**`LogicOperators`** (numeric, used in `Logic` on groups and nodes): `NONE=0`, `AND=1`, `OR=2`.

**`DataStoreFilterNodeType`** (numeric, used in `DataStoreFilterNodeDto.Type`): `Condition=1`, `Group=2`.

**`SortDirection`** (numeric, used in `DataStoreSortDto.Direction`): `None=0`, `Asc=1`, `Desc=2`.

**`DataStoreCsvJobType`**: `Export=0`, `Import=10`.

**`DataStoreCsvJobStatus`**: `Queued=0`, `Running=10`, `Completed=20`, `CompletedWithFailures=30`, `Failed=40`, `Cancelled=50`.

**`DataModelTypeParam`** (legacy GET selector): `Normal=1` (DataModelType.Expanded), `Webhook=2` (DataModelType.External). Defaults to `Normal`.

**`PrimaryDataType`** (`CsharpCorrespondent`): `None=0`, `Boolean=10`, `Integer=20`, `Float=30`, `Double=40`, `String=50`, `Date=60`, `Relationship=70`, `Time=80`, `DateTime=90`, `Guid=100`, `Uri=110`, `Json=120`, `Credentials=130`, `Object=140`.
