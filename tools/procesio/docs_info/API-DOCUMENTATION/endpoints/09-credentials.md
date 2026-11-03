# Credentials endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/CredentialsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/CredentialsAuthController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/CredentialsTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/ProcesioAdmin/CredentialsTemplateController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/ProcessInstanceCredentialsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Credentials/ProcessTemplateCredentialsController.cs`

The Credentials domain is PROCESIO's **credentials vault**: the store of secrets and connection details (FTP servers, OAuth2 apps, API keys, etc.) that process actions use to reach third-party systems. A **credentials template** (`CredentialsTemplate`) defines the shape of a connection type — its list of input properties (host, username, password, OAuth client id/secret, …). A **credentials instance** (`Credentials`) is a saved set of values for one template, owned by a workspace. Actions in a process reference a credentials instance by its `gid`.

This domain covers:
- CRUD over credentials instances (`CredentialsController`).
- A "test connection" probe that validates values before saving.
- File upload for private-key / certificate auth, and the **OAuth2 authorization flow** (build authorize URL → external consent → callback → access/refresh tokens stored server-side) in `CredentialsAuthController`.
- Read access to credentials templates and their "verbs" (`CredentialsTemplateController`).
- ProcesioAdmin-only template authoring and predefined secure-data seeding (`ProcesioAdmin/CredentialsTemplateController`) — hidden from Swagger.
- Restricted/base read variants used internally by the Designer and running process instances (`ProcessTemplateCredentialsController`, `ProcessInstanceCredentialsController`).

**Routing note:** all six controllers share `[Route("api/Credentials")]`. They are separate C# classes purely to attach different `[AuthorizationEntity(...)]` values (and therefore different permission checks) to different subroutes. The `OAuthCallback` action overrides the base route with an absolute path (`/api/CredentialsAuth/...`).

**Secret handling:** secret values are submitted as ordinary fields inside the `properties` array of a `CredentialsDto` (`POST`/`PUT api/Credentials`) — each property is `{ id, value }` where `value` is free-form (`object`). The server encrypts/stores them; reads of an instance return property metadata but the vault does not echo plaintext secrets back in the restricted/base read variants. OAuth2 tokens are never sent by the client: the client only forwards the `code`/`state` from the provider redirect, and the server exchanges them for tokens and persists them. Certificates/private keys are uploaded as `multipart/form-data` files.

All routes are served under the Web-Api gateway base URL. Versioning is via the optional `x-version` header (default `1.19`); do not add a version path segment.

---

## Endpoints

### CredentialsController — `[AuthorizationEntity(Credentials)]`

Permission strings below are `Credentials:{Action}`. (The Swagger summaries say "Credentials.Write" for the create action; this maps to the `Create` action type.)

---

### `POST api/Credentials/test`

- **Operation:** `TestConfiguration` — validate a credentials configuration by attempting a live connection, without saving.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Request body** (`application/json`): `CredentialsDto`
- **Responses:**
  - `200 OK` → test result object (server-defined; the raw result of the connection probe, shape not strongly typed)
- **Notes:** Performs an outbound connection attempt to the third-party system using the supplied property values. Use before `POST api/Credentials` to confirm secrets are correct. For connection types needing a certificate file, first call `POST api/Credentials/upload/test` and reference the returned path.

---

### `GET api/Credentials`

- **Operation:** `GetConfigurations` — list credentials instances for the current workspace, paginated, with optional name search.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Query params:**
  - `pageNumber` — `number`, optional (defaults to page 1 server-side; values ≤ 1 are coerced to 1) — 1-based page index.
  - `pageItemCount` — `number`, optional (defaults to 0 = unbounded server-side) — page size.
  - `searchName` — `string`, optional, default `null` — case-insensitive name filter; **ignored if trimmed length < 3 characters** (treated as no filter).
- **Responses:**
  - `200 OK` → array of `BaseCredentialsDto` (instance summaries) — exact element shape is service-defined; see Notes.
  - `400 Bad Request` → error payload when the lookup returns null.
- **Notes:** Returns instances scoped to the caller's workspace. See `Pagination` in Shared DTOs for how page params are interpreted.

---

### `GET api/Credentials/count`

- **Operation:** `CountConfigurations` — total number of credentials instances for the workspace.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Responses:**
  - `200 OK` → `number` (total count)
  - `400 Bad Request` → error payload when count < 0 (not-found path).

