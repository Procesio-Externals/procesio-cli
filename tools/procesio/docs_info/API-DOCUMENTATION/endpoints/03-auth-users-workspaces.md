# Authentication, Users, Workspaces, Permissions & Preferences endpoints

> Service: **Web-Api** (public gateway) · Base URL: see [../02-conventions.md](../02-conventions.md) · Auth: see [../01-authentication.md](../01-authentication.md)
> Source controllers:
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/AuthenticationController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/UsersController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/UserPermissionsController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/UserPreferencesController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/WorkspaceController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/WorkspaceMasterController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/ProcesioAdmin/UsersController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/ProcesioAdmin/WorkspaceController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/AuthenticationProxy/ProcesioAdmin/UserPropertyController.cs`
> - `BE/Web-Api/WebApi/Application/Controllers/UsersController.cs`

This domain covers everything related to identity and tenancy in PROCESIO: logging in (password, OAuth2 SSO via external identity providers, OTP/2FA), refreshing and revoking tokens, self-service account management (sign-up, profile, password reset, OTP setup), reading the catalog of permission entities/roles/user-types and assigning them, per-user UI preferences, workspace membership and invitations, master-workspace / sub-workspace hierarchy management, and platform-admin (`ProcesioAdmin`) surfaces for managing all workspaces, user properties, referral codes and OTP resets.

Most of these controllers are thin proxies in front of the internal authentication/identity service (hence the `AuthenticationProxy` folder). All routes are served under the Web-Api gateway base URL; versioning is via the optional `x-version` header (default `1.19`). Unless noted as **Anonymous**, every endpoint requires a Bearer JWT.

**Permission model recap:** `Permission = {AuthorizationEntity}:{AuthorizationActionType}`. `Permission: None` means an authenticated caller is required but no specific entity permission is checked. The controller-level `[AuthorizationEntity(...)]` supplies the entity; the method-level `[AuthorizationAction(...)]` supplies the action.

**Cookie vs body token handling (Authentication endpoints):** the login / refresh / logout endpoints support two modes. If the request uses cookies (PROCESIO UI), tokens are set/read via HTTP-only cookies and the JSON body contains only a status message. Otherwise (backward-compatible/API clients) the full token DTO is returned in the body. This is detailed per-endpoint below.

---

## Endpoints

### AuthenticationController — `[Route("api/Authentication")]`

Controller entity: `AuthorizationEntityType.None`. Body content type is `application/json` by default, but the token-issuing actions override it to `application/x-www-form-urlencoded`.

#### `POST api/Authentication`

- **Operation:** `Authenticate` — authenticate a user with username + password (and optional OTP code), returning an access/refresh token.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/x-www-form-urlencoded`): `AuthenticateUserDto`
  - `username` — `string`, required — the user's username/email.
  - `password` — `string`, required — the user's password.
  - `code` — `string`, optional — OTP/2FA code (required only when OTP is enabled for the account/workspace).
- **Responses:**
  - `200 OK` → `AuthenticationTokenResponseDto` (body mode) **or** `{ "message": "Authentication successful" }` (cookie mode; tokens set as cookies).
  - `400 Bad Request` → `{ "error": "...", "error_description": "..." }` (cookie mode, on auth error).
- **Notes:** Behaviour depends on whether the request carries auth cookies. In cookie mode tokens are written to HTTP-only cookies and only a status message is returned; in body mode the full token DTO is returned.

#### `GET api/Authentication`

- **Operation:** `AuthenticationForm` — return the hosted authentication form/configuration for a given redirect URI (used by the login UI).
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** yes
- **Query params:** `redirect_uri` — `string`, required — URI to redirect back to after authentication.
- **Responses:**
  - `200 OK` → form/config payload (opaque object returned from the auth service).

#### `GET api/Authentication/oauth2/callback/{identityProvider}`

- **Operation:** `AuthenticateByBroker` — OAuth2 SSO callback endpoint; completes single sign-on via an external identity provider and issues PROCESIO tokens.
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** yes
- **Path params:** `{identityProvider}` — `string|number (enum IdentityProvider)`, required — the external IdP that performed the login. See `IdentityProvider` in Shared DTOs.
- **Special headers:** `referral` `[FromHeader]` — `string` — referral code carried through the SSO flow. `inviteToken` `[FromHeader]` — `string` — workspace invitation token carried through the SSO flow.
- **Responses:**
  - `200 OK` → `AuthenticationTokenResponseDto` (body mode) **or** `{ "message": "Authentication successful" }` (cookie mode), with the same `400` error shape as `POST api/Authentication`.
