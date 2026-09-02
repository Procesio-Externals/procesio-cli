# procesio

Talk to the **PROCESIO** low-code automation platform (procesio.app / procesio.com)
over its Web API. Run processes, read instances / workspaces / data-types / the
action catalog, and reach **every** documented endpoint through a generic
`request` action.

## Capabilities are ACTIONS — list them, don't reimplement

> If you want to *do* something to PROCESIO, there is almost certainly already an
> action for it. **List them first — never reimplement a capability the notes
> describe as a recipe:** `python scripts/run-tool.py procesio` prints all ~330.
> Curated (ergonomic) actions win; a raw `<method>-<path>` wrapper or `request`
> is the fallback only when no curated action fits.

| Want to… | Action(s) |
|---|---|
| **Build** a process / form / document / webhook / credential / data model | `process-create` · `form-create` · `document-create` · `webhook-create` · `credential-create` · `datatype-create` (+ each `*-edit`) |
| **Get / list / delete** any of those | `<res>-get` · `list-processes`/`form-list`/`document-list`/`list-datatypes` · `<res>-delete` |
| **Run / validate / activate** a process | `run-process` (`--synchronous`) · `process-validate` · `process-toggle-activation` |
| **Duplicate / copy** a process or form | `duplicate-process` · `form-duplicate` |
| **Export / import** a `.procesio` bundle | `export` · `import` |
| **Test** a credential / a custom action (the oracles) | `credential-test` · `customaction-test` |
| **Custom actions** (connectors): install / delete / list | `customaction-upload` · `customaction-delete` · `customaction-list` |
| **Download** a flow-instance file (PDF etc.) | `file-download` (`--from-run`) |
| **Launch** a webhook-triggered process | `webhook-launch` |
| **Canvas layout / flow graph** (offline) | `layout-flow` · `verify-layout` · `read-flow-graph` · `inspect-flow` · `layout-resource-map` · `relayout-process` |
| **Rename canvas actions** in bulk (kill the default `Node` / `Call API` labels) | `rename-actions` (`--map` / `--map-file`, `--dry-run`) |
| **Data-model lifecycle** | `datatype-add-attribute` · `datatype-change-to-public` · `datatype-clone` · `datatype-get`/`-delete` |
| **Schedules** | `create-schedule` / `get-schedule` / `update-schedule` / `delete-schedule` / `list-schedules` / `set-schedule-status` |
| Anything else (raw 1:1) | `<method>-<path>` (e.g. `post-actions-test`) or `request --method --path` |

## Authentication — two modes, many credentials

PROCESIO supports two auth modes, and this tool keeps **multiple named
credential profiles** so you can switch accounts/keys with `--profile`:

| Mode | How it authenticates | Access |
|------|----------------------|--------|
| **apikey** | three request headers `key`, `value`, `workspaceid` | one workspace |
| **userpass** | form login on `webapi/api/authentication` → `__Host-procesio` **cookie session** (+ `x-requested-by`) | everything the UI has |

> **Prefer `userpass` when you have a choice.** It carries the user's full access
> (owner/admin + cross-workspace), so it reaches endpoints an API key can't — e.g.
> listing a master workspace's sub-workspaces returns 401 for an API key but 200
> for userpass. Use an API key only to pin to a single workspace. The stored default profile is `account` (userpass).

Secrets live **only** in the OS credential store - Windows Credential Manager,
the macOS login Keychain, or the Linux desktop keyring - under
`agents-and-tools:procesio:cred-<name>`, never on disk. The non-secret index
(`…:procesio:credentials`) lists which profiles exist.

### Manage credentials

```powershell
# list profiles (names/types/workspaces only — never secrets)
python scripts/run-tool.py procesio list-credentials

# add an API key (workspace-scoped). workspace-id is the workspace GUID.
python scripts/run-tool.py procesio add-credential `
  --name personal --type apikey --key <KEY> --value <VALUE> `
  --workspace-id <GUID> --workspace "My workspace"

# add a username/password account (full access)
python scripts/run-tool.py procesio add-credential `
  --name account --type userpass --username me@example.com --password '<PW>'

