# Forms endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormApplicationController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormChainController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormProcessController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FileFormController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FileFormProcessController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormDataStoreController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormSigningController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormSigningPublicController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Forms/FormSigningTemplateController.cs`

This domain covers PROCESIO **forms**. A *form template* (`FormTemplate`) defines a form's layout, assignees and status; a *form instance* (`FormInstance`, exposed as "form") is a filled-in copy of a template that lives inside a process/flow run. *Form applications* group form templates into dashboards/menus. *Form chains* link a sequence of form instances that originate from the same template. *Form processes* let a public (anonymous) form front-end fetch/launch the backing flow and read its variables. *File-form* endpoints handle file upload/download tied to form instances and flow instances. *Form data-store* endpoints let a form read/write rows in a backing DataStore. *Form signing* endpoints let the person filling a form send the PDF in its signing element for signature, let the signers sign or decline, and store the designer's PDF for a signing element — see [Form signing — shared rules](#form-signing--shared-rules).

**Important — anonymous/public surface:** Several endpoints are `[AllowAnonymous]` so that publicly shared forms can be fetched, submitted, and can launch their backing flow without a JWT. These are flagged per-endpoint below and summarized in [Notes on anonymous access](#notes-on-anonymous-access). Anonymous endpoints rely on the `formTemplateWorkspaceId` route/header value to scope the request, and several add a randomized response delay (`TimeDelay.RandomWait`) as a timing-attack mitigation.

All routes are served under the Web-Api gateway base URL with no version path segment; versioning is via the optional `x-version` header (default `1.19`). Unless noted, request and response bodies are `application/json`.

---

## Endpoints

### FormController — `api/Form`

Controller route `api/[controller]` → **`api/Form`**. Controller auth entity: `FormInstance`. Manages **form instances** (filled forms).

#### `GET api/Form/{id}`

- **Operation:** `GetForm` — Get a single form instance by id.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Path params:** `{id}` — `string (uuid)`, required — form instance id.
- **Responses:**
  - `200 OK` → `GetFormDto`
  - `400 Bad Request` → array of `ApiErrorResponse` (e.g. not found)
- **Notes:** Adds a randomized response delay (timing-attack mitigation).

#### `GET api/Form/{pid}/all`

- **Operation:** `GetForms` — Get the list of form instances for a given process/parent id (`pid`).
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Path params:** `{pid}` — `string (uuid)`, required — parent id (process template / form template id).
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Responses:**
  - `200 OK` → paginated list of `GetFormDto` (manager returns the list shape; declared `ProducesResponseType` is `GetFormDto`)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/Form/assigned`

- **Operation:** `GetForms` — Get form instances assigned to the current authenticated user.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
  - `awaitingAction` — `boolean`, required — selects which link table the query reads. `true` reads the form assignees, so you get the forms that await the user's action. `false` reads the form submitters, so you get the forms the user already submitted. The endpoint doesn't filter on the form's `Stage` field.
- **Ordering:** The response is ordered by `SubmissionDate` descending, with the form `Id` ascending breaking ties. The query applies that order inside the paged subquery, before `LIMIT` cuts the page. The order therefore holds across pages: page 2 continues where page 1 stopped, and no form repeats or goes missing. `SubmissionDate` maps from the form's `UpdatedOn` column, which is the column the query sorts on.
- **Responses:**
  - `200 OK` → paginated list of `GetFormDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Both the returned page and `totalItemCount` join the form table and scope it to the caller's workspace, so the two agree. A link row whose form is missing, or whose form belongs to another workspace, counts in neither.

#### `POST api/Form`

- **Operation:** `SaveForm` — Save (create) a form instance. **Public form submission entry point.**
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `SetFormDto`
- **Responses:**
  - `200 OK` → created form id / value (manager `Value`)
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** `[AllowAnonymous]` — lets a publicly shared form be submitted without a JWT. Adds a randomized response delay.

#### `PUT api/Form`

- **Operation:** `UpdateForm` — Update an existing form instance.
- **Auth:** Bearer JWT — **Permission:** None (authenticated, no specific permission)
- **Request body** (`application/json`): `SetFormDto`
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Adds a randomized response delay.

#### `DELETE api/Form/{id}`

- **Operation:** `RemoveForm` — Delete a single form instance.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — form instance id.
- **Responses:**
  - `200 OK` → deleted id / value
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `DELETE api/Form`

- **Operation:** `RemoveForms` — Delete several form instances by id.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Delete`
- **Request body** (`application/json`): `array of string (uuid)` — list of form instance ids.
- **Responses:**
  - `200 OK` → result value
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/Form/{pid}/count`

- **Operation:** `FormCount` — Count of form instances for a parent id (`pid`).
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Path params:** `{pid}` — `string (uuid)`, required — parent id.
- **Responses:**
  - `200 OK` → `number` (count)

---

### FormTemplateController — `api/FormTemplate`

Controller route `api/[controller]` → **`api/FormTemplate`**. Controller auth entity: `FormTemplate`. Manages **form templates** (form definitions).

#### `POST api/FormTemplate`

- **Operation:** `SaveForm` — Create a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Create` (summary says "FormTemplate.Write")
- **Request body** (`application/json`): `FormTemplateDto`
- **Responses:**
  - `200 OK` → created template id / value
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PUT api/FormTemplate`

- **Operation:** `UpdateForm` — Update a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update`
- **Request body** (`application/json`): `FormTemplateDto`
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PATCH api/FormTemplate/{id}`

- **Operation:** `UpdateFormState` — Enable/disable (toggle the `State` flag of) a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update`
- **Path params:** `{id}` — `string (uuid)`, required — form template id.
- **Query params:** `state` — `boolean`, required — new state.
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `DELETE api/FormTemplate/{id}`

- **Operation:** `RemoveForm` — Delete a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — form template id.
- **Responses:**
  - `200 OK` → empty
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormTemplate/{id}`

- **Operation:** `GetForm` — Get a form template by id.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Read`
- **Path params:** `{id}` — `string (uuid)`, required — form template id.
- **Responses:**
  - `200 OK` → `FormTemplateDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormTemplate`

- **Operation:** `GetForms` — Get a paginated list of form templates, optionally filtered by name.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Read`
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
  - `searchName` — `string`, optional, default `null` — name filter; ignored if trimmed length < 3.
- **Responses:**
  - `200 OK` → paginated list of `FormTemplateDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormTemplate/all/basic`

- **Operation:** `GetAllFormIds` — Get all form templates in a lightweight (basic) shape.
- **Auth:** Bearer JWT — **Permission:** None (summary says "FormTemplate.None")
- **Responses:**
  - `200 OK` → array of `BasicFormTemplateDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `POST api/FormTemplate/{id}/duplicate`

- **Operation:** `DuplicateForm` — Duplicate an existing form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Create` (summary says "FormTemplate.Write")
- **Path params:** `{id}` — `string (uuid)`, required — template id to duplicate.
- **Responses:**
  - `200 OK` → `FormTemplateDto` (the new copy)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormTemplate/{workspaceId}/{id}`

- **Operation:** `GetAnonymousForm` — **Public** fetch of a form template by workspace + template id (used to render a shared/published form).
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{workspaceId}` — `string (uuid)`, required — owning workspace id.
  - `{id}` — `string (uuid)`, required — form template id.
- **Responses:**
  - `200 OK` → `FormTemplateDto`
  - `400 Bad Request` (empty or array of `ApiErrorResponse`)
  - `401 Unauthorized` → when the form requires authentication (`AuthenticationRequiredException`).
- **Notes:** `[AllowAnonymous]`. Adds a randomized response delay. If the template is private/requires auth it returns `401` rather than the body. Route order matters: `{workspaceId}/{id}` only matches two-segment paths.

#### `GET api/FormTemplate/processTemplate/list`

- **Operation:** `GetProcessTemplates` — List process/flow templates available to back a form.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Read`
- **Responses:**
  - `200 OK` → list of process templates (manager-defined shape; not a Forms DTO)

#### `GET api/FormTemplate/processTemplate/{id}`

- **Operation:** `GetProcessTemplates` — Get a single process/flow template usable by a form, by id.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Read`
- **Path params:** `{id}` — `string (uuid)`, required — process template id.
- **Responses:**
  - `200 OK` → process template (manager-defined shape; not a Forms DTO)

---

### FormApplicationController — `api/FormApplication`

Controller route `api/[controller]` → **`api/FormApplication`**. Controller auth entity: `FormTemplate`. Manages **form applications** (dashboard/menu groupings of forms).

#### `GET api/FormApplication/{id}`

- **Operation:** `GetApplication` — Get a form application by id.
- **Auth:** Bearer JWT — **Permission:** None (summary "FormTemplate.None")
- **Path params:** `{id}` — `string (uuid)`, required — form application id.
- **Responses:**
  - `200 OK` → `FormApplicationDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Adds a randomized response delay.

#### `GET api/FormApplication/all`

- **Operation:** `GetApplications` — Get a paginated list of all form applications.
- **Auth:** Bearer JWT — **Permission:** None
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Responses:**
  - `200 OK` → array / paginated list of `FormApplicationDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormApplication/all/{pid}`

- **Operation:** `GetApplicationsByPid` — Get the form applications tied to a form template id (`pid`).
- **Auth:** Bearer JWT — **Permission:** None
- **Path params:** `{pid}` — `string (uuid)`, required — form template id.
- **Responses:**
  - `200 OK` → array of `FormApplicationDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/FormApplication/all/filter`

- **Operation:** `GetApplicationsByFilter` — Get form applications filtered by state and type.
- **Auth:** Bearer JWT — **Permission:** None
- **Query params:**
  - `state` — `FormApplicationState` (enum), required — see Shared DTOs.
  - `type` — `FormApplicationType` (enum), required — see Shared DTOs. If omitted/`default (0)` the controller coerces it to `ALL`.
- **Responses:**
  - `200 OK` → array of `FormApplicationDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `POST api/FormApplication`

- **Operation:** `CreateApplication` — Create a form application.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Create` (summary "FormTemplate.Write")
- **Request body** (`application/json`): `FormApplicationDto`
- **Responses:**
  - `200 OK` → `string (uuid)` (new application id)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PUT api/FormApplication`

- **Operation:** `UpdateApplication` — Update a form application.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update`
- **Request body** (`application/json`): `FormApplicationDto`
- **Responses:**
  - `200 OK` → empty (declared `bool`)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PATCH api/FormApplication/{id}`

- **Operation:** `ToggleApplication` — Enable/disable a form application.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update`
- **Path params:** `{id}` — `string (uuid)`, required — application id.
- **Query params:** `state` — `FormApplicationState` (enum), required — new state.
- **Responses:**
  - `200 OK` → empty (declared `bool`)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `DELETE api/FormApplication/{id}`

- **Operation:** `DeleteApplication` — Delete a form application.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Delete`
- **Path params:** `{id}` — `string (uuid)`, required — application id.
- **Responses:**
  - `200 OK` → empty (declared `bool`)
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### FormChainController — `api/Form` (chain sub-routes)

Controller route is explicitly **`api/Form`**. Controller auth entity: `FormInstance`. Manages **form chains** (sequences of linked form instances).

#### `GET api/Form/chain/{formTemplateId}/all`

- **Operation:** `GetFormChainSummary` — Paginated list of form chains that started from a given form template.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Path params:** `{formTemplateId}` — `string (uuid)`, required — originating form template id.
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Responses:**
  - `200 OK` → paginated list of chain summaries (manager-defined shape)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/Form/chain/{chainId}`

- **Operation:** `GetFormChainById` — Get an entire form chain by chain id.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Path params:** `{chainId}` — `string (uuid)`, required — chain id.
- **Responses:**
  - `200 OK` → chain object (manager-defined shape)
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `PATCH api/Form/chain/{chainId}/{formInstanceId}`

- **Operation:** `UpdateFormChainById` — Patch the chain data of one form instance within a chain (scoped to the current workspace).
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Update`
- **Path params:**
  - `{chainId}` — `string (uuid)`, required — chain id.
  - `{formInstanceId}` — `string (uuid)`, required — form instance id within the chain.
- **Request body** (`application/json`): `object` — free-form chain data (arbitrary JSON; FE-defined).
- **Responses:**
  - `200 OK` → update result (manager-defined)
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** On error, adds a randomized response delay.

---

### FormProcessController — `api/FormProcess`

Controller route `api/[controller]` → **`api/FormProcess`**. Controller auth entity: `FormInstance`. **Entirely anonymous** — these endpoints let a public form front-end read and launch the form's backing flow. Every endpoint uses the `formTemplateWorkspaceId` header to scope the request.

#### `GET api/FormProcess/{formTemplateId}/{processTemplateId}`

- **Operation:** `GetProcessTemplate` — **Public** fetch of the flow/process template backing a form.
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required — form template id.
  - `{processTemplateId}` — `string (uuid)`, required — process/flow template id.
- **Special headers:** `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required — workspace that owns the form template.
- **Responses:**
  - `200 OK` → flow template (manager-defined shape)

#### `POST api/FormProcess/{formTemplateId}/{processTemplateId}/publish`

- **Operation:** `PublishFlow` — **Public** publish of the form's backing flow.
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required.
  - `{processTemplateId}` — `string (uuid)`, required.
- **Special headers:** `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required.
- **Request body** (`application/json`): `object` — free-form publish payload (FE-defined).
- **Responses:**
  - `200 OK` → published flow result (manager-defined)
  - `400 Bad Request` → array of `ApiErrorResponse` (flow errors)
- **Notes:** `[AllowAnonymous]`. On error, adds a randomized response delay.

#### `POST api/FormProcess/{formTemplateId}/{processTemplateId}/launch`

- **Operation:** `LaunchFlowInstance` — **Public** launch of a flow instance from a form (the core "submit form → run flow" action).
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required.
  - `{processTemplateId}` — `string (uuid)`, required.
- **Query params:**
  - `runSynchronous` — `boolean`, optional, default `false` — when `true`, waits for the flow to finish.
  - `secondsTimeOut` — `number`, optional, default `60` — synchronous-wait timeout (seconds).
- **Special headers:** `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required.
- **Request body** (`application/json`): `LaunchFlowPayload`
- **Responses:**
  - `200 OK` → launch result (process instance id and/or variables; manager-defined)
  - `400 Bad Request` → array of `ApiErrorResponse` (flow errors)
- **Notes:** `[AllowAnonymous]`. On error, adds a randomized response delay.

#### `GET api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables`

- **Operation:** `GetFlowInstanceVariables` — **Public** read of a running flow instance's variables (e.g. to show form-submission results).
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required.
  - `{processTemplateId}` — `string (uuid)`, required.
  - `{processInstanceId}` — `string (uuid)`, required — the launched flow instance id.
- **Special headers:** `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → flow instance variables (manager-defined shape)
  - `400 Bad Request` → array of `ApiErrorResponse` (flow errors)
- **Notes:** `[AllowAnonymous]`. On error, adds a randomized response delay.

---

### FileFormController — `api/Form` (file upload/download)

Controller route is explicitly **`api/Form`**. Controller auth entity: `FormInstance`. Handles file upload/download tied to a **form instance**.

#### `POST api/Form/upload`

- **Operation:** `UploadFormFile` — **Public** file upload attached to a form instance.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:**
  - `formId` `[FromHeader]` — `string (uuid)`, required — form instance id.
  - `fileId` `[FromHeader]` — `string (uuid)`, required — target file slot id.
- **Request body** (`multipart/form-data`): form field `package` — the uploaded file (`IFormFile`).
- **Responses:**
  - `200 OK` → upload result value (manager-defined)
  - `400 Bad Request` → array of `ApiErrorResponse`, or a plain error string on exception.
- **Notes:** `[AllowAnonymous]` so files can be attached to a publicly submitted form. Content type is `multipart/form-data` (overrides the controller-level `application/json`).

#### `GET api/Form/download`

- **Operation:** `DownloadFormFile` — Download a file previously attached to a form instance.
- **Auth:** Bearer JWT — **Permission:** `FormInstance:Read`
- **Special headers:**
  - `formId` `[FromHeader]` — `string (uuid)`, required — form instance id.
  - `fileId` `[FromHeader]` — `string (uuid)`, required — file id.
- **Responses:**
  - `200 OK` → file stream (`File(...)`, original content type and file name)
  - `400 Bad Request` → array of `ApiErrorResponse`, or a plain error string on exception.
- **Notes:** Returns a binary file download, not JSON.

---

### FileFormProcessController — `api/FormProcess` (flow-instance file upload/download)

Controller route is explicitly **`api/FormProcess`**. Controller auth entity: `FormInstance`. **Both endpoints anonymous** — file upload/download tied to a flow instance launched from a public form.

#### `POST api/FormProcess/{formTemplateId}/{flowInstanceId}/upload`

- **Operation:** `Upload` — **Public** file upload into a flow-instance variable (for a form-launched flow).
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required — form template id.
  - `{flowInstanceId}` — `string (uuid)`, required — launched flow instance id.
- **Special headers:**
  - `flowTemplateId` `[FromHeader]` — `string (uuid)`, required — flow/process template id.
  - `variableName` `[FromHeader]` — `string`, required — name of the flow variable to attach the file to.
  - `fileId` `[FromHeader]` — `string (uuid)`, required — target file slot id.
  - `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required — workspace owning the form template.
- **Request body** (`multipart/form-data`): form field `package` — the uploaded file (`IFormFile`).
- **Responses:**
  - `200 OK` → `string (uuid)` (the `fileId`)
  - `400 Bad Request` → array of `ApiErrorResponse` (flow errors), or a plain error string on exception.
- **Notes:** `[AllowAnonymous]`. Content type `multipart/form-data`. On error, adds a randomized response delay.

#### `GET api/FormProcess/download`

- **Operation:** `Download` — **Public** download of a file from a flow-instance variable / storage path.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:**
  - `uploadFilePath` `[FromHeader]` — `string`, required — storage path of the file.
  - `variableId` `[FromHeader]` — `string (uuid)`, optional — flow variable id.
  - `instanceId` `[FromHeader]` — `string (uuid)`, optional — flow instance id.
  - `flowTemplateId` `[FromHeader]` — `string (uuid)`, optional — flow template id.
  - `formTemplateId` `[FromHeader]` — `string (uuid)`, optional — form template id.
- **Responses:**
  - `200 OK` → file stream (`File(...)`, original content type and file name)
  - `400 Bad Request` → array of `ApiErrorResponse`, or a plain error string on exception.
- **Notes:** `[AllowAnonymous]`. Returns a binary file download, not JSON.

---

### FormDataStoreController — `api/Form/dataStore/{dataStoreId}/rows`

Controller route is explicitly **`api/Form/dataStore/{dataStoreId}/rows`**. Controller auth entity: `FormInstance`. **All endpoints anonymous** — lets a (possibly public) form read/write rows in a backing DataStore. Each request is scoped by the `formTemplateWorkspaceId` / `formTemplateId` headers (and optional `formInstanceId`). Row dictionaries use **display names** as keys; Web-Api maps them to DataStore column aliases internally.

> `{dataStoreId}` — `string (uuid)`, required — applies to every endpoint below (path param).

#### `POST api/Form/dataStore/{dataStoreId}/rows/filter`

> **Replaces the former `GET api/Form/dataStore/{dataStoreId}/rows`.** Filtering now travels in the request body as a recursive tree — the same read capability the Data Store viewer and the Process-Execution Data Store connector have.

- **Operation:** `GetRows` — Read a page of rows, optionally narrowed by a recursive filter tree with AND/OR grouping and sorted by one or more columns.
- **Auth:** Anonymous — **Permission:** None (access is granted by the form template/instance headers)
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Special headers:**
  - `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required.
  - `formTemplateId` `[FromHeader]` — `string (uuid)`, required.
  - `formInstanceId` `[FromHeader]` — `string (uuid)`, optional.
- **Request body** (`application/json`): `DataStoreGetRowsRequestDto` — **optional** (`EmptyBodyBehavior.Allow`). Send no body to read every row. Same shape as the viewer read path — see [09 → the filter tree](10-datastore.md#the-filter-tree).
- **Responses:**
  - `200 OK` → paginated rows (manager-defined shape)
  - error → standardized error response (`this.ErrorResponse(result)`)

#### `POST api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `AddRows` — Add one or more rows to the data store.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreInsertRowsRequestDto`
- **Responses:**
  - `200 OK` → result value (manager-defined)
  - error → standardized error response

#### `PUT api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `UpdateRows` — Set the given values on every row the filter matches.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreUpdateRowsRequestDto` — `Values` (dictionary `displayName → value`) plus a mandatory `Filter`. See [09](10-datastore.md#datastoreupdaterowsrequestdto-request).
- **Responses:**
  - `200 OK` → result value
  - error → standardized error response

#### `DELETE api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `DeleteRows` — Remove every row the filter matches.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreDeleteRowsRequestDto` — a mandatory `Filter`. See [09](10-datastore.md#datastoredeleterowsrequestdto-request).
- **Responses:**
  - `200 OK` → result value
  - error → standardized error response

---

### Form signing — shared rules

A **signing envelope** holds one PDF from a form's signing element, the spots to fill on it and its signers (*parties*). The person filling the form (the *preparer*) creates it as a `DRAFT`, places spots and signers, and sends it once the form is submitted; the send binds it to that form instance. Signers then sign in their order, and the envelope ends `COMPLETED` with a signed PDF. Three controllers serve it: `FormSigningController` (in-app, Bearer JWT), `FormSigningPublicController` (a public form's anonymous filler) and `FormSigningTemplateController` (the designer's PDF for a signing element). Who may prepare, the signing step in `api/Form/assigned`, the audit chain and the safeguards are in the Web-Api [forms technical reference](../../BE/Web-Api/.features/forms/forms.md).

- **Feature flag.** With the `Forms` flag off, every signing endpoint answers `400` `FEATURE_DISABLED` (1013); see [Forms disabled](../../BE/Web-Api/.features/forms/forms.md#forms-disabled).
- **Status codes.** The first error code decides the HTTP status:

  | Error code | HTTP | Body |
  |---|---|---|
  | `710` `SIGNING_ENVELOPE_NOT_FOUND`, `1004` `ENTITY_NOT_FOUND` | `404` | array of `ApiErrorResponse` |
  | `501` `USER_IS_NOT_AUTHORIZED` | `403` | array of `ApiErrorResponse` |
  | `711` `SIGNING_ENVELOPE_INVALID_STATE`, `712` `SIGNING_CONCURRENT_UPDATE`, `713` `SIGNING_ORDER_VIOLATION` | `409` | `SigningConflictResponse`: the errors plus the current state, so the client reconciles |
  | any other (`502` `INVALID_REQUEST`, `714` `SIGNING_PARTY_INVALID`, `715` `SIGNING_SPOT_INVALID`, `716` `SIGNING_DOCUMENT_INVALID`, `719` `SIGNING_SIGNATURE_INVALID`, `210` `FILE_UPLOAD_FAILED`) | `400` | array of `ApiErrorResponse` |

  An empty `package` on an upload answers `400` with `450` `DB_ENTRY_NOT_FOUND`. A body over the request ceiling answers `413`.
- **Replays.** A send, sign or decline that already succeeded answers `200` with the current state, never an error.
- **Optimistic concurrency.** Every envelope read carries `RowVersion`. Echo it on the draft save and on the send; a stale one answers `409` `712`.
- **Refusal delay.** Refusals from `my-session`, `sign`, `decline` and from every public endpoint return after a random 120–400 ms pause, so timing does not tell whether an envelope, party or token exists. Successful answers are not delayed.
- **Limits.** Request ceilings: upload 16 MB, draft save 1 MB, signature 4 MB, decline 32 KB. The document itself must be a PDF within the configured cap (10 MB by default), not encrypted and without XFA; the signature PNG must be within 1024 KB and 16 megapixels by default. A draft holds at most 50 parties and 1000 spots.

---

### FormSigningController — `api/form/signing`

Controller route is explicitly **`api/form/signing`**. Controller auth entity: `FormInstance`. Every endpoint needs a Bearer JWT and declares `AuthorizationAction(None)`: the manager decides access, not an entity permission. A create is open to whoever may fill the form (an enabled, published template; a private one only for a caller in its scope). A `DRAFT` belongs to its creator or a `FormInstance` role holder. A sent envelope is readable by anyone who can see its form instance. The `my-session` endpoints are open to the envelope's parties only.

#### `POST api/form/signing/envelope`

- **Operation:** `CreateEnvelope` — Create a `DRAFT` envelope from a PDF uploaded into a form's signing element.
- **Auth:** Bearer JWT — **Permission:** None (summary: whoever may fill the form)
- **Request body** (`multipart/form-data`):
  - `package` — file, required — the PDF.
  - `formTemplateId` — `string (uuid)`, required — the form template being filled.
  - `elementId` — `string`, required, max 64 — the signing element's id.
  - `name` — `string`, optional, max 256 — document name; defaults to the file name.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto` (status `DRAFT`, `FormId` empty until the send)
  - `400 Bad Request` → `502` (field too long), `716` (document invalid)
  - `403 Forbidden` → `501` — the caller may not fill the form, the form has no such signing element, or the element's document is the designer's (use `envelope/from-template`)

#### `POST api/form/signing/envelope/from-template`

- **Operation:** `CreateEnvelopeFromTemplate` — Create the envelope of a signing element whose document the designer attached, seeded with the designer's signers and spots. Such an element takes no upload.
- **Auth:** Bearer JWT — **Permission:** None (summary: whoever may fill the form)
- **Request body** (`application/json`): `CreateSigningEnvelopeFromTemplateDto`
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto` (the seeded `DRAFT`)
  - `400 Bad Request` → `502`, `716` (the element's document cannot be opened), or the draft save's errors (for example `714` when a designer signer is no longer a workspace member); the envelope is then discarded
  - `403 Forbidden` → `501` — as for the upload

#### `GET api/form/signing/envelope/{id}`

- **Operation:** `GetEnvelope` — Envelope with its document, spots, parties and effective status.
- **Auth:** Bearer JWT — **Permission:** None (summary: sent — whoever sees its submission; a `DRAFT` — its creator, or `FormInstance.Read`)
- **Path params:** `{id}` — `string (uuid)`, required — envelope id.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto`
  - `403 Forbidden` → `501` — a `DRAFT` that is not the caller's
  - `404 Not Found` → `710`

#### `PUT api/form/signing/envelope/{id}`

- **Operation:** `UpdateDraft` — Replace the draft's name, order mode, spots and signers. `DRAFT` only.
- **Auth:** Bearer JWT — **Permission:** None (summary: the envelope's creator, or `FormInstance.Update`)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Request body** (`application/json`): `SetSigningEnvelopeDto`. `Spots` and `Parties` replace the stored ones whole. Every signer is a member of the envelope's workspace given by `UserId` (on a personal workspace, only its owner); a signer by e-mail is refused here.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto` (with the new `RowVersion`)
  - `400 Bad Request` → `502` (no body, unknown `OrderMode`, `Name` over 256); `714` (over 50 parties, a party without exactly one of `UserId` / `Email`, a duplicate signer, a negative `OrderIndex`, a non-member); `715` (over 1000 spots, empty or duplicate `SpotId`, empty `PartyId`, `Page` < 1, bounds outside 0..1, unsupported `Type`, `Value` over 256, `Label` over 128)
  - `403 Forbidden` → `501`
  - `404 Not Found` → `710`
  - `409 Conflict` → `711` (not a `DRAFT`, a spot whose party is not in `Parties`, or a page past the document's last), `712` (stale `RowVersion`)

#### `DELETE api/form/signing/envelope/{id}`

- **Operation:** `DiscardDraft` — Delete a `DRAFT` with its document.
- **Auth:** Bearer JWT — **Permission:** None (summary: the envelope's creator, or `FormInstance.Update`; `DRAFT` only)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → empty
  - `403 Forbidden` → `501`
  - `404 Not Found` → `710`
  - `409 Conflict` → `711` — the envelope was already sent

#### `POST api/form/signing/envelope/{id}/send`

- **Operation:** `Send` — Send for signing: binds the envelope to the submitted form instance, freezes spots and parties, opens the first order group, sets `ExpiresOn` (14 days by default) and e-mails the first group's signers, except the sender.
- **Auth:** Bearer JWT — **Permission:** None (summary: the envelope's creator, or `FormInstance.Update`)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Query params:**
  - `formId` — `string (uuid)`, required — the form instance the submit created; its values must name this envelope under its signing element.
  - `rowVersion` — `number`, required — from the last read.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto`, also when the envelope is already `SENT` or `IN_PROGRESS`
  - `403 Forbidden` → `501`
  - `404 Not Found` → `710` — also when the instance is outside the caller's scope, belongs to another template, or does not name this envelope
  - `409 Conflict` → `711` (no parties, a party without a required `SIGNATURE` spot, no `formId`, or the envelope has ended), `712` (stale `rowVersion`)

#### `GET api/form/signing/envelope/{id}/document`

- **Operation:** `Download` — Stream a rendition of the document.
- **Auth:** Bearer JWT — **Permission:** None (summary: as the envelope's read; `my-step`: the envelope's parties)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Query params:** `version` — `string`, optional, default `current`, case-insensitive; an unknown value reads as `current`:
  - `current` — the document with every signature captured so far.
  - `signed` — the final signed PDF, once the envelope is `COMPLETED`.
  - `source` — the original upload.
  - `my-step` — the caller's step-scoped view: the source plus the fulfilled spots of their order group and earlier ones, rendered on each call. Parties only.
- **Responses:**
  - `200 OK` → `application/pdf` stream, named after the document (`-signed` before the extension for `signed`)
  - `404 Not Found` → the caller may not read it, is not a party (`my-step`), or the rendition does not exist yet
- **Notes:** Returns a binary file download, not JSON.

#### `GET api/form/signing/envelope/{id}/my-session`

- **Operation:** `GetMySession` — The signer's scoped view: their party, their own spots, progress counts and whether it is their turn. The first open by a notified signer marks them `VIEWED`.
- **Auth:** Bearer JWT — **Permission:** None (summary: authenticated signers only; party membership enforced)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `SigningSessionDto`
  - `403 Forbidden` → `501` — the caller is not a party
  - `404 Not Found` → `710`

#### `POST api/form/signing/envelope/{id}/my-session/sign`

- **Operation:** `Sign` — Apply the signature image to every spot of the caller; the auto-filled spots (names, date) get their value. The envelope moves to the next order group, or completes, once every party of the group signed.
- **Auth:** Bearer JWT — **Permission:** None (summary: authenticated signers only)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Request body** (`application/json`): `SubmitSignatureDto`
- **Responses:**
  - `200 OK` → `SigningSessionDto`, also when the caller already signed
  - `400 Bad Request` → `719` — missing, not base64, not a PNG, or over the size or pixel cap
  - `403 Forbidden` → `501`
  - `404 Not Found` → `710`
  - `409 Conflict` → `713` (not the caller's turn), `711` (the caller declined, or the envelope is not `SENT` / `IN_PROGRESS`)

#### `POST api/form/signing/envelope/{id}/my-session/decline`

- **Operation:** `Decline` — Decline to sign, on the caller's turn only. The envelope becomes `DECLINED` and stops circulating; its creator is e-mailed.
- **Auth:** Bearer JWT — **Permission:** None (summary: authenticated signers only)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Request body** (`application/json`): `SigningDeclineDto`
- **Responses:**
  - `200 OK` → `SigningSessionDto` (the party carries `DeclineReason`), also when the caller already declined
  - `403 Forbidden` → `501`
  - `404 Not Found` → `710`
  - `409 Conflict` → `713` (not the caller's turn), `711` (the caller already signed, or the envelope is not `SENT` / `IN_PROGRESS`)

---

### FormSigningPublicController — `api/form/signing/public`

Controller route is explicitly **`api/form/signing/public`**. Controller auth entity: `FormInstance`. **All endpoints anonymous** — signing on a public form by the anonymous person filling it, who is the envelope's one signer (names and e-mail optional) and cannot add others. A create returns an access token once; every later envelope call sends it in the **`x-signing-token`** header. Every call also needs an anonymous caller (a request carrying a JWT or API key is refused) and a form that is still enabled, published and public. An unknown, expired, revoked or foreign token, a form closed since, or public signing switched off in the deployment, all read as `404` `710`. Decline is not available here.

#### `POST api/form/signing/public/envelope`

- **Operation:** `CreateEnvelope` — Create a `DRAFT` envelope from the PDF the filler uploads into the form's signing element.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`multipart/form-data`):
  - `package` — file, required — the PDF.
  - `formTemplateId` — `string (uuid)`, required.
  - `workspaceId` — `string (uuid)`, required — the workspace that owns the form template.
  - `elementId` — `string`, required, max 64.
  - `name` — `string`, optional, max 256.
  - `firstName`, `lastName` — `string`, optional, max 128 each — the signer.
  - `email` — `string`, optional, max 256 — a valid address when given.
- **Responses:**
  - `200 OK` → `PublicSigningEnvelopeDto`
  - `400 Bad Request` → `502`, `714` (signer fields), `716`
  - `403 Forbidden` → `501` — a signed-in caller, a form that is not enabled, published and public, no such signing element, or an element holding the designer's document
  - `404 Not Found` → `710` — public signing is off

#### `POST api/form/signing/public/envelope/from-template`

- **Operation:** `CreateEnvelopeFromTemplate` — Create the envelope of a signing element whose document the designer attached, with the spots of the designer's slots the filler takes.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `CreatePublicSigningEnvelopeFromTemplateDto`
- **Responses:**
  - `200 OK` → `PublicSigningEnvelopeDto`
  - `400 Bad Request` → `502`, `714`, `716`, or the draft save's errors (the envelope is then discarded)
  - `403 Forbidden` → `501` — as for the upload
  - `404 Not Found` → `710` — public signing is off

#### `GET api/form/signing/public/envelope/{id}`

- **Operation:** `GetEnvelope` — Envelope with its document, spots, its one party and effective status.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` `[FromHeader]` — `string`, required.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto`
  - `404 Not Found` → `710`

#### `PUT api/form/signing/public/envelope/{id}`

- **Operation:** `UpdateDraft` — Replace the draft's name and the signer's spots. `DRAFT` only.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Request body** (`application/json`): `SetSigningEnvelopeDto`. `Parties` and `OrderMode` are ignored; an `OrderMode` given must still be a valid name.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto`
  - `400 Bad Request` → `502`, `715`
  - `404 Not Found` → `710`
  - `409 Conflict` → `711`, `712`

#### `POST api/form/signing/public/envelope/{id}/send`

- **Operation:** `Send` — Send after the public submit, bound to the instance it created. No e-mail is sent: the filler signs right away.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Query params:** `formId` — `string (uuid)`, required — the instance the public submit created; `rowVersion` — `number`, required.
- **Responses:**
  - `200 OK` → `GetSigningEnvelopeDto`, also when already sent
  - `404 Not Found` → `710` — also when the instance belongs to another form or does not name this envelope
  - `409 Conflict` → `711`, `712`

#### `DELETE api/form/signing/public/envelope/{id}`

- **Operation:** `DiscardDraft` — Delete the `DRAFT` with its document and the signer's details.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Responses:**
  - `200 OK` → empty
  - `404 Not Found` → `710`
  - `409 Conflict` → `711` — already sent

#### `GET api/form/signing/public/envelope/{id}/document`

- **Operation:** `Download` — Stream a rendition: `current` (default), `signed` or `source`, as in the in-app download; `my-step` reads as `current`.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Query params:** `version` — `string`, optional, default `current`.
- **Responses:**
  - `200 OK` → `application/pdf` stream
  - `404 Not Found`
- **Notes:** Returns a binary file download, not JSON.

#### `GET api/form/signing/public/envelope/{id}/my-session`

- **Operation:** `GetMySession` — The signer's session view (their own spots and turn).
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Responses:**
  - `200 OK` → `SigningSessionDto`
  - `404 Not Found` → `710`

#### `POST api/form/signing/public/envelope/{id}/my-session/sign`

- **Operation:** `Sign` — Apply the drawn signature to every spot of the signer.
- **Auth:** Anonymous — **Permission:** None (access token)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Special headers:** `x-signing-token` — `string`, required.
- **Request body** (`application/json`): `SubmitSignatureDto`
- **Responses:**
  - `200 OK` → `SigningSessionDto`, also when already signed
  - `400 Bad Request` → `719`
  - `404 Not Found` → `710`
  - `409 Conflict` → `711` — the envelope is not `SENT` / `IN_PROGRESS`

#### `GET api/form/signing/public/template-document/{workspaceId}/{formTemplateId}/{fileId}`

- **Operation:** `DownloadTemplateDocument` — Stream the PDF the designer attached to a public form's signing element: the document the filler starts from. No access token.
- **Auth:** Anonymous — **Permission:** None
- **Path params:**
  - `{workspaceId}` — `string (uuid)`, required — the workspace that owns the form template.
  - `{formTemplateId}` — `string (uuid)`, required.
  - `{fileId}` — `string (uuid)`, required — the `fileId` the element's `document` setting keeps.
- **Responses:**
  - `200 OK` → `application/pdf` stream named `document.pdf`
  - `404 Not Found` — public signing is off, the form is not enabled, published and public, or no signing element of the form keeps that file
- **Notes:** Returns a binary file download, not JSON.

---

### FormSigningTemplateController — `api/form/signing/template-document`

Controller route is explicitly **`api/form/signing/template-document`**. Controller auth entity: `FormTemplate`. Stores the PDF a designer attaches to a signing element; the element's `document` setting then keeps `{ fileId, name }` instead of the file.

#### `POST api/form/signing/template-document`

- **Operation:** `UploadTemplateDocument` — Store the designer's PDF for a signing element of the form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update`
- **Request body** (`multipart/form-data`):
  - `package` — file, required — the PDF.
  - `formTemplateId` — `string (uuid)`, required — a saved template.
- **Responses:**
  - `200 OK` → `SigningTemplateDocumentDto`
  - `400 Bad Request` → `716` (document invalid), `210` (the file could not be stored)
  - `404 Not Found` → `1004` — the template is not in the caller's workspace, or not the caller's on a personal workspace

#### `GET api/form/signing/template-document/{formTemplateId}/{fileId}`

- **Operation:** `DownloadTemplateDocument` — Stream a template's signing document: one a signing element of the template keeps, or, with `formId`, one that submission keeps (made before the document was replaced).
- **Auth:** Bearer JWT — **Permission:** None (summary: `FormTemplate.Read`, `FormInstance.Read`, or whoever may fill the form)
- **Path params:**
  - `{formTemplateId}` — `string (uuid)`, required.
  - `{fileId}` — `string (uuid)`, required.
- **Query params:** `formId` — `string (uuid)`, optional, default `null` — a submission of this template.
- **Responses:**
  - `200 OK` → `application/pdf` stream named `document.pdf`
  - `404 Not Found` — the caller may not see the template, or neither the template nor the submission keeps that file
- **Notes:** Returns a binary file download, not JSON.

---

## Notes on anonymous access

The following endpoints are `[AllowAnonymous]` (no JWT required). They form the **public form runtime** — a shared form's front-end uses them to render the form, submit it, attach/download files, launch the backing flow, read results, and interact with form-backed data stores. Anonymous endpoints are scoped by an explicit workspace id (route segment `{workspaceId}` or header `formTemplateWorkspaceId`) and frequently add a randomized response delay (`TimeDelay.RandomWait`) as a timing-attack countermeasure.

- `POST api/Form` (`SaveForm`) — submit/save a form instance.
- `GET api/FormTemplate/{workspaceId}/{id}` (`GetAnonymousForm`) — fetch a shared form template (returns `401` if it requires auth).
- `GET api/FormProcess/{formTemplateId}/{processTemplateId}` (`GetProcessTemplate`).
- `POST api/FormProcess/{formTemplateId}/{processTemplateId}/publish` (`PublishFlow`).
- `POST api/FormProcess/{formTemplateId}/{processTemplateId}/launch` (`LaunchFlowInstance`).
- `GET api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables` (`GetFlowInstanceVariables`).
- `POST api/Form/upload` (`UploadFormFile`).
- `POST api/FormProcess/{formTemplateId}/{flowInstanceId}/upload` (`Upload`).
- `GET api/FormProcess/download` (`Download`).
- `POST api/Form/dataStore/{dataStoreId}/rows/filter` and `POST|PUT|DELETE api/Form/dataStore/{dataStoreId}/rows` (all four `FormDataStore` endpoints).
- Every `api/form/signing/public/*` endpoint (`FormSigningPublicController`, ten in all) — the envelope calls authenticate by the `x-signing-token` access token the create returns; the template-document download needs none.

All other endpoints in this domain require a Bearer JWT.

---

## Shared DTOs

### `GetFormDto` (response — form instance)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required | form instance id |
| `Pid` | `string (uuid)` | required | parent id (process/template) |
| `WorkspaceId` | `string (uuid)` | required | owning workspace |
| `ChainId` | `string (uuid)` | optional | chain id, if part of a chain |
| `Name` | `string` | optional | form name |
| `StartedOn` | `string (date-time, ISO-8601)` | required | when the form was started |
| `SubmissionDate` | `string (date-time, ISO-8601)` | required | when the form was submitted — maps from the form's `UpdatedOn` column, which is the key `GET api/Form/assigned` sorts on |
| `Stage` | `FormStage` (enum) | required | form stage |
| `Submitters` | array of `FormSubmitterDto` | optional | who submitted and when |
| `Assignees` | array of `FormAssigneeDto` | optional | assignees/approvers |
| `NextStep` | `FormNextStepDto` | optional | next step descriptor |
| `FormFiles` | array of `FormFileDto` | optional | attached files |
| `Data` | `object` | optional | FE-defined form data (stored as JSON) |
| `ChainData` | `object` | optional | FE-defined per-instance chain data |
| `ChainDataList` | array of `FormChainDataModel` | optional | aggregated chain data across the chain |

### `SetFormDto` (request — create/update form instance)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | form instance id (set on update) |
| `Pid` | `string (uuid)` | optional | parent id |
| `WorkspaceId` | `string (uuid)` | optional | owning workspace |
| `ChainStage` | `FormChain` (enum) | optional, default `None (1)` | chain role of this form |
| `ChainId` | `string (uuid)` | optional, default `null` | chain id |
| `Name` | `string` | optional | form name |
| `NextStep` | `FormNextStepDto` | optional | next step descriptor |
| `FormFiles` | array of `FormFileDto` | optional | attached files |
| `OverrideAssignees` | array of `FormAssigneeDto` | optional | assignee overrides |
| `Data` | `object` | optional | FE-defined form data (stored as JSON) |
| `ChainData` | `object` | optional | FE-defined per-instance chain data |

### `FormTemplateDto` (request & response — form template)

Inherits `OwnershipAuditDto` (audit fields below).

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | template id (set on update) |
| `Name` | `string` | optional | template name |
| `IsPrivate` | `boolean` | required | whether the form requires authentication to view |
| `Type` | `FormType` (enum) | required, default `UserTask (0)` | form type |
| `Status` | `FormStatus` (enum) | required, default `DRAFT (0)` | publication status |
| `State` | `boolean` | required | enabled/disabled state |
| `Assignees` | array of `FormAssigneeDto` | optional | assignees/approvers |
| `Data` | `object` | optional | FE-defined layout/config (stored as JSON) |
| `CustomUrl` | `CustomUrlDto` | optional, default `null` | custom/shared URL config |
| `WorkspaceName` | `string` | optional | owning workspace name |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `BasicFormTemplateDto` (response — lightweight template)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | template id |
| `Name` | `string` | optional | template name |
| `IsPrivate` | `boolean` | required | requires auth to view |
| `Type` | `FormType` (enum) | required, default `UserTask (0)` | form type |
| `Status` | `FormStatus` (enum) | required, default `DRAFT (0)` | publication status |
| `State` | `boolean` | required | enabled/disabled state |

### `FormApplicationDto` (request & response — form application)

Inherits `OwnershipAuditDto` (audit fields below).

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | application id |
| `Pid` | `string (uuid)` | required | form template id this application belongs to |
| `Name` | `string` | optional | application name |
| `Description` | `string` | optional | description |
| `Image` | `FormApplicationImageDto` | optional | icon/image |
| `Type` | `FormApplicationType` (enum) | required | application type |
| `Enabled` | `boolean` | required | enabled flag |
| `IsProcesio` | `boolean` | required | whether it is a built-in PROCESIO application |
| `UrlSlug` | `string` | optional | URL slug |
| `WorkspaceName` | `string` | optional | owning workspace name |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `FormApplicationImageDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `Url` | `string` | optional | image URL |
| `Name` | `string` | optional | image name |
| `Value` | `string` | optional | image value (e.g. base64) |
| `Source` | `FormApplicationImageSource` (enum) | required | image source kind |

### `FormNextStepDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | next step id |
| `OrderId` | `number` | required | step order |
| `Name` | `string` | optional | step name |

### `FormFileDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required | file id |
| `StepId` | `string (uuid)` | required | step the file belongs to |
| `Name` | `string` | optional | file name |
| `Type` | `string` | optional | content type |
| `Size` | `number` | optional | file size in bytes |
| `Path` | `string` | optional | storage path |
| `Hash` | `string` | optional | content hash |

### `FormAssigneeDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `StepId` | `string (uuid)` | required | step id |
| `OrderId` | `number` | required | order |
| `Type` | `FormAssigneeType` (enum) | required | assignee vs approver |
| `Users` | array of `FormUserDto` | optional (defaults to empty) | assigned users |

### `FormUserDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `UserId` | `string (uuid)` | required | user id |
| `FirstName` | `string` | optional | first name |
| `LastName` | `string` | optional | last name |

### `FormSubmitterDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `SubmissionDate` | `string (date-time, ISO-8601)` | required | submission timestamp |
| `User` | `FormUserDto` | optional | submitting user |

### `FormChainDataModel`

| wire field | type | req/opt | description |
|---|---|---|---|
| `FormId` | `string (uuid)` | required | form instance id |
| `FormTemplateId` | `string (uuid)` | required | template id |
| `Data` | `object` | optional | FE-defined chain data |
| `CreatedOn` | `string (date-time, ISO-8601)` | required | created timestamp |
| `UpdatedOn` | `string (date-time, ISO-8601)` | required | updated timestamp |

### `LaunchFlowPayload` (request — launch flow from a form)

| wire field | type | req/opt | description |
|---|---|---|---|
| `connectionId` | `string` | optional | client/connection id (e.g. SignalR connection for async result delivery) |
| `flowTemplateId` | `string (uuid)` | required | flow template to launch |

> Note: wire names are camelCase here (`System.Text.Json` `[JsonPropertyName]` on this DTO).

### `DataStoreInsertRowsRequestDto` (request — add rows)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Rows` | array of `object` (map: `string` → value) | required (defaults to empty) | rows to insert; keys are column display names |

### `DataStoreUpdateRowsRequestDto` (request — update the rows a filter matches)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Values` | `object` (map: `string` → value) | required (defaults to empty) | columns to set (display-name keys) |
| `Filter` | `DataStoreFilterGroupDto` | nullable in the DTO, required in practice | selects the rows to update — see [09 → the filter tree](10-datastore.md#the-filter-tree) |

### `DataStoreDeleteRowsRequestDto` (request — delete rows)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Filter` | `DataStoreFilterGroupDto` | nullable in the DTO, required in practice | selects the rows to delete — see [09 → the filter tree](10-datastore.md#the-filter-tree) |

### `GetSigningEnvelopeDto` (response — signing envelope)

Inherits `OwnershipAuditDto`; its `firstName`, `lastName`, `createdBy` and `updatedBy` stay empty.

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required | envelope id |
| `FormId` | `string (uuid)` | required | form instance the send bound it to; empty uuid while `DRAFT` |
| `FormTemplateId` | `string (uuid)` | required | form template |
| `ElementId` | `string` | optional | signing element id |
| `Name` | `string` | optional | document name |
| `Status` | `SigningEffectiveStatus` (string) | required | effective status, `EXPIRED` included — read this, never infer it from the dates |
| `OrderMode` | `SigningOrderMode` (string) | required | how the preparer described the order; round-trips for the setup UI |
| `CurrentOrderIndex` | `number` | required | the order group whose turn it is |
| `RowVersion` | `number` | required | echo on the draft save and the send |
| `Document` | `SigningDocumentDto` | optional | the document |
| `Spots` | array of `SigningSpotDto` | required (defaults to empty) | every spot |
| `Parties` | array of `SigningPartyDto` | required (defaults to empty) | every signer |
| `SentOn` | `string (date-time, ISO-8601)` | optional | send time |
| `ExpiresOn` | `string (date-time, ISO-8601)` | optional | after it, a live envelope reads `EXPIRED` |
| `CompletedOn` | `string (date-time, ISO-8601)` | optional | completion time |
| *(+ `OwnershipAuditDto` fields)* | | | see below |

### `SigningDocumentDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | required | document id — do not assume it equals the envelope id |
| `Name` | `string` | optional | document name |
| `PageCount` | `number` | required | pages in the PDF |
| `OriginalHash` | `string` | optional | SHA-256, lowercase hex, of the original upload |
| `CurrentHash` | `string` | optional | SHA-256, lowercase hex, of the current rendition |
| `SignedFileId` | `string (uuid)` | optional | file id of the signed PDF; `null` until `COMPLETED` |
| `HasSignedArtifact` | `boolean` | required | whether `version=signed` can be downloaded |

### `SigningSpotDto`

Coordinates are normalised 0..1 of the displayed page, top-left origin. Clients must ignore unknown `Type` values and unknown extra fields.

| wire field | type | req/opt | description |
|---|---|---|---|
| `SpotId` | `string (uuid)` | required | client-generated, unique in the envelope |
| `PartyId` | `string (uuid)` | required | the party who fills the spot |
| `Page` | `number` | required | 1-based page |
| `X`, `Y` | `number` | required | top-left corner, ≥ 0 |
| `W`, `H` | `number` | required | size, > 0; `X + W` and `Y + H` at most 1 |
| `Type` | `SigningSpotType` (string) | optional, default `SIGNATURE` | what the spot collects |
| `Required` | `boolean` | optional, default `true` | must be filled for the envelope to complete |
| `Value` | `string` | optional, max 256 | `TEXT`: the preparer's text, kept on a draft save for `TEXT` only; auto-filled types: the value stamped when the party signs |
| `Label` | `string` | optional, max 128 | the preparer's name for the spot; shown by the setup UI, never stamped |
| `SignedOn` | `string (date-time, ISO-8601)` | read-only | when the spot was filled |

### `SigningPartyDto`

On an in-app draft save each party carries exactly one of `UserId` / `Email`, and only `UserId` is accepted. A public form's one signer may have an `Email`, or no identity at all.

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional on write | the id spots reference in `PartyId`; the server assigns one when empty |
| `UserId` | `string (uuid)` | optional | the signer's user (a member of the envelope's workspace) |
| `Email` | `string` | optional, max 256 | a signer by e-mail (public form) |
| `FirstName`, `LastName` | `string` | optional, max 128 each | the signer's names |
| `OrderIndex` | `number` | required, ≥ 0 | signing step; equal values sign in parallel, the lowest first |
| `Status` | `SigningPartyStatus` (string) | read-only | |
| `SignedOn` | `string (date-time, ISO-8601)` | read-only | |
| `LastNotifiedOn` | `string (date-time, ISO-8601)` | read-only | last sign-request e-mail |
| `DeclineReason` | `string` | read-only | the reason the signer gave when declining |

### `SetSigningEnvelopeDto` (request — draft save)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Name` | `string` | optional, max 256 | blank keeps the current name |
| `OrderMode` | `SigningOrderMode` (string) | optional, default `NONE` | |
| `RowVersion` | `number` | required | from the last read |
| `Spots` | array of `SigningSpotDto` | required (defaults to empty), max 1000 | replaces every spot |
| `Parties` | array of `SigningPartyDto` | required (defaults to empty), max 50 | replaces every party; ignored on a public form |

### `SigningSessionDto` (response — the signer's view)

Carries the caller's own party and spots only, never another signer's.

| wire field | type | req/opt | description |
|---|---|---|---|
| `EnvelopeId` | `string (uuid)` | required | |
| `DocumentName` | `string` | optional | |
| `PageCount` | `number` | required | |
| `Status` | `SigningEffectiveStatus` (string) | required | |
| `Party` | `SigningPartyDto` | required | the caller's party |
| `OwnSpots` | array of `SigningSpotDto` | required (defaults to empty) | the caller's spots |
| `SignedPartyCount` | `number` | required | parties that signed |
| `TotalPartyCount` | `number` | required | all parties |
| `IsMyTurn` | `boolean` | required | the caller's group is the current one and the envelope is `SENT` or `IN_PROGRESS` |

### `SubmitSignatureDto` (request — sign)

| wire field | type | req/opt | description |
|---|---|---|---|
| `SignaturePngBase64` | `string` | required | the signature as a base64 PNG, no `data:` prefix; applied to every spot of the caller |
| `TimeZone` | `string` | optional | the signer's IANA time zone (for example `Europe/Bucharest`) for `DATE_SIGNED` spots; unknown ids fall back to UTC |

### `SigningDeclineDto` (request — decline)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Reason` | `string` | optional | returned as the party's `DeclineReason` |

### `CreateSigningEnvelopeFromTemplateDto` (request — in-app envelope of the designer's document)

| wire field | type | req/opt | description |
|---|---|---|---|
| `FormTemplateId` | `string (uuid)` | required | form template |
| `ElementId` | `string` | required, max 64 | signing element id |
| `FormId` | `string (uuid)` | optional | a submission being shown: its stored element is used instead of the template's |

### `CreatePublicSigningEnvelopeFromTemplateDto` (request — public envelope of the designer's document)

| wire field | type | req/opt | description |
|---|---|---|---|
| `FormTemplateId` | `string (uuid)` | required | form template |
| `WorkspaceId` | `string (uuid)` | required | workspace that owns the template |
| `ElementId` | `string` | required, max 64 | signing element id |
| `FirstName`, `LastName` | `string` | optional, max 128 each | the signer |
| `Email` | `string` | optional, max 256 | a valid address when given |

### `PublicSigningEnvelopeDto` (response — public create)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Envelope` | `GetSigningEnvelopeDto` | required | the new `DRAFT` |
| `AccessToken` | `string` | required | send as `x-signing-token`; returned only here and stored hashed, so a lost token cannot be recovered |

### `SigningTemplateDocumentDto` (response — designer's document upload)

Keep `{ fileId, name }` in the signing element's `document` setting.

| wire field | type | req/opt | description |
|---|---|---|---|
| `FileId` | `string (uuid)` | required | stored file id |
| `Name` | `string` | optional | document name |
| `PageCount` | `number` | required | pages in the PDF |

### `SigningConflictResponse` (`409` body of the signing endpoints)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Errors` | array of `ApiErrorResponse` | required | why the command was refused |
| `State` | `GetSigningEnvelopeDto` or `SigningSessionDto` | optional | the current state — the session for `my-session` commands, the envelope otherwise |

### `CustomUrlDto`

| wire field | type | req/opt | description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | custom URL id |
| `WorkspaceId` | `string (uuid)` | optional | owning workspace |
| `EntityId` | `string (uuid)` | optional | linked entity id |
| `EntityType` | `CustomUrlEntityType` (enum) | optional | linked entity kind |
| `Type` | `CustomUrlType` (enum) | optional | URL type |
| `Url` | `string` | optional | full URL |
| `TinyUrl` | `string` | optional | shortened URL |
| `CreatedOn` | `string (date-time, ISO-8601)` | optional | created timestamp |
| `UpdatedOn` | `string (date-time, ISO-8601)` | optional | updated timestamp |
| `CreatedById` | `string (uuid)` | optional | creator id |
| `UpdatedById` | `string (uuid)` | optional | updater id |

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

## Enums

### `FormStage`
| name | value |
|---|---|
| `NONE` | 0 |
| `PENDING` | 1 |
| `COMPLETED` | 2 |

### `FormChain`
| name | value | meaning |
|---|---|---|
| `None` | 1 | form is not part of a chain |
| `Entry` | 2 | form is the start of a chain |
| `Step` | 3 | form is a step within a chain |

### `FormType`
| name | value |
|---|---|
| `UserTask` | 0 |
| `General` | 1 |

### `FormStatus`
| name | value |
|---|---|
| `DRAFT` | 0 |
| `PUBLISHED` | 1 |

### `FormAssigneeType`
| name | value |
|---|---|
| `ASSIGNEE` | 1 |
| `APPROVER` | 2 |

### `FormApplicationType`
| name | value |
|---|---|
| `ALL` | 1 |
| `DASHBOARD` | 2 |
| `MENU` | 3 |

### `FormApplicationState`
| name | value |
|---|---|
| `ALL` | 0 |
| `DISABLED` | 1 |
| `ENABLED` | 2 |

### `FormApplicationImageSource`
| name | value |
|---|---|
| `ALL` | 1 |
| `BASE64` | 2 |
| `URL` | 3 |

### `CustomUrlType`
| name | value |
|---|---|
| `Master` | 1 |
| `Workspace` | 2 |
| `Entity` | 3 |

### `CustomUrlEntityType`
| name | value |
|---|---|
| `None` | 0 |
| `Form` | 1 |
| `Webhook` | 2 |

The signing enums travel as their **names** (strings), not numbers.

### `SigningEffectiveStatus`
| name | meaning |
|---|---|
| `DRAFT` | being prepared; spots and parties editable |
| `SENT` | sent, nobody has signed yet |
| `IN_PROGRESS` | at least one party signed |
| `COMPLETED` | every party signed; the signed PDF exists |
| `DECLINED` | a signer declined; the envelope stopped circulating |
| `VOIDED` | withdrawn because its form instance or template was deleted |
| `EXPIRED` | derived at read time: `ExpiresOn` passed while `SENT` or `IN_PROGRESS` |

### `SigningPartyStatus`
| name | meaning |
|---|---|
| `PENDING` | not asked yet |
| `NOTIFIED` | sent a sign request |
| `VIEWED` | opened their session |
| `SIGNED` | signed |
| `DECLINED` | declined |

### `SigningOrderMode`
| name |
|---|
| `NONE` |
| `SEQUENTIAL` |
| `MIXED` |

The order itself is each party's `OrderIndex`; the mode only restores the editor the preparer used.

### `SigningSpotType` (accepted values)
| name | filled with |
|---|---|
| `SIGNATURE` | the signature image |
| `PRINTED_NAME` | the signer's full name |
| `FIRST_NAME` | the signer's first name |
| `LAST_NAME` | the signer's last name |
| `DATE_SIGNED` | the signing date, in the signer's `TimeZone` |
| `TEXT` | the preparer's `Value`, as typed |

A draft save refuses any other name with `715`.
