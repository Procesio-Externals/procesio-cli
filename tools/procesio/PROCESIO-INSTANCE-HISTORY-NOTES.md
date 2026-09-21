# PROCESIO instance-history API — notes

How run history is read (endpoints + native actions), and the traps. Generalized
API facts; no client data. Measured live against Internal-PROD, 28/08/2026.

## The endpoints (contract + measured shapes)

- **`GET /api/Projects/{id}/history`** (`get-projects-by-id-history`) — finished,
  non-archived instances of a process, in a **time window**. Query: `pageNumber`,
  `pageItemCount` (both required), `filter` (`ProcessTimeSpanFilterType`, default
  `Last30Days=5`), `monthFilter` (with `CertainMonth=14`).
- **`GET /api/Projects/{id}/instances`** (`get-projects-by-id-instances`) — **live**
  runtime instances only. Query: paging + `filterStatus` (repeatable `FlowStatus`).
  No date filter.
- **`GET /api/Projects/{id}/instances/count`** — returns `{"result": <int>}`.
- **`GET /api/Projects/{id}/archive`** — archived (Cassandra) instances, same query
  as `/history`. Hidden from Swagger; reachable.
- **`GET /api/Projects/instances/{id}/status`** (`get-instance-status`) — the
  **primary result reader**. `flowTemplateId` required; `isArchived`/`getActions`/
  `getVariables`/`getInternalVariables`/`addExtras` default true. Returns
  `{"instance": {...}}`.

**List envelope:** `{result:{totalItemCount, pageNumber, pageItemCount, pageItems[]}}`.
Read `totalItemCount`, not the row count, to know the true size (page cap hides the rest).

## Traps (each cost a real diagnosis)

- ⚠ **`filter` values are calendar buckets, not rolling windows.** `LastYear=13` is the
  **previous calendar year**, not "last 12 months"; `ThisYear=8` is the current year.
  A `/history` read with the wrong `filter` returns a well-formed **all-zero envelope
  indistinguishable from "no history exists."** Runs in the current year need `filter=8`;
  the endpoint default is `Last30Days=5`. Probe more than one window before concluding empty.
- ⚠ **`/instances/count` and `/instances` report different tiers.** The count can equal
  the **history** total while the live `/instances` list is **empty** (finished runs have
  left the live tier). For finished runs read `/history` (right window), not `/instances`.
- ⚠ **A history/instance list ROW carries no variables.** camelCase, ~26 fields: identity
  = `id` (instance id) + `parentId` (the process id) + `title` + trigger (`formName` /
  `webhookName` / `scheduleName`); timing = `createdOn` / `updatedOn` / `timeConsumed` /
  `totalTimeConsumed` / `actionsConsumed`; `status` = `FlowStatus` (50 `STATUS_FINISH`,
  40 `STATUS_RUNNING_WITH_ERRORS`, 6 `STATUS_STOP_BY_USER`). The **outcome is not in the
  row** — read it per instance from `/status`.
- ⚠ **`/status` `instance.variables[]` is VariableDto SCHEMA, not runtime values on a
  historical read.** Each element has `id, name, type` (10 INPUT / 20 PROCESS / 30 OUTPUT),
  `dataType, isList, isError, isRequired, defaultValue` — **no `value` field**. So a past
  run's `/status` gives the run record + the variable *definitions*; the concrete output
  *values* are not on that path (use `isArchived=true` or the `Get Instance Outputs`
  action). `/output` (`GetInstanceOutput`) is deprecated ("Not used by FE+BE"); prefer
  `/status`. Casing: **live reads are camelCase; export bundles are PascalCase** — running
  one shape's keys against the other yields a census of zeros.

## Reading history from INSIDE a flow — binding matters

- ✅ **Native actions read run history with NO credential and NO store binding**
  (`isProcesioAction=true`, `credential_params=0`):
  - **`Get Recent Instances`** (`cf514e01-bd19-3b48-8e58-db786c0d7fd2`) — recent instances,
    status filter ALL/1/6/30/50/40, optional process-id list.
  - **`Count Recent Instances`** (`d42b8056-4cba-d34d-819c-00295ef66d53`).
  - **`Get Instance Outputs`** (`98ab31ca-1dd2-fb47-bde7-40171612e4b1`) — a specific
    instance's OUTPUT variables by name (needs flow + instance id + output selection).
  - Their process-template-id list is **optional**: *"If this list is null or empty … the
    entire workspace"* (`docs_info/Procesio Platform Actions.json`). So a flow reads its own
    workspace's runs/counts/outputs with no foreign binding — the only ids are the pack's own.
