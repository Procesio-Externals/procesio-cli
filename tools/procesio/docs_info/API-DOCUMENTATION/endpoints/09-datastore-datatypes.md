# Data Store & Data Types endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreRowsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/DataStore/DataStoreCsvController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/DataTypesController.cs`

This domain covers two related capabilities.

**Data Store** is PROCESIO's user-defined dynamic data-table feature: tenants define a table (a "data store") with a typed column schema, then read/write rows in it. A data store is backed by an internal **data model** (a data type) describing its columns. Rows are exchanged as JSON dictionaries keyed by **column display name** (never by the internal column alias). Large reads/writes can be offloaded to asynchronous **CSV jobs** (import/export) that produce downloadable files.

**Data Types** (a.k.a. data models) are the platform's type-definition registry: primitive types, PROCESIO built-in types, and user-defined composite "data models" (objects with nested attributes). These types are what columns, process variables, and action inputs/outputs are typed against. This controller manages their CRUD, cloning, attribute editing, generation from sample content, and read-only listing of primary/PROCESIO types.

All routes are served under the Web-Api gateway base URL. Versioning is via the optional `x-version` header (default `1.19`). Unless an endpoint is marked **Auth: Anonymous**, send a Bearer JWT (see [../01-authentication.md](../01-authentication.md)). All four controllers are PUBLIC (none carry `[SecureInternalController]`; no `internal/` route prefix).

Error responses for the Data Store controllers use `ProducesResponseType(List<ApiErrorResponse>)` (see Shared DTOs → `ApiErrorResponse`). The Data Types controller returns its errors as `400 Bad Request` with a list of composed error objects.

---

## Endpoints