- **Notes:** All inbound OAuth2 query-string parameters (e.g. `code`, `state`) are forwarded to the auth service as-is. This is the redirect target configured at the external IdP.

#### `GET api/Authentication/otp/callback`

- **Operation:** `AuthenticateOTPCallback` — complete authentication after the user registers/confirms an OTP (2FA) factor.
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** yes
- **Query params:** all query-string parameters are forwarded as an opaque payload to the auth service (the OTP enrollment callback parameters).
- **Responses:**
  - `200 OK` → `AuthenticationTokenResponseDto` (body mode) **or** `{ "message": "Authentication successful" }` (cookie mode), same `400` error shape as `POST api/Authentication`.

#### `GET api/Authentication/authorize/{identityProvider}`

- **Operation:** `GetAuthorization` — build the external IdP authorization URL the client should redirect the user to in order to start SSO.
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** yes
- **Path params:** `{identityProvider}` — `string|number (enum IdentityProvider)`, required — the IdP to authorize against.
- **Query params:** `redirect_uri` — `string`, optional — URI the IdP should redirect back to after authorization.
- **Responses:**
  - `200 OK` → authorization URL / config payload (opaque).

#### `POST api/Authentication/refreshToken`

- **Operation:** `RefreshToken` — exchange a refresh token for a new access/refresh token pair.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/x-www-form-urlencoded`): `RefreshTokenRequestDto`
  - `client_id` — `string`, optional, default `procesio-ui` — realm client id.
  - `refresh_token` — `string`, required (in body mode) — the refresh token to exchange.
- **Responses:**
  - `200 OK` → `AuthenticationTokenResponseDto` (body mode) **or** `{ "message": "Token refreshed successfully" }` (cookie mode; new tokens set as cookies).
  - `400 Bad Request` → `{ "error": "invalid_request", "error_description": "Refresh token is missing" }` when no refresh token is supplied in body or cookie.
- **Notes:** In cookie mode the refresh token is read from the `COOKIE_REFRESH_TOKEN` cookie (ignoring the body) and `client_id` is forced to `procesio-ui`. Old auth cookies are cleared before new ones are set.

#### `POST api/Authentication/logOut`

- **Operation:** `Logout` — end the current session associated with the supplied (or cookie) refresh token.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/x-www-form-urlencoded`): `RefreshTokenRequestDto` (see above).
- **Responses:**
  - `204 No Content`
- **Notes:** In cookie mode the refresh token is taken from the `COOKIE_REFRESH_TOKEN` cookie. Auth cookies are deleted from the response.

#### `DELETE api/Authentication/logOut`