- ⚠ **Call API to the platform's OWN REST API needs a bound REST credential.** `Call API`
  v1/v2/v3 carry a **required** `credentials` param; only the legacy `Call API`
  (`cd8bd0bc-9c9c-476c-b16e-975acde804de`) makes it optional — and the history endpoints
  require a Bearer JWT, so a credential-less legacy call reaches them unauthenticated and
  fails. A REST credential is a per-workspace, id-bound object that does not travel with an
  exported pack. **To read run history binding-free, use the native actions, not Call API.**

## Retention — how long a record lives

- **Customer process data: default UNLIMITED**, configurable per Master Workspace and per
  process (security refs `07-data-protection-gdpr.md`, `13-questionnaire-template.md`). The
  2-week / 7-day figures are platform **logs** and **backups**, not run data.
- Per-process **`DataRetentionPolicyDto`** = `{deleteOnSuccess, deleteOnError,
  deleteOnStopped}`, each `FlowDataRetentionType` (`Never=0`, `AtEndOfRuntime=1`,
  `AtMoveToHistory=2`). `PATCH /api/Projects/{id}/dataRetention` sets it;
  `DELETE /api/Projects/instances/{id}/dataRetention` deletes an instance's data.
  A flow/instance with `DataRetention: null` inherits the workspace default (unlimited).
- **HIPAA Mode** is opt-in: "Controlled data retention + secure output retrieval"
  (`08-application-security.md`) — can delete/secure outputs when enabled.
- Tiers: live `/instances` → `/history` (non-archived, windowed) → `/archive` (Cassandra,
  `isArchived=true`). Tier moves are storage progression, **not deletion by default**.
- **Consequence for a run-history feature:** history is durable by default, so it can back a
  log — but a customer's per-workspace/per-process retention policy or HIPAA Mode can delete
  it, and a silently-aged-out history turns "did we process this?" into a confident wrong "no".

## `Get Recent Instances` at RUNTIME — measured, and it corrects the action doc

Executed live (E-166); two documented behaviours did **not** reproduce, so verify before you
rely on them:

- **It is a RECENT-WINDOW read.** A process's older *finished* runs read as `griTotal 0`
  until a fresh run appears, then the fresh one shows. A run-history view MUST set the window
  deliberately (default `Last30Days`); trusting the default to reach back far enough returns
  a well-formed zero for runs that really happened (the census-of-zeros, on the native action
  now, not only the `/history` calendar bucket).
- **A single process id filters correctly** in EITHER `Select Process` or `Process Template
  Id`. The Result rows carry `{Id, Status, UpdatedOn}` **only — no `parentId`/title**, so you
  cannot tell processes apart per-row; the *filter value* is the only scoping.
- ⚠ **A LIST value in the process filter FAULTS at runtime.** A two-element id list
  (`[pidA, pidB]`) in either param validates and `put-projects` fine, but the run returns
  `griTotal = null` / 0 rows (a fault, not "0 matches") — tested with both processes freshly
  run, so not a window effect. The friendly builder DSL additionally rejects a list literal at
  the config-schema layer and a variable binding at back-end validation.
- ⚠ **An omitted / null filter returns 0 — NOT the whole workspace.** The action doc's "if
  this list is null or empty … the entire workspace" did not reproduce for an omitted filter.
- **Therefore: to show N processes' histories, do N single-id reads and union them** — not one
  list value, not the null=whole-workspace shortcut. (Bounded residual: the designer's own
  multi-select picker may store a Value shape the action accepts that a bare id-list does not;
  untested.) Reading a past run's OUTPUT *values* back works — via `/status` `defaultValue`
  and `/output` `result.variable[<name>]`, not gated by `isArchived` (E-164 F-1310).

## Capturing a run's output — capture it LIVE, don't count on reading it back

- ⚠ **`run-process` (POST /api/Projects/{id}/run) is fire-and-forget: it returns only
  `{instanceId}` and launches asynchronously.** To get the run's output in one call pass
  **`--synchronous`** (`run-process --id … --synchronous --timeout N`) — it polls to a terminal
  status and returns `{instanceId, status, variable{<name>: <value>}, error}`. Without it you get
  the id and nothing else. `run-process-with-file` already publishes → uploads → launches →
  **polls** → returns that same output shape, so it needs no flag.
- ⚠ **A finished instance's output can be UNREADABLE afterwards, so capture at run time.**
  Measured 01/09/2026 on finished scratch instances (status 50, minutes old): `/status`
  (`get-instance-status`) returned **HTTP 400 / statusCode 450 "Database requested information not
  found"** *even with `flowTemplateId` supplied*, and `/output` (`get-instance-output`) returned
  **HTTP 500 wrapping 403** (it is the deprecated path). This does **not** contradict E-164's
  "past-run values readable via `/status` `defaultValue`" as a rule — that was measured on a
  deployed card, likely inside its retention/live window — but it shows the read-back is **not
  guaranteed** for an arbitrary finished instance (retention policy, elapsed window, or workspace
  tier can take it away). **The reliable pattern: capture the output synchronously as the run
  finishes** (`--synchronous` / `run-process-with-file`); treat a later `/status` read-back as a
  best-effort bonus, not the capture path. The list-instances row (identity + `status` + timing) is
  always there to prove a run landed; the run's *values* are not.

