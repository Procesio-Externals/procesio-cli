# Forms & Documents endpoints

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
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/DocumentTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/ProcessInstanceDocumentsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Documents/ProcessTemplateDocumentsController.cs`

This domain covers PROCESIO **forms** and **documents**. A *form template* (`FormTemplate`) defines a form's layout, assignees and status; a *form instance* (`FormInstance`, exposed as "form") is a filled-in copy of a template that lives inside a process/flow run. *Form applications* group form templates into dashboards/menus. *Form chains* link a sequence of form instances that originate from the same template. *Form processes* let a public (anonymous) form front-end fetch/launch the backing flow and read its variables. *File-form* endpoints handle file upload/download tied to form instances and flow instances. *Form data-store* endpoints let a form read/write rows in a backing DataStore. *Document templates* are reusable rich-text/HTML templates with placeholder variables used to render documents in processes.

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
  - `awaitingAction` — `boolean`, required — when `true`, only forms awaiting the user's action.
- **Responses:**
  - `200 OK` → paginated list of `GetFormDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

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

#### `GET api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `GetRows` — Get a paginated set of rows from the data store.
- **Auth:** Anonymous — **Permission:** None
- **Query params:**
  - `pageNumber` — `number`, required — 1-based page index.
  - `pageItemCount` — `number`, required — page size.
- **Special headers:**
  - `formTemplateWorkspaceId` `[FromHeader]` — `string (uuid)`, required.
  - `formTemplateId` `[FromHeader]` — `string (uuid)`, required.
  - `formInstanceId` `[FromHeader]` — `string (uuid)`, optional.
- **Responses:**
  - `200 OK` → paginated rows (manager-defined shape)
  - error → standardized error response (`this.ErrorResponse(result)`)

#### `POST api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `AddRows` — Add one or more rows to the data store.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreRowsDto`
- **Responses:**
  - `200 OK` → result value (manager-defined)
  - error → standardized error response

#### `PUT api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `UpdateRow` — Update a single row.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreUpdateRowRequestDto`
- **Responses:**
  - `200 OK` → result value
  - error → standardized error response

#### `DELETE api/Form/dataStore/{dataStoreId}/rows`

- **Operation:** `DeleteRows` — Delete one or more rows.
- **Auth:** Anonymous — **Permission:** None
- **Special headers:** `formTemplateWorkspaceId` (req), `formTemplateId` (req), `formInstanceId` (opt) — all `[FromHeader]`, `string (uuid)`.
- **Request body** (`application/json`): `DataStoreRowsPrimaryKeysDto`
- **Responses:**
  - `200 OK` → result value
  - error → standardized error response

---

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
- `GET|POST|PUT|DELETE api/Form/dataStore/{dataStoreId}/rows` (all four `FormDataStore` endpoints).

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
| `SubmissionDate` | `string (date-time, ISO-8601)` | required | when the form was submitted |
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

### `DataStoreRowsDto` (request — add rows)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Rows` | array of `object` (map: `string` → value) | required (defaults to empty) | rows to insert; keys are column display names |

### `DataStoreUpdateRowRequestDto` (request — update one row)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Keys` | `object` (map: `string` → value) | required (defaults to empty) | PK columns identifying the row (display-name keys) |
| `Values` | `object` (map: `string` → value) | required (defaults to empty) | columns to update (display-name keys) |

### `DataStoreRowsPrimaryKeysDto` (request — delete rows)

| wire field | type | req/opt | description |
|---|---|---|---|
| `Keys` | array of `object` (map: `string` → value) | required (defaults to empty) | one map of PK columns per row to delete (display-name keys) |

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