> ⚠ **STALE on row reads (corrected 2026-08).** After the "unified row filters" release (Web-Api #1453 / Data-Store #16), reads go through **`POST api/DataStore/{dataStoreId}/rows/filter`** with a JSON body — NOT the `GET .../rows` query-string form documented below. Pagination is on the QUERY STRING (`?pageNumber=&pageItemCount=`); the body is a recursive filter tree `{filter:<group>, sort:[{column,direction}]}` (empty = read all). The operator set is the FULL `QueryOperators` enum (0..20), not the 1–8 subset shown here. Update = `{values,filter}`, delete = `{filter}` — a non-empty filter is MANDATORY (no key-array form). See `tools/procesio/PROCESIO-API-NOTES.md` ## DataStore (authoritative); the tool's `datastore-*` actions implement the corrected contract.

### DataStoreController — `api/DataStore` (table / schema CRUD)

Controller route: `[Route("api/[controller]")]` → **`api/DataStore`**. Controller-level permission entity: `DataStore`.

---

#### `POST api/DataStore`

- **Operation:** `Create` — Create a new data store (table + column schema).
- **Auth:** Bearer JWT — **Permission:** `DataStore:Create` (Swagger: "Permission required: DataStore.Write")
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
- **Auth:** Bearer JWT — **Permission:** `DataStore:Update` (Swagger: "Permission required: DataStore.Update")
- **Request body** (`application/json`): `DataStoreMetadataDto`
  - Same fields as Create. `Id` identifies the store to update. `DataTypeId` is **forced to null by the controller** (retrieved server-side).
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `400` / `403 Forbidden` / `500` → array of `ApiErrorResponse`

---

#### `PATCH api/DataStore/{dataStoreId}/column`

- **Operation:** `ModifyColumn` — Modify a single column: rename, change its data type, or update its constraints.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Update` (Swagger: "Permission required: DataStore.Update")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required — target data store.
- **Request body** (`application/json`): `DataStoreModifyColumnDto`
  - `OriginalColumn` — `object (DataStoreColumnDefinitionDto)`, required — the column as it currently exists (identifies which column to change).
  - `UpdatedColumn` — `object (DataStoreColumnDefinitionDto)`, required — the desired new column definition.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto` (updated store metadata)
  - `204 No Content` (when the operation produced no metadata payload, e.g. a no-op change)
  - `400` / `403 Forbidden` / `500` → array of `ApiErrorResponse`

---

#### `DELETE api/DataStore/{id}`

- **Operation:** `Delete` — Delete a data store by id (drops the table and its backing data type).
- **Auth:** Bearer JWT — **Permission:** `DataStore:Delete` (Swagger: "Permission required: DataStore.Delete")
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` (empty body)
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore/{id}`

- **Operation:** `GetById` — Get a single data store's metadata (including its column schema).
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `DataStoreMetadataResponseDto`
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore`

- **Operation:** `GetAll` — List data stores with pagination and optional name search.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
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
- **Auth:** Bearer JWT — **Permission:** `DataStore:Create` (Swagger: "Permission required: DataStore.Write")
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
- **Auth:** Bearer JWT — **Permission:** `DataStore:Create` (Swagger: "Permission required: DataStore.Write")
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
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `DataModelDto` (see Shared DTOs)
  - `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `GET api/DataStore/restricted`

- **Operation:** `GetRestrictedDataStores` — List "restricted" data stores with pagination (data stores the caller can see but has limited access to).
- **Auth:** Bearer JWT — **Permission:** `None` (authenticated only; Swagger: "Permission required: None")
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → `PageRequestResult<DataStoreMetadataResponseDto>`
  - `500` → array of `ApiErrorResponse`

---

### DataStoreRowsController — `api/DataStore` (row CRUD + query)

Controller route: `[Route("api/DataStore")]`. Controller-level permission entity: `DataStore`. All actions are tagged `DataStore` in Swagger.

> **Row model (read this first).** Every row is a JSON object (dictionary). Keys are **column display names**, not internal aliases — the Web-Api layer maps display names to aliases before calling the Data Store service. Values are arbitrary JSON (`object` / nullable). Primary-key columns identify rows for update/delete.

---

#### `GET api/DataStore/{dataStoreId}/rows`

- **Operation:** `GetRows` — Get paginated rows from a data store, with optional filtering and sorting supplied **via query-string parameters** (not a request body).
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
  - **Filters** (repeatable, indexed) — each filter is three keys (parsed by `HttpRequestExtensions.GetDataStoreGetRowsPayload`):
    - `filters[N].displayName` — `string` — column display name to filter on.
    - `filters[N].operator` — `number` — numeric `DataStoreRowsFilterOperator` value (see enum in Shared DTOs; e.g. `1`=Equals, `2`=Contains).
    - `filters[N].value` — `string` — value to compare against.
    - `N` is a 0-based integer index; multiple filters use `filters[0].*`, `filters[1].*`, etc. A filter is only applied if its `displayName` is non-empty **and** its `operator` resolves to a defined non-`None` value; otherwise it is silently dropped.
  - **Sort** (single):
    - `sort.displayName` — `string` — column display name to sort by.
    - `sort.direction` — `number` — numeric `DataStoreRowsSortDirection` value (`1`=Asc, `2`=Desc). Sort is applied only if `displayName` is non-empty and direction resolves to non-`None`.
- **Responses:**
  - `200 OK` → `DataStoreViewerResponseDto` (column metadata + a `PageRequestResult` of row dictionaries)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`
- **Notes:** Filters/sort are parsed into the internal `InternalDataStoreGetRowsDto` shape (see Shared DTOs). Example query string: `?pageNumber=1&pageItemCount=50&filters[0].displayName=Status&filters[0].operator=1&filters[0].value=Active&sort.displayName=CreatedOn&sort.direction=2`.

---

#### `POST api/DataStore/{dataStoreId}/rows`

- **Operation:** `AddRows` — Add one or more rows to a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Create` (Swagger: "Permission required: DataStore.Write")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreRowsDto`
  - `Rows` — array of `object` (each a dictionary of `displayName → value`), required — the rows to insert.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto` (`{ "AffectedRows": <number> }`)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `PUT api/DataStore/{dataStoreId}/rows`

- **Operation:** `UpdateRow` — Update a single row in a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Update` (Swagger: "Permission required: DataStore.Update")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreUpdateRowRequestDto`
  - `Keys` — `object` (dictionary `displayName → value`), required — the primary-key column values identifying the row to update.
  - `Values` — `object` (dictionary `displayName → value`), required — the columns to set and their new values.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto`
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `DELETE api/DataStore/{dataStoreId}/rows`

- **Operation:** `DeleteRows` — Delete one or more rows from a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Delete` (Swagger: "Permission required: DataStore.Delete")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataStoreRowsPrimaryKeysDto`
  - `Keys` — array of `object` (each a dictionary `displayName → value` of the PK columns), required — one entry per row to delete.
- **Responses:**
  - `200 OK` → `DataStoreRowsAffectedDto`
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`

---

#### `QueryRows` (NOT a reachable HTTP endpoint)

- **Operation:** `QueryRows` — Filtered/sorted paginated row query using a rich JSON body.
- **Hidden from Swagger:** yes (`[ApiExplorerSettings(IgnoreApi = true)]`)
- **Routable:** **No.** The method is annotated `[NonAction]`, so ASP.NET does **not** map any route to it — it is not callable over HTTP. It exists as an internal helper only. App builders should use `GET api/DataStore/{dataStoreId}/rows` (query-string filters) for filtered reads.
- For completeness, the intended body shape was `DataStoreQueryRequestDto` (defined in Shared DTOs) — note this is a different, richer filter format (string operators, per-filter `Logic`, named sort) than the query-string format the live `GetRows` endpoint accepts.

---

### DataStoreCsvController — `api/DataStore` (CSV import/export jobs)

Controller route: `[Route("api/DataStore")]`. Controller-level permission entity: `DataStore`. All actions tagged `DataStore` in Swagger. CSV jobs are **asynchronous**: start a job, then poll/download by `jobId`.

---

#### `POST api/DataStore/{dataStoreId}/export-start`

- **Operation:** `StartExport` — Start an asynchronous CSV export job for a data store.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:** `{dataStoreId}` — `string (uuid)`, required.
- **Special headers:** `connectionId` `[FromHeader]` — `string`, optional — SignalR/connection id used to push job progress notifications back to the caller.
- **Responses:**
  - `200 OK` → `DataStoreCsvJobResponseDto` (the created job descriptor; use its `JobId` to download)
  - `400` / `404 Not Found` / `500` → array of `ApiErrorResponse`
- **Notes:** Read-only system columns are **never** included in the export (the `includeSystemColumns` flag is hard-coded to `false`). The export runs in the background; the response only confirms the job was queued.

---

#### `GET api/DataStore/{dataStoreId}/export-download/{jobId}`

- **Operation:** `DownloadExport` — Download the CSV file produced by a completed export job.
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:**
  - `{dataStoreId}` — `string (uuid)`, required.
  - `{jobId}` — `string (uuid)`, required — the export job id returned by `export-start`.
- **Responses:**
  - `200 OK` → CSV file download (`text/csv; charset=utf-8`, content type `text/csv`, returned as a `FileResult` with a server-set filename)
  - `400` / `404 Not Found` / `409 Conflict` (job not yet complete / wrong state) / `500` → array of `ApiErrorResponse`

---

#### `POST api/DataStore/{dataStoreId}/import-start`

- **Operation:** `Import` — Import CSV data into a data store (starts an asynchronous import job).
- **Auth:** Bearer JWT — **Permission:** `DataStore:Create` (Swagger: "Permission required: DataStore.Write")
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
- **Auth:** Bearer JWT — **Permission:** `DataStore:Read` (Swagger: "Permission required: DataStore.Read")
- **Path params:**
  - `{dataStoreId}` — `string (uuid)`, required.
  - `{jobId}` — `string (uuid)`, required — the import job id returned by `import-start`.
- **Responses:**
  - `200 OK` → CSV file download (`text/csv; charset=utf-8`) of failed rows
  - `400` / `404 Not Found` / `409 Conflict` (job not yet complete) / `500` → array of `ApiErrorResponse`

---

### DataTypesController — `api/DataTypes` (platform data-type definitions)

Controller route: `[Route("api/[controller]")]` → **`api/DataTypes`**. Controller-level permission entity: `DataModels`. Controller-level `[Consumes("application/json", "multipart/form-data")]`. Errors are returned as `400 Bad Request` with a list of composed error objects (no typed response DTO is declared).

> **Route ordering caveat.** Two GET routes share the same shape: `{id:guid}/{type?}` and `{value}`. A GUID-looking single segment matches `GetDataType(Guid, type)`; a non-GUID single segment matches `GetDataType(string value, ...)`. App builders should send a real GUID to hit the id-based lookup.

---

#### `POST api/DataTypes`

- **Operation:** `SaveDataType` — Store a new data type (data model).
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`application/json`): `CreateDataTypeDto`
  - `Name` — `string`, optional — internal name.
  - `DisplayName` — `string`, optional — UI name.
  - `Content` — `object (DataModelDto)`, optional — the full data-model definition (attributes, etc.).
  - `IsPublic` — `boolean`, optional, default `true`.
