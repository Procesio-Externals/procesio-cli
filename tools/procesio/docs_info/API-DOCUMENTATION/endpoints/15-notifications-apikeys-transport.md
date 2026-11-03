# Notifications, API Keys & Transport endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/NotificationsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/ApiKeyController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/TransportController.cs`

This domain covers three loosely related capabilities of the PROCESIO platform:

- **Notifications** — in-app notification inbox: list the current user's notifications and mark them read.
- **API Keys** — manage long-lived API keys that let machine clients authenticate to the whole gateway with `key` + `value` headers instead of a JWT.
- **Transport** — export PROCESIO platform entities (flows, data types, credentials, documents, forms, data stores, webhooks) to a `.procesio` archive and import them back.

---

## Endpoints

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

- **Operation:** `GetApiKeys` — list the caller's **own** API keys in the current workspace.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Read` (`"Permission required: ApiKey.Read"`)
- **Responses:**
  - `200 OK` → array of `ApiKeyDto` (the `value` field is **not** populated here). Each row carries `id`, `name`, `label`, `createdOn`, `createdById` / `createdBy` (creator = the key's owner; name JOINed from `users`), `lastAccessed`.
  - `401/403 Unauthorized` → if the request authenticated via API key.
- **Note:** a MasterWorkspace Owner/Co-Owner sees **every** user's keys via the separate `GET api/ApiKeyMaster` (below).

---

#### `GET api/ApiKeyMaster`

- **Operation:** `GetWorkspaceApiKeys` — list **every** user's API keys in the active (sub-)workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (`"Permission required: MasterWorkspace.Read"`) — held by workspace Owners/Co-Owners. Gated by the standard authorization attribute, no manual check.
- **Responses:**
  - `200 OK` → array of `ApiKeyDto`, each with `createdBy` identifying whose key it is.
  - `401/403 Unauthorized` → if the request authenticated via API key, or the caller lacks the MasterWorkspace permission.

---

#### `POST api/ApiKey`

- **Operation:** `CreateApiKey` — generate a new API key for the current user/workspace.
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Create` (`"Permission required: ApiKey.Write"`)
- **Label:** passed via the **`label` request header** (`[FromHeader]`). Optional — a request with no `label` header creates a key with no label.
- **Responses:**
  - `200 OK` → `ApiKeyDto` — **this is the only response that returns the plaintext `value`** (the secret). The server stores only a hash, so the value cannot be retrieved again.
  - `400 Bad Request` → `MAX_NR_API_KEYS` (already has 25 keys), `LABEL_ALREADY_EXISTS` (the label is already used by this user in this workspace), or `INVALID_API_KEY_LABEL` (over 255 chars / contains control characters).
  - `401/403 Unauthorized` → if the request authenticated via API key.
- **Notes:** `name` (the auth handle) is a random 16-char string; `value` is a random 64-char string. `label` is a separate, user-set, human-readable name — unique per (user, workspace), blank allowed. Maximum 25 keys per user/workspace.

---

#### `PUT api/ApiKey/{id}/label`

- **Operation:** `UpdateApiKeyLabel` — rename a key (edits the `label` only; `name`/`value` never change, so authentication with the key is unaffected).
- **Auth:** Bearer JWT — **Permission:** `ApiKey:Update` (`"Permission required: ApiKey.Update"`)
- **Path params:** `{id}` — `string (uuid)`, required.
- **Label:** passed via the **`label` request header** (`[FromHeader]`); blank clears the label.
- **Scope:** the caller's **own** key (the update is filtered by id + userId + workspaceId).
- **Responses:**
  - `200 OK` → empty (the FE reflects the new label locally).
  - `400 Bad Request` → `INVALID_API_KEY_ID` (not found for this caller in this workspace), `LABEL_ALREADY_EXISTS`, or `INVALID_API_KEY_LABEL`.
  - `401/403 Unauthorized` → if the request authenticated via API key.

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
- **Scope:** the caller's **own** key (filtered by userId + workspaceId).
- **Responses:**
  - `200 OK` → empty.
  - `400 Bad Request` → `"Invalid key id."` when the key does not exist for this caller.
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
| `name` | `string` | optional | API key **handle** (random 16-char) — sent as the `key` header when authenticating. Not user-editable. |
| `label` | `string` | optional | nullable; human-readable, user-set name. Unique per (user, workspace). |
| `createdOn` | `string (date-time, ISO-8601)` | optional | nullable; UTC creation timestamp (back-filled for legacy keys). |
| `createdById` | `string (uuid)` | optional | id of the creator (= the key's owner). |
| `createdBy` | `string` | optional | nullable; `"FirstName LastName"` of the creator, JOINed from `users`. |
| `firstName` / `lastName` | `string` | optional | creator's first/last name (flattened audit fields, `OwnershipAuditDto`). |
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

