# Realtime (SignalR) endpoints

> Service: **System-Notifications** · Auth: see [../01-authentication.md](../01-authentication.md) · Conventions: see [../02-conventions.md](../02-conventions.md)
> Source: `BE/System-Notifications/Notifications/Application/Hubs/MessageHub.cs`, `.../Application/Program.cs`, `.../Application/Extensions/ServiceExtensions.cs`, `.../Application/Managers/EventsManager.cs`, `.../Application/BLL/EventsBll.cs`, `.../Application/BLL/NotificationsBll.cs`, `.../Domain/Constants/NotificationConstants.cs`

PROCESIO pushes realtime results to client apps over a single **ASP.NET Core SignalR hub** hosted by the **System-Notifications** microservice. This is the channel that delivers asynchronous outcomes for operations a client kicks off via the Web-Api gateway (flow runs, connector actions, test actions, webhook test data, CSV import/export jobs) and live "data changed" pings (user rights, workspace membership, resource limits, in-app announcements).

The client never sends business data **up** the hub. The hub is a one-way realtime delivery channel: the client connects, learns its `ConnectionId`, hands that id to the relevant **Web-Api REST endpoint**, and then receives the result as a server→client event on the hub. All "produce a notification" operations are internal (service-to-service) and are not callable by a client app.

---

## Connection

### Hub URL & transport

- **Hub path:** `/hub/notification` (constant `NotificationConstants.HUB_PATH`, registered via `app.MapHub<MessageHub>(...)`).
- **Host:** the System-Notifications service. In Kubernetes it listens on port `8000`. The public/ingress origin is environment-specific — use the realtime/notifications base URL configured for your environment (it is a different host from the Web-Api gateway base URL). It is **not** served under the Web-Api `/api` gateway path.
- **Transport:** standard SignalR negotiation. WebSockets are explicitly enabled server-side (`app.UseWebSockets`, 30s keep-alive) and are the primary transport; SignalR's normal fallbacks (Server-Sent Events, long polling) apply if WebSockets are unavailable.
- **Protocol:** JSON. The server uses the SignalR JSON protocol with **PascalCase preserved** (`PropertyNamingPolicy = null`) — i.e. payload property names are sent verbatim as listed below (note the mixed casing: some payloads are camelCase by design, see each event).
- **Keep-alive / timeouts (server):** `KeepAliveInterval = 20s`, `ClientTimeoutInterval = 90s`. Configure the client accordingly (a SignalR client default keep-alive/timeout is compatible).
- **CORS:** the hub requires the `CorsPolicy` (origins are configured per environment; credentials allowed). Connect from an allowed origin.

### Authentication

- **No JWT / bearer auth is enforced on the hub.** The hub class has no `[Authorize]` attribute and the service does **not** register authentication middleware (`Program.cs` calls `UseAuthorization()` but there is no `UseAuthentication()` and no JWT bearer setup). Do not send an `Authorization` header or `access_token` to the hub — it is ignored.
- **Identity is established by a query-string parameter.** On connect, pass the caller's user id as the `userId` query parameter (constant `HUB_USER_ID_QUERY_PARAM = "userId"`):

  ```
  /hub/notification?userId=<user-guid>
  ```

  - If `userId` is a valid non-empty GUID, the server records the mapping `userId → ConnectionId` in an in-memory cache, so the service can later push **per-user** "data changed" events to every live connection that user holds.
  - If `userId` is missing, empty, or not a GUID, the connection is treated as **anonymous**: it still connects and still receives `ConnectionId`-targeted events (flow/action/CSV results keyed off the connection id) and group broadcasts, but it will **not** receive per-user events.

- **Trust model:** because the hub does not validate the token, `userId` is self-asserted. Treat the hub as an internal-network component fronted by your trusted client; do not rely on it for authorization decisions.

### Connection lifecycle (server behaviour)

- **OnConnectedAsync:** logs the connection, registers `userId → ConnectionId` (if provided), and adds the connection to the group `Procesio_Users` (constant `PROCESIO_GROUP_NAME`).
- **OnDisconnectedAsync:** removes the connection from the `Procesio_Users` group and evicts it from the user-connection cache.

---

## Client → server methods (invokable on the hub)

The hub exposes exactly **one** invokable method. (`MessageHub : Hub` — the only public instance method besides the framework `OnConnected`/`OnDisconnected` overrides.)

### `GetConnectionId`