## Only FORM-launched instances are LISTED; API-launched ones are only COUNTED

> ⚠⚠ **CONTRADICTED 2026-09-16 — re-measure before relying on this section.** Runs launched
> through `POST /api/Projects/{id}/run` (synchronous and asynchronous) and through an anonymous
> webhook launch WERE listed: they appeared in `…/instances` first and then in `…/history`
> within minutes, in three workspaces, with and without recording enabled. The rows move
> between tiers on a timer, so a list read a few minutes after a run can show nothing in
> `/instances` while `/history` holds the run. The most likely explanation of the reading
> below is that tier move, not a route-dependent listing rule; that explanation is inferred,
> not measured. Always read `/instances` AND `/history` before concluding a run is unlisted.

Verified live on one flow, both ways, same day:

| launch route | `…/instances/count` | `…/instances` (list) | `Get Recent Instances` |
|---|---|---|---|
| process API (`/api/Projects/{id}/run`, publish→launch) | 41 | `totalItemCount: 0`, `pageItems: []` | `[]` |
| form API (`/api/FormProcess/…` — what a browser does) | +1 | the run, with `formName` populated | the run |

The listed row carries `formName`, `actionsConsumed`, `timeConsumed` and the submitter's
name — fields an API launch has no value for. That is the tell: the history list is a record
of **form submissions**, not of flow executions.

**Consequences.**

- A run-history view tested only through the process API reads as permanently empty, and the
  natural conclusion — "the history flow is broken" — is wrong. Nothing is broken; the query
  is correct and the store genuinely holds no listable rows yet.
- `Get Recent Instances` returning `[]` while `Count Recent Instances` returns a positive
  number is not a contradiction and not a bug. Count and list are answering different
  questions.
- **Acceptance for any card shipping a run-history view must include one submission through
  `run-form-with-files`.** Without it the view cannot be distinguished from a broken one, and
  a mockup render will fill the gap in review — which is exactly how a fabricated "-LIVE"
  view gets shipped.

Generalises: where a platform exposes both a machine route and a UI route to the same
action, the audit trail may only record the UI route. Test the route the user will take.

## The three response shapes, measured field-by-field (10/09/2026)

Measured against a scratch workspace on Internal-PROD. Field NAMES only; no values recorded.
These are the shapes anything that pre-fills a diagnostic bundle from the product has to bind to.

**Envelope:** `GET /api/Projects/instances/{id}/status` returns `{"result": {"instance": {…}}}`.

**`instance` — 33 fields:** `actions, actionsConsumed, active, canvasData, createdBy, createdById,
createdOn, currentActionId, customResponse, dataRetention, debugMode, description, firstName, formName,
id, isNotification, isValid, lastName, parentFlow, parentId, scheduleName, status, timeConsumed,
timeout, title, updatedBy, updatedById, updatedOn, variables, webhookName, webhooks, workspaceId,
workspaceName`.

**`instance.actions[]` — 19 fields:** `actionName, actionTemplateName, breakPoint, category, customData,
errorMessage, events, flowId, id, isDisabled, isTestable, parameters, parentId, ports, status,
templateId, testValues, variableErrorId`.
→ **The error lives on the ACTION, not on the instance.** Select failed actions as those whose
`errorMessage` is non-empty; `variableErrorId` names the error-port variable. `currentActionId` on the
instance points at the action in flight.

**`instance.variables[]` — 9 fields:** `contextId, dataType, defaultValue, id, isError, isList,
isRequired, name, type`. **No `value` field**, confirming that a historical read yields the variable
SCHEMA and not runtime values. Values need the `Get Instance Outputs` native action or a synchronous run.

**`/history` row — 26 fields:** as listed earlier in this note, plus confirmed presence of
**`currentActionId` and `workspaceId` on the row itself**, so a sweep can shortlist candidates without a
per-instance `/status` call. The outcome is still not on the row.

### ⚠ There is no version anywhere on either object

`instance` has no version-shaped key, and `GET /api/Projects/{id}` returns `{result:{flow:{…}}}` whose 27
keys contain none either. `updatedOn` / `updatedBy` / `updatedById` record **that** a flow was edited and
**by whom**, never **what** changed: no endpoint returns a diff, a revision or a change log.

Generalises: **a record that carries an "updated" timestamp and an author is not a version history, and
treating it as one turns "what changed?" into an unanswerable question at exactly the moment it is
asked.** Any workflow whose next step depends on the previous definition must capture that definition
itself at the time it runs, because the platform will not reconstruct it afterwards.