---

### `GET api/Credentials/list/{typeId}`

- **Operation:** `GetConfigurationsByType` — list credentials instances created from a given template, paginated, with base properties.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Path params:** `{typeId}` — `string (uuid)`, required — the credentials template id (`gtid`).
- **Query params:**
  - `pageNumber` — `number`, optional — 1-based page index.
  - `pageItemCount` — `number`, optional — page size.
- **Responses:**
  - `200 OK` → array of `BaseCredentialsDto` (base view of matching instances)
  - `400 Bad Request` → error payload when null.

---

### `GET api/Credentials/list/{typeId}/count`

- **Operation:** `CountConfigurationsByType` — number of credentials instances for a given template.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Path params:** `{typeId}` — `string (uuid)`, required — the credentials template id.
- **Responses:**
  - `200 OK` → `number` (count)
  - `400 Bad Request` → error payload when count < 0.

---

### `GET api/Credentials/{id}`

- **Operation:** `GetConfiguration` — get a single credentials instance by id (full view).
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Path params:** `{id}` — `string (uuid)`, required — credentials instance id (`gid`).
- **Responses:**
  - `200 OK` → `CredentialsDto` (instance with its `properties`)
  - `400 Bad Request` → error payload when not found.

---

### `POST api/Credentials`

- **Operation:** `StoreConfiguration` — create/store a new credentials instance (with secret values).
- **Auth:** Bearer JWT — **Permission:** `Credentials:Create`
- **SwaggerOperation Summary:** "Permission required: Credentials.Write"
- **Request body** (`application/json`): `CredentialsDto`
- **Responses:**
  - `200 OK` → `{ "id": "<uuid>" }` — `id` is the new instance's `Gid` (the server populates `Gid` during save).
  - `400 Bad Request` → composed error payload (array of credentials errors) when validation/storage fails.
- **Notes:** Secret values are carried in `properties[].value`. The server assigns the `gid`.

---

### `PUT api/Credentials`

- **Operation:** `UpdateConfiguration` — update an existing credentials instance.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Request body** (`application/json`): `CredentialsDto` (include `gid` of the instance to update).
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → composed credentials error payload when update fails.

---

### `DELETE api/Credentials/{id}`

- **Operation:** `RemoveConfiguration` — delete a credentials instance by id.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Delete`
- **SwaggerOperation Summary:** "Permission required: Credentials.Delete"
- **Path params:** `{id}` — `string (uuid)`, required — credentials instance id.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → composed credentials error payload when deletion fails (e.g. still referenced).

---

### CredentialsAuthController — `[AuthorizationEntity(Credentials)]`

Certificate/private-key file upload and the OAuth2 authorization flow. Also routed under `api/Credentials` (except the callback, which is absolute).

---

### `POST api/Credentials/upload/{credentialsId}`

- **Operation:** `Upload` — upload a certificate / private key file for an existing credentials instance (e.g. FTP private-key auth).
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Path params:** `{credentialsId}` — `string (uuid)`, required — credentials instance the file belongs to.
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the certificate/private-key file. Must be non-empty.
- **Responses:**
  - `200 OK` → `string` — the stored file path (`StorageObject.FilePath`).
  - `400 Bad Request` → error payload `FILE_NOT_FOUND` if the file is empty, or composed credentials errors on upload failure.
- **Notes:** Stores the file in object storage and associates it with the credentials instance. The returned path is the value other endpoints reference for the certificate.

---

### `POST api/Credentials/upload/test`

- **Operation:** `UploadTestConnection` — upload a certificate / private key file for a **test connection** (not yet tied to a saved instance).
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Request body** (`multipart/form-data`):
  - `package` — file (`IFormFile`), required — the certificate/private-key file. Must be non-empty.
- **Responses:**
  - `200 OK` → upload response (server-defined; typically a temporary file reference to pass into `POST api/Credentials/test`).
  - `400 Bad Request` → error payload `FILE_NOT_FOUND` if empty, or composed credentials errors.
- **Notes:** Pair with `POST api/Credentials/test` to validate a private-key connection before saving the instance.

---

### `GET api/Credentials/authorize/{id}`

- **Operation:** `GetAuthorization` — build the OAuth2 authorization URL for a credentials instance.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Path params:** `{id}` — `string (uuid)`, required — credentials instance id (an OAuth2-type credential that already has client id/secret/scopes stored).
- **Responses:**
  - `200 OK` → `AuthorizationConnection` — `{ url, headers }`; redirect the user's browser to `url` to start consent.
  - `400 Bad Request` → error body when the authorization URL could not be built.
- **Notes:** **OAuth2 step 1.** The client opens the returned `url`; the provider redirects the user back to the configured PROCESIO callback (`GET /api/CredentialsAuth/oauth2/callback`) with `code`/`state`.

---

### `POST api/Credentials/accessToken/{id}`

- **Operation:** `SaveAccessToken` — exchange an OAuth2 authorization code for tokens and persist them on the credentials instance.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Update`
- **SwaggerOperation Summary:** "Permission required: Credentials.Update"
- **Path params:** `{id}` — `string (uuid)`, required — credentials instance id.
- **Request body** (`application/json`): `AccessTokenRequestDto`
- **Responses:**
  - `200 OK` → server response of the token-save operation (service-defined).