- **Invoke:** `connection.invoke("GetConnectionId")`
- **Params:** none
- **Returns:** `string` — the current connection's SignalR `ConnectionId`.
- **Purpose:** the client calls this immediately after connecting to obtain its `ConnectionId`, which it then passes to Web-Api REST endpoints so their async results are routed back to this exact connection. (The same value is available client-side as `connection.connectionId` once connected; this method is the server-confirmed equivalent.)

> There are **no other** client→server hub methods. The client cannot publish notifications, join custom groups, or send messages through the hub.

---

## Server → client events (messages the client must handle)

Register a handler (`connection.on("<event>", payload => ...)`) for each event below. The server sends each event with a **single argument** (the payload). Events are delivered one of three ways:

- **To a specific connection** — `Clients.Client(connectionId).SendAsync(...)` — used for results of operations the client started and tagged with its `ConnectionId`.
- **To a specific user's live connections** — looked up from the `userId→ConnectionId` cache — used for "your data changed" pings.
- **Broadcast to the `Procesio_Users` group** — `Clients.Group("Procesio_Users").SendAsync(...)` — used when an event has no target connection id.

| Event name (wire) | Constant | Delivery | Payload |
|---|---|---|---|
| `instance-ran` | `HUB_SEND_METHOD_FLOW_INSTANCE` | per-connection | `FlowStatusPayload` |
| `debugger-action-done` | `FLOW_DEBUGGER_ACTION_DONE` | per-connection | `FlowStatusPayload` |
| `test-action` | `HUB_SEND_METHOD_TEST_ACTION` | per-connection (or group if no connection id) | `EventPayload` |
| `design-time-run` | `HUB_SEND_METHOD_DESIGN_TIME_RUN` | per-connection (or group) | `EventPayload` |
| `global-form-app` | `HUB_SEND_METHOD_FORM_APPLICATION` | per-connection (or group) | `EventPayload` |
| `generate-data` | `HUB_SEND_METHOD_TEST_WEBHOOK` | per-connection | `WebhookTestPayload` |
| `entity-updated` | `HUB_SEND_METHOD_ENTITY_UPDATED` | per-connection (per user) / default fallback | `EventPayload` *or* a serialized notification message (see notes) |
| `user-data-updated` | `HUB_SEND_METHOD_USER_DATA_UPDATED` | per-user connections | empty string `""` (signal only) |
| `resources-updated` | `HUB_SEND_METHOD_RESOURCES_UPDATED` | per-user connections | empty string `""` (signal only) |

### Event payload shapes

#### `FlowStatusPayload` — for `instance-ran`, `debugger-action-done`
Source: `Domain/Data/FlowStatusModel.cs`. Property names are intentionally **camelCase**.
- `instanceId` — `string (uuid)` — the flow instance that ran.
- `processId` — `string (uuid)` — the process/flow id.
- `workspaceId` — `string (uuid)` or `null` — workspace id (null when empty/unset).

#### `EventPayload` — for `test-action`, `design-time-run`, `global-form-app`, and most `entity-updated`
Anonymous object projected from `EventDto` (`Infrastructure.Core/DTOs/EventDto.cs`). Property names are **PascalCase**.
- `Id` — `string (uuid)` — entity/action id the event concerns.
- `WorkspaceId` — `string (uuid)` or `null`.
- `Title` — `string` or `null`.
- `Message` — `string` or `null`.
- `Status` — `string` or `null` — operation status text.

#### `WebhookTestPayload` — for `generate-data`
Anonymous object built in `EventsManager.OnWebhook`. Property names are **camelCase**.
- `listenType` — `number (int)` — webhook listen type code.
- `payload` — `string` — the captured webhook payload (raw string).

#### `entity-updated` — secondary shape
In addition to `EventPayload`, the workspace "simple notification" path (`NotificationsBll.SendWorkspaceNotifications`) sends `entity-updated` with the payload being a **JSON-serialized string** of a notification message:
- `title` — `string` — notification title.
- `message` — `string` — notification body.
- `workspaceId` — `string (uuid)` — target workspace.

Clients should be prepared to accept the argument as either an object (`EventPayload`) or a JSON string (parse it) depending on source.

