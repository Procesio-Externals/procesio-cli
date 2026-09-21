# PROCESIO connectors & platform actions - what the tool resolves live vs what it bundles

Scope: how PROCESIO's built-in **connectors** and **platform actions** reach this tool,
and the specific ones added in the Aug-Sep 2026 wave. Companion to
`PROCESIO-CUSTOM-ACTION-NOTES.md` (which is about *building* NuGet custom actions) and
`PROCESIO-SQL-ACTIONS-NOTES.md`.

## The one rule that governs "is a new action supported?"

The process builder resolves the **action catalog live** at build time
(`dto/process/builder.py` `prepare_ctx` → `GET /api/Actions?getFullAction=true` on the
target workspace) and only falls back to the bundled `dto/data/action_catalog.json`
when the live fetch is slow or fails. Credential types are likewise live-resolved
(`GET /api/Credentials/types`). **Consequence:** a new platform action or a new
credential type works at runtime the moment PROCESIO ships it - no tool change. What
goes stale is the *offline* bundle (the fallback) and the human notes.

Refresh the offline bundle with `dto/data/_refresh.py`:

```
python tools/procesio/dto/data/_refresh.py --profile <name> --workspace-id <guid> --procesio-only            # report
python tools/procesio/dto/data/_refresh.py --profile <name> --workspace-id <guid> --procesio-only --write    # apply
```

Always pass **`--procesio-only`** when the refresh runs against a real workspace: it
keeps only `isProcesioAction=true` entries, so that workspace's own uploaded custom
actions never leak into the platform bundle. It is additive by default;
`--replace-existing` also updates the shape of actions already bundled (diff before
committing - an in-place shape change silently alters every process the builder emits).

## Three action kinds (do not conflate)

`RunActionDto.ActionType` has three values:

- **Platform (built-in) action** - seeded in the DB, `isProcesioAction=true`, global to
  every workspace. Uploaded by admins via `POST /api/PlatformAction`. This is what the
  catalog bundle mirrors. Connectors like Prelude/Redis/Data Store are platform actions.
- **Custom action** - a developer's NuGet package implementing `IAction`, uploaded per
  workspace via `POST /api/Actions` (multipart), `isProcesioAction=false`, run by the
  Action-Execution service. Namespace blacklist on upload (Reflection, Diagnostics.Process,
  IO, InteropServices, Loader, …).
- **Connector action** - the *design-time* execution of a connector's property/event to
  populate dynamic UI (chained dropdowns, previews): `POST /api/Actions/event`
  (`ConnectorActionRequestDto`), async, results over SignalR (`ConnectionId`) or polled
  at `GET /api/Actions/event/{id}`. A built-in connector (e.g. Data Store) exposes
  `OnReady`/`OnChange` handlers with `OutputTarget.Options` to fill selects.

## New/relevant `FeComponentType` values (custom-action / connector control types)

Backend enum `Action-Core/.../Utils/FeComponentType.cs`; serialized lowercase-hyphenated
(e.g. `Data_Store_Decisional` → `data-store-decisional`). Do not confuse with the FE
form-element enum `ElementType`.

- `Ai_Decisional_Case = 44`, `Credentials_Ai = 45`
- `Data_Store_Mapper = 46`, `Data_Store_Decisional = 47`
- (also in play: `Map_Parameters = 43`, `Credentials_Db = 32`, `Document_Mapper = 38`,
  `Document_Select = 39`, `Form_Template = 42`)

## The connectors/actions added in the Aug-Sep 2026 wave (all prod-verified)

- **Prelude** connector (`isProcesioAction=true`) - phone verification + lookup via
  prelude.so. Credential is a **REST_API/Bearer** derived template ("REST API/ Prelude",
  base `https://platform.prelude.so`); pick the operation via a `SelectedAction`/
  `Operation` select. Inputs vary by operation (Target, TargetType, Code, Method,
  PreferredChannel, SenderId, TemplateId, Variables, Locale, CodeSize, ForceChallenge,
  CallbackUrl, CorrelationId, IncludeCallerName); output `Result`/`Status`/
  `VerificationId`/`RequestId`. Confirms the old "Prelude" worked-example in
  `PROCESIO-API-NOTES.md` is now a **real shipped connector**, not just an illustration.
- **Redis** connector + Redis credential - code merged (Web-Api #1452 validation +
  test client, Process-Execution #250), but **NOT yet activated on PROD**: as of
  2026-09-21 `Redis` is still absent from `GET /api/Credentials/types` (35 types, no
  Redis), so a Redis credential cannot be created there yet. Contract is documented in
  `dto/credential/description.md`; treat as shipped-not-activated until it appears live.
- **Query Store** action (`DataStoreQueryAction`) - query a data store from a process.
  Input `Query` in a **code-editor whose text format is `datastore`** (the new format,
  alongside `sql`/`python`/`ruby`), plus `Parameters` (map-parameters) and `Timeout`
  (60-1800); output `ResultRows` (datatype) + `TotalCount`. This is the read path a
  process uses; the interactive rows API is the `DataStore` REST surface the tool
  already maps.
- **CURL** action (`CurlAction`) - `CurlCommand` (code-editor) in → `Result` (datatype),
  `Status` (number), `Error`. "Run curl commands."
- **Data Store** connector in the process designer - operations
  `SelectAll/SelectWhere/InsertRows/UpdateRows/DeleteRows` (sent by NAME), a WHERE tree
  using the 21-value `QueryOperators` vocabulary (superset of the REST filter operators;
  the tool already carries 0-20 in `handlers/datastore_ops.py`), and the
  `Data_Store_Mapper`/`Data_Store_Decisional` control types above. In the FORM designer,
  a data store is not an element - it is an event action
  `RUN_DATA_STORE_OPERATION` (config `{dataStoreId, operation READ|ADD|UPDATE|DELETE,
  inputMap[], outputMap[]}`) attachable to any element's `field-events`.

## Scripting languages

Python, Javascript, Node, **Ruby**, and **CURL** - no C# scripting action (C# is the
custom-action NuGet path). Each takes a `Code` string and returns an output; Node adds a
`Timeout` (60-300) and a `Stdout` output (console.log capture, added 2026-09). See
`PROCESIO-NODE-MODULE-WHITELIST.md` / `PROCESIO-PYTHON-ACTION-NOTES.md` for the sandbox.