- **Responses:**
  - `200 OK` → created data type (manager result value; data-type object)
  - `400 Bad Request` → list of composed data-type / authorization errors

---

#### `POST api/DataTypes/private`

- **Operation:** `SavePrivateDataType` — Store a new private (nested/sub) data type attached to a root data type.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`application/json`): `PrivateDataTypeDto`
  - `Name` — `string`, optional.
  - `DisplayName` — `string`, optional.
  - `Attribute` — `object (DataAttributeDto)`, optional — the attribute definition.
  - `RootDataTypeId` — `string (uuid)`, required — the owning root data type.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type / authorization errors

---

#### `POST api/DataTypes/changeToPublic`

- **Operation:** `ChangeToPublic` — Promote a data type to public visibility.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`application/json`): `DataTypeTransferDto`
  - `RootDataTypeId` — `string (uuid)`, required.
  - `DataTypeId` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `POST api/DataTypes/clone`

- **Operation:** `CloneDataModel` — Clone an existing data type / data model.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`application/json`): `DataTypeTransferDto`
  - `RootDataTypeId` — `string (uuid)`, required.
  - `DataTypeId` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `DELETE api/DataTypes/attribute/{rootDataTypeId}/{attributeId}`

- **Operation:** `DeleteAttribute` — Delete an attribute from a data type.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Update` (Swagger: "Permission required: DataModels.Update")
- **Path params:**
  - `{rootDataTypeId}` — `string (uuid)`, required — the data type being modified.
  - `{attributeId}` — `string (uuid)`, required — the attribute to remove.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `POST api/DataTypes/attribute/{rootDataTypeId}`

- **Operation:** `CreateAttribute` — Add a new attribute to a data type.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Update` (Swagger: "Permission required: DataModels.Update")
- **Path params:** `{rootDataTypeId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataAttributeDto`
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `PUT api/DataTypes/attribute/{rootDataTypeId}`