- **Operation:** `DeleteAllSessions` — terminate **all** active sessions for the user identified by the supplied access token.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/x-www-form-urlencoded`): single form field
  - `token` — `string`, optional — the access token whose user's sessions should all be closed. If omitted, the access token is read from the `COOKIE_ACCESS_TOKEN` cookie.
- **Responses:**
  - `204 No Content`
- **Notes:** Deletes auth cookies from the response. Same route (`logOut`) as the POST above, distinguished by HTTP verb (`DELETE`).

---

### UsersController (AuthenticationProxy) — `[Route("api/Users")]`

Controller entity: `AuthorizationEntityType.None`. Self-service user account management. Body content type `application/json`. Several endpoints add a randomized 100–300 ms delay to mitigate timing attacks (noted where present).

#### `GET api/Users/me`

- **Operation:** `GetCurrentUser` — return the currently authenticated user's profile/claims.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → current-user object (derived from the JWT claims; opaque shape).

#### `POST api/Users/otp/setup`

- **Operation:** `OtpSetup` — enable or disable OTP (2FA) for the current user.
- **Auth:** Bearer JWT — **Permission:** None
- **Special headers:** `enable` `[FromHeader]` — `boolean`, required — `true` to enable OTP, `false` to disable.
- **Responses:**
  - `200 OK` → proxied result (typically OTP enrollment data such as a secret/QR payload).

#### `POST api/Users`

- **Operation:** `CreateUser` — register/sign up a new user account.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `UserDto`
- **Responses:**
  - `200 OK` → proxied creation result.
- **Notes:** Adds a randomized 100–300 ms response delay (anti-timing-attack).

#### `PUT api/Users/details`

- **Operation:** `UpdateUserDetails` — update the current user's first/last name.
- **Auth:** Bearer JWT — **Permission:** None
- **Request body** (`application/json`): `UpdateUserDetailsDto`
- **Responses:**
  - `200 OK` → empty.
- **Notes:** Adds a randomized 100–300 ms response delay.

#### `POST api/Users/withActivation`

- **Operation:** `CreateUserWithActivationResponse` — create a user and return the activation token in the response (legacy flow, originally for AppSumo accounts).
- **Auth:** Anonymous — **Permission:** None
- **Hidden from Swagger:** yes
- **Request body** (`application/json`): `UserDto`
- **Responses:**
  - `200 OK` → activation token / proxied result.
- **Notes:** Adds a randomized 100–300 ms response delay.

#### `POST api/Users/resendToken`

- **Operation:** `RefreshCreateUserToken` — resend the account-activation token for a pending registration.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `UserDto`
- **Responses:**
  - `200 OK` → proxied result.

#### `POST api/Users/password/change`

- **Operation:** `ChangePassword` — change the password for an authenticated user given the old + new password.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `UserPasswordDto`
- **Responses:**
  - `200 OK` → proxied result.
- **Notes:** Although the route is `[AllowAnonymous]`, the DTO carries a client id + token (`IdentifyRequestDto`) identifying the user.

#### `POST api/Users/password/forgot`

- **Operation:** `ForgotPassword` — trigger the forgot-password email flow for an email address.
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `SimpleEmailDto`
- **Responses:**
  - `200 OK` → empty.
- **Notes:** Fire-and-forget — the proxy call is not awaited for its result. Adds a randomized 100–300 ms delay. Always returns `200` regardless of whether the email exists (anti-enumeration).

#### `POST api/Users/password/update`

- **Operation:** `UpdatePassword` — set a new password using a reset token (final step of the forgot-password flow).
- **Auth:** Anonymous — **Permission:** None
- **Request body** (`application/json`): `UpdatePasswordDto`
- **Responses:**
  - `200 OK` → proxied result.

---

### UserPermissionsController — `[Route("api/UserPermissions")]`

Controller entity: `AuthorizationEntityType.Workspace`. Read the permission catalog (user types, roles, entities) and read/assign user permissions within a workspace. Body content type `application/json`.

#### `GET api/UserPermissions/userTypes`

- **Operation:** `GetUserTypes` — list the available user types.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → list of user types (opaque catalog objects).

#### `GET api/UserPermissions/roles`

- **Operation:** `GetUserRoles` — list the available roles.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → list of roles.

#### `GET api/UserPermissions/entities`

- **Operation:** `GetEntities` — list the authorization entities (the resources permissions can be granted on).
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → list of entities.

#### `PUT api/UserPermissions/{userId}`

- **Operation:** `UpdateUserPermissions` — set the user type + role assignments for a target user.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Admin` (Swagger: "Permission required: Workspace.Admin")
- **Path params:** `{userId}` — `string (uuid)`, required — the user to update.
- **Query params:** `targetWorkspace` — `string (uuid)`, optional — operate on a specific workspace instead of the caller's current one.
- **Request body** (`application/json`): `UserPermissionsDto`
- **Responses:**
  - `200 OK` → empty.

#### `GET api/UserPermissions/{userId}`

- **Operation:** `GetTargetUserPermissions` — get the permissions of a specific (target) user.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Admin` (Swagger: "Permission required: Workspace.Admin")
- **Path params:** `{userId}` — `string (uuid)`, required — the user whose permissions to read.
- **Responses:**
  - `200 OK` → the user's permissions (`BaseUserPermissionsDto`-shaped, plus catalog metadata from the auth service).

#### `GET api/UserPermissions`

- **Operation:** `GetUserPermissions` — get the current authenticated user's own permissions.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → the caller's permissions.

#### `GET api/UserPermissions/workspace/{workspaceId}/default`

- **Operation:** `GetWorkspaceDefaultConfig` — get the default permission configuration for a workspace.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Admin` (Swagger: "Permission required: Workspace.Admin")
- **Path params:** `{workspaceId}` — `string (uuid)`, required — the workspace whose default config to read.
- **Responses:**
  - `200 OK` → default workspace permission config (`UPDefaultWorkspaceDto`-shaped).

