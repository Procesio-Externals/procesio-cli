# PROCESIO SQL Server actions — PARAMETERIZED (safe) vs INLINE `<%N%>` (WRONG)

**Discovered 2026-07-03** during a review of a chat flow's contact-resolution
nodes: the reviewer suffixed the existing nodes `[old]`, disabled them, and added
`[new]` nodes "properly configured using parameters". The whole 2026-07 Networky build authored
SQL nodes by **string-interpolating flow-variable values into the SQL text** as `N'<%N%>'`. That is
(a) SQL-injection-prone and (b) the wrong action configuration.

## THE RULE
Never interpolate a flow-variable value into SQL as `N'<%N%>'`. Use the **`Execute Query`** action
(NOT `Execute Query V2`) — or **`Execute Command`** for non-query writes — with its **parameter
binding**: named `@params` in the SQL + a **`Parameters config tab`** (`map-parameters`) collection
mapping each `@param` to a flow variable. The DB driver passes values as **typed SQL parameters**
(escaped), so `O'Brien`, quotes, or malicious input can never break or inject the query.
Literals (`@TopN = 5`) may stay inline. Variable values must be bound, never inlined.

## WRONG (injectable — do NOT author, and convert existing)
- Template **`Execute Query V2`** (inline-only; substitutes `<%N%>` as raw string into the SQL text).
- Any `Execute Query` / `Execute Command` node whose SQL contains `N'<%N%>'` / `'<%N%>'` for a value.
```sql
-- INJECTABLE: a name like  O'Brien  or  '; DROP ...  breaks/injects it
EXEC sp_FindContact @ConversationId = N'<%0%>', @Query = N'<%1%>', @TopN = 5
```

## CORRECT — `Execute Query` template, parameter binding
```sql
EXEC sp_FindContact @ConversationId = @conversationId, @Query = @resolveHint, @TopN = 5
```
plus a binding: `@conversationId <- flowVar(conversation)`, `@resolveHint <- flowVar(resolveHint)`.

### Exact node DTO (the `Execute Query` template — property ids are stable, reuse them)
`customData.configuration[0].settings`:
- `Select Database Server` (type `credentials`) = credential gid (e.g. `45a1dd18-…` = Database).
- `Execute Query` (type `side-pannel`) = a list of sub-settings:
  - `{id: 11350a1d-4139-d942-adcb-a2c2c52e5e22, label: "Query", type: "code-editor", language: "sql", value: <SQL with @params>}`
  - `{id: 73416282-bcfe-4934-9e40-a39f2bb33d2d, label: "Parameters config tab", type: "map-parameters", value: [{id, destination: "<paramName>", source: "<variableId>"}]}`
  - `{id: 9ce93b2d-5226-4228-a64d-3693c8d3e0e3, label: "Time Out", type: "number", value: "100"}`
  - `{id: 8aa02e91-1a1e-a44a-b09b-6965d67da04d, label: "Output", type: "any", value: "<output-var-gid>"}`

`parameters[]` (the RUNTIME form the engine executes — must be kept in sync with the settings;
tabPropertyId == the setting/sub-setting id):
- `{tabPropertyId: f96ff811-572f-084a-8cac-a74a2c2e365f, value: "<credential-gid>"}`  (Select Database Server)
- `{tabPropertyId: 11350a1d-…, value: "<SQL text with @params>"}`  (Query)
- `{tabPropertyId: 73416282-…, value: [ {id:0, source:{value:"<%0%>", variable:[{id:0, variableId:"<gid>", attribute:null}]}, destination:{value:"<paramName>", variable:[]}}, … ] }`  (binding)
- `{tabPropertyId: 9ce93b2d-…, value: "100"}`  (Time Out)
- `{tabPropertyId: 8aa02e91-…, value: "<%K%>"}`  (Output binding; setting holds the output-var gid)

Binding semantics: `destination.value` = the SQL parameter NAME (as it appears after `@` in the SQL —
the action substitutes it with a typed parameter); `source.value` = a positional `<%N%>` whose
`variable[0].variableId` is the flow variable GUID. So: SQL `@conversationId` ⇄ binding
`destination:"conversationId"` ⇄ `source:<%0%>` ⇄ variable `conversation`.

Reference DTO captured at `scratchpad/eq_reference.json` (the live `Execute Query [new]` from Resolve Contact).

