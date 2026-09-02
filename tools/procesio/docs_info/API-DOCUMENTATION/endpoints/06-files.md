# Files endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Files/FileController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Files/FileConnectorActionController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Files/FileScheduleController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Files/FileTestActionController.cs`

The **Files** domain handles the binary content behind PROCESIO *file-type variables*. When a process instance, a connector/test action run, or a schedule has a variable of the platform "File" data type, the variable's JSON value holds file *metadata* (id, name, path, type, size, hash) but not the bytes. These endpoints move the actual bytes in and out of blob storage:

- **Upload** (`POST .../upload/...`) accepts one file via `multipart/form-data`, streams it into storage, and back-fills the matching file model in the target variable's value (path / type / size / hash). The client picks the `fileId` (a GUID it generates) and passes it in a header; the same id is echoed in the `200 OK` body so the client can correlate.
- **Download** (`GET .../download/...`) streams a single file back to the caller. Although the controllers declare `[Produces("application/json")]` at class level, the success path returns an ASP.NET `FileResult` (raw binary stream with `Content-Type` and a download `FileName`), **not** JSON. JSON is only produced on the error path.

All four controllers are **public**: none carry `[SecureInternalController]` and none use an `internal/` route. Every method requires a **Bearer JWT** (or API key via `key`+`value` headers where the gateway supports it) — there are no `[AllowAnonymous]` methods. All four controllers resolve to the same route prefix `api/File` (in `FileController` the `[controller]` token expands to `File`; the other three set `[Route("api/File")]` explicitly), so the sub-routes (`upload/flow`, `download`, `upload/action-event`, `upload/schedule`, `upload/testAction`, `download/schedule`, `download/testAction`, `download/action-event`) are what disambiguate them.

A notable consequence of the shared prefix: `FileController` exposes `GET api/File/download` and `FileConnectorActionController` exposes `GET api/File/download/action-event` — different routes, do not confuse them.

Permission strings below are derived from the controller-level `[AuthorizationEntity(...)]` + method-level `[AuthorizationAction(...)]`. Several `SwaggerOperation` summaries say `.Write` while the actual attribute is `AuthorizationActionType.Create` (value 4); both are reported and **the attribute is authoritative**.

### Common upload mechanics (applies to every `upload/...` endpoint)

- **Body content type:** `multipart/form-data`.
- **Body:** a single form-file part named **`package`** (`IFormFile`). This is the file bytes; the part's own filename and content-type are used as the stored file's name and MIME type.
- **All other inputs are sent as request headers**, not form fields (the action methods bind them with `[FromHeader]`). Header names match the parameter names exactly and are case-insensitive, e.g. `flowInstanceId`, `variableName`, `fileId`, `connectorActionId`, `variableId`, `scheduleId`, `testActionId`, `connectionId`.
- **`fileId` semantics:** the client supplies the file's GUID. For a *list* file-variable, the `fileId` must match the `id` of one element already present in the variable's JSON value (the upload back-fills that element). For a single (non-list) file-variable it identifies the one file model. On success the endpoint returns this same `fileId` in the body so the upload can be correlated to the metadata.
- **Success body:** `200 OK` with the `fileId` as a bare JSON string (uuid).
- **Failure body:** `400 Bad Request` with either an array of `ApiErrorResponse` (validation/upload errors, e.g. missing variable value, variable not found, file model mismatch) or, on an unhandled exception, the raw exception message string.

### Common download mechanics (applies to every `download/...` endpoint)

- **No request body.** Inputs are passed as request headers (`uploadFilePath`, `variableId`, etc.) plus, for `FileController`, one query param.
- **`uploadFilePath`** is the storage path of the file (the `path` property stored on the file model after upload). It is the primary key for retrieval.
- **Success response:** raw file stream. The response `Content-Type` is the file's stored MIME type and the response carries a download `FileName` (i.e. a `Content-Disposition` with the original name). This is **not** JSON despite the class-level `[Produces("application/json")]`.
- **Failure response:** `400 Bad Request` with an array of `ApiErrorResponse`, or the raw exception message string on an unhandled exception.

---

## Endpoints

### FileController (`api/File`)

Entity: `ProcessInstance`. Handles files attached to **running process instances** (flow execution input/output file variables).

#### `POST api/File/upload/flow`

- **Operation:** `Upload` — upload one file for a file-type variable of a running flow instance; streams the bytes to storage and updates that variable's file metadata.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Create` (Swagger summary says "ProcessInstance.Write"; attribute is `Create`).
- **Special headers** (`[FromHeader]`):
  - `flowInstanceId` — `string (uuid)`, required — id of the running flow instance (bound to `UploadFileHeaders.Id`).
  - `flowTemplateId` — `string (uuid)`, required — id of the flow template the instance was launched from.
  - `variableName` — `string`, required — name of the target file variable on the flow.
  - `fileId` — `string (uuid)`, required — client-chosen id of the file (see "`fileId` semantics" above). Echoed back on success.