---

### UserPreferencesController — `[Route("api/UserPreferences")]`

Controller entity: `AuthorizationEntityType.None`. Stores an arbitrary JSON blob of per-user UI preferences. Body content type `application/json`.

#### `GET api/UserPreferences`

- **Operation:** `GetPreferences` — get the current user's stored preferences.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → arbitrary JSON (the previously stored preferences blob).

#### `POST api/UserPreferences`

- **Operation:** `AddEditPreferences` — create or replace the current user's preferences.
- **Auth:** Bearer JWT — **Permission:** None
- **Request body** (`application/json`): arbitrary JSON (`JToken`) — any valid JSON value/object; no fixed schema.
- **Responses:**
  - `200 OK` → `"Preferences saved."` (string).

#### `DELETE api/UserPreferences`

- **Operation:** `DeletePreferences` — delete the current user's preferences.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → `"Preferences removed."` (string).

---

### WorkspaceController (AuthenticationProxy) — `[Route("api/Workspace")]`

Controller entity: `AuthorizationEntityType.Workspace`. Workspace membership: list the caller's workspaces, list/invite/revoke members. Body content type `application/json`.

> Note: this is the workspace-member controller. Sub-workspace hierarchy lives in `WorkspaceMasterController` (also `api/Workspace`, distinguished by route shape) and platform-admin workspace ops live in `ProcesioAdmin/WorkspaceController` (`api/Workspace/all`, `api/Workspace/master`, `api/Workspace/any/...`).

#### `GET api/Workspaces`

- **Operation:** `GetUserWorkspaces` — list the workspaces the current user belongs to.
- **Auth:** Bearer JWT — **Permission:** None
- **Responses:**
  - `200 OK` → list of the caller's workspaces.
- **Notes:** Note the route override: this action is served at `api/Workspaces` (plural, via `[Route("~/api/Workspaces")]`), **not** `api/Workspace`.

#### `GET api/Workspace/users`

- **Operation:** `GetWorkspaceUsers` — list (paginated) the users in a workspace.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Create` (Swagger: "Permission required: Workspace.Write")
- **Query params:**
  - `pageNumber` — `number`, required — page index.
  - `pageItemCount` — `number`, required — page size.
  - `targetWorkspace` — `string (uuid)`, optional — list users of a specific workspace instead of the caller's current one.
- **Responses:**
  - `200 OK` → paginated list of workspace users.

#### `POST api/Workspace/invite`

- **Operation:** `InviteUser` — invite a user (by email) to the workspace.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Create` (Swagger: "Permission required: Workspace.Write")
- **Query params:** `targetWorkspace` — `string (uuid)`, optional — invite into a specific workspace.
- **Request body** (`application/json`): `SimpleEmailDto`
- **Responses:**
  - `200 OK` → `"The invitation was sent."` (string).
- **Notes:** Fire-and-forget (invite send is not awaited). Adds a randomized 100–300 ms delay (anti-timing/enumeration).

#### `DELETE api/Workspace/invite/{id}`

- **Operation:** `RevokeInvitation` — revoke a pending invitation / remove a workspace membership.
- **Auth:** Bearer JWT — **Permission:** `Workspace:Update` (Swagger: "Permission required: Workspace.Update")
- **Path params:** `{id}` — `string (uuid)`, required — the invitation/membership id to revoke.
- **Query params:** `targetWorkspace` — `string (uuid)`, optional — operate on a specific workspace.
- **Responses:**
  - `200 OK` → proxied result.

---

### WorkspaceMasterController — `[Route("api/Workspace")]`

Controller entity: `AuthorizationEntityType.MasterWorkspace`. Manage the master-workspace → sub-workspace hierarchy, ownership transfer, OTP enforcement, and default workspace options. Body content type `application/json`.

#### `GET api/Workspace/{parentId}/subworkspaces`

- **Operation:** `GetSubWorkspaces` — list (paginated) the sub-workspaces under a master workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (Swagger: "Permission required: MasterWorkspace.Read")
- **Path params:** `{parentId}` — `string (uuid)`, required — the master (parent) workspace id.
- **Query params:** `pageNumber` — `number`, required; `pageItemCount` — `number`, required.
- **Responses:**
  - `200 OK` → paginated list of sub-workspaces.