#### `user-data-updated`, `resources-updated` — signal-only
Sent with an **empty string** argument. They carry no data; they are a cue for the client to refetch the relevant resource (e.g. re-load the user's notifications inbox, permissions, or resource/usage limits) from the Web-Api. `user-data-updated` fires on user-rights / workspace-membership / new-notification changes; `resources-updated` fires on usage/paid-time/limit changes.

> **Note on event-name derivation:** for the generic `EventDto` events, the server maps the DTO's `Type` (enum `EventType`) to the event name via `EventType.GetEventName()`: `TestAction→test-action`, `TestWebhook→generate-data`, `UserData→user-data-updated`, `Resources→resources-updated`, `Entity→entity-updated`, `FlowInstance→instance-ran`, `FormApplication→global-form-app`, `DesignTimeActionRun→design-time-run`. Unknown types default to `entity-updated`.

---

## Group / connection semantics

- **`Procesio_Users` group:** every connection (authenticated or anonymous) is auto-joined on connect. Used only for **broadcasts** — i.e. generic `EventDto` events that arrive without a `ConnectionId` are fanned out to all connected clients. There is **no per-workspace group**; workspace targeting is done by resolving workspace members to user ids, then to their cached connection ids.
- **Per-connection targeting:** results of client-initiated operations are delivered only to the originating connection, matched by the `ConnectionId` the client supplied to the REST endpoint.
- **Per-user targeting:** "data changed" signals (`user-data-updated`, `resources-updated`, and new-notification pings) are delivered to **all** live connections registered for the affected user id(s) in the in-memory cache. A user with multiple tabs/devices receives the signal on each.
- **No reconnect persistence:** the connection cache and group membership are in-memory and per-instance. On reconnect the client gets a **new** `ConnectionId` and must re-fetch it via `GetConnectionId` and re-supply it on subsequent REST calls. Events missed while disconnected are not replayed (except inbox notifications, which are persisted server-side and re-fetched on the `user-data-updated` signal).

---

## Public REST endpoints in System-Notifications

**None.** Both controllers in this service — `NotificationsController` (`api/Notifications`, the notification inbox: list, list-in-workspace, acknowledge, store) and `EventsController` (`api/Events`) — are decorated with `[SecureInternalController]` and every action is `[ApiExplorerSettings(IgnoreApi = true)]`. The `SecureInternalRequests` middleware rejects any request to these endpoints that lacks valid `prc-service` + `prc-code` service headers (returning `404 Not Found`). They are **inter-service only** and are out of scope for a client app.

A client app reads/acknowledges its **notification inbox** through the **Web-Api gateway**, not this service. When `user-data-updated` arrives over the hub, the client should re-fetch the inbox from the corresponding Web-Api endpoint. (See the notifications domain doc for those public REST endpoints and their DTOs.)

---

## Obtaining & using a `connectionId` with Web-Api endpoints

The hub is the realtime channel for the Web-Api operations that return asynchronously. The connection model is:

1. **Connect** to `/hub/notification?userId=<user-guid>` on the System-Notifications host and wait for the connection to be established.
2. **Get the connection id** — either read `connection.connectionId` client-side, or invoke `GetConnectionId` on the hub.
3. **Pass that `connectionId` to the Web-Api REST endpoint** that starts the work. The endpoint accepts it either in the request body or as a header, depending on the operation:
   - **Connector actions** — body field `ConnectionId` on `ConnectorActionRequestDto` (`Web-Api/.../DTO/ConnectorActions/ConnectorActionRequestDto.cs`).
   - **Test actions** — body field `ConnectionId` on `DetailedTestActionRequestDto` (`Web-Api/.../DTO/FlowTemplate/DetailedTestActionRequestDto.cs`).
   - **CSV import/export** (Data Store) — `connectionId` **`[FromHeader]`** on `POST api/DataStore/{dataStoreId}/export-start` and `POST api/DataStore/{dataStoreId}/import-start` (`Web-Api/.../Controllers/DataStore/DataStoreCsvController.cs`). The Web-Api forwards it as `ConnectionId` to the System-Notifications event endpoints.
   - **Flow runs / webhook tests** similarly carry a `ConnectionId` so their `instance-ran` / `generate-data` results are routed back.
4. **Handle the matching server→client event** on the hub (e.g. `test-action`, `instance-ran`, `generate-data`) — the result arrives on the connection whose id you supplied.

> Do **not** re-document those Web-Api REST endpoints here — see their respective domain docs. The takeaway: the `connectionId` they reference is the SignalR `ConnectionId` from **this** hub.

---

## Shared DTOs

- **`FlowStatusPayload`** (`FlowStatusModel`): `instanceId` `string(uuid)`, `processId` `string(uuid)`, `workspaceId` `string(uuid)|null`. Wire names camelCase.
- **`EventPayload`** (projection of `EventDto`): `Id` `string(uuid)`, `WorkspaceId` `string(uuid)|null`, `Title` `string|null`, `Message` `string|null`, `Status` `string|null`. Wire names PascalCase.
- **`WebhookTestPayload`** (anonymous): `listenType` `number(int)`, `payload` `string`. Wire names camelCase.