python scripts/run-tool.py procesio set-default --name account
python scripts/run-tool.py procesio remove-credential --name old
```

> **API-key `workspaceid`.** Most workspace-scoped keys require the `workspaceid`
> header (the workspace GUID) to authenticate — without it you get `401`. A
> master/personal key may work without one. Find a workspace's GUID with
> `list-workspaces` (the `id` field).

### Verify

```powershell
python scripts/run-tool.py procesio check-auth --profile personal
python scripts/run-tool.py procesio login --profile account   # caches the Bearer token
```

## Endpoints — full 1:1 coverage

**Every** Web-API endpoint (247 of them) is a dispatchable action, generated from
the bundled Swagger index. There are three ways in, from most to least
ergonomic:

1. **Curated shortcuts** — hand-written, friendly names + arg mapping
   (`list-processes`, `run-process`, `list-workspaces`, …; see below).
2. **Generated per-endpoint actions** — one per operation, named
   `<method>-<path-slug>` where `{param}` → `by-param`:

   | Endpoint | Action |
   |----------|--------|
   | `GET /api/Projects` | `get-projects` |
   | `GET /api/Projects/{id}/payload` | `get-projects-by-id-payload` |
   | `POST /api/Projects/{id}/run` | `post-projects-by-id-run` |
   | `DELETE /api/Webhooks/{webhookId}` | `delete-webhooks-by-webhookid` |

   Path params are **required** `--<name>` args, query params are optional
   `--<name>` args, request bodies are passed as `--body '<json>'`, and every
   generated action takes **`--dry-run`** to compose-and-return the request
   without sending it.
3. **`request`** — the raw escape hatch for anything (custom query keys, etc.).

```powershell
# discover
python scripts/run-tool.py procesio list-endpoints --tags-only
python scripts/run-tool.py procesio list-endpoints --tag ProcessInstance --filter run

# generated action (preview a destructive call first)
python scripts/run-tool.py procesio post-projects-by-id-run --profile personal `
  --id <pid> --runSynchronous true --body '{"payload":{},"connectionid":null}' --dry-run

# raw escape hatch
python scripts/run-tool.py procesio request --profile personal `
  --method GET --path /api/Projects --query '{"pageNumber":1,"pageItemCount":20}'
```

> Complex objects (process / form / data type / credential / webhook / document)
> have **structured DTO sub-tools** — see below. The raw `post-*`/`put-*`
> endpoints remain the escape hatch.

## DTO sub-tools — `<component>-create` / `<component>-edit`

Deterministic builders that turn a small validated `config` into a full PROCESIO
DTO and create/edit the resource (build → JSON-Schema validate → merge onto a
golden template → validate@source → create/edit → re-GET). All six components are
live-verified. See `DTO-SUBTOOLS-NOTE.md` and each `dto/<component>/description.md`.

```powershell
# preview the built DTO (+ validate@source) without sending
procesio process-create --workspace-id <ws> --dry-run --config '{...}'