- **Operation:** `EditAttribute` — Edit an existing attribute on a data type.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Update` (Swagger: "Permission required: DataModels.Update")
- **Path params:** `{rootDataTypeId}` — `string (uuid)`, required.
- **Request body** (`application/json`): `DataAttributeDto`
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `PUT api/DataTypes`

- **Operation:** `UpdateDataType` — Update top-level data type properties (name / display name).
- **Auth:** Bearer JWT — **Permission:** `DataModels:Update` (Swagger: "Permission required: DataModels.Update")
- **Request body** (`application/json`): `DataTypeUpdateDto`
  - `Id` — `string (uuid)`, required.
  - `Name` — `string`, optional.
  - `DisplayName` — `string`, optional.
  - `IsProcesio` — `boolean`, optional.
  - `IsPrimaryType` — `boolean`, optional.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → authorization error if `IsProcesio` or `IsPrimaryType` is `true` (cannot update PROCESIO / primary types); otherwise list of composed data-type errors
- **Notes:** The request is rejected outright (unauthorized) when `IsProcesio` **or** `IsPrimaryType` is set `true` in the body.

---

#### `GET api/DataTypes/{id}/{type?}`

- **Operation:** `GetDataType` — Get a data type by id. Returns the same data-type structure regardless of `type` (the `type` segment is legacy and no longer affects the result).
- **Auth:** Bearer JWT — **Permission:** `DataModels:Read` (Swagger: "Permission required: DataModels.Read")
- **Path params:**
  - `{id}` — `string (uuid)`, required.
  - `{type}` — `string|number (enum: DataModelTypeParam — Normal=1, Webhook=2)`, optional, default `Normal` — legacy selector; defaults to `Normal` when omitted or null.
- **Responses:**
  - `200 OK` → data type object (`DataModelDto`-shaped)
  - `400 Bad Request` → list of composed data-type errors

---

#### `GET api/DataTypes/{value}`

- **Operation:** `GetDataType` — Get a specific data type by its name or display name.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Read` (Swagger: "Permission required: DataModels.Read")
- **Path params:** `{value}` — `string`, required — the data type's name or display name (non-GUID; a GUID single segment routes to the id-based overload above).
- **Query params:** `displayName` — `boolean`, required — when `true`, `value` is matched against display names; when `false`, against internal names.
- **Responses:**
  - `200 OK` → data type object (or `null` if not found)