## `Execute Command` (SQL Server Command — INSERT/UPDATE/DELETE, no result set)
Same defect when inlined — e.g. `Chat Flow/Extract Info Image` `Execute Command` node:
`UPDATE messages SET ocr_text = COALESCE(ocr_text,' ') + N'<%0%>' …` (inline, injectable if the value
is OCR/user text). Fix identically: named `@param` in the SQL + the `Parameters config tab` binding.
(The Command template exposes the same `Query`/`Parameters config tab`/`Time Out` sub-settings; confirm
its property ids from a live corrected node before authoring — do not assume they equal the Query ids.)

## Converter / tooling — the `procesio` tool (NOT a Networky script)
- **`procesio sql-scan --id <process-id>`** — lists every SQL node (Execute Query / Execute Command) with inline-vs-parameterized status. Read-only.
- **`procesio sql-parameterize --id <process-id> {--node <label|id> | --all} [--dry-run]`** — converts inline `N'<%K%>'` → `@pK`, builds the `Parameters config tab` binding from the node's `<%N%>`→variable map (migrating a deprecated `Execute Query V2` node to `Execute Query`), then PROCESIO-validates and PUTs. NEVER PUTs an invalid flow; `--dry-run` previews.
- Implementation: `tools/procesio/flowmodel/sqlparam.py` (pure) + `tools/procesio/handlers/sqlactions.py` + `tools/procesio/tests/test_sqlparam.py`.
- **flowpatch note:** `setscript`/`syncparams` `_to_runtime_form` (GUID→`<%N%>`) is for **CODE (JS) nodes**,
  NOT SQL. Never use it to (re)author a SQL node's `<%N%>` — that reproduces the injectable inline form.

## Scope in the live build (to convert; audit ongoing)
- `Execute Query V2` nodes (inline): `Get Last 10 msg` (sp_GetLastMesseges) in Start + clone (GUID inlined — low risk, still convert).
- `Execute Command` inline: Extract Info Image OCR `UPDATE messages` (OCR text inlined — **user-text, HIGH risk**).
- `Execute Query` template but inline SQL (my Leak-A edits): `Get info from SalesOMMO` Persist node
  (`f2503397`, RecordSearchClaim/UpdateSessionContext) + Callback resolver (`11f25dbf`, sp_ClaimSearchResult).
- **HIGH injection risk = wherever USER TEXT is inlined**: `@Query`/name (sp_FindContact), message_text
  (sp_MessageAdd/AddMessage), OCR text — prioritize these. GUID/int-only inlines are lower risk.
- The reviewer already fixed the two contact-resolution nodes (`Execute Query [new]`, `Pending Write [new]`); my
  `[old]` disabled copies can be deleted.


## CRITICAL — the action TYPE is the templateId, NOT the label (learned the hard way, 2026-07-04)
The designer renders ACTION TYPE from **templateId**, not actionTemplateName. The 2026-07 build put MOST
SQL nodes on the deprecated **V2 template `a9f851c2-e0ba-4fee-9a06-5445ba000001`** while LABELLING many
of them "Execute Query". The map-parameters binding (73416282) is a property of the LATEST template
`76470756-...` ONLY — it does NOT exist on V2. So adding the binding + @params to an a9f851c2 node leaves
the @params UNBOUND at runtime -> the query errors (a real message creates no user/rows).
- `procesio sql-parameterize` migrates by **templateId**: any node whose templateId contains `a9f851c2`
  is swapped to `76470756` (role-based id remap) BEFORE the binding is added. Changing templateId on PUT
  DOES persist. Keying on the "V2" LABEL alone misses the mislabelled nodes — that bug broke prod once.
- **PROCESIO `validate` does NOT catch unbound @params** (structure only, not runtime binding). A
  parameterized SQL change can pass validate and still fail at runtime. ALWAYS runtime-verify (below).

## Runtime verification — the webhook E2E harness (no WhatsApp Web needed)
Inject a synthetic WhatsApp-Business inbound at Start's webhook, then read the DB:
`procesio webhook-launch --id db92281a-17b5-451f-b9f4-2a7f6a70f1fc --payload '{"PhoneNumber":"<digits>","FinalMessage":"<text>","MessageId":"wamid.TEST","ImageBase64":"","AudioBase64":""}'`
The body is the flat WTB DataModel (PhoneNumber / FinalMessage / MessageId / ImageBase64 / AudioBase64),
passed DIRECTLY (not wrapped in {WTB:...}). Use a fake phone (e.g. 4070000001X) so the Business-API reply
fails harmlessly. Verify in chatbotAI: a users row + an in message + an out reply = the flow (incl. its SQL
nodes) works. A REAL launch runs the live LLM + DB + Business-API send and creates real rows (delete test
rows after). WhatsApp Web itself needs the linked phone ONLINE (else chats stay "Loading…", #main never
opens; also dismiss the "What'''s new" modal).