- **Request body** (`multipart/form-data`): single file part
  - `package` — file (`IFormFile`), required — the file content to upload. Part filename → stored name; part content-type → stored MIME type.
- **Responses:**
  - `200 OK` → `string (uuid)` — the `fileId` that was uploaded.
  - `400 Bad Request` → array of `ApiErrorResponse` (upload/validation errors) **or** a raw error-message string (on exception).
- **Notes:** Server builds an `UploadFileHeaders` from the headers and calls `IFileManager.UploadFlowFile`. Updates the instance variable's file model (path/type/size/hash) for the matching `fileId`.

#### `GET api/File/download`

- **Operation:** `Download` — download a single file belonging to a flow instance (or, when `isArchived=true`, from archived storage).
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read`.
- **Query params:**
  - `isArchived` — `boolean`, optional, default `false` — when `true`, fetch from the archived-files store.
- **Special headers** (`[FromHeader]`):
  - `uploadFilePath` — `string`, required — storage path of the file to retrieve.
  - `variableId` — `string (uuid)`, optional — id of the file variable the file belongs to.
  - `instanceId` — `string (uuid)`, optional — id of the flow instance.
  - `flowTemplateId` — `string (uuid)`, optional — id of the flow template.
- **Responses:**
  - `200 OK` → binary file stream; `Content-Type` = stored file MIME type, response carries the original `FileName`. (Built from `FileInformation`.)
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Calls `IFileManager.DownloadFile(variableId, instanceId, flowTemplateId, uploadFilePath, isArchived)`. The success branch returns `File(fileInfo.FileData.FileStream, fileInfo.FileData.FileType, fileInfo.FileName)`.

---

### FileConnectorActionController (`api/File`)

Entity: `ProcessDesigner`. Handles files used when running a **connector action** standalone in the designer (action-event preview).

#### `POST api/File/upload/action-event`

- **Operation:** `UploadConnectorAction` — upload one file for a file-type variable of a connector action being tested/previewed in the designer.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger summary: "ProcessDesigner.Update"). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `connectorActionId` — `string (uuid)`, required — id of the connector action (bound to `UploadTestFileHeaders.Id`).
  - `variableId` — `string (uuid)`, required — id of the target file variable.
  - `fileId` — `string (uuid)`, required — client-chosen file id; echoed back on success.
  - `connectionId` — `string`, required — identifier of the live designer connection/session for this preview run.
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the file content.
- **Responses:**
  - `200 OK` → `string (uuid)` — the `fileId`.
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Builds `UploadTestFileHeaders` and calls `IFileManager.UploadConnectorActionFile(package, headers, connectionId)`.

#### `GET api/File/download/action-event`

- **Operation:** `Download` — download a single file produced/used by a connector-action preview.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger summary: "ProcessDesigner.Read"). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `uploadFilePath` — `string`, required — storage path of the file.
  - `variableId` — `string (uuid)`, optional — id of the file variable.
- **Responses:**
  - `200 OK` → binary file stream (`Content-Type` = stored MIME type, original `FileName`).
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Calls `IFileManager.DownloadConnectorFileData(uploadFilePath, variableId)`.

---

### FileScheduleController (`api/File`)

Entity: `Schedule`. Handles files attached to **schedules** (scheduled process launches whose input variables include files).

#### `POST api/File/upload/schedule`

- **Operation:** `UploadSchedule` — upload one file for a file-type variable of a schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Create` (Swagger summary says "Schedule.Write"; attribute is `Create`). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `scheduleId` — `string (uuid)`, required — id of the schedule (bound to `UploadTestFileHeaders.Id`).
  - `variableId` — `string (uuid)`, required — id of the target file variable.
  - `fileId` — `string (uuid)`, required — client-chosen file id; echoed back on success.
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the file content.
- **Responses:**
  - `200 OK` → `string (uuid)` — the `fileId`.
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Builds `UploadTestFileHeaders` and calls `IFileManager.UploadScheduleFile(package, headers)`. (No `connectionId` for schedules.)

#### `GET api/File/download/schedule`

- **Operation:** `Download` — download a single file attached to a schedule.
- **Auth:** Bearer JWT — **Permission:** `Schedule:Read` (Swagger summary: "Schedule.Read"). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `uploadFilePath` — `string`, required — storage path of the file.
  - `variableId` — `string (uuid)`, optional — id of the file variable.
  - `flowTemplateId` — `string (uuid)`, optional — id of the flow template the schedule launches.
- **Responses:**
  - `200 OK` → binary file stream (`Content-Type` = stored MIME type, original `FileName`).
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Calls `IFileManager.DownloadScheduleFileData(uploadFilePath, variableId, flowTemplateId)`.

---

### FileTestActionController (`api/File`)

Entity: `ProcessDesigner`. Handles files used when running a single **test action** in the designer (standalone action test, distinct from connector-action preview by route).

#### `POST api/File/upload/testAction`