---

#### `GET api/DataTypes`

- **Operation:** `GetDataTypes` — List data types with pagination and optional filters.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Read` (Swagger: "Permission required: DataModels.Read")
- **Query params:**
  - `addProperties` — `boolean`, required — include each type's attributes/properties in the response.
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
  - `includeProcesioEntries` — `boolean`, optional, default `true` — include PROCESIO built-in types.
  - `includeExternalEntries` — `boolean`, optional, default `false` — include external/webhook types.
  - `searchName` — `string`, optional, default `null` — name filter; **ignored if shorter than 3 characters** after trim.
- **Responses:**
  - `200 OK` → paginated list of data types
  - `400 Bad Request` → not-found error message if the manager returns null

---

#### `GET api/DataTypes/count`

- **Operation:** `CountDataTypes` — Count data types matching the inclusion flags.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Read` (Swagger: "Permission required: DataModels.Read")
- **Query params:**
  - `includeProcesioEntries` — `boolean`, optional, default `true`.
  - `includeExternalEntries` — `boolean`, optional, default `false`.
- **Responses:**
  - `200 OK` → `number` (count)
  - `400 Bad Request` → not-found error message if count is negative

---

#### `GET api/DataTypes/primary`

- **Operation:** `GetPrimaryTypes` — List the platform's primary (built-in primitive) data types, paginated.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None`
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → paginated list of primary data types

---

#### `GET api/DataTypes/procesio`

- **Operation:** `GetProcesioTypes` — List the PROCESIO built-in data types, paginated.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None`
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → paginated list of PROCESIO data types

---

#### `GET api/DataTypes/primary/count`

- **Operation:** `CountPrimaryDataTypes` — Count primary data types.
- **Auth:** Bearer JWT — **Permission:** `None` (no `[AllowAnonymous]` here; authenticated only. Swagger: "Permission required: None")
- **Responses:**
  - `200 OK` → `number` (count)

---

#### `GET api/DataTypes/procesio/count`

- **Operation:** `CountProcesioDataTypes` — Count PROCESIO data types.
- **Auth:** Bearer JWT — **Permission:** `None` (authenticated only. Swagger: "Permission required: None")
- **Responses:**
  - `200 OK` → `number` (count)

---

#### `DELETE api/DataTypes/{id}`

- **Operation:** `DeleteDataType` — Delete a data type by id.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Delete` (Swagger: "Permission required: DataModels.Delete")
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` (empty body)
  - `400 Bad Request` → list of composed data-type errors

---

#### `POST api/DataTypes/generate`

- **Operation:** `GenerateDataModel` — Generate a data model from inline content (e.g. sample JSON/text supplied as a string).
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`application/json`): `GenerateDataTypeDto`
  - `Name` — `string`, optional.
  - `DisplayName` — `string`, optional.
  - `Content` — `string`, optional — the source content to infer the model from.
- **Responses:**
  - `200 OK` → generated data model
  - `400 Bad Request` → list of composed data-type errors

---

#### `POST api/DataTypes/generate/file`

- **Operation:** `GenerateDataModelByFile` — Generate a data model by inferring it from an uploaded file.
- **Auth:** Bearer JWT — **Permission:** `DataModels:Create` (Swagger: "Permission required: DataModels.Write")
- **Request body** (`multipart/form-data`): `DataTypeFileDto`
  - `File` — file (`IFormFile`), required — the source file.
  - `Name` — `string`, optional.
  - `DisplayName` — `string`, optional.
- **Responses:**
  - `200 OK` → generated data model
  - `400 Bad Request` → list of composed data-type errors

---

#### `GET api/DataTypes/restricted`

- **Operation:** `GetRestrictedDataTypes` — List "restricted" data types with pagination.
- **Auth:** Bearer JWT — **Permission:** `None` (authenticated only. Swagger tag `DataTypes`, "Permission required: None")
- **Query params:**
  - `pageNumber` — `number`, required.
  - `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → paginated list of restricted data types
  - `400 Bad Request` → not-found error message if null

