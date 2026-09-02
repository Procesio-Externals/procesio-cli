# Authentication & Authorization

> Audience: an integrator (human or AI) building an application whose backend is the PROCESIO microservices platform.
> Source of truth: `BE/Web-Api/WebApi/Application/Middleware/*`, `Application/Controllers/AuthenticationProxy/AuthenticationController.cs`, `Domain/Constants/TokenConstants.cs`, `Domain/Enums/Authentication*` , `Domain/Enums/Authorization/*`.

Everything an external client talks to goes through the **Web-Api gateway**. The gateway runs a fixed middleware chain on every request:

```
HTTP request
  → LoggingMiddleware          (request/response logging)
  → SecureInternalRequests     (only for internal/ endpoints — see §6; 404 if headers missing)
  → DeserializeToken           (detect auth mode, parse JWT claims into internal headers)
  → Authentication             (validate the token against Authentication-Proxy/Keycloak)
  → GetUserFromToken           (hydrate the user context)
  → Authorization              (enforce the per-route permission)
  → Controller
```

Identity itself (users, passwords, sessions, OTP, social login) lives in **Keycloak**, fronted by the **Authentication-Proxy** service. Web-Api never stores passwords — it forwards credentials to the proxy and returns the issued tokens.

---

## 1. The three authentication modes

`DeserializeToken` picks the mode automatically from the headers present (`Domain/Enums/AuthenticationTypes.cs → WebApiAuthTypes`):

| Mode | How the gateway detects it | Use it for |
| --- | --- | --- |
| **Bearer JWT** (`Token = 0`) | `Authorization: Bearer <jwt>` header **or** an access-token cookie | Interactive apps, server-to-server with a logged-in user |
| **API key** (`ApiKey = 1`) | Both `key` and `value` headers present | Headless/machine integrations, scripts, webhook producers |
| **Anonymous** (`Anonymous = 2`) | Neither of the above, and the endpoint is `[AllowAnonymous]` | Login, token refresh, inbound webhook trigger, public forms, custom-URL launches |

If an endpoint requires auth and none is supplied, the gateway returns **`401 Unauthorized`** (cookie clients may instead get a `307` auto-refresh redirect — see §4).

---

## 2. Logging in (Bearer JWT) — `POST api/Authentication`

This is the entry point that mints a token from a username + password.

- **Method/route:** `POST {baseUrl}/api/Authentication`
- **Auth:** Anonymous
- **Content-Type:** `application/x-www-form-urlencoded` (note: **form fields, not JSON**)
- **Body** (`AuthenticateUserDto`):

  | Form field | Type | Required | Notes |
  | --- | --- | --- | --- |
  | `username` | string | yes | The PROCESIO account username/email |
  | `password` | string | yes | |
  | `code` | string | no | One-time code (OTP/MFA), when the account requires it |

- **Response `200 OK`** (`AuthenticationTokenResponseDto`, JSON; returned in the body **only when the client is not using cookies** — see §4):

  | JSON field | Type | Meaning |
  | --- | --- | --- |
  | `access_token` | string (JWT) | Send as `Authorization: Bearer <access_token>` on later calls |
  | `expires_in` | number (seconds) | Access-token lifetime |
  | `refresh_token` | string (JWT) | Used to obtain a new access token |
  | `refresh_expires_in` | number (seconds) | Refresh-token lifetime |
  | `token_type` | string | Usually `Bearer` |
  | `session_state` | string | Keycloak session id |
  | `scope` | string | Granted scopes |
  | `error` | string | Present on failure (e.g. `invalid_grant`) |
  | `error_description` | string | Human-readable failure reason |

**Example**

```bash
curl -X POST "https://api.procesio.app/api/Authentication" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "username=alice@example.com" \
  --data-urlencode "password=•••••••••"
# → { "access_token": "eyJ...", "expires_in": 300, "refresh_token": "eyJ...", ... }
```

Then call any protected endpoint:

```bash
curl "https://api.procesio.app/api/Projects" \
  -H "Authorization: Bearer eyJ..." \
  -H "x-version: 1.19"
```

### Single sign-on (SSO)
For social / external IdP login the proxy exposes a redirect-based OAuth2 flow (all Anonymous, mostly hidden from Swagger):
- `GET api/Authentication/authorize/{identityProvider}?redirect_uri=...` → returns the IdP authorization URL.
- `GET api/Authentication/oauth2/callback/{identityProvider}` → IdP redirects here; PROCESIO completes login and issues tokens.
- `GET api/Authentication/otp/callback` → OTP completion.

`identityProvider` is the `IdentityProvider` enum (see `03-auth-users-workspaces.md`).

---

## 3. Refreshing & ending a session

| Action | Endpoint | Body (`x-www-form-urlencoded`) |
| --- | --- | --- |
| Refresh access token | `POST api/Authentication/refreshToken` | `refresh_token` (required), `client_id` (default `procesio-ui`) |
| Log out current session | `POST api/Authentication/logOut` | `refresh_token` |
| Log out **all** sessions | `DELETE api/Authentication/logOut` | `token` (an access token) |

All three are Anonymous (they authenticate by possession of the refresh/access token itself).

---

## 4. Two client styles: token-in-body vs. cookie (BFF)