- **Notes:** **OAuth2 step 3 (explicit variant).** Use when the front end captures `code`/`state` itself and submits them. The server performs the token exchange with the provider and stores the access/refresh tokens server-side — the client never receives the raw tokens. Compare with the anonymous callback below, which does the same exchange and then redirects.

---

### `GET /api/CredentialsAuth/oauth2/callback`

- **Operation:** `OAuthCallback` — OAuth2 provider redirect target; exchanges the code for tokens, stores them, and redirects back to the front end.
- **Auth:** Anonymous (`[AllowAnonymous]`) — **Permission:** None (`AuthorizationActionType.None`)
- **Hidden from Swagger:** yes (`[ApiExplorerSettings(IgnoreApi = true)]`)
- **Absolute route:** this method overrides the controller route and is served at `/api/CredentialsAuth/oauth2/callback` (NOT under `api/Credentials`).
- **Query params** (set by the OAuth2 provider on redirect):
  - `code` — `string`, required — the authorization code.
  - `state` — `string`, required — the opaque state value originally issued in the authorize URL (used to correlate to the credentials instance).
  - `scope` — `string`, optional — granted scopes returned by the provider (accepted but not used by the handler).
- **Responses:**
  - `302 Redirect` → redirects the browser to a front-end URL returned by the token-save service (success/failure landing page).
- **Notes:** **OAuth2 step 2→3.** This is the public callback the external provider hits directly; it requires no JWT. It builds an `AccessTokenRequestDto` from `code`+`state`, performs the token exchange, saves tokens, then `Redirect`s. The credentials instance is resolved from `state` (no `id` in the URL).

---

### CredentialsTemplateController — `[AuthorizationEntity(Credentials)]`

Read-only access to credentials templates (the connection-type definitions) and their verbs.

---

### `GET api/Credentials/types`

- **Operation:** `GetConfigurationTypes` — list all credentials template types available to the caller.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Responses:**
  - `200 OK` → array of `CredentialsTemplateDto` (templates with their `properties`)
  - `400 Bad Request` → error payload when null.

---

### `GET api/Credentials/types/{id}`

- **Operation:** `GetConfigurationType` — get one credentials template by id. Admin callers may receive an extended version of the template.
- **Auth:** Bearer JWT — **Permission:** `Credentials:Read`
- **SwaggerOperation Summary:** "Permission required: Credentials.Read"
- **Path params:** `{id}` — `string (uuid)`, required — credentials template id.
- **Responses:**
  - `200 OK` → `CredentialsTemplateDto` for normal users; `ExtendedCredentialsTemplateDto` (adds `be_id` / `be_value` backend mapping fields) for admins.
- **Notes:** The response variant depends on the caller's admin status (decided server-side); both shapes are documented in Shared DTOs.

---

### `GET api/Credentials/verbs/{templateId}`

- **Operation:** `GetCredentialsVerbs` — list the "verbs" (e.g. HTTP methods / supported operations) associated with a credentials template.
- **Auth:** Bearer JWT — **Permission:** None (`AuthorizationActionType.None` — authenticated but no specific Credentials permission)
- **SwaggerOperation Summary:** "Permission required: None"
- **Path params:** `{templateId}` — `string (uuid)`, required — credentials template id.
- **Responses:**
  - `200 OK` → array of `CredentialsVerbDto`
  - `400 Bad Request` → error payload when not found.

---