## MySQL + Redis engines (PRC-3696, 2026-08)

The DB credential (catalog type "SQL") became multi-engine: `DbClientType` gained
`MYSQL = 2` (alongside `MSSQL = 1`). A **MySQL** connection is the same DB credential with
its **server-type** option set to MySQL; the existing `Execute Query` / `Execute Command`
actions run against it unchanged (they resolve the client by the credential's DbClientType).
`CustomMySQLClient` was added in BOTH the Web-Api credential-test stack and the
Process-Execution runtime stack. **Redis** is a STANDALONE credential type
(`CredentialsType.REDIS = 9`, NOT a `DbClientType`/SQL sub-type) with its own **"Redis
Connector"** action (19 typed ops; no raw-command execution) — Web-Api #1452 / Action-Core
#130 / Process-Execution #250. Redis properties: Host/Port(6379)/Username/Password/
Database(0)/UseTls/ValidateCertificate/ConnectTimeoutSeconds/CommandTimeoutSeconds.
It shipped but is **not yet activated** (template not seeded in DataBase-Update), so `Redis`
is not in `/api/Credentials/types` yet; the contract is stable. Security: outbound DB hosts
are validated by `DbHostBlacklistChecker` (CIDR blacklist) — a private/blacklisted host is
rejected at connect time. Tool impact: none — credential types are live-resolved from
`/api/Credentials/types`, so a MySQL/Redis credential is created by setting the template +
properties (incl. the server-type option). Confirm the exact server-type option name/GUID
with `procesio list-connection-types` post-launch.

## `Execute Command` is a SECOND family with its own property ids

`sql-parameterize` originally knew only the `Execute Query` family. Command nodes need their own
ids, and getting this wrong is silent:

| role | Execute Query (`76470756`) | Execute Command (`a1625da6`) |
|---|---|---|
| credentials | `f96ff811-572f-084a-8cac-a74a2c2e365f` | `5f75a4fd-d0f5-4ac1-8257-467e50e7292e` |
| side-pannel | `8add0f17-b2b1-4d5f-962b-c5d400a4e2d4` | `975f25dc-1044-4488-b635-10a2039f8d89` |
| sql | `11350a1d-4139-d942-adcb-a2c2c52e5e22` (Query) | `824575f6-7652-4bc2-8186-63b32c92cc22` (Command) |
| **Parameters config tab** | `73416282-bcfe-4934-9e40-a39f2bb33d2d` | `0acb249e-8b21-4bfd-946c-1e65e26baa68` |
| Time Out | `9ce93b2d-5226-4228-a64d-3693c8d3e0e3` | `2be309c6-9144-4b27-a722-fbc9c89735c2` |
| Output | `8aa02e91-1a1e-a44a-b09b-6965d67da04d` (any) | `e6ffaa2d-2c32-412d-a9d4-b1038ece9d38` (number) |

**Write the Query bind id onto a Command node and every `@param` is unbound at runtime**, with no
validation error to show for it: the SQL still executes, the parameter simply arrives NULL, and a
procedure that reads `OPENJSON(NULL)` inserts nothing and reports success. `sqlparam` now keys the
family off `templateId` (`family_of` / `bind_pid`) so the right id is always used.

### Deprecated templates, and why the label cannot be trusted

Three templates are inline-only (no map-parameters), so a node on one MUST be migrated before it can
bind anything: `Execute Query V2` (`a9f851c2-…ba000001`), `Execute Query V1`
(`574a2ab1-…`), `Execute Command V1` (`c2760ff2-…`). `_migrate_to_current` does a role-based id
remap from a table of each legacy template's ids, in both the runtime and designer layers, and
refreshes each remapped setting's label to the current template's wording.

**Always key on `templateId`, never on `actionTemplateName`.** In one live workspace all four
collectors sat on `Execute Command V1` while two of them were *labelled* "Execute Command". The
label is cosmetic and drifts; the templateId is what the designer and the engine resolve.

### Migrating raises the Output type bar

`Execute Command V1`'s Output was permissive; the current template types it **number** (rows
affected, `isRequired`). A legacy node that bound an `Object`/`Json` variable there validates fine on
V1 and fails migration with `statusCode 142 Data type mismatch … at parameter Output`. Retype that
variable to number first (`variable-set-type`, safe when it is an internal type-20 variable that
nothing else reads). The current template also makes **Time Out required** (60..1800) where the
legacy one had none, so the migration seeds a default rather than leaving a required field empty.