# data model
procesio datatype-create  --workspace-id <ws> --config '{"name":"Order","attributes":[{"name":"id","type":"guid"},{"name":"total","type":"double"}]}'
# process (any catalog action; runs to STATUS_FINISH)
procesio process-create   --workspace-id <ws> --config '{"title":"P","variables":[{"name":"r","type":"guid","direction":"output"}],"actions":[{"id":"g","action":"Generate GUID","params":{"Guid":{"var":"r"}}}]}'
# credential (validated by POST /api/Credentials/test)
procesio credential-create --workspace-id <ws> --config '{"template":"REST API","name":"GH","properties":{"URL":"https://api.github.com","Authentication method":"No authentication","Method":"GET","Test endpoint":"/zen"}}'
# document, webhook, form
procesio document-create  --workspace-id <ws> --config '{"name":"Doc","body":"<div>Hello <%name%></div>","variables":[{"name":"name","type":"string"}]}'
procesio webhook-create   --workspace-id <ws> --config '{"name":"Hook","sample":{"orderId":"x"},"type":"manual"}'
procesio form-create      --workspace-id <ws> --config '{"name":"Reg","elements":[{"type":"heading","label":"Sign up"},{"type":"input","label":"Email","required":true},{"type":"button","label":"Submit","submit":true}]}'
```

Config shapes (full schemas in `dto/<component>/config.schema.json`):
- **process** — `variables` (input/process/output, primitive or `model`), `actions`
  (`action` = catalog name; `params` bind by property label: literal / `{var}` /
  `{var,path}` / `{template,vars}`), `edges` (linear by default), `branches`
  (Decisional), `webhooks` (attach a trigger).
- **form** — `elements[]` of `{type,label,name,required,options,children,...}`;
  renders at `forms.procesio.app/{tinyUrl}` after a CustomUrl is created.
- After changing any handler/builder, regenerate the manifest:
  `python -m tools.procesio.gen_manifest` (it is too large to hand-edit).

## Curated actions

```powershell
procesio list-processes        --profile personal [--search inv] [--page 1 --page-size 20]
procesio get-process           --profile personal --id <pid>
procesio get-process-payload   --profile personal --id <pid>   # input shape for run
procesio run-process           --profile personal --id <pid> --payload '{"x":1}' [--dry-run]
procesio list-instances        --profile personal --id <pid> [--status <s>]
procesio get-instance-status   --profile personal --id <iid> --flow-template-id <pid> --variables
procesio get-instance-output   --profile personal --id <iid> --flow-template-id <pid>
procesio stop-instance         --profile personal --id <iid> --flow-template-id <pid>

procesio list-workspaces       --profile personal
procesio list-subworkspaces    --profile account --workspace-id <master> --parent-id <master>   # active-only (+ --include-removed)
procesio list-workspace-users  --profile personal
procesio list-datatypes        --profile personal [--search <n>]
procesio list-actions-catalog  --profile personal [--full]
procesio list-connections      --profile personal      # stored connection credentials
procesio list-connection-types --profile personal
procesio list-api-keys         --profile personal

procesio list-schedules            --profile account [--search <n> --page 1 --page-size 20]
procesio get-schedule              --profile account --id <sid>
procesio create-schedule           --profile account --payload '{...}'   # body shape: PROCESIO-API-NOTES.md
procesio update-schedule           --profile account --payload '{"id":"<sid>",...}'
procesio delete-schedule           --profile account --id <sid>
procesio set-schedule-status       --profile account --id <sid> --active true|false   # maps to ?enable=
procesio get-schedule-notifications --profile account --id <sid>
procesio set-schedule-notifications --profile account --payload '{...}'
procesio list-project-schedules    --profile account --id <pid>   # the target process's flow detail
```

`run-process` builds the documented body `{"payload": {...}, "connectionid": null}`
and posts to `/api/Projects/{id}/run`. Use `--dry-run` to preview the request
without executing the process.

## Export — `.procesio` bundle (Transport)

```powershell
# names, ids, or "all" per type; credentials excluded by default; --dry-run to preview
python scripts/run-tool.py procesio export --profile account --workspace-id <ws> `
  --data-models lazarusDM `
  --processes "Lazarus Data process,Import excel products to pdf" `
  --documents all `
  --output C:\path\export.procesio
```
Requires `Workspace.Admin` (use the userpass `account` profile). Resolves
names→IDs against the scoped workspace, builds the selection, calls
`POST /api/Transport/export-entities`, and saves the raw `.procesio` file.
`--export-sensitive-data` includes credential secrets (off by default).

## `--workspace-id` (active workspace)

Every client-backed action takes `--workspace-id <guid>` — it sets the
`workspaceid` header, which **scopes a userpass session to a workspace** and
**overrides an api-key profile's** own workspace. This is how the userpass
`account` profile reaches owner/cross-workspace endpoints.

## Configuration

Base URLs are overridable per-profile (`--web-base` on `add-credential`) or via
environment:

| Setting | Default | Env override |
|---------|---------|--------------|
| Web API (also userpass login) | `https://webapi.procesio.app` | `PROCESIO_WEB_BASE` |
| Proxy/Auth API (legacy, unused for login) | `https://auth.procesio.app` | `PROCESIO_AUTH_BASE` |