---

## Shared DTOs

### `DataStoreColumnDefinitionDto`

A single column in a data store's schema.

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

Combined viewer payload returned by `GET .../rows`.

- `Columns` — array of `DataStoreColumnDefinitionDto` — schema for rendering.
- `Rows` — `object (PageRequestResult<row>)` — paginated rows, where each row is an `object` (dictionary `displayName → value`, values are arbitrary JSON / nullable).

### `DataStoreRowsDto` (request)

- `Rows` — array of `object` (each a dictionary `displayName → value`).

### `DataStoreUpdateRowRequestDto` (request)

- `Keys` — `object` (dictionary `displayName → value`) — PK columns identifying the row.
- `Values` — `object` (dictionary `displayName → value`) — columns to update.

### `DataStoreRowsPrimaryKeysDto` (request)

- `Keys` — array of `object` (each a dictionary `displayName → value` of PK columns) — one per row to delete.

### `DataStoreRowsAffectedDto` (response)

- `AffectedRows` — `number` — count of rows inserted/updated/deleted.

### `DataStoreQueryRequestDto` (NOT used by any live endpoint)

Intended body for the non-routable `QueryRows` helper. Documented for completeness only; do not call.

- `Filters` — array of `DataStoreFilterEntryDto`, nullable.
- `Sort` — array of `DataStoreSortEntryDto`, nullable.
- `PageNumber` — `number`, default `1`.
- `PageItemCount` — `number`, default `50`.
- `IncludePagination` — `boolean`, default `true`.

### `DataStoreFilterEntryDto`

- `DisplayName` — `string` — column display name.
- `Operator` — `string` — string operator name (this format uses string operators, unlike the live `GetRows` query-string which uses numeric `DataStoreRowsFilterOperator` values).
- `Value` — `object`, nullable.
- `Logic` — `string`, default `"and"` — how this filter combines with others (`"and"`/`"or"`).

### `DataStoreSortEntryDto`

- `DisplayName` — `string`.
- `Direction` — `string`, default `"asc"` (`"asc"`/`"desc"`).

### `InternalDataStoreGetRowsDto` (parsed query payload for `GET .../rows`)

Built server-side from the `filters[N].*` and `sort.*` query parameters.

- `Filters` — array of `InternalDataStoreRowsFilterDto`.
- `Sort` — `object (InternalDataStoreRowsSortDto)`, nullable.

### `InternalDataStoreRowsFilterDto`

- `DisplayName` — `string`, nullable — column display name (from `filters[N].displayName`).
- `ColumnAlias` — `string` — internal alias resolved server-side (not client-supplied).
- `Operator` — `number (enum: DataStoreRowsFilterOperator)` — from `filters[N].operator`.
- `Value` — `object`, nullable — from `filters[N].value`.

### `InternalDataStoreRowsSortDto`

