# Custom URLs & public launch URLs endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/CustomUrlMasterController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/CustomUrlWorkspaceController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/CustomUrlFormController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/CustomUrlWebhookController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/CustomUrlLaunchController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/CustomUrls/TinyUrlLaunchController.cs`

This domain manages **custom (vanity) URLs** and **tiny/short URLs** that PROCESIO maps to forms, webhooks, workspaces and a master workspace. A full custom URL is a three-segment path `{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl}` and a tiny URL is a single short token. Both forms of public URL resolve at runtime to either a **Form** (returns the form template definition so a client can render it) or a **Webhook** (forwards the incoming request — body, query, headers, files — to the webhook/process-launch service to trigger a process).

There are two distinct groups of endpoints here:

1. **Management (CRUD) endpoints** (`api/CustomUrl/...`) — authenticated, permission-protected endpoints used by the PROCESIO app to configure which vanity/tiny URL maps to a master workspace, a workspace, a form template, or a webhook.
2. **Public launch endpoints** — two catch-all controllers with `[AllowAnonymous]` that sit at the **root of the gateway** (no `api/` prefix) and act as the public entry points end users actually hit. These are the anonymous entry points for launching forms and triggering webhooks/processes.

The launch controllers' route regex `^(?!api$|internal$|health$).*` is what keeps these catch-alls from swallowing the real `api/*`, `internal/*` and `health` routes — the first path segment is rejected if it equals exactly `api`, `internal` or `health`. The management `Create`/`Update` endpoints on the master controller additionally reject those three reserved words as URL values.

---

## Endpoints

### CustomUrlMasterController — `api/CustomUrl/MasterWorkspace`

Controller-level: `[Route("api/CustomUrl/MasterWorkspace")]`, `[Consumes("application/json")]`, `[Produces("application/json")]`, `[AuthorizationEntity(MasterWorkspace)]`. All endpoints require Bearer JWT.

#### `GET api/CustomUrl/MasterWorkspace`

- **Operation:** `Get` — read the custom URL configured for the caller's master workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (Summary: "Permission required: MasterWorkspace.Read")
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Resolves the master-workspace custom URL for the current user/context (no body or params).

#### `POST api/CustomUrl/MasterWorkspace`

- **Operation:** `Create` — create the master-workspace vanity URL segment.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Create` (Summary: "Permission required: MasterWorkspace.Write")
- **Request body** (`application/json`): a bare JSON string (the URL value), bound `[FromBody] string url`.
  - body — `string`, required — the master URL segment. Sent as a raw JSON string, e.g. `"acme"`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → `"The provided URL is reserved and cannot be used."` (plain string) if the trimmed lower-cased value equals `api`, `internal` or `health`; otherwise array of `ApiErrorResponse`
- **Notes:** Server builds a `CustomUrlDto { Type = Master, Url = url }` internally. Reserved-word check is case-insensitive and trims whitespace.

#### `PUT api/CustomUrl/MasterWorkspace`

- **Operation:** `Update` — update the master-workspace vanity URL segment.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Update` (Summary: "Permission required: MasterWorkspace.Update")
- **Request body** (`application/json`): bare JSON string, bound `[FromBody] string url`.
  - body — `string`, required — the new master URL segment.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → reserved-word string message (same as Create) or array of `ApiErrorResponse`
- **Notes:** Same reserved-word validation as `Create`.

#### `DELETE api/CustomUrl/MasterWorkspace/{id}`

- **Operation:** `Delete` — delete a master-workspace custom URL by id.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Update` (Summary: "Permission required: MasterWorkspace.Update") — note: action attribute is `Update`, not `Delete`.
- **Path params:** `{id}` — `string (uuid)`, required — id of the custom URL record. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### CustomUrlWorkspaceController — `api/CustomUrl/Workspace`

Controller-level: `[Route("api/CustomUrl/Workspace")]`, `[Consumes("application/json")]`, `[Produces("application/json")]`, `[AuthorizationEntity(Workspace)]`. All endpoints require Bearer JWT.

#### `GET api/CustomUrl/Workspace`

- **Operation:** `Get` — read the custom URL configured for the caller's current workspace.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Read` (Summary: "Permission required: Workspace.Read")
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `GET api/CustomUrl/Workspace/master`

