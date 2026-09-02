# Webhooks, Notifications, API Keys & Transport endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/Webhooks/WebhooksController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Webhooks/WebhookLaunchController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Webhooks/VerifoneWebhooksController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/Webhooks/ProcesioAdmin/WebhookEventsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/NotificationsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/ApiKeyController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/TransportController.cs`

This domain covers four loosely related capabilities of the PROCESIO platform:

- **Webhooks** — CRUD for webhook definitions plus a tooling endpoint set used by the flow designer to listen for and generate data models from sample payloads. A webhook ties an inbound HTTP request to a process flow.
- **Inbound webhook trigger** (`WebhookLaunchController`) — the public, **anonymous** entry point external systems call to fire a webhook and launch the associated process. Accepts every common HTTP verb and any common body content type. This is the primary public integration surface of the platform.
- **Verifone / 2Checkout callbacks** (`VerifoneWebhooksController`) — anonymous payment-provider IPN (Instant Payment Notification) callbacks that route into the same webhook machinery.
- **Notifications** — in-app notification inbox: list the current user's notifications and mark them read.
- **API Keys** — manage long-lived API keys that let machine clients authenticate to the whole gateway with `key` + `value` headers instead of a JWT.
- **Transport** — export PROCESIO platform entities (flows, data types, credentials, documents, forms, data stores, webhooks) to a `.procesio` archive and import them back.

---

## Endpoints

### WebhooksController — `api/Webhooks` (webhook CRUD & designer tooling)

Controller route: `[Route("api/[controller]")]` → `api/Webhooks`. Controller-level `[AuthorizationEntity(Webhook)]`. All actions return `application/json`. Every action declares `[Consumes("application/json", "multipart/form-data")]`.

---

#### `GET api/Webhooks`

- **Operation:** `GetWebhooks` — paginated list of webhooks in the current workspace, optionally filtered by name.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Read` (`"Permission required: Webhook.Read"`)
- **Query params:**
  - `pageNumber` — `number`, optional, default `1` — 1-based page index.
  - `pageItemCount` — `number`, optional, default `0` — items per page; `0` means "all items".
  - `searchName` — `string`, optional, default `null` — name filter; ignored (treated as `null`) if the trimmed value is shorter than 3 characters.
- **Responses:**
  - `200 OK` → paginated list of `WebhookDto` (JSON).
  - `400 Bad Request` → error payload (`USER_IS_NOT_AUTHORIZED`) when the manager returns `null`.

---

#### `GET api/Webhooks/{webhookId}`

- **Operation:** `GetWebhook` — fetch a single webhook by id.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Read` (`"Permission required: Webhook.Read"`)
- **Path params:** `{webhookId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → `WebhookDto`
  - `400 Bad Request` → webhook error payload.

---

#### `POST api/Webhooks`

- **Operation:** `CreateWebhook` — create a new webhook definition.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Create` (`"Permission required: Webhook.Write"`)
- **Request body** (`application/json` or `multipart/form-data`): `WebhookDto`
- **Responses:**
  - `200 OK` → created `WebhookDto` (manager `Value`).
  - `400 Bad Request` → webhook error payload.

---

#### `PUT api/Webhooks`

- **Operation:** `UpdateWebhook` — update an existing webhook definition.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Update` (`"Permission required: Webhook.Update"`)
- **Request body** (`application/json` or `multipart/form-data`): `WebhookDto` (the `id` field identifies the target).
- **Responses:**
  - `200 OK` → updated `WebhookDto`.
  - `400 Bad Request` → webhook error payload.

---

#### `DELETE api/Webhooks/{webhookId}`

- **Operation:** `DeleteWebhook` — delete a webhook by id.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Delete` (`"Permission required: Webhook.Delete"`)
- **Path params:** `{webhookId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → webhook error payload.

---

#### `GET api/Webhooks/datamodels/{webhookId}`

- **Operation:** `GetDataModelsByWebhook` — return the data model(s) associated with a webhook (the shape of its payload).
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Read` (`"Permission required: Webhook.Read"`)
- **Path params:** `{webhookId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → data model(s) (JSON; shaped like `DataModelDto`).
  - `400 Bad Request` → webhook error payload.

---

#### `POST api/Webhooks/generate-data`

- **Operation:** `GenerateDataModel` — generate a data model from a raw payload definition (used by the designer when configuring a webhook).
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Create` (`"Permission required: Webhook.Write"`)
- **Request body** (`application/json` or `multipart/form-data`): `WebhookDataModelDto`
- **Responses:**
  - `200 OK` → generated data model (JSON).
  - `400 Bad Request` → webhook error payload.