#### `GET api/Workspace/{parentId}/subworkspaces/{id}`

- **Operation:** `GetSubWorkspace` — get a single sub-workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (Swagger: "Permission required: MasterWorkspace.Read")
- **Path params:** `{parentId}` — `string (uuid)`, required — master workspace id. `{id}` — `string (uuid)`, required — sub-workspace id.
- **Responses:**
  - `200 OK` → the sub-workspace object.

#### `POST api/Workspace`

- **Operation:** `CreateSubWorkspace` — create a new sub-workspace under a master workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Create` (Swagger: "Permission required: MasterWorkspace.Write")
- **Request body** (`application/json`): `CreateWorkspaceDto`
- **Responses:**
  - `200 OK` → created workspace info.

#### `PUT api/Workspace`

- **Operation:** `UpdateSubWorkspace` — update a sub-workspace (name, limits, license type, default config, settings).
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Update` (Swagger: "Permission required: MasterWorkspace.Update")
- **Request body** (`application/json`): `UpdateWorkspaceDto`
- **Responses:**
  - `200 OK` → updated workspace info.

#### `DELETE api/Workspace/{workspaceToDelete}`

- **Operation:** `DeleteSubWorkspace` — delete a sub-workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Delete` (Swagger: "Permission required: MasterWorkspace.Delete")
- **Path params:** `{workspaceToDelete}` — `string (uuid)`, required — sub-workspace id to delete.
- **Responses:**
  - `200 OK` → empty.

#### `POST api/Workspace/transfer-ownership/{coOwnerId}`

- **Operation:** `TransferOwnership` — transfer master-workspace ownership to a co-owner.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Update` (Swagger: "Permission required: MasterWorkspace.Update")
- **Path params:** `{coOwnerId}` — `string (uuid)`, required — the user id of the new owner (an existing co-owner).
- **Responses:**
  - `200 OK` → empty.

#### `GET api/Workspace/{parentId}/otp`

- **Operation:** `GetMasterWorkspaceOtpField` — check whether OTP (2FA) is enforced on a master workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (Swagger: "Permission required: MasterWorkspace.Read")
- **Path params:** `{parentId}` — `string (uuid)`, required — master workspace id.
- **Responses:**
  - `200 OK` → `{ "OtpEnabled": boolean }`.

#### `PUT api/Workspace/{parentId}/otp`

- **Operation:** `UpdateMasterWorkspaceOtpField` — enable/disable OTP enforcement on a master workspace.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Update` (Swagger: "Permission required: MasterWorkspace.Update")
- **Path params:** `{parentId}` — `string (uuid)`, required — master workspace id.
- **Query params:** `otpEnabled` — `boolean`, required — `true` to enforce OTP, `false` to disable.
- **Responses:**
  - `200 OK` → `"Enabling otp in progress."` (string).
- **Notes:** Operation is asynchronous (the response indicates progress, not completion).

#### `GET api/Workspace/settings/default`

- **Operation:** `GetDefaultWorkspaceOptions` — get the catalog of default workspace option settings.
- **Auth:** Bearer JWT — **Permission:** `MasterWorkspace:Read` (Swagger: "Permission required: MasterWorkspace.Read")
- **Responses:**
  - `200 OK` → list of default workspace option settings.

---

### UsersController (ProcesioAdmin) — `[Route("api/Users")]`

Controller entity: `AuthorizationEntityType.ProcesioAdmin`. Platform-admin user operations. Entire controller is `[ApiExplorerSettings(IgnoreApi = true)]` (hidden from Swagger). Body content type `application/json`.

> Disambiguation: same `[Route("api/Users")]` as the self-service `UsersController`, but these sub-routes (`referral-code`, `otp`) and the `ProcesioAdmin` entity distinguish it. Full paths are `api/Users/referral-code` and `api/Users/otp`.

#### `POST api/Users/referral-code`

- **Operation:** `GenerateReferralCode` — create/assign a referral code with an expiration date for a user.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes
- **Query params:**
  - `referralCode` — `string`, required — the referral code value.
  - `expirationDate` — `string (date-time, ISO-8601)`, required — when the code expires.
- **Special headers:** `userEmail` `[FromHeader]` — `string`, required — the user the referral code is for.
- **Responses:**
  - `200 OK` → proxied result.

#### `DELETE api/Users/otp`

- **Operation:** `OtpDelete` — remove/reset OTP (2FA) for a user (admin recovery).
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Delete`
- **Hidden from Swagger:** yes
- **Special headers:** `userId` `[FromHeader]` — `string (uuid)`, required — the user whose OTP to remove.
- **Responses:**
  - `200 OK` → proxied result.

