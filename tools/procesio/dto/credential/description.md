# Credential sub-tool

Create/edit a PROCESIO **credential instance** — saved values for a connection
template (REST API, SMTP, SQL, SFTP, OAuth2 services, …). Actions reference a
credential by its instance id.

## Config

```json
{
  "template": "REST API",
  "name": "GitHub public",
  "description": "no-auth REST",
  "properties": {
    "URL": "https://api.github.com",
    "Authentication method": "No authentication",
    "Method": "GET",
    "Test endpoint": "/zen"
  }
}
```

- **template** — the connection type **name** (from `GET /api/Credentials/types`;
  e.g. `REST API`, `Outbound e-mail (SMTP)`, `SQL`, `SFTP`).
- **properties** — property **label** (or id) → value. Secret values (passwords,
  keys) go here. For `select`/`radio` properties you may pass the option **name**
  (e.g. `"No authentication"`, `"GET"`) — it is resolved to the option's value.

## Database credentials — SQL Server, MySQL, and Redis

The DB credential type (named **`SQL`** in the live catalog) is now multi-engine: the
platform added `DbClientType.MYSQL = 2` alongside `MSSQL = 1` (Web-Api / Process-Execution
`CustomMySQLClient`, PRC-3696), so the SAME credential template creates a **MySQL**
connection by choosing the **"Server Type"** option `MySQL` (live-confirmed option value
`40404040-0001-0001-0002-cccccccccccc`; MSSQL is `…-0001-…`). No new tool code — the builder
resolves the option name to its guid like any other select property. The DB actions
(**Execute Query V3** / **Execute Command V2** — the current versions) then run against it
unchanged, and the credential's Test button opens a real `MySqlConnection`. Live property
labels on the `SQL` type: Server Type, Protocol Type, Server Name, Port Number, Database
Name, Encrypt, Pooling, Trust Server Certificate, Authentication Type, Username, Password.

```json
{
  "template": "SQL",
  "name": "reporting-mysql",
  "properties": {
    "Server Type": "MySQL",
    "Server Name": "db.internal",
    "Port Number": "3306",
    "Database Name": "reporting",
    "Username": "svc_report",
    "Password": "<secret>"
  }
}
```

