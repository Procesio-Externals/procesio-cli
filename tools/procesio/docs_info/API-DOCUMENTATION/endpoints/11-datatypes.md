# Data Types endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/DataTypesController.cs`

**Data Types** (a.k.a. data models) are the platform's type-definition registry: primitive types, PROCESIO built-in types, and user-defined composite "data models" (objects with nested attributes). These types are what columns, process variables, and action inputs/outputs are typed against. This controller manages their CRUD, cloning, attribute editing, generation from sample content, and read-only listing of primary/PROCESIO types.

All routes are served under the Web-Api gateway base URL. Versioning is via the optional `x-version` header (default `1.19`). Unless an endpoint is marked **Auth: Anonymous**, send a Bearer JWT (see [../01-authentication.md](../01-authentication.md)). The controller is PUBLIC (it does not carry `[SecureInternalController]` and has no `internal/` route prefix).

The Data Types controller returns its errors as `400 Bad Request` with a list of composed error objects.

---

## Endpoints

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

### Enums

**`DataModelTypeParam`** (legacy GET selector): `Normal=1` (DataModelType.Expanded), `Webhook=2` (DataModelType.External). Defaults to `Normal`.

**`PrimaryDataType`** (`CsharpCorrespondent`): `None=0`, `Boolean=10`, `Integer=20`, `Float=30`, `Double=40`, `String=50`, `Date=60`, `Relationship=70`, `Time=80`, `DateTime=90`, `Guid=100`, `Uri=110`, `Json=120`, `Credentials=130`, `Object=140`.