---

### WorkspaceController (ProcesioAdmin) — `[Route("api/Workspace")]`

Controller entity: `AuthorizationEntityType.ProcesioAdmin`. Platform-admin workspace operations. Entire controller is `[ApiExplorerSettings(IgnoreApi = true)]` (hidden from Swagger). Body content type `application/json`.

> Disambiguation: shares `[Route("api/Workspace")]` with the member and master workspace controllers; distinguished by the `all` / `master` / `any/{id}` sub-routes and the `ProcesioAdmin` entity.

#### `GET api/Workspace/all`

- **Operation:** `GetAllWorkspaces` — list every workspace on the platform.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Admin`
- **Hidden from Swagger:** yes
- **Responses:**
  - `200 OK` → list of all workspaces.

#### `POST api/Workspace/master`

- **Operation:** `CreateMasterWorkspace` — create a new master workspace owned by a given user.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes
- **Query params:** `newMasterWorkspace` — `string`, required — the new master workspace name.
- **Special headers:** `userEmail` `[FromHeader]` — `string`, required — the owner's email.
- **Responses:**
  - `200 OK` → created master workspace info.

#### `DELETE api/Workspace/any/{workspaceToDelete}`

- **Operation:** `DeleteWorkspace` — delete any workspace, including master workspaces (admin-only capability).
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Delete`
- **Hidden from Swagger:** yes
- **Path params:** `{workspaceToDelete}` — `string (uuid)`, required — workspace id to delete.
- **Responses:**
  - `200 OK` → empty.

---

### UserPropertyController (ProcesioAdmin) — `[Route("api/UserProperty")]`

Controller entity: `AuthorizationEntityType.ProcesioAdmin`. Platform-admin CRUD over user properties (e.g. referral metadata). Entire controller is `[ApiExplorerSettings(IgnoreApi = true)]` (hidden from Swagger). Body content type `application/json`.

#### `GET api/UserProperty/all`

- **Operation:** `GetAllUserProperties` — list all user properties.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Responses:**
  - `200 OK` → array of `UserPropertyDto`.

#### `GET api/UserProperty/{id}`

- **Operation:** `GetUserProperty` — get a single user property by id.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Path params:** `{id}` — `string (uuid)`, required — user property id.
- **Responses:**
  - `200 OK` → `UserPropertyDto`.

#### `GET api/UserProperty/user/{userId}`

- **Operation:** `GetUserProperties` — list all properties belonging to a given user.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Read`
- **Hidden from Swagger:** yes
- **Path params:** `{userId}` — `string (uuid)`, required — the user id.
- **Responses:**
  - `200 OK` → array of `UserPropertyDto`.

#### `POST api/UserProperty`

- **Operation:** `CreateUserProperty` — create a user property.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Create`
- **Hidden from Swagger:** yes
- **Request body** (`application/json`): `UserPropertyDto`
- **Responses:**
  - `200 OK` → empty.

#### `PUT api/UserProperty`