**userpass login** is a form POST to `{web_base}/api/authentication` with header
`x-requested-by: playground-v1` and `client_id=procesio-ui` (both overridable per
profile via `--client-id` / a `requested_by` field). It returns the
`__Host-procesio.access` / `.refresh` cookies, which the tool caches and replays.
The legacy `auth.procesio.app` host is no longer used for login.

## I/O contract

JSON in / JSON out. Success → one JSON object on stdout, exit 0. Failure →
`{"error":{"code","message","details"}}` on stdout, non-zero exit. Stable error
codes: `auth_required`, `invalid_argument`, `permission_denied`, `not_found`,
`proxy_auth_failed`, `rate_limited`, `server_error`.

See [PROCESIO-AUTH-NOTES.md](PROCESIO-AUTH-NOTES.md) for the live-validated auth
findings (which keys work, the `workspaceid` requirement, the userpass host
caveat) and the full endpoint inventory.

## Start here: the rules that are not obvious

[**PROCESIO-USAGE-GUIDE.md**](PROCESIO-USAGE-GUIDE.md) indexes every rule the notes in
this folder mark as one: the places the platform does something defensible that reads
as a failure until you know it. A call succeeds, the status says finished, nothing is
logged, and the thing you asked for did not happen.

It is GENERATED from the notes, so it cannot drift from them and it holds no second
copy of any fact: it carries the rule and a link, and the reasoning stays in the note.
Regenerate it after changing a note:

```bash
python scripts/run-tool.py procesio usage-guide          # write
python scripts/run-tool.py procesio usage-guide --check  # is it stale?
```

To add a rule to it, mark the section in its note with a `⚠`. That marker is the
convention the guide reads, and it is applied to three of the twenty notes so far; the
guide lists the rest by name rather than pretending they hold nothing.

## Tool notes vs agent guidance

The notes in this folder document **how the tool works and why** (API behaviors,
DTO shapes, builder internals, platform gotchas) - for whoever maintains the tool:
[PHASE4-E2E-NOTES.md](PHASE4-E2E-NOTES.md), [PROCESIO-API-NOTES.md](PROCESIO-API-NOTES.md),
[PROCESIO-AUTH-NOTES.md](PROCESIO-AUTH-NOTES.md), [DTO-SUBTOOLS-NOTE.md](DTO-SUBTOOLS-NOTE.md),
[PROCESIO-SEND-EMAIL-NOTES.md](PROCESIO-SEND-EMAIL-NOTES.md),
[PROCESIO-METERING-NOTES.md](PROCESIO-METERING-NOTES.md) (what a run costs, and why
`/api/Resources/used` is the wrong place to read it).

**How to build well in PROCESIO** (the build-and-test operating procedure, best
practices, which skills to use) is agent-level and lives separately in
`agents/procesio/` - the staged knowledge base for the PROCESIO agent. Keep that
boundary: tool mechanics here, methodology there.


## Front-end (designer-layer) validation + the save gate

`POST /api/Projects/validate` only checks the **runtime** layer and returns empty even
when the designer would REFUSE to save. The designer's client-side "Process Errors" panel
is a separate check of the **designer layer** (`customData`) with no server endpoint.

- **`process-fe-validate --id <id>`** replicates that check offline: unconnected actions,
  missing Start/Stop, empty node names, required-empty fields, leftover placeholders, bad
  number/integer values, out-of-range limits, duplicate/primitive-named variables, and
  unmapped required subprocess inputs. `clean=true` when there are no blocking errors.
  Data-type mismatches come back as (non-blocking) `warnings`. Add `--include-be` to also
  run the API validator, `--no-types` to skip the advisory type layer.

- **Auto-gate (no conscious decision needed):** every `process-create` and `process-edit`
  now runs **FE validation first, then BE validation, then saves** — and *blocks* the save
  (JSON error `validation_failed`, exit 2, with the full report) if either finds errors.
  Pass `--force` to override the gate; `--dry-run` shows the validation report without
  saving. Other components (form/document/…) are unaffected.

Rules live in `flowmodel/fevalidation.py` (pure) + `handlers/fevalidate.py` (live).
Full design + DTO↔FE-model quirks: `PROCESIO-FE-VALIDATION-NOTES.md`.