The same auth endpoints serve two client styles, decided by whether the request carries the PROCESIO UI cookie marker:

- **Programmatic clients (recommended for integrations):** do **not** use cookies. `POST api/Authentication` returns the full `AuthenticationTokenResponseDto` in the body. You store `access_token` and send it as `Authorization: Bearer ...`. You refresh manually via `refreshToken`.
- **Browser/BFF clients (the PROCESIO SPA):** the gateway sets HTTP-only cookies `__Host-procesio.access` / `__Host-procesio.refresh` (`__Dev-` prefix in debug builds) and returns only `{ "message": "Authentication successful" }`. When the access token expires, the gateway transparently refreshes from the cookie and replies `307 Temporary Redirect` to the same path so the browser retries with fresh cookies. A `x-session-expires-at` response header carries the refresh-token expiry.

> For an app builder, prefer the **token-in-body** style — it is stateless and predictable. Only the official SPA needs the cookie path.

---

## 5. API keys (headless auth) — alternative to JWT

API keys let a machine integration authenticate without a user login. They are **workspace-scoped** and managed under `api/ApiKey` (see `12-webhooks-notifications-misc.md`).

- **Create:** `POST api/ApiKey` (JWT-authenticated) returns the secret **once**. A user may hold up to **25** keys.
- **Use:** send two headers on every request:

  | Header | Value |
  | --- | --- |
  | `key` | the 16-char key **name** |
  | `value` | the 64-char key **secret** |

  Optionally set `auth_type: 1` to force API-key mode. The gateway looks the key up within its workspace, checks it is active, and validates the secret against a stored hash.

```bash
curl "https://api.procesio.app/api/Projects" \
  -H "key: myintegrationkey" \
  -H "value: <64-char-secret>" \
  -H "x-version: 1.19"
```

> **Restriction:** API-key requests are explicitly **rejected by every `api/ApiKey` management endpoint** — you must use a JWT to create/list/delete keys. API keys are for calling the *rest* of the API.

---

## 6. Authorization model — permissions per endpoint

Once authenticated, the `Authorization` middleware enforces a permission derived from two attributes on the controller/action:

- **Entity** — `[AuthorizationEntity(AuthorizationEntityType.X)]` (controller level). Values (`Domain/Enums/Authorization/AuthorizationEntityType.cs`):

  `MasterWorkspace(1)`, `Workspace(2)`, `ProcessDesigner(3)`, `ProcessInstance(4)`, `CustomActions(5)`, `DataModels(6)`, `Credentials(7)`, `DocumentDesigner(8)`, `Webhook(9)`, `Schedule(10)`, `ApiKey(11)`, `FormTemplate(12)`, `FormInstance(13)`, `DataStore(14)`, `ProcesioAdmin(101)`, `None(102)`.

- **Action** — `[AuthorizationAction(AuthorizationActionType.X)]` (method level). Values (`AuthorizationActionType.cs`):

  `None(1)` = authenticated but no specific permission required · `Read(2)` · `Update(3)` · `Create(4)` · `Delete(5)` · `Admin(6)`.

The effective permission documented per endpoint is written **`Entity:Action`** (e.g. `ProcessInstance:Read`, `Credentials:Create`). `Permission: None` means "any authenticated caller". `ProcesioAdmin:*` endpoints require platform-admin rights and are typically hidden from Swagger (but still reachable).

> **Internal endpoints are out of scope for external clients.** Routes beginning with `internal/` (and controllers marked `[SecureInternalController]`) require the `prc-service` + `prc-code` headers and return **404** to anyone else. They are service-to-service only and are *not* documented in the endpoint reference. See [Appendix: internal & inter-service surface](endpoints/99-internal-and-other-services.md).

---

## 7. Workspace context

PROCESIO is multi-tenant via **workspaces**. A user belongs to one or more workspaces under a **master workspace**. Most data operations are scoped to the "active" workspace:

- The active workspace is normally encoded in the JWT, but many endpoints accept an explicit override:
  - Header `workspaceId: <guid>`, or
  - Query param `targetWorkspace=<guid>` (declared via the `[HasOptionalParameter]` filter on endpoints that support switching).
- Master-workspace-level operations use the `MasterWorkspace` entity; per-workspace operations use `Workspace`.

When building an app that spans multiple workspaces, pass the target workspace explicitly on each call rather than relying on a default.

---

## 8. Quick-start checklist for an integration

1. **Get a token:** `POST /api/Authentication` (form-urlencoded) → keep `access_token` + `refresh_token`. *(Or create an API key in the UI and use `key`/`value` headers.)*
2. **Always send** `Authorization: Bearer <token>` (or `key`+`value`) and `x-version: 1.19`.
3. **Pick the workspace** with `workspaceId`/`targetWorkspace` when needed.
4. **Refresh** before `expires_in` elapses via `POST /api/Authentication/refreshToken`.
5. **Call the domain endpoints** documented in [`endpoints/`](endpoints/). The most common goal — *run an automation* — is in [`04-processes.md`](endpoints/04-processes.md).
6. **For realtime results** (async action/test/CSV runs) open the SignalR hub — see [`13-realtime-signalr.md`](endpoints/13-realtime-signalr.md).