### ProcesioAdmin/CredentialsTemplateController — `[AuthorizationEntity(ProcesioAdmin)]`

Template authoring + predefined secure-data seeding. **Entire controller is `[ApiExplorerSettings(IgnoreApi = true)]` (hidden from Swagger)** and requires ProcesioAdmin-level authorization. Still reachable at runtime.

---

### `POST api/Credentials/template`

- **Operation:** `StoreCredentialTemplate` — create a new credentials template. Only a ProcesioAdmin can add a template.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes (controller-level `IgnoreApi = true`)
- **Request body** (`application/json`): `StoreCredentialsTemplateDto`
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → composed context error payload on validation/storage failure.

---

### `POST api/Credentials/template/{id}/predefined`

- **Operation:** `StorePredefinedCredentialTemplateData` — store secure data for a predefined credentials template. Only a ProcesioAdmin can add SecureData.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes (controller-level `IgnoreApi = true`)
- **Path params:** `{id}` — `string (uuid)`, required — credentials template id.
- **Special headers:** `type` `[FromHeader]` — `string`, required — the type/kind of secure data being stored.
- **Request body** (`application/json`): free-form `object` (`values`) — the secure-data values for this template; shape depends on `type`.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → composed context error payload on failure.
- **Notes:** Used to seed sensitive defaults (e.g. shared client secrets) onto a predefined/system template. Body is untyped JSON.

---

### ProcessInstanceCredentialsController — `[AuthorizationEntity(ProcessInstance)]`

A single restricted read used by running process instances (actions) to fetch the credential they need.

---

### `GET api/Credentials/{id}/restricted`

- **Operation:** `GetConfiguration` — get a credentials instance by id, base (restricted) view, for use by a process instance's actions.
- **Auth:** Bearer JWT — **Permission:** `ProcessInstance:Read`
- **SwaggerOperation Summary:** "Permission required: ProcessInstance.Read"
- **Path params:** `{id}` — `string (uuid)`, required — credentials instance id.
- **Responses:**
  - `200 OK` → `BaseCredentialsDto` (base/restricted instance view — no full property list)
  - `400 Bad Request` → error payload when not found.
- **Notes:** Permission is checked against the **ProcessInstance** entity, not Credentials — this route is intended for execution-time use where the caller holds process-instance read rights.

---

### ProcessTemplateCredentialsController — `[AuthorizationEntity(ProcessDesigner)]`

A single restricted listing used by the Process Designer when the user picks a credential for an action.

---

### `GET api/Credentials/list/{typeId}/restricted`

- **Operation:** `GetConfigurationsByType` — list credentials instances of a given template with base properties, for the Designer's credential picker.
- **Auth:** Bearer JWT — **Permission:** `ProcessDesigner:Read`
- **SwaggerOperation Summary:** "Permission required: ProcessDesigner.Read"
- **Path params:** `{typeId}` — `string (uuid)`, required — credentials template id.
- **Query params:**
  - `pageNumber` — `number`, optional — 1-based page index.
  - `pageItemCount` — `number`, optional — page size.
- **Responses:**
  - `200 OK` → array of `BaseCredentialsDto`
  - `400 Bad Request` → error payload when null.
- **Notes:** Permission is checked against the **ProcessDesigner** entity. Same underlying service call as `GET api/Credentials/list/{typeId}` but gated for Designer-read users.

---

## Shared DTOs

> Wire names are the `[JsonProperty(PropertyName=...)]` values. `Guid`→`string (uuid)`, `DateTime?`→`string (date-time, ISO-8601)`, `bool`→`boolean`, numeric→`number`, enum→`number (enum)`.

### `OwnershipAuditDto` (base audit fields, inherited by instance & template DTOs)

- `firstName` — `string`, optional — (deprecated) creator first name.
- `lastName` — `string`, optional — (deprecated) creator last name.
- `workspaceId` — `string (uuid)`, optional — owning workspace id.
- `createdBy` — `string`, optional — "FirstName LastName" of creator.
- `updatedBy` — `string`, optional — "FirstName LastName" of last updater.
- `createdById` — `string (uuid)`, optional — creator user id.
- `updatedById` — `string (uuid)`, optional — last-updater user id.
- `createdOn` — `string (date-time, ISO-8601)`, optional — creation timestamp.
- `updatedOn` — `string (date-time, ISO-8601)`, optional — last-update timestamp.