- **Operation:** `UpdateUserProperty` — update a user property.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Update`
- **Hidden from Swagger:** yes
- **Request body** (`application/json`): `UserPropertyDto`
- **Responses:**
  - `200 OK` → empty.

#### `DELETE api/UserProperty/{id}`

- **Operation:** `RemoveUserProperty` — delete a user property by id.
- **Auth:** Bearer JWT — **Permission:** `ProcesioAdmin:Delete`
- **Hidden from Swagger:** yes
- **Path params:** `{id}` — `string (uuid)`, required — user property id.
- **Responses:**
  - `200 OK` → empty.

---

### UsersController (root) — `[Route("api/Users")]`

Located directly under `Controllers/` (file `Application/Controllers/UsersController.cs`). Controller entity: `AuthorizationEntityType.None`. Single self-service action that triggers the "refer a friend" process. Body content type `application/json`.

> Disambiguation: this is a third class named `UsersController`. It shares `[Route("api/Users")]` but exposes only the `refer-friend` sub-route, so the full path `api/Users/refer-friend` is unique.

#### `POST api/Users/refer-friend`

- **Operation:** `RunReferFriend` — trigger the referral ("refer a friend") flow/process with a caller-supplied payload.
- **Auth:** Bearer JWT — **Permission:** None
- **Request body** (`application/json`): `RunFlowPayload`
  - `Payload` — `object` (arbitrary), optional — the flow input payload forwarded to the referral process.
  - `ConnectionId` — `string`, optional — SignalR/connection id (used for async progress; not used by this action).
- **Responses:**
  - `200 OK` → empty (on success).
  - `400 Bad Request` → composed flow-error object (when the referral process returns errors), or `"invalid instance"` (string) when the process result is not a `FlowResponseDto`.
- **Notes:** Only the `Payload` property is forwarded to the referral process trigger.

---

## Shared DTOs

### `AuthenticateUserDto`
Form-encoded login credentials. (`[ModelBinder(Name=...)]` wire names.)

| Wire field | Type | Required | Description |
|---|---|---|---|
| `username` | `string` | required | Username / email. |
| `password` | `string` | required | Password. |
| `code` | `string` | optional | OTP/2FA code (when OTP is enabled). |

### `RefreshTokenRequestDto`
Form-encoded refresh/logout request. (`[ModelBinder(Name=...)]` wire names.)

| Wire field | Type | Required | Description |
|---|---|---|---|
| `client_id` | `string` | optional (default `procesio-ui`) | Realm client id. |
| `refresh_token` | `string` | required | Refresh token to exchange/revoke. |

### `AuthenticationTokenResponseDto`
Token response (body mode). (`[JsonProperty]` wire names.)

| Wire field | Type | Required | Description |
|---|---|---|---|
| `access_token` | `string` | required | JWT access token. |
| `expires_in` | `number` | required | Access token lifetime (seconds). |
| `refresh_expires_in` | `number` | required | Refresh token lifetime (seconds). |
| `refresh_token` | `string` | required | Refresh token. |
| `token_type` | `string` | required | Token type (e.g. `Bearer`). |
| `session_state` | `string` | optional | IdP session state. |
| `scope` | `string` | optional | Granted scopes. |
| `error` | `string` | optional | Error code (present on failure). |
| `error_description` | `string` | optional | Human-readable error detail. |

### `UserDto`
User registration / account payload. (`[JsonProperty]` wire names.)

| Wire field | Type | Required | Description |
|---|---|---|---|
| `firstName` | `string` | optional | First name. |
| `lastName` | `string` | optional | Last name. |
| `email` | `string` | optional | Email address. |
| `userName` | `string` | optional | Username. |
| `inviteToken` | `string` | optional | Workspace invitation token (sign-up via invite). |
| `referral` | `string` | optional | Referral code. |
| `extraData` | `object (UserExtraDataDto)` | optional | Extra account data. |

### `UserExtraDataDto`
| Wire field | Type | Required | Description |
|---|---|---|---|
| `hours` | `number` | optional | Allotted hours (nullable `int?`). |

### `UpdateUserDetailsDto`
| Wire field | Type | Required | Description |
|---|---|---|---|
| `firstName` | `string` | optional | First name. |
| `lastName` | `string` | optional | Last name. |

### `IdentifyRequestDto` (base of `UserPasswordDto`)
| Wire field | Type | Required | Description |
|---|---|---|---|
| `clientId` | `string` | optional | Realm client id. |
| `token` | `string` | optional | Authentication token identifying the user. |

### `UserPasswordDto` (extends `IdentifyRequestDto`)
Inherits `clientId`, `token` plus:

| Wire field | Type | Required | Description |
|---|---|---|---|
| `oldPassword` | `string` | optional | Current password. |
| `newPassword` | `string` | optional | New password. |

### `UpdatePasswordDto`
| Wire field | Type | Required | Description |
|---|---|---|---|
| `token` | `string` | optional | Password-reset token. |
| `password` | `string` | optional | New password. |

### `SimpleEmailDto`
| Wire field | Type | Required | Description |
|---|---|---|---|
| `email` | `string` | optional | Email address. |

### `BaseUserPermissionsDto`
No `[JsonProperty]` attributes → Newtonsoft default (PascalCase wire names as written).

| Wire field | Type | Required | Description |
|---|---|---|---|
| `UserTypeId` | `string (uuid)` | required | User type id. |
| `Roles` | `object` — map of `string (uuid)` → `array of string (uuid)` | optional | Per-entity role assignments: keyed by entity/workspace id, value is the list of role ids. |

### `UserPermissionsDto`
Empty subclass of `BaseUserPermissionsDto` — same fields (`UserTypeId`, `Roles`).

### `UPDefaultWorkspaceDto`
Empty subclass of `BaseUserPermissionsDto` — same fields (`UserTypeId`, `Roles`).

### `SimpleWorkspaceDto` (base of `UpdateWorkspaceDto`)
| Wire field | Type | Required | Description |
|---|---|---|---|
| `workspace` | `string` | optional | Workspace name. |
| `id` | `string (uuid)` | optional | Workspace id (nullable `Guid?`). |
| `parentId` | `string (uuid)` | optional | Parent (master) workspace id (nullable `Guid?`). |

### `CreateWorkspaceDto`
| Wire field | Type | Required | Description |
|---|---|---|---|
| `workspaceName` | `string` | optional | New workspace name. |
| `userEmail` | `string` | optional | Owner email. |
| `parentId` | `string (uuid)` | optional | Parent (master) workspace id (nullable `Guid?`). |
| `canExceedPaidTime` | `boolean` | required | Whether the workspace may exceed paid execution time. |
| `defaultWorkspaceConfiguration` | `object (UPDefaultWorkspaceDto)` | optional | Default permission configuration. |
| `settings` | `array of WorkspaceOptionsSettingDto` | optional | Workspace option settings. |

### `UpdateWorkspaceDto` (extends `SimpleWorkspaceDto`)
Inherits `workspace`, `id`, `parentId` plus:

| Wire field | Type | Required | Description |
|---|---|---|---|
| `canExceedPaidTime` | `boolean` | required | Whether the workspace may exceed paid execution time. |
| `maxThreads` | `number` | required | Max concurrent execution threads. |
| `licenseType` | `string|number (enum LicenseType)` | required | License type. See `LicenseType`. |
| `defaultWorkspaceConfiguration` | `object (UPDefaultWorkspaceDto)` | optional | Default permission configuration. |
| `settings` | `array of WorkspaceOptionsSettingDto` | optional | Workspace option settings. |

### `WorkspaceOptionsSettingDto`
No `[JsonProperty]` attributes → Newtonsoft default (PascalCase wire names).

| Wire field | Type | Required | Description |
|---|---|---|---|
| `WorkspaceOptionId` | `string (uuid)` | required | The workspace option being set. |
| `Value` | `JToken` (arbitrary JSON) | required | The option value (any JSON; `required` modifier in source). |

### `UserPropertyDto`
No `[JsonProperty]` attributes → Newtonsoft default (PascalCase wire names).

| Wire field | Type | Required | Description |
|---|---|---|---|
| `Gid` | `string (uuid)` | required | User property id. |
| `UserId` | `string (uuid)` | required | Owning user id. |
| `Type` | `string|number (enum UserPropertyType)` | required | Property type. See `UserPropertyType`. |
| `Value` | `string` | optional | Property value. |
| `Data` | `string` | optional | Extra info (e.g. expiration date). |

### `RunFlowPayload`
No `[JsonProperty]` attributes → Newtonsoft default (PascalCase wire names).

| Wire field | Type | Required | Description |
|---|---|---|---|
| `Payload` | `object` (arbitrary) | optional | Flow input payload. |
| `ConnectionId` | `string` | optional | SignalR/connection id. |

### Enums

#### `IdentityProvider` (external SSO providers)
| Name | Value |
|---|---|
| `none` | 0 |
| `azureAD` | 1 |
| `google` | 2 |
| `github` | 3 |

#### `LicenseType`
| Name | Value |
|---|---|
| `None` | 0 |
| `Time` | 1 |
| `Thread` | 2 |

#### `UserPropertyType`
| Name | Value |
|---|---|
| `NONE` | 0 |
| `REFERRAL` | 1 |
| `REFERRAL_USED` | 2 |