### Proving a parameter is actually bound

A NULL-bound parameter is indistinguishable from "nothing to do" in the logs, so prove the binding
instead of assuming it. Temporarily prefix the statement with a guard that fails loudly, keeping the
real statement after it, and run the process:

```sql
IF @p0 IS NULL OR LEN(@p0) < 1000 RAISERROR('PROBE-PARAM-NOT-BOUND', 16, 1);
EXEC <the real procedure> @Body = @p0;
```

A successful run proves the value arrived with real length; the RAISERROR surfaces as a failed
instance carrying the message. **Run the negative control too**: set the threshold absurdly high and
confirm the run DOES fail, otherwise a guard that never fires proves nothing. Restore the plain
statement afterwards. At every point the process is either correct or fails safe, so this is
usable on a live process when no fresh source data is available to observe an insert.

## `Execute Command` DISCARDS a result set — `sql-convert` moves the node to `Execute Query`

Discovered 2026-08-27. The two SQL families differ in more than their property ids: **`Execute
Query` carries a RESULT SET into a flow variable; `Execute Command` carries ROWS AFFECTED** (its
Output property is literally typed `number`). So a stored procedure that ends in `SELECT` — the
normal way a procedure reports `Success` / `ErrorMessage` / a new id / a token back to its caller
— returns all of that into a Command node's Output and it is thrown away. There is no error to
find: the flow is valid, the run finishes green, `flow-lint` is clean, and the output variable
just holds a count. Everything downstream then treats a refusal and a success identically.

**The tell:** an `Execute Command` node whose SQL is `EXEC <proc>` where the proc's last statement
is a `SELECT`. Also: an output variable declared `list<Object>` but bound to a Command node — the
declared shape and the family disagree, and the family wins.

**The fix:** `procesio sql-convert --id <process> --node <label|id> --to query
[--output-variable <name|id>]`. It is a role-based property-id remap (the same machinery as the
legacy-template migration) across BOTH the runtime `parameters[]` and the designer `customData`,
plus three things the remap does not reach and a reader WILL trust: the Output setting's designer
`type` (`number` -> `any`), the configuration container's label, and `customData.description`.
The SQL text, credential, timeout and `@param` binding are carried across untouched. `--to command`
is the exact inverse. A node on a deprecated template is refused rather than half-converted — run
`sql-parameterize` first, which migrates it onto its family's current template.

**Order matters when both are needed:** parameterize FIRST (it can migrate a legacy template), then
convert the family. Converting first leaves `sql-parameterize`'s inline detector looking at the new
family's property id, which is fine, but a legacy node would already have been refused.

### The output variable's data type is a separate axis from the family
`flow-lint`'s `EXECQUERY_OUTPUT_TYPE` wants an Execute Query Output to be `list<Object>`
(`...121221`, `isList: true`). `...121220` (Json) also works at RUNTIME — a whole workspace ran on
it — but the designer renders a "data type mismatch" on every such node. Fix it with
`variable-set-type --data-type ...121221 --is-list true`; an output/input variable needs
`--allow-contract-change` because it is the process's public shape.

## Verifying a SQL change: run BOTH paths, and run one through the FORM

`run-process --synchronous` returns `{status, variable, error}` directly, which makes the
success path easy. The path that actually regresses is the REFUSAL path, because a discarded
result set looks exactly like a successful one — so assert on a call the procedure must reject
(a slot outside the offered list, a malformed email) and read the `ErrorMessage` back.

And prove the injection fix while you are there: submit a value containing an apostrophe and a
statement terminator (`O'Brien Test; DROP TABLE x--`). Under the old inline `N'<%N%>'` form that
breaks or injects; under parameter binding it is stored verbatim as data. Reading the row back
afterwards is the assertion.

Finally run one submission through `run-form-with-files`, not just `run-process`: the form and the
process are assembled separately and nothing asserts they agree. See
PROCESIO-FORM-SUBMISSION-NOTES.md.