### `BaseCredentialsDto` (extends `OwnershipAuditDto`) — credentials instance summary

- `gid` — `string (uuid)`, optional (nullable) — instance id. On `POST` the server fills it in.
- `gtid` — `string (uuid)`, required — credentials template id this instance is built from.
- `gtpid` — `string (uuid)`, required — template's parent id.
- `name` — `string`, optional — instance name.
- `tname` — `string`, optional — template name.
- `type` — `string`, optional — template type.
- `status` — `boolean`, optional, default `false` — instance status flag.
- `description` — `string`, optional — free-text description.
- *(plus all `OwnershipAuditDto` fields)*

### `CredentialsDto` (extends `BaseCredentialsDto`) — full credentials instance (request body for create/update/test; response for GET by id)

- *(all `BaseCredentialsDto` + `OwnershipAuditDto` fields)*
- `properties` — array of `BaseCredentialsPropertyDto`, optional — the credential's input values (where secrets live).

### `ExtendedCredentialsDto` (extends `BaseCredentialsDto`) — admin/internal full instance view

- *(all `BaseCredentialsDto` + `OwnershipAuditDto` fields)*
- `properties` — array of `CredentialsPropertyDto`, optional — properties with full display metadata + options.

> Note: `ExtendedCredentialsDto` is defined in the DTO set but is not the declared return type of any public endpoint above; included for completeness.

### `BaseCredentialsPropertyDto` — minimal property (id + value)

- `id` — `string (uuid)`, required — property id (matches a template property).
- `value` — `object` (any JSON), optional — the value entered for this property; for secret properties this is the secret. Free-form (string/number/object).

### `BaseCredentialsPropertyDetailsDto` (extends `BaseCredentialsPropertyDto`) — property with display metadata

- `id` — `string (uuid)`, required.
- `value` — `object`, optional.
- `label` — `string`, optional — display label.
- `placeholder` — `string`, optional.
- `type` — `string`, optional — UI field type.
- `tooltip` — `string`, optional.
- `message` — `string`, optional.
- `isTest` — `boolean`, optional — whether the field participates in test-connection.
- `order` — `number`, optional — display order.
- `validations` — `object (ValidationDto)`, optional.
- `layout` — `object (LayoutDto)`, optional.
- `condition` — `object (CredentialsPropertyConditionDto)`, optional — show/hide dependency rule.
- `disabled` — `boolean`, optional.
- `pill` — `string`, optional.
- `configurations` — `object` (any JSON), optional — extra FE configuration.

### `CredentialsPropertyDto` (extends `BaseCredentialsPropertyDetailsDto`)

- *(all `BaseCredentialsPropertyDetailsDto` fields)*
- `options` — array of `CredentialsPropertyOptionDto`, optional — selectable options for dropdown-type properties.

### `ExtendedCredentialsPropertyDto` (extends `BaseCredentialsPropertyDetailsDto`) — admin/template-authoring property

- *(all `BaseCredentialsPropertyDetailsDto` fields)*
- `be_id` — `string`, optional — backend identifier mapping.
- `options` — array of `ExtendedCredentialsPropertyOptionDto`, optional.

### `CredentialsPropertyOptionDto`

- `name` — `string`, optional — option display name.
- `value` — `string (uuid)`, required — option value.

### `ExtendedCredentialsPropertyOptionDto` (extends `CredentialsPropertyOptionDto`)

- `name` — `string`, optional.
- `value` — `string (uuid)`, required.
- `be_value` — `string`, optional — backend value mapping.

### `ValidationDto`

- `isRequired` — `boolean`, optional — whether the property is required.
- `expects` — `number (enum ValidationType)`, optional — expected value format. Values: `NONE = 0`, `URI = 1`, `HOSTNAME = 2`.

### `LayoutDto`

- `columns` — `string`, optional — FE layout column spec.

### `CredentialsPropertyConditionDto`

- `dependencyId` — `string (uuid)`, required — id of the property this one depends on.
- `operator` — `string`, optional — comparison operator.
- `value` — `string (uuid)`, required — value to compare against.

### `BaseCredentialsTemplateDto` (extends `OwnershipAuditDto`) — credentials template summary

- `gid` — `string (uuid)`, required — template id.
- `pid` — `string (uuid)`, required — template parent id.
- `name` — `string`, optional — template name.
- `type` — `string`, optional — template type.
- `icon` — `string`, optional — template icon reference.
- *(plus all `OwnershipAuditDto` fields)*