- **Operation:** `UploadTestAction` — upload one file for a file-type variable of a test action.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Update` (Swagger summary: "ProcessDesigner.Update"). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `testActionId` — `string (uuid)`, required — id of the test action (bound to `UploadTestFileHeaders.Id`).
  - `variableId` — `string (uuid)`, required — id of the target file variable.
  - `fileId` — `string (uuid)`, required — client-chosen file id; echoed back on success.
  - `connectionId` — `string`, required — identifier of the live designer connection/session for this test run.
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the file content.
- **Responses:**
  - `200 OK` → `string (uuid)` — the `fileId`.
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Builds `UploadTestFileHeaders` and calls `IFileManager.UploadTestActionFile(package, headers, connectionId)`.

#### `GET api/File/download/testAction`

- **Operation:** `Download` — download a single file produced/used by a test-action run.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read` (Swagger summary: "ProcessDesigner.Read"). Swagger tag: `File`.
- **Special headers** (`[FromHeader]`):
  - `uploadFilePath` — `string`, required — storage path of the file.
  - `variableId` — `string (uuid)`, optional — id of the file variable.
- **Responses:**
  - `200 OK` → binary file stream (`Content-Type` = stored MIME type, original `FileName`).
  - `400 Bad Request` → array of `ApiErrorResponse` **or** raw error-message string.
- **Notes:** Calls `IFileManager.DownloadTestFileData(uploadFilePath, variableId)`.

---

## Shared DTOs

### Upload — header binding objects (informational)

These are **not** JSON bodies. The server constructs them internally from the `[FromHeader]` values listed per endpoint above; the file bytes always come from the `multipart/form-data` `package` part. They are documented here so the field-to-header mapping is explicit.

#### `BaseUploadFileHeaders`
Base class for upload header binders.
- `Id` — `string (uuid)` — the owning entity id. Mapped from a different header per endpoint: `flowInstanceId` (flow), `connectorActionId` (connector action), `scheduleId` (schedule), `testActionId` (test action).
- `FlowTemplateId` — `string (uuid)` — flow template id. Only set by the flow upload (from header `flowTemplateId`); left default (all-zeros GUID) by the test/connector/schedule uploads.
- `FileId` — `string (uuid)` — client-chosen file id (from header `fileId`).

#### `UploadFileHeaders : BaseUploadFileHeaders`
Used by `POST api/File/upload/flow`.
- inherits `Id`, `FlowTemplateId`, `FileId`.
- `VariableName` — `string` — target file variable name (from header `variableName`).

#### `UploadTestFileHeaders : BaseUploadFileHeaders`
Used by the connector-action, schedule, and test-action uploads.
- inherits `Id`, `FlowTemplateId` (unused / default), `FileId`.
- `VariableId` — `string (uuid)` — target file variable id (from header `variableId`).

### Download — success payload (internal transport)

Downloads do not serialize a DTO to the client; they stream the file. The following internal type is what the manager returns and from which the streamed `FileResult` is built — included for reference.

#### `FileInformation`
- `FileData` — `object (StorageObject)` — the storage object. Relevant fields used to build the response: `FileStream` (the byte stream → response body), `FileType` (MIME string → response `Content-Type`), `FilePath` (storage path). `StorageObject` is defined in the external `ExternalAdapters.Storage.Models` adapter (not in this repo) — see "DTO not resolved" below.
- `FileId` — `string (uuid)` — file id.
- `FileName` — `string` — original file name → response download filename.
- `FileSize` — `number (long)` — size in bytes.
- `FileHash` — `string` — content hash.
- `FileVariable` — `object (IFlowVariable)` — the associated flow variable (internal).
- `Value` — `object` — the source value (flow instance default value / test action attribute value / schedule input value) the file metadata is merged into.
- `CurrentFileModel` — `object (JObject)` — the JSON file model element currently being processed.

### Error payloads

#### `ApiErrorResponse`
Each element of the `400 Bad Request` error array.
- `StatusCode` — `number (int)` — the integer value of the internal `ErrorCodes` enum for this error.
- `Value` — `object` (typically `string`) — human-readable message resolved from the file-upload error map (may be empty if unmapped).
- `Target` — `object` (typically `string`) — the offending field/variable name (e.g. the variable name with a missing value).

> Note: on an *unhandled* exception the upload/download endpoints return the raw `ex.Message` **string** as the `400` body instead of an `ApiErrorResponse` array. Clients should tolerate both shapes for `400`.

### Enums (reference)

#### `AuthorizationActionType`
`None=1`, `Read=2`, `Update=3`, `Create=4`, `Delete=5`, `Admin=6`. (Used in permission strings above; not sent on the wire.)

#### `AuthorizationEntityType` (relevant values)
`ProcessDesigner=3`, `ProcessInstance=4`, `Schedule=10`. (Controller-level entity; not sent on the wire.)

### Unresolved

- **`StorageObject`** (`ExternalAdapters.Storage.Models.StorageObject`) — referenced by `FileInformation.FileData` but defined in an external adapter package, not in the `Web-Api` repo. Only the fields used by these endpoints are known from usage: `FileStream` (stream), `FileType` (string MIME), `FilePath` (string). DTO not resolved in full.
