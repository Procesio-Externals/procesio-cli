# Document template endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/DocumentTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/ProcessInstanceDocumentsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/ProcessTemplateDocumentsController.cs`

This domain covers PROCESIO **document templates**: reusable rich-text/HTML templates with placeholder variables used to render documents in processes.

All routes are served under the Web-Api gateway base URL with no version path segment; versioning is via the optional `x-version` header (default `1.19`). Unless noted, request and response bodies are `application/json`.

---

## Endpoints

### DocumentTemplateController — `api/DocumentTemplate`

Controller route `api/[controller]` → **`api/DocumentTemplate`**. Controller auth entity: `DocumentDesigner`. Manages **document templates**.

#### `GET api/DocumentTemplate/{id}`

- **Operation:** `GetTemplate` — Get a full document template (with body) by id.
- **Auth:** Bearer JWT — **Permission:** `DocumentDesigner:Read`
- **Path params:** `{id}` — `string (uuid)`, required — document template id.
- **Responses:**
  - `200 OK` → `DocumentTemplateDto`
  - `400 Bad Request` → array of `ApiErrorResponse` (not found)

#### `GET api/DocumentTemplate`

- **Operation:** `GetTemplates` — Paginated list of document templates (without body), optionally filtered by name.
- **Auth:** Bearer JWT — **Permission:** `DocumentDesigner:Read`
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
  - `searchName` — `string`, optional, default `null` — name filter; ignored if trimmed length < 3.
- **Responses:**
  - `200 OK` → `PageRequestResult<BaseDocumentTemplateDto>`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `POST api/DocumentTemplate`

- **Operation:** `SaveTemplate` — Create a document template.
- **Auth:** Bearer JWT — **Permission:** `DocumentDesigner:Create` (summary "DocumentDesigner.Write")
- **Request body** (`application/json`): `DocumentTemplateDto`
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PUT api/DocumentTemplate`

- **Operation:** `UpdateTemplate` — Update a document template.
- **Auth:** Bearer JWT — **Permission:** `DocumentDesigner:Update`
- **Request body** (`application/json`): `DocumentTemplateDto`
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `DELETE api/DocumentTemplate/{id}`

- **Operation:** `RemoveTemplate` — Delete a document template.
- **Auth:** Bearer JWT — **Permission:** `DocumentDesigner:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — document template id.
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### ProcessInstanceDocumentsController — `api/DocumentTemplate` (restricted, instance scope)

Controller route is explicitly **`api/DocumentTemplate`**. Controller auth entity: `ProcessInstance`. Swagger groups this under the `DocumentTemplate` tag. Exposes a body-free ("restricted") view of a document template for use within a process instance.

#### `GET api/DocumentTemplate/{id}/restricted`

- **Operation:** `GetTemplate` — Get a single document template **without its body** (variables/metadata only).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read`
- **Path params:** `{id}` — `string (uuid)`, required — document template id.
- **Responses:**
  - `200 OK` → `RestrictedDocumentTemplateDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### ProcessTemplateDocumentsController — `api/DocumentTemplate` (restricted, list)

Controller route is explicitly **`api/DocumentTemplate`**. Controller auth entity: `ProcessDesigner`. Swagger groups this under the `DocumentTemplate` tag. Exposes a body-free list of document templates for the process designer.

#### `GET api/DocumentTemplate/restricted`

- **Operation:** `GetTemplates` — Paginated list of document templates **without bodies**.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Responses:**
  - `200 OK` → array of `RestrictedDocumentTemplateDto` (paginated result)
  - `400 Bad Request` → array of `ApiErrorResponse`

---

## Shared DTOs

### `DocumentTemplateDto` (request & response — full document template)

Inherits `BaseDocumentTemplateDto` (which inherits `OwnershipAuditDto`). All names below are explicit `[JsonProperty]` wire names.

| wire field | type | req/opt | description |
|---|---|---|---|
| `id` | `string (uuid)` | required | template id (from base) |
| `name` | `string` | optional | template name (from base) |
| `description` | `string` | optional | description |
| `body` | `string` | optional | document body (HTML/rich text) |
| `placeholderDelimiterStart` | `string` | optional | placeholder start delimiter |
| `placeholderDelimiterStop` | `string` | optional | placeholder end delimiter |
| `documentPageSize` | `string` | optional | page size (e.g. "A4") |
| `documentPageOrientation` | `number` | required | page orientation code |
| `variables` | array of `DocumentVariableDto` | optional | template variables/placeholders |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `BaseDocumentTemplateDto` (response — document template list item)

Inherits `OwnershipAuditDto`.

| wire field | type | req/opt | description |
|---|---|---|---|
| `id` | `string (uuid)` | required | template id |
| `name` | `string` | optional | template name |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `RestrictedDocumentTemplateDto` (response — body-free template)

Inherits `BaseDocumentTemplateDto` → `OwnershipAuditDto`.

| wire field | type | req/opt | description |
|---|---|---|---|
| `id` | `string (uuid)` | required | template id |
| `name` | `string` | optional | template name |
| `variables` | array of `DocumentVariableDto` | optional | template variables (no body) |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `DocumentVariableDto`

All names are explicit `[JsonProperty]` wire names.

| wire field | type | req/opt | description |
|---|---|---|---|
| `id` | `string (uuid)` | required | variable id |
| `dataType` | `string (uuid)` | required | data-type id |
| `type` | `number` | required | variable type code |
| `name` | `string` | optional | variable name |
| `defaultValue` | `object` | optional | default value |
| `isList` | `boolean` | required | whether the variable is a list |
| `isInput` | `boolean` | required | input flag |
| `isOutput` | `boolean` | required | output flag |

### `OwnershipAuditDto` (audit fields, inherited by several DTOs)

All names are explicit `[JsonProperty]` wire names.

| wire field | type | req/opt | description |
|---|---|---|---|
| `firstName` | `string` | optional | (deprecated) creator first name |
| `lastName` | `string` | optional | (deprecated) creator last name |
| `workspaceId` | `string (uuid)` | optional | owning workspace |
| `createdBy` | `string` | optional | "FirstName LastName" of creator |
| `updatedBy` | `string` | optional | "FirstName LastName" of last updater |
| `createdById` | `string (uuid)` | optional | creator id |
| `updatedById` | `string (uuid)` | optional | updater id |
| `createdOn` | `string (date-time, ISO-8601)` | optional | created timestamp |
| `updatedOn` | `string (date-time, ISO-8601)` | optional | updated timestamp |

### `PageRequestResult<T>` (generic paginated response)

All names are explicit `[JsonProperty]` wire names.

| wire field | type | req/opt | description |
|---|---|---|---|
| `totalItemCount` | `number` | required | total items across all pages |
| `pageNumber` | `number` | required | current page (1-based) |
| `pageItemCount` | `number` | required | items per page |
| `pageItems` | array of `T` | required | items on this page |

### `ApiErrorResponse` (error item — used inside `400` responses as an array)

| wire field | type | req/opt | description |
|---|---|---|---|
| `StatusCode` | `number` | required | error status code |
| `Value` | `object` | optional | error value/message |
| `Target` | `object` | optional | error target/field |

---