### `CredentialsTemplateDto` (extends `BaseCredentialsTemplateDto`) — template with properties (standard read)

- *(all `BaseCredentialsTemplateDto` + `OwnershipAuditDto` fields)*
- `properties` — array of `CredentialsPropertyDto`, optional — the template's input field definitions.

### `ExtendedCredentialsTemplateDto` (extends `BaseCredentialsTemplateDto`) — template with backend-mapped properties (admin read)

- *(all `BaseCredentialsTemplateDto` + `OwnershipAuditDto` fields)*
- `properties` — array of `ExtendedCredentialsPropertyDto`, optional — properties including `be_id`/`be_value` backend mappings.

### `StoreCredentialsTemplateDto` — create-template request (ProcesioAdmin)

- `gid` — `string (uuid)`, optional (nullable) — template id (server-assigned if omitted).
- `pid` — `string (uuid)`, optional (nullable) — parent template id.
- `name` — `string`, optional — template name.
- `type` — `string`, optional — template type.
- `icon` — `string`, optional — icon reference.
- `properties` — array of `ExtendedCredentialsPropertyDto`, optional — the property definitions for the new template.

### `CredentialsVerbDto`

- `gid` — `string (uuid)`, required — verb/method id.
- `gtid` — `string (uuid)`, required — credentials template id the verb belongs to.
- `value` — `string`, optional — the verb value (e.g. method name).

### `AccessTokenRequestDto` (OAuth2)

- `code` — `string`, optional — OAuth2 authorization code from the provider redirect.
- `state` — `string`, optional — opaque state value correlating to the credentials instance.

### `AuthorizationConnection` (OAuth2 authorize-URL response)

- `url` — `string`, optional — the OAuth2 authorization URL the client should redirect the user to.
- `headers` — `object` (any JSON), optional — extra header parameters for the authorization request.

### `AccessTokenResponse` (OAuth2 token shape — used server-side; not a direct public response body)

- `access_token` — `string`, optional.
- `token_type` — `string`, optional.
- `expires_in` — `number`, optional (nullable) — access-token lifetime in seconds.
- `scope` — `string`, optional — granted scopes.
- `refresh_token` — `string`, optional.
- `refresh_token_expires_in` — `number`, optional (nullable) — refresh-token lifetime in seconds.

### `AccessTokenErrorResponse` (OAuth2 error shape — server-side)

- `error` — `string`, optional — error code.
- `error_description` — `string`, optional — human-readable description.
- `error_uri` — `string`, optional — link to provider docs.

### `CredentialsTableDto` (defined in domain; not a direct public response body)

- `Header` — array of `TableHeaderDto`, optional. (No `[JsonProperty]` — Newtonsoft default name `Header`.)
- `Rows` — array of `object`, optional. (default name `Rows`.)

### `TableHeaderDto` (no `[JsonProperty]` attributes → default property names)

- `Order` — `number`, required.
- `Key` — `string`, optional.
- `Type` — `string`, optional.
- `Label` — `string`, optional.
- `Placeholder` — `string`, optional.
- `Tooltip` — `string`, optional.
- `Width` — `number`, required.
- `Options` — array of `ExtendedCredentialsPropertyOptionDto`, optional.

### `Pagination` (query-param binding for list endpoints — not a body DTO)

Built from `pageNumber` + `pageItemCount` query params.
- `PageNumber` — only applied if `> 1`; otherwise stays at default `1`. (So `pageNumber=0` or `1` → page 1.)
- `PageItemCount` — only applied if `> 0`; otherwise stays at default `0` (interpreted as "all items" downstream).
- `StartIndex` (derived) = `PageItemCount * (PageNumber - 1)`.

### `ErrorPayload` (element of `400 Bad Request` error responses)

- `Code` — `number (enum ErrorCodes)` — error code (enum defined in `Domain/Enums/ErrorCodes`; e.g. `FILE_NOT_FOUND`).
- `Target` — `string`, optional (nullable) — the property/field the error refers to.

> `400` responses from create/update/delete/store endpoints are produced via `CustomErrorHelper.ComposeResponse(...)`, which wraps a list of `ErrorPayload` into a composed error object (codes resolved to messages). Exact composed envelope shape is shared across the service — see `../02-conventions.md` for the standard error response format.