- **Operation:** `GetFromMaster` — read the master-workspace custom URL associated with the caller's (sub-)workspace.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Read` (Summary: "Permission required: Workspace.Read")
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Resolves the master URL by the current sub-workspace id (used to build the full vanity path from a workspace context).

#### `POST api/CustomUrl/Workspace`

- **Operation:** `Create` — create the workspace vanity URL segment.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Create` (Summary: "Permission required: Workspace.Write")
- **Request body** (`application/json`): bare JSON string, bound `[FromBody] string url`.
  - body — `string`, required — the workspace URL segment.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Server builds `CustomUrlDto { Type = Workspace, Url = url }`. No reserved-word check on this controller.

#### `PUT api/CustomUrl/Workspace`

- **Operation:** `Update` — update the workspace vanity URL segment.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Update` (Summary: "Permission required: Workspace.Update")
- **Request body** (`application/json`): bare JSON string, bound `[FromBody] string url`.
  - body — `string`, required — the new workspace URL segment.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`

#### `DELETE api/CustomUrl/Workspace/{id}`

- **Operation:** `Delete` — delete a workspace custom URL by id.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Delete` (Summary: "Permission required: Workspace.Delete")
- **Path params:** `{id}` — `string (uuid)`, required — id of the custom URL record. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### CustomUrlFormController — `api/CustomUrl/FormTemplate`

Controller-level: `[Route("api/CustomUrl/FormTemplate")]`, `[Consumes("application/json")]`, `[Produces("application/json")]`, `[AuthorizationEntity(FormTemplate)]`. All endpoints require Bearer JWT. Manages the custom URL that maps to a specific form template (entity-type custom URL).

#### `GET api/CustomUrl/FormTemplate/{id}`

- **Operation:** `Get` — read the custom URL mapped to a given form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Read` (Summary: "Permission required: FormTemplate.Read")
- **Path params:** `{id}` — `string (uuid)`, required — the form template (entity) id. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Reads with `Type = Entity`, `EntityType = Form`, `EntityId = id`.

#### `POST api/CustomUrl/FormTemplate`

- **Operation:** `Create` — create a custom URL mapping for a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Create` (Summary: "Permission required: FormTemplate.Write")
- **Request body** (`application/json`): `CustomUrlDto`
  - The body must have `type = Entity (3)` and `entityType = Form (1)`, otherwise the request is rejected.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → `"Only Form Template URL can be created via this endpoint."` (plain string) when `type != Entity` or `entityType != Form`; otherwise array of `ApiErrorResponse`

#### `PUT api/CustomUrl/FormTemplate`