**Redis** is its own standalone credential type — `CredentialsType.REDIS = 9`, NOT a
`DbClientType`/SQL sub-type (Web-Api #1452 / Action-Core #130 / Process-Execution #250).
Set `template` to `Redis` and pass its properties: **Host** (req; bare host/IP), **Port**
(6379), **Username**, **Password**, **Database** (0), **UseTls** (false),
**ValidateCertificate** (true), **ConnectTimeoutSeconds** (5), **CommandTimeoutSeconds** (5;
both >0, ≤300). Its process action is **"Redis Connector"** (pick Operation family →
Operation; 19 typed ops across Key/String, Expiration, Hash, List, Set/SortedSet, Pub/Sub;
outputs Response / Found / AffectedCount; no raw-command execution). Template GUID referenced
by the connector: `80808080-0001-0000-0000-aaaaaaaaaaaa`.

> ⚠ **Redis shipped to prod but is not yet activated** — its credential template is not
> seeded in DataBase-Update, so `Redis` does not yet appear in `GET /api/Credentials/types`
> (only 34 types today; MySQL via `SQL` is live). The contract above is stable and will
> work as-is once activated; until then a Redis credential cannot be created. Verify with
> the property/option names before relying on the literals above. (Outbound DB hosts are
> also SSRF-guarded by a host blacklist — `DbHostBlacklistChecker` — so a blacklisted /
> private host is rejected at connect time.)

## API contract (verified live 2026-06-24)

- **Validate@source:** `POST /api/Credentials/test` — a **live connection probe**
  (e.g. a real GET for REST). Run via `--dry-run` (returns the built DTO + test
  result) or automatically on create.
- **Create:** `POST /api/Credentials` (`CredentialsDto {gtid, gtpid, name, properties[]}`)
  → `{ "id": "<gid>" }`.
- **Get:** `GET /api/Credentials/{id}`.
- **Edit:** `PUT /api/Credentials` with `gid = id`.
- **Delete:** `DELETE /api/Credentials/{id}`.

## Validated status (auto)

The credential list shows **validated** / **not validated** (the DTO `status` flag).
On create/edit the builder runs `POST /api/Credentials/test`; if it returns
`isSuccess`/2xx, the credential is saved as **validated** (`status:true`). A
not-validated credential is functionally identical — this is cosmetic. To make a
credential validate, give it whatever its connection type needs to probe: for REST,
set `Method` and a `Test endpoint` (e.g. `"?cx=...&q=..."`); for SMTP the connection
probe alone suffices. **These test parameters are for validation only — they do NOT
flow into the action**, so the action still needs its own request params (e.g. Call
API's `Request Parameters` queryParams).

## Using a credential in a process

A credentials-type action property (e.g. Call API's "Select REST API credentials")
is bound by passing the credential **id** as the param value:
`"Select REST API credentials": "<credential id>"`.

## Gotchas

- `gtid`/`gtpid` are stable per template; the builder reads them from the live
  template so it never hardcodes ids.
- Some required properties are *conditional* (depend on a radio choice, e.g.
  Basic-auth fields only matter when Basic auth is selected) — send only what your
  chosen path needs.

## Editing an existing credential — what a partial `--config` silently costs

`credential-edit` builds a **whole** DTO from the config you pass; it does not
merge with what is on the server. Everything you leave out is re-derived or
sent empty, so an edit meant to change one field can quietly move several.

- **Unconditionally-required properties must be re-sent even when you are not
  changing them.** Omitting one fails the PUT with
  `{"statusCode": 113, "value": "Required credentials fields should not be
  empty.", "target": "<Property Label>"}`. The 400 names the property, so read
  `target` rather than guessing. For REST API that is at least `Method`; a
  credential that carries a test probe also needs its `Test endpoint`.
- **Re-send the current value of every property you want left alone**, read
  from `credential-get` — not typed from a console display. A value copied out
  of terminal output is truncated at the terminal width, and the edit then
  shortens the stored field to whatever fitted on screen. A description silently
  went from 183 characters to 88 this way. Read the field, pass the field.
- **`status` cannot be pinned.** The config schema refuses the key outright
  (`Additional properties are not allowed ('status' was unexpected)`), because
  it is not a setting: it is the manager list's *validated* flag, recomputed on
  every create/edit from the `POST /api/Credentials/test` probe. Expect it to
  move on any edit and report it rather than claiming the field held still.
- **The validated flag proves only what the test endpoint proves.** If the
  credential's `Test endpoint` points at an unauthenticated route, the probe
  passes with no credentials at all and *validated* says nothing about whether
  the auth material works. Only a real call through the action does.
- **Collapsable properties come back with different scaffolding after an edit.**
  The server starts emitting a `be_id` per sub-field and stops emitting
  `configurations`/`pill`, and it drops blank placeholder rows from table
  properties. None of that is a value change. When diffing a before/after
  export, reduce each property to its `{sub-field id -> value}` leaves — do not
  compare the raw blobs (five phantom differences) and do not skip the
  properties (a real change would hide).
- **⚠ The tool's response echoes secret-bearing property values back**, in both
  the dry-run DTO and the edit result. Never log, capture or persist that
  stdout. Build the config in-process from the credential store and parse the
  response rather than printing it.

## No Bearer option in the REST API template

The authentication selector offers `NoAuth`, `BasicAuth`, `ApiKey`, `OAuth2`
and `Certificate` — there is **no Bearer**. To send `Authorization: Bearer
<token>`, choose API key authentication and set `Key` = `Authorization`,
`Value` = `Bearer <token>`, with the `Header` checkbox true (it routes the pair
to a header rather than a query parameter). The auth method must be given as the
option **name** (`"API key authentication"`), not its `be_value`; a raw string
saves but fails at runtime with `Unrecognized Guid format`.
