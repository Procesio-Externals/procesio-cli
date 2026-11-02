# Calling PROCESIO from outside: Web API, Swagger, SDKs

What an external app, script or Swagger session meets when it starts a process over the REST API. Verified live against Internal-PROD in 2026-10 with a workspace-scoped API key and a cookie session. Auth itself (cookie session, key handle vs label) is in [PROCESIO-AUTH-NOTES.md](PROCESIO-AUTH-NOTES.md); this file is the caller's view.

## One host: sign-in moved into the Web API

- The docs still describe two APIs: a "Proxy API" for authentication (`auth.procesio.app`, Swagger at `auth.procesio.app/swagger`) and the Web API. The Proxy API host still resolves in DNS but no longer answers HTTPS (connection fails). Sign-in is `POST /api/Authentication` on `webapi.procesio.app`, listed in the Web API Swagger under **Authentication**.
- `POST /api/Authentication` answers `{"message": ...}` in the body; the session is the two HttpOnly cookies `__Host-procesio.access` / `__Host-procesio.refresh`. The access cookie's value is also accepted as `Authorization: Bearer <value>` (with or without `x-requested-by`), which is what Swagger's "Bearer" scheme takes.
- Swagger UI: `https://webapi.procesio.app/swagger/index.html` (spec `swagger/v1.19/swagger.json`). Security schemes: `Bearer` (Authorization header), `KeyName` (header `key`), `KeyValue` (header `value`). `workspaceId` is NOT a security scheme; it is a header parameter on each operation, so Try it out needs it typed per call.
- A browser signed in to PROCESIO carries the session cookies for the Web API host, so Swagger's Try it out works without Authorize (GET and `POST .../run` both accepted without `x-requested-by`). When a request carries both the session and a `key`/`value` pair, the key is what is checked: a wrong value answers 403 even with a valid session.

## Starting a run: `POST /api/Projects/{id}/run`

- Headers: `key` (the key's handle), `value` (its secret), `workspaceId` (GUID). Missing `workspaceId`, a different workspace's GUID, or a wrong value all answer **403 `"Unauthorized"`**; no credentials at all answer **401**. With a session instead of a key, a missing `workspaceId` answers 400 code 502 "Invalid request due to missing or incorrect resource parameters." target `flow`.
- Body: `{"payload": {<input name>: <value>, ...}}`. Inputs sent at the top level (no `payload` wrapper) answer **400 code 373 "Process needs to be valid in order to be launched."**, the same message as for a genuinely invalid process, so check the wrapper first. Swagger's example body (`"payload": "string", "connectionId": "string"`) is not runnable as is. `{"payload": {}}` starts a run with the inputs' defaults.
- No query string: answers `{"instanceId": ...}` at once; the run goes on by itself.
- `?runSynchronous=true&secondsTimeOut=N`: waits and answers `{"instanceId", "status", "variable": {<outputs>}, "error": []}` (status 50 = finished, 40 = finished with errors). If the run outlasts N seconds, the answer comes after about N seconds with `status: 0` and `variable: {}`, and the run continues; read it later from `/status`. Without `secondsTimeOut` an 8 s run was waited for in full.
- An unknown process id answers 400 code 502 target `flow`.

## Reading a run: `GET /api/Projects/instances/{id}/status`

- Needs `flowTemplateId=<process id>` in the query even though Swagger marks it optional; without it the answer is 400 code 450 "Database requested information not found." (see also the section on `/status` in [PROCESIO-API-NOTES.md](PROCESIO-API-NOTES.md)).
- The answer is `{"instance": {...}}`: `status`, `variables[]` (inputs and outputs, each value in `defaultValue`), `actions[]`, and the starter's `firstName` / `lastName`, `workspaceName`, `workspaceId`. `getActions=false` drops `actions[]` and keeps the answer short enough to read on screen.

## API keys from the caller's side

- `POST /api/ApiKey` (header `label`) answers the key with `name` (the handle sent as `key`) and `value`; `GET /api/ApiKey` lists keys without the value: it is shown once. The ApiKey endpoints refuse API-key auth (401), so the first key needs a session.

## The SDKs (state in 2026-10)

- Two public repos on github.com/PROCESIO: `procesio-sdk-typescript` and `procesio-sdk-dotnet` (NuGet `ProcesioSDK`, latest 1.1.6, `netcoreapp3.1`). Their default branches have had no code change since 2021.
- TypeScript: base URL `https://api.procesio.app` with ports 4532 (auth) and 4321 (calls), and the request helper hardcodes `:4321`, so pointing `serverName` at `webapi.procesio.app` still fails (connection time-out on 4321). Sign-in sends `realm`. Sends a `workspace` header, not `workspaceId`. The README's npm package `@procesio/procesio-sdk-typescript` is not on the npm registry (404).
- .NET: `ServerUri` / `AuthenticationUri` are configurable, but sign-in requires `realm` and `grant_type` (the old flow) and every call sends the workspace NAME in a `workspace` header. The current API ignores that header, so a workspace-scoped key answers 403 (verified by replaying the SDK's headers).
- Net: until they are updated, an external caller should call the REST API directly (or use procesio-cli).