- **Operation:** `Update` — update a custom URL mapping for a form template.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Update` (Summary: "Permission required: FormTemplate.Update")
- **Request body** (`application/json`): `CustomUrlDto`
  - Must have `type = Entity (3)` and `entityType = Form (1)`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → `"Only Form Template URL can be updated via this endpoint."` (plain string) on type mismatch; otherwise array of `ApiErrorResponse`

#### `DELETE api/CustomUrl/FormTemplate/{id}`

- **Operation:** `Delete` — delete a form-template custom URL by id.
- **Auth:** Bearer JWT — **Permission:** `FormTemplate:Delete` (Summary: "Permission required: FormTemplate.Delete")
- **Path params:** `{id}` — `string (uuid)`, required — the custom URL record id. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### CustomUrlWebhookController — `api/CustomUrl/Webhook`

Controller-level: `[Route("api/CustomUrl/Webhook")]`, `[Consumes("application/json")]`, `[Produces("application/json")]`, `[AuthorizationEntity(Webhook)]`. All endpoints require Bearer JWT. Manages the custom URL that maps to a specific webhook (entity-type custom URL). Structurally identical to the Form controller but for `EntityType = Webhook (2)`.

#### `GET api/CustomUrl/Webhook/{id}`

- **Operation:** `Get` — read the custom URL mapped to a given webhook.
- **Auth:** Bearer JWT — **Permission:** `Webhook:Read` (Summary: "Permission required: Webhook.Read")
- **Path params:** `{id}` — `string (uuid)`, required — the webhook (entity) id. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → array of `ApiErrorResponse`
- **Notes:** Reads with `Type = Entity`, `EntityType = Webhook`, `EntityId = id`.

#### `POST api/CustomUrl/Webhook`

- **Operation:** `Create` — create a custom URL mapping for a webhook.
- **Auth:** Bearer JWT — **Permission:** `Webhook:Create` (Summary: "Permission required: Webhook.Write")
- **Request body** (`application/json`): `CustomUrlDto`
  - Must have `type = Entity (3)` and `entityType = Webhook (2)`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → `"Only Webhook URL can be created via this endpoint."` (plain string) on type mismatch; otherwise array of `ApiErrorResponse`

#### `PUT api/CustomUrl/Webhook`

- **Operation:** `Update` — update a custom URL mapping for a webhook.
- **Auth:** Bearer JWT — **Permission:** `Webhook:Update` (Summary: "Permission required: Webhook.Update")
- **Request body** (`application/json`): `CustomUrlDto`
  - Must have `type = Entity (3)` and `entityType = Webhook (2)`.
- **Responses:**
  - `200 OK` → `CustomUrlDto`
  - `400 Bad Request` → `"Only Webhook URL can be updated via this endpoint."` (plain string) on type mismatch; otherwise array of `ApiErrorResponse`

#### `DELETE api/CustomUrl/Webhook/{id}`

- **Operation:** `Delete` — delete a webhook custom URL by id.
- **Auth:** Bearer JWT — **Permission:** `Webhook:Delete` (Summary: "Permission required: Webhook.Delete")
- **Path params:** `{id}` — `string (uuid)`, required — the custom URL record id. Route constraint `:guid`.
- **Responses:**
  - `200 OK` → empty body
  - `400 Bad Request` → array of `ApiErrorResponse`

---

### CustomUrlLaunchController — catch-all `{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl}` (ANONYMOUS public entry point)

Controller-level: `[Route("{masterWorkspaceUrl:regex(^(?!api$|internal$|health$).*)}/{workspaceUrl}/{entityUrl}")]`, `[AllowAnonymous]`, `[AuthorizationEntity(None)]`. **No `[Consumes]`/`[Produces]`** — content type is whatever the caller sends; response varies by resolved entity (JSON for forms, pass-through / HTML / 200 for webhooks). This is the public **full-path** vanity URL entry point.

#### `GET|POST|PUT|PATCH|DELETE /{masterWorkspaceUrl}/{workspaceUrl}/{entityUrl}`

- **Operation:** `Launch` — resolve a 3-segment vanity URL to a form or webhook and serve/trigger it. The single method is decorated with all of `[HttpGet] [HttpPost] [HttpPut] [HttpPatch] [HttpDelete]`, so any of those HTTP verbs hit it.
- **Auth:** Anonymous — **Permission:** None (Summary: "Permission required: None")
- **Path params:**
  - `{masterWorkspaceUrl}` — `string`, required — first path segment (master workspace vanity segment). Route regex constraint: must NOT be exactly `api`, `internal`, or `health` (`^(?!api$|internal$|health$).*`).
  - `{workspaceUrl}` — `string`, required — second path segment (workspace vanity segment).
  - `{entityUrl}` — `string`, required — third path segment (the form/webhook vanity segment).
- **Query params:**
  - `payload` — `string`, optional, default `null` — for webhooks, an explicit payload string. When present it is treated as the request body: it is JSON-parsed (`JToken.Parse`) into the webhook body and also stored as the param string, bypassing content-type-based body parsing.
  - `respondOk` — `boolean`, optional, default `null` — for webhooks, controls the response shape (see Notes). Ignored for forms.
- **Request body:** for webhooks, the raw request body is read and interpreted by content type (see Notes / `WebhookLaunchManager`). For forms the body is ignored.
- **Responses:**
  - `404 Not Found` — the vanity URL did not resolve to any entity, or resolved to a non-form/non-webhook type.
  - **Webhook resolved** → result of `IWebhookLaunchManager.LaunchAsync` (pass-through of the webhook/process-launch service response, or `200 OK`, or an HTML "Request sent" page — see Notes). Can also be `415 Unsupported Media Type` or `400 Bad Request`.
  - **Form resolved** → `200 OK` with `FormTemplateDto` (the form definition to render); `400 Bad Request` with a forms error payload if the form is missing/draft/disabled; `401 Unauthorized` if the form is private and the caller is not authorized.
- **Notes:**
  - **Resolution:** calls `ICustomUrlManager.Resolve(masterWorkspaceUrl, workspaceUrl, entityUrl)` → `ICustomUrlModel`. Branch on `EntityType`: `Webhook` → launch webhook; `Form` → return form template; anything else (or null) → `404`.
  - **Anti-timing-attack:** every non-webhook return path calls `TimeDelay.RandomWait()` to randomize response time and avoid leaking whether a URL exists.
  - **Form workspace context:** before fetching the form it calls `EnsureWorkspaceContext(workspaceId, HttpContext)`. If a Bearer access token is present (custom headers `token_param` + `type_param=Bearer`) and the user is authorized for that workspace, an anonymous profile is initialized for that workspace so private-form authorization works; otherwise the form is served in anonymous context.
  - **Private forms:** `GetFormTemplate` throws `AuthenticationRequiredException` (→ `401`) if the form is private and the caller is anonymous / unauthorized / in the wrong workspace. Forms with `State == false` or `Status == DRAFT` produce a `400`.
  - **Webhook `respondOk` behavior:** if `respondOk` is omitted, the raw response from `RedirectToWebhookService` is returned as-is. If `respondOk == true`, returns bare `200 OK`. If `respondOk == false`, returns `200` with an HTML "Request sent" confirmation page (`text/html`).
  - **Webhook body parsing** (when `payload` query is absent) is by `Content-Type`: `application/json`, `application/x-ndjson`, `application/xml`, `application/x-www-form-urlencoded`, `multipart/form-data` (files uploaded via the webhook manager), `text/plain`, or no content type (empty JSON object). Any other content type → `415 Unsupported Media Type`. The incoming headers and query string are always captured into the webhook payload.

---

### TinyUrlLaunchController — catch-all `{tinyUrl}` (ANONYMOUS public entry point)

Controller-level: `[Route("{tinyUrl:regex(^(?!api$|internal$|health$).*)}")]`, `[AllowAnonymous]`, `[AuthorizationEntity(None)]`. Single-segment short-URL public entry point. Same body/response handling as the launch controller above. **No `[Consumes]`/`[Produces]`.**

#### `GET|POST|PUT|PATCH|DELETE /{tinyUrl}`

- **Operation:** `Launch` — resolve a single-segment tiny/short URL to a form or webhook and serve/trigger it. Decorated with all of `[HttpGet] [HttpPost] [HttpPut] [HttpPatch] [HttpDelete]`.
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** no (note: unlike `CustomUrlLaunchController`, this method has **no `[SwaggerOperation]`** attribute).
- **Path params:**
  - `{tinyUrl}` — `string`, required — the short URL token (single path segment). Route regex constraint: must NOT be exactly `api`, `internal`, or `health` (`^(?!api$|internal$|health$).*`).
- **Query params:**
  - `payload` — `string`, optional, default `null` — same meaning as in `CustomUrlLaunchController` (webhook payload override).
  - `respondOk` — `boolean`, optional, default `null` — same meaning (webhook response shaping).
- **Request body:** same content-type-driven webhook body handling as the full-path launch controller; ignored for forms.
- **Responses:**
  - `404 Not Found` — tiny URL did not resolve, resolved record has no `EntityId`, or resolved to a non-form/non-webhook type.
  - **Webhook resolved** → result of `IWebhookLaunchManager.LaunchAsync` (pass-through / `200 OK` / HTML page; or `415` / `400`).
  - **Form resolved** → `200 OK` with `FormTemplateDto`; `400 Bad Request` (form missing/draft/disabled); `401 Unauthorized` (private form, unauthorized).
- **Notes:**
  - **Resolution:** calls `ICustomUrlManager.Resolve(tinyUrl)` (single-arg overload) → `ICustomUrlModel`. Returns `404` immediately if the result is null **or** `EntityId` has no value.
  - All other behavior (anti-timing `TimeDelay.RandomWait`, `EnsureWorkspaceContext`, private-form `401`, webhook content-type handling, `respondOk` shaping) is identical to `CustomUrlLaunchController`.

---

## Shared DTOs

### `CustomUrlDto`

Source: `BE/Web-Api/WebApi/Infrastructure/Infrastructure.Core/DTO/CustomUrl/CustomUrlDto.cs`. Newtonsoft default serialization (no `[JsonProperty]` overrides) — wire names are the C# property names verbatim (PascalCase).

| Wire field | Type | Required | Description |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | Custom URL record id (`Guid?`). Server-assigned on create; supply on update/delete-by-record. |
| `WorkspaceId` | `string (uuid)` | optional | Owning workspace id (`Guid?`). |
| `EntityId` | `string (uuid)` | optional | Id of the mapped entity (form template id or webhook id) (`Guid?`). Required when `Type = Entity`. |
| `EntityType` | `string\|number (enum CustomUrlEntityType)` | optional | `None=0`, `Form=1`, `Webhook=2`. Required when `Type = Entity`. |
| `Type` | `string\|number (enum CustomUrlType)` | optional | `Master=1`, `Workspace=2`, `Entity=3`. |
| `Url` | `string` | optional | The vanity URL segment value. |
| `TinyUrl` | `string` | optional | The tiny/short URL token. |
| `CreatedOn` | `string (date-time, ISO-8601)` | optional | Creation timestamp (`DateTime?`). |
| `UpdatedOn` | `string (date-time, ISO-8601)` | optional | Last-update timestamp (`DateTime?`). |
| `CreatedById` | `string (uuid)` | optional | Creator user id (`Guid?`). |
| `UpdatedById` | `string (uuid)` | optional | Last-updater user id (`Guid?`). |

Notes:
- On the **Master** and **Workspace** controllers, `Create`/`Update` do NOT accept this DTO — they accept a bare JSON string and the server constructs the DTO with the appropriate `Type`.
- On the **Form** and **Webhook** controllers, `Create`/`Update` accept the full DTO and enforce `Type = Entity` plus the matching `EntityType`.

### `CustomUrlType` (enum)

Source: `BE/Web-Api/WebApi/Domain/Enums/CustomUrl/CustomUrlType.cs`.

- `Master = 1`
- `Workspace = 2`
- `Entity = 3`

### `CustomUrlEntityType` (enum)

Source: `BE/Web-Api/WebApi/Domain/Enums/CustomUrl/CustomUrlEntityType.cs`.

- `None = 0`
- `Form = 1`
- `Webhook = 2`

### `ApiErrorResponse`

Standard PROCESIO error payload returned (as an array) on `400 Bad Request` across all management endpoints. See the shared conventions doc ([../02-conventions.md](../02-conventions.md)) for its fields; not re-defined here.

### `FormTemplateDto`

The form definition returned by the public launch endpoints (`200 OK`) when a vanity/tiny URL resolves to a Form. This DTO belongs to the **Forms** domain — see the Forms endpoints reference for its full field list. Not re-defined here.

### `ICustomUrlModel` (internal resolution model — not on the wire)

Source: `BE/Web-Api/WebApi/Domain/Contracts/Models/CustomUrl/ICustomUrlModel.cs`. Returned by `ICustomUrlManager.Resolve(...)` internally to drive launch routing; never serialized to clients. Fields: `Gid (Guid)`, `WorkspaceId (Guid)`, `EntityId (Guid?)`, `EntityType (CustomUrlEntityType?)`, `Type (CustomUrlType)`, `Url`, `TinyUrl`, `CreatedOn`, `UpdatedOn`, `CreatedById`, `UpdatedById`. Documented here only to explain how launch routing decides form-vs-webhook.