---

#### `DELETE api/Webhooks/{webhookId}/undo`

- **Operation:** `UndoTemporaryWebhook` — discard the temporary/draft webhook created while editing without saving.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Update` (`"Permission required: Webhook.Update"`)
- **Path params:** `{webhookId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → webhook error payload.
- **Notes:** Deletes the temporary webhook record linked to `webhookId`; used when a designer edit session is abandoned.

---

#### `GET api/Webhooks/{webhookId}/used`

- **Operation:** `IsUsed` — check whether a webhook is referenced inside any flow.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Read` (`"Permission required: Webhook.Read"`)
- **Path params:** `{webhookId}` — `string (uuid)`, required.
- **Responses:**
  - `200 OK` → boolean-like value (the manager's `Value`; `true` if the webhook is used in a flow).
  - `400 Bad Request` → webhook error payload.

---

#### `POST api/Webhooks/listen`

- **Operation:** `Listen` — start/stop a "listen" session so the designer can capture a sample inbound request and build a data model from it (or perform handshake configuration).
- **Auth:** Bearer JWT (or API key) — **Permission:** `Webhook:Update` (`"Permission required: Webhook.Update"`)
- **Request body** (`application/json` or `multipart/form-data`): `WebhookListenDto`
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → webhook error payload.
- **Notes:** Real-time designer tooling. `ConnectionId` ties the session to a SignalR/websocket connection so captured payloads can be pushed back to the client.

---

### WebhookLaunchController — `api/Webhooks/launch/{id}` (ANONYMOUS inbound trigger)

Controller route: `[Route("api/Webhooks")]`. Controller-level `[AuthorizationEntity(Webhook)]`, but the single action is `[AllowAnonymous]`.

> **This is the key public integration point.** External systems call this URL to fire a configured webhook, which launches the associated PROCESIO process flow. No JWT or API key is required.

---

#### `GET|POST|PUT|PATCH|DELETE api/Webhooks/launch/{id}`

- **Operation:** `LaunchWebhook` — fire the webhook identified by `{id}`, capture the inbound request (headers, query string, body), and launch the linked process flow.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None` (`"Permission required: None"`)
- **HTTP verbs:** the same action is registered for **GET, POST, PUT, PATCH, and DELETE** (five `[HttpX("launch/{id:guid}")]` attributes on one method). All five behave identically.
- **Path params:** `{id}` — `string (uuid)`, required — the webhook id to trigger.
- **Query params:**
  - `payload` — `string`, optional, default `null` — when supplied, it is parsed as JSON and used as **both** the webhook body (`Body = JToken.Parse(payload)`) **and** the param value, *overriding* any request body. Lets a caller pass the payload entirely in the query string (handy for `GET`/`DELETE` that have no body). Must be valid JSON or the request fails with `400`.
  - `respondOk` — `boolean`, optional, default `null` — controls the synchronous HTTP response (see Notes). When omitted, the response is whatever the downstream webhook service returns; `true` returns an empty `200 OK`; `false` returns a styled HTML "Request sent" confirmation page.
- **Request body** (any content type when `payload` is not supplied): the raw body is parsed according to `Content-Type`:
  - `application/json` → parsed as JSON.
  - `application/x-ndjson` → parsed as a JSON array (newline-delimited JSON).
  - `application/xml` → converted from XML to JSON.
  - `application/x-www-form-urlencoded` → form fields converted to a JSON object.
  - `multipart/form-data` → text fields + uploaded files; files are stored and merged into the payload. Returns `400` if a text key and a file share the same key.
  - `text/plain` → wrapped in a JSON object.
  - no `Content-Type` (null) → empty JSON object `{}`.
  - any other content type → `415 Unsupported Media Type`.
- **Responses:**
  - `200 OK` → depends on `respondOk`:
    - `respondOk` omitted → the `IActionResult` returned by the downstream webhook service (may include a custom response body configured on the webhook).
    - `respondOk=true` → empty `200 OK`.
    - `respondOk=false` → `200 OK` with `Content-Type: text/html` rendering a PROCESIO-branded "Request sent" page.
  - `400 Bad Request` → `INTERNAL_ERROR` on any processing exception (e.g. invalid JSON in `payload`), or a multipart key-collision message.
  - `415 Unsupported Media Type` → unrecognized `Content-Type`.
- **Notes:**
  - The full inbound request is captured: request **headers** and **query string** are serialized into the webhook payload (`Header`, `Param`) alongside the parsed **body**, so the launched flow can read all three.
  - Each launch creates a new webhook event id (`Guid`) server-side and redirects the payload to the internal webhook service, which triggers the process flow asynchronously.
  - Idempotency: none — every call triggers a new process instance.

---

### VerifoneWebhooksController — `api/Webhooks/launch/{id}/verifone` (payment provider callbacks)

Controller route: `[Route("api/Webhooks")]`. Controller-level `[AuthorizationEntity(Webhook)]`. Both actions are `[AllowAnonymous]` and `[ApiExplorerSettings(IgnoreApi = true)]` (hidden from Swagger but reachable). Used for Verifone / 2Checkout IPN callbacks.

---

#### `POST api/Webhooks/launch/{id}/verifone`

- **Operation:** `LaunchFormData` — handle a Verifone/2Checkout IPN callback delivered as URL-encoded form data and route it through the IPN service.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None`
- **Hidden from Swagger:** yes
- **Path params:** `{id}` — `string (uuid)`, required — the webhook id.
- **Request body** (`application/x-www-form-urlencoded`): raw form collection (`IFormCollection`) — the provider's IPN fields. No fixed DTO; fields are provider-defined.
- **Responses:**
  - `200 OK` → empty when the IPN service returns no content.
  - `200 OK` (`text/plain`) → the IPN service's response string when non-empty (e.g. an acknowledgement token expected by the provider).
  - `400 Bad Request` → `"Internal server error!"` on any exception.
- **Notes:** Wraps all processing in a try/catch and never surfaces internal errors verbatim.

---

#### `GET api/Webhooks/launch/{id}/verifone`

- **Operation:** `LaunchGetFormData` — handle a Verifone/2Checkout callback delivered via GET with the payload in the query string.
- **Auth:** **Anonymous** (`[AllowAnonymous]`) — **Permission:** `None`
- **Hidden from Swagger:** yes
- **Path params:** `{id}` — `string (uuid)`, required.
- **Query params:** `payload` — `string`, required — JSON string; parsed (`JToken.Parse`) into the webhook body. (No body content is read; `Param` is set to `"[]"` and `Header` to `"{}"`.)
- **Responses:**
  - `200 OK` → empty.
- **Notes:** Generates a new webhook event id and redirects the payload directly to the internal webhook service. Declares `[Consumes("application/json", "multipart/form-data")]` despite reading only the query string.

---

### WebhookEventsController — `api/WebhookEvents` (ProcesioAdmin, hidden)

Controller route: `[Route("api/[controller]")]` → `api/WebhookEvents`. Controller-level `[AuthorizationEntity(ProcesioAdmin)]`, `[ApiExplorerSettings(IgnoreApi = true)]`, `[Consumes("application/json")]`. Both actions require ProcesioAdmin rights and are hidden from Swagger but reachable. Tagged `ProcesioAdmin`.

> Note: this controller is **not** under an `internal/` route and is **not** `[SecureInternalController]`, so it is technically part of the public gateway surface, but it is an admin-only operational endpoint. Documented for completeness.

---

#### `GET api/WebhookEvents`

- **Operation:** `GetRunningWebhookEvents` — list webhook events that are currently running (in progress), filtered by workspace / user / webhook.
- **Auth:** Bearer JWT (or API key) — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Special headers** (all `[FromHeader]`, all optional):
  - `targetWorkspace` — `string (uuid)` — filter by workspace.
  - `userId` — `string (uuid)` — filter by user.
  - `webhookId` — `string (uuid)` — filter by webhook.
- **Query params:**
  - `pageNumber` — `number`, optional, default `1`.
  - `pageItemCount` — `number`, optional, default `0` (all items).
- **Responses:**
  - `200 OK` → paginated list of running webhook events (JSON).

---

#### `GET api/WebhookEvents/count`

- **Operation:** `CountRunningWebhookEvents` — count webhook events currently running, filtered by workspace / user / webhook.
- **Auth:** Bearer JWT (or API key) — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Special headers** (all `[FromHeader]`, all optional): `targetWorkspace`, `userId`, `webhookId` — same as above.
- **Responses:**
  - `200 OK` → number of running events (JSON).

---

### NotificationsController — `api/Notifications` (in-app notification inbox)

Controller route: `[Route("api/[controller]")]` → `api/Notifications`. Controller-level `[AuthorizationEntity(None)]`, `[Consumes("application/json")]`, `[Produces("application/json")]`. Proxies to the Notifications service.

---

#### `GET api/Notifications`

- **Operation:** `GetUserNotifications` — return all in-app notifications for the current user.
- **Auth:** Bearer JWT (or API key) — **Permission:** `None` (`"Permission required: None"`) — authenticated only.
- **Responses:**
  - `200 OK` → the Notifications service response (user notifications list).
  - `400 Bad Request` → context error payload.

---

#### `PATCH api/Notifications`

- **Operation:** `AcknowledgeUserNotifications` — mark one notification, or all unread notifications, as read.
- **Auth:** Bearer JWT (or API key) — **Permission:** `None` (`"Permission required: None"`)
- **Request body** (`application/json`): `AcknowledgeUserNotificationDto`
- **Responses:**
  - `200 OK` → the Notifications service response.
  - `400 Bad Request` → context error payload.
- **Notes:** If `id` is null and `markAllUnread` is `true`, all the user's notifications are marked read; otherwise only the notification with the given `id` is marked read.

---

### ApiKeyController — `api/ApiKey` (API key management)

Controller route: `[Route("api/[controller]")]` → `api/ApiKey`. Controller-level `[AuthorizationEntity(ApiKey)]`, `[Consumes("application/json")]`, `[Produces("application/json")]`.

> **Important:** every action rejects callers that authenticated *with an API key* (`AuthenticationType == ApiKey`) and returns an unauthorized response. **API keys can be used everywhere else on the gateway, but they cannot be used to manage API keys** — you must use a JWT (a real user session) to create/list/revoke keys. See "## How API key authentication works" below.

---

#### `GET api/ApiKey`

- **Operation:** `GetApiKeys` — list the current user's API keys in the current workspace.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Read` (`"Permission required: ApiKey.Read"`)
- **Responses:**
  - `200 OK` → array of `ApiKeyDto` (the `value` field is **not** populated here — only `id`, `name`, `lastAccessed`).
  - `401/403 Unauthorized` → if the request authenticated via API key.

---

#### `POST api/ApiKey`

- **Operation:** `CreateApiKey` — generate a new API key for the current user/workspace.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Create` (`"Permission required: ApiKey.Write"`)
- **Responses:**
  - `200 OK` → `ApiKeyDto` — **this is the only response that returns the plaintext `value`** (the secret). The server stores only a hash, so the value cannot be retrieved again.
  - `400 Bad Request` → error payload `MAX_NR_API_KEYS` if the user already has 25 keys (the per-user/workspace limit).
  - `401/403 Unauthorized` → if the request authenticated via API key.
- **Notes:** Key name is a random 16-char string; value is a random 64-char string. Maximum 25 keys per user/workspace.

---

#### `DELETE api/ApiKey`

- **Operation:** `RevokeAll` — revoke (delete) all of the current user's API keys in the current workspace.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Delete` (`"Permission required: ApiKey.Delete"`)
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → `"No apikey found to delete"` when there are none.
  - `401/403 Unauthorized` → if the request authenticated via API key.

---

#### `DELETE api/ApiKey/{id}`

- **Operation:** `RevokeKey` — revoke (delete) a single API key by id.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Delete` (`"Permission required: ApiKey.Delete"`)
- **Path params:** `{id}` — `string (uuid)`, required — the API key id.
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → `"Invalid key id."` when the key does not exist.
  - `401/403 Unauthorized` → if the request authenticated via API key.

---

### TransportController — `api/Transport` (export / import of platform entities)

Controller route: `[Route("api/[controller]")]` → `api/Transport`. Controller-level `[AuthorizationEntity(Workspace)]`. (No controller-level `[Produces]`/`[Consumes]`.)

---

#### `POST api/Transport/import`

- **Operation:** `ImportProcesioData` — import platform entities from an uploaded `.procesio` archive.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Workspace:Admin` (`"Permission required: Workspace.Admin"`)
- **Special headers** (all `[FromHeader]`, `boolean`, required — value types):
  - `overrideData` — overwrite existing entities instead of creating copies.
  - `importDataTypes` — include data types/models.
  - `importFlows` — include flows.
  - `importCredentials` — include credentials.
  - `importDocuments` — include document templates.
  - `importForms` — include forms.
  - `importDataStores` — include data stores.
- **Request body** (`multipart/form-data`): `importedData` — `file`, required — the `.procesio` archive (`IFormFile`).
- **Responses:**
  - `200 OK` → empty on success.
  - `403 Forbidden` → body `MIGRATE` constant on any error.
- **Notes:** The webhook-import flag passed to the manager is hard-coded `false` (webhooks are not imported by this endpoint). Import work is delegated to `IDataTransportManager.Import`.

---

#### `GET api/Transport/export`

- **Operation:** `ExportProcesioData` — export selected platform entities to a downloadable `.procesio` archive. (Comment in source: "No longer used by FE".)
- **Auth:** Bearer JWT (or API key) — **Permission:** `Workspace:Admin` (`"Permission required: Workspace.Admin"`)
- **Special headers** (all `[FromHeader]`, `boolean`, required — value types):
  - `exportDataTypes`, `exportFlows`, `exportCredentials`, `exportWebhooks`, `exportDocuments`, `exportForms`, `exportDataStores` — include each entity category.
  - `exportSensitiveData` — include sensitive data (e.g. credential secrets).
- **Responses:**
  - `200 OK` → binary file (`application/octet-stream`), filename `ExportedData-<UTC timestamp>.procesio`.
  - `403 Forbidden` → body `MIGRATE` constant on any error.

---

#### `POST api/Transport/export-entities`

- **Operation:** `ExportProcesioData` (overload) — export specific entities selected by id lists to a downloadable `.procesio` archive.
- **Auth:** Bearer JWT (or API key) — **Permission:** `Workspace:Admin` (`"Permission required: Workspace.Admin"`)
- **Request body** (`application/json`): `ExportEntitiesDto`
- **Responses:**
  - `200 OK` → binary file (`application/octet-stream`), filename `ExportedEntities-<UTC timestamp>.procesio`.
  - `403 Forbidden` → body `MIGRATE` constant on any error.

---

## How API key authentication works (alternative to JWT)

API keys let a machine client authenticate to the Web-Api gateway **without a JWT**. They are the alternative credential for nearly every endpoint in this service.

- The gateway selects the auth mode from the `auth_type` request header (parsed into `WebApiAuthTypes`: `Token=0`, `ApiKey=1`, `Anonymous=2`). To use an API key, set `auth_type: 1` (`ApiKey`).
- The key itself is sent in **two headers**:
  - `key` — the API key **name** (the random 16-char identifier returned as `name` from `POST api/ApiKey`).
  - `value` — the API key **secret** (the random 64-char string returned as `value` from `POST api/ApiKey`, shown only once at creation).
- Server-side validation (`UserProfile.InitApiKey` + `Authentication` middleware): the gateway looks up the key by `key`(name) within the workspace, verifies it is active, and validates `value` against the stored hash (`Hash.ValidateHash`). On success it loads the owning user's profile and authorization, then updates the key's `lastAccessed` timestamp. Any mismatch → `403 Forbidden`.
- Workspace scoping: keys are bound to the workspace they were created in. Send the workspace id the same way a JWT request would (`workspaceId` header).
- **Restriction:** API-key-authenticated requests cannot manage API keys — all `ApiKeyController` actions reject `AuthenticationType == ApiKey`. Use a JWT to create/list/revoke keys.
- Limit: max **25** keys per user/workspace.

For the inbound webhook trigger (`api/Webhooks/launch/{id}`) and the Verifone callbacks, no credential is needed at all — those are `[AllowAnonymous]` and rely on the unguessable webhook `{id}` (uuid) for access control.

---

## Shared DTOs

### `WebhookDto` (extends `BaseWebhookDto`)
Webhook definition. Inherits all `BaseWebhookDto` fields plus:

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `Id` | `string (uuid)` | optional | from `BaseWebhookDto`; nullable. |
| `Name` | `string` | optional | from `BaseWebhookDto`; webhook name. |
| `PayloadIsList` | `boolean` | required | from `BaseWebhookDto`; payload root is an array. |
| `HasHeader` | `boolean` | required | from `BaseWebhookDto`; capture/expose request headers. |
| `HasQuery` | `boolean` | required | from `BaseWebhookDto`; capture/expose query string. |
| `DataModelId` | `string (uuid)` | required | id of the data model describing the payload. |
| `Type` | `string\|number (enum WebhookType: AUTO=0, MANUAL=1)` | required | how the webhook fires. |
| `Definition` | `string` | optional | raw payload/data-model definition. |
| `IsEdited` | `boolean` | optional | nullable; draft/edit flag. |
| `DataModel` | `object (DataModelDto)` | optional | the resolved data model. |
| `CustomResponseConfig` | `object (WebhookCustomResponseDto)` | optional | configures the synchronous HTTP response returned to the caller. |
| `CreatedOn` | `string (date-time, ISO-8601)` | optional | server-set. |
| `UpdatedOn` | `string (date-time, ISO-8601)` | optional | server-set. |

### `BaseWebhookDto`
Base type for webhook DTOs. Fields: `Id` (`string (uuid)`, optional/nullable), `Name` (`string`, optional), `PayloadIsList` (`boolean`, required), `HasHeader` (`boolean`, required), `HasQuery` (`boolean`, required). (Listed inline in `WebhookDto` above.)

### `WebhookCustomResponseDto`
Configures the custom response returned synchronously by the inbound trigger.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `ConfigType` | `string\|number (enum WebhookResponseType: StaticJson=1, Javascript=2, JsonPath=3)` | required | how the response body is produced. |
| `Config` | `string` | optional | the static JSON, JS snippet, or JSON path, depending on `ConfigType`. |

### `WebhookDataModelDto`
Request body for `POST api/Webhooks/generate-data`.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `Definition` | `string` | optional | raw payload definition used to infer a data model. |

### `WebhookListenDto`
Request body for `POST api/Webhooks/listen`.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `ConnectionId` | `string` | optional | client connection (SignalR) id to push captured payload back to. |
| `Listen` | `boolean` | required | start (`true`) or stop (`false`) listening. |
| `ListenType` | `string\|number (enum WebhookListenType: DataModel=1, Handshake=2)` | required | purpose of the listen session. |
| `WebhookId` | `string (uuid)` | optional | nullable; the webhook being configured. |
| `WebhookName` | `string` | optional | name shown during configuration. |
| `HasQuery` | `boolean` | required | capture query string. |
| `HasHeader` | `boolean` | required | capture request headers. |
| `HandshakeConfig` | `object (HandshakeConfigDto)` | optional | handshake response configuration (when `ListenType=Handshake`). |

### `HandshakeConfigDto`
Handshake response configuration used in `WebhookListenDto`.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `ConfigType` | `string\|number (enum WebhookResponseType: StaticJson=1, Javascript=2, JsonPath=3)` | required | how the handshake response body is produced. |
| `Status` | `number` | required | HTTP status code to return for the handshake. |
| `Config` | `string` | optional | the static JSON / JS / JSON path. |

### `AcknowledgeUserNotificationDto`
Request body for `PATCH api/Notifications`.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `id` | `string (uuid)` | optional | nullable; the notification to mark read. |
| `markAllUnread` | `boolean` | required | when `true` and `id` is null, mark all unread notifications as read. |

### `ApiKeyDto`
Response from `GET api/ApiKey` (array) and `POST api/ApiKey` (single).

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `id` | `string (uuid)` | required | API key id (used to revoke via `DELETE api/ApiKey/{id}`). |
| `name` | `string` | optional | API key name — sent as the `key` header when authenticating. |
| `lastAccessed` | `string (date-time, ISO-8601)` | optional | nullable; last time the key was used. |
| `value` | `string` | optional | the plaintext secret — populated **only** on `POST api/ApiKey` (creation). Sent as the `value` header when authenticating. |

### `ExportEntitiesDto`
Request body for `POST api/Transport/export-entities`. Each id list selects the entities of that type to export.

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `dataModelIds` | `array of string (uuid)` | optional | data types/models to export. |
| `flowIds` | `array of string (uuid)` | optional | flows to export. |
| `credentialIds` | `array of string (uuid)` | optional | credentials to export. |
| `webhookIds` | `array of string (uuid)` | optional | webhooks to export. |
| `documentIds` | `array of string (uuid)` | optional | document templates to export. |
| `formIds` | `array of string (uuid)` | optional | forms to export. |
| `dataStoreIds` | `array of string (uuid)` | optional | data stores to export. |
| `exportSensitiveData` | `boolean` | required | include sensitive data (e.g. credential secrets). |

### `DataModelDto` (cross-domain — defined fully in the Data Types domain)
Returned by `GET api/Webhooks/datamodels/{webhookId}` and nested in `WebhookDto.DataModel`. Describes the shape of a webhook payload. Key fields (extends `BaseDataTypeDto`):

| Wire field | Type | Req? | Notes |
|---|---|---|---|
| `Id` | `string (uuid)` | required | |
| `Name` | `string` | optional | |
| `DisplayName` | `string` | optional | |
| `IsDataModel` | `boolean` | required | |
| `IsPrimaryType` | `boolean` | required | |
| `IsProcesio` | `boolean` | required | |
| `IsPublic` | `boolean` | required | |
| `CsharpCorrespondent` | `string\|number (enum PrimaryDataType)` | required | underlying primitive type. |
| `Type` | `string\|number (enum DataModelTypeParam, default Normal)` | required | |
| `Attributes` | `array of DataAttributeDto` | optional | the model's fields. |
| `ParentIds` | `array of string (uuid)` | optional | parent data type ids. |

`DataAttributeDto` (recursive — a field of a data model) carries: `Id` (`uuid?`), `DataTypeId` (`uuid`), `ParentDataTypeId` (`uuid`), `Name`, `DisplayName`, `DataTypeName`, `IsDataModel`, `IsPrimaryType`, `IsProcesio`, `IsPublic`, `CsharpCorrespondent` (enum `PrimaryDataType`), `Type` (enum `DataModelTypeParam`), `IsList` (`boolean`), `jsonProperty` (`string`, JSON-mapped from `JsonPropertyName`), `updatedOn` (`date-time`), and nested `Attributes` (`array of DataAttributeDto`). The `PrimaryDataType` and `DataModelTypeParam` enums and `OwnershipAuditDto` base are defined in the Data Types domain doc.

### `WebhookPayloadModel` (internal payload envelope — not a request body)
The server constructs this from the inbound trigger request; not directly posted by clients. Fields: `Body` (JSON token — the parsed request body), `Header` (`string` — serialized request headers), `Param` (`string` — serialized query string, or the `payload` query value when supplied). Listed here because the Verifone GET callback and the launch flow build it explicitly.