- `DisplayName` — `string`, nullable — from `sort.displayName`.
- `ColumnAlias` — `string` — resolved server-side.
- `Direction` — `number (enum: DataStoreRowsSortDirection)` — from `sort.direction`.

### `DataStoreCsvJobResponseDto` (response)

- `JobId` — `string (uuid)` — use to download results / failures.
- `JobType` — `number (enum: DataStoreCsvJobType — Export=0, Import=10)`.
- `Status` — `number (enum: DataStoreCsvJobStatus — Queued=0, Running=10, Completed=20, CompletedWithFailures=30, Failed=40, Cancelled=50)`.
- `CreatedOn` — `string (date-time, ISO-8601)`.

### `CreateDataTypeDto` (request)

- `Name` — `string`, optional.
- `DisplayName` — `string`, optional.
- `Content` — `object (DataModelDto)`, optional.
- `IsPublic` — `boolean`, optional, default `true`.

### `PrivateDataTypeDto` (request)

- `Name` — `string`, optional.
- `DisplayName` — `string`, optional.
- `Attribute` — `object (DataAttributeDto)`, optional.
- `RootDataTypeId` — `string (uuid)`, required.

### `DataTypeTransferDto` (request)

- `RootDataTypeId` — `string (uuid)`, required.
- `DataTypeId` — `string (uuid)`, required.

### `DataTypeUpdateDto` (request)

- `Id` — `string (uuid)`, required.
- `Name` — `string`, optional.
- `DisplayName` — `string`, optional.
- `IsProcesio` — `boolean`, optional — must be `false` (request rejected if `true`).
- `IsPrimaryType` — `boolean`, optional — must be `false` (request rejected if `true`).

### `GenerateDataTypeDto` (request)

- `Name` — `string`, optional.
- `DisplayName` — `string`, optional.
- `Content` — `string`, optional — source content to infer the model from.

### `DataTypeFileDto` (multipart/form-data request)

- `File` — file (`IFormFile`), required.
- `Name` — `string`, optional.
- `DisplayName` — `string`, optional.

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
- `pageNumber` — `number` — current page (1-based).
- `pageItemCount` — `number` — items in this page.
- `pageItems` — array of `T` — the page's items.

### `Pagination` (query-param trio, not a body)

Used by all paginated endpoints via `pageNumber` + `pageItemCount` query params.

- `PageNumber` — `number` — 1-based; values `<= 1` are clamped to `1`.
- `PageItemCount` — `number` — page size; values `<= 0` are clamped to `0` (treated as "all" depending on the manager).

### `ApiErrorResponse` (error item — Data Store controllers)

Data Store error responses are a JSON **array** of these objects.

- `StatusCode` — `number`.
- `Value` — `object` — error detail/message payload.
- `Target` — `object` — what the error refers to (field/entity).

### Enums

**`DataStoreRowsFilterOperator`** (numeric, used in `GET .../rows` `filters[N].operator`):
`None=0`, `Equals=1`, `Contains=2`, `StartsWith=3`, `EndsWith=4`, `GreaterThan=5`, `LessThan=6`, `GreaterThanOrEqual=7`, `LessThanOrEqual=8`.

**`DataStoreRowsSortDirection`** (numeric, used in `sort.direction`): `None=0`, `Asc=1`, `Desc=2`.

**`DataStoreCsvJobType`**: `Export=0`, `Import=10`.

**`DataStoreCsvJobStatus`**: `Queued=0`, `Running=10`, `Completed=20`, `CompletedWithFailures=30`, `Failed=40`, `Cancelled=50`.

**`DataModelTypeParam`** (legacy GET selector): `Normal=1` (DataModelType.Expanded), `Webhook=2` (DataModelType.External). Defaults to `Normal`.

**`PrimaryDataType`** (`CsharpCorrespondent`): `None=0`, `Boolean=10`, `Integer=20`, `Float=30`, `Double=40`, `String=50`, `Date=60`, `Relationship=70`, `Time=80`, `DateTime=90`, `Guid=100`, `Uri=110`, `Json=120`, `Credentials=130`, `Object=140`.
