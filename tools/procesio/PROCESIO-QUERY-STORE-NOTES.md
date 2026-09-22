# PROCESIO Query Store action - authoring & usage contract

The **Query Store** action (`DataStoreQueryAction`, actionId `02577ada-0000-0200-0000-00000000b001`,
config tab "Configure Query") runs **exactly one SQL statement** against the workspace's Data
Stores as a single process step. Data Stores are MySQL-backed, so the dialect is **MySQL**.
There is no credential, connection string or external database. It does both **reads and
writes** (see the accepted-statements matrix below).

Two different datastore actions, do not confuse them:
- **Data Store action** (the `DataStoreConnector`, TemplateId `02577ada-0000-0100-0000-00000000a001`):
  point-and-click CRUD on ONE store (SelectAll/SelectWhere/Insert/Update/Delete), no SQL.
- **Query Store** (this note): one SQL statement, for filtering, joins, totals/reports, and
  bulk writes across a condition.
- **Execute Query** is unrelated: it targets your own external Microsoft SQL Server.

Sources: docs.procesio.com/query-store (read 2026-09-22), a real process export (the node
encoding below), and a QA behaviour matrix (accepted = run status 50, refused = status 40).
Where they disagree, the matrix + platform owner win.

## Availability
Runs in **personal AND organisation** workspaces. (The public doc still says organisation-only,
"not available on a personal workspace"; that line is STALE as of 2026-09-22.)

## I/O (as the catalog serves it)
- Input `Query` - code-editor, TextFormat `datastore` (chips, see encoding below).
- Input `Parameters` - map-parameters (`@name` -> value/variable), **bound as data** (safe).
- Input `Time Out` - seconds, **60..1800, default 1800**; out of range is refused at validate.
- Output `Result Rows` - a list of JSON objects, one per row; keys are the column names (or
  your `AS` aliases). **Empty for INSERT/UPDATE/DELETE/REPLACE.** Map to a **list of Json**.
- Output `Total Count` - for a SELECT, rows returned; for INSERT/UPDATE/DELETE/REPLACE, rows
  affected (REPLACE that overwrites reports 2 = delete+insert). Map to an **Integer**.
- **No row limit.** A SELECT with no WHERE/LIMIT returns the whole table; add `LIMIT`.

## Saved node encoding (verified from a real export) - what a builder must emit
The node's `Parameters` is a list of property objects `{TabPropertyId, Variable[], Value}`, one
per property of the action template `...b001`. Every Data Store / column / process-variable
reference uses PROCESIO's standard **`<%N%>` placeholder** inside `Value`, resolved by the
`Variable[]` entry whose `id == N`. Chip `id`s are one sequence across the whole node.

- `...b102` **Query**: `Value` is the SQL with chip placeholders, e.g.
  `"select * from <%0%>\nwhere <%1%> <= @threshold"`. `Variable[]` holds the chips:
  - table chip: `{"id":0,"type":"dataStoreTable","variableId":null,"dataStoreId":"<store guid>","attribute":null}`
  - column chip: `{"id":1,"type":"dataStoreColumn","variableId":null,"dataStoreId":"<store guid>","columnId":"<col guid>","attribute":null}`
  `@threshold` is a SQL parameter (NOT a chip); it is resolved by the Parameters map below.
- `...b103` **Parameters** (map): `Value` is a list of
  `{"id":K,"source":{"value":..,"variable":[..]},"destination":{"value":"<param name>","variable":[]}}`.
  `destination.value` is the SQL parameter name (no `@`). `source.value` is a `<%N%>` placeholder
  resolved by `source.variable[] = [{"id":N,"variableId":"<flow var guid>","attribute":null}]`;
  a fixed literal instead goes straight in `source.value` with an empty `variable[]`.
- `...b104` **Time Out**: `Value:"1800"`, `Variable:[]`.
- `...b105` **Result Rows** (output): `Value:"<%N%>"`, `Variable:[{"id":N,"variableId":"<list-of-json var>"}]`.
- `...b106` **Total Count** (output): `Value:"<%N%>"`, `Variable:[{"id":N,"variableId":"<integer var>"}]`.

So the only Query-Store-specific part of the well-known `<%N%>`+`Variable[]` pattern is the
chip entries typed `dataStoreTable` / `dataStoreColumn`, which carry `dataStoreId` (and
`columnId`) instead of a `variableId`. Resolve those ids live from the Data Store metadata.

## The `Query` value chips (behaviour)
A Data Store or column is inserted with Ctrl+I and stored as a chip **bound to the resource
ID, not its name**: renaming the store/column keeps the query working; deleting one turns the
chip red ("Unknown") and fails the step. Names with spaces/special chars work because the name
never enters the SQL. **System columns** `CreatedOn`, `UpdatedOn`, `CreatedById`, `UpdatedById`
are NOT in the picker; type them by name (e.g. `WHERE CreatedOn > @since`).

## Parameters (always use them for external values)
- Write `@name` in the SQL; map it below the editor to a fixed value or a process variable.
  A parameter value is always **data, never SQL** (injection-safe).
- Name rules: start with a letter or `_`, then letters/digits/`_`, **<=64 chars**, each name
  once per query; the leading `@` in the mapping is optional.
- **An empty parameter row blocks Test Action** - delete it when the query has no parameters.
- Do NOT paste a variable straight into the SQL via the picker (it inlines the value as text).

## Passing a list (real trap)
A list variable arrives in the query as a **JSON array**. `IN (@list)` runs but matches
**nothing**. Use instead:
- text values: `WHERE JSON_CONTAINS(@codes, JSON_QUOTE(SomeColumn))`
- whole numbers: `WHERE SomeColumn MEMBER OF (CAST(@numbers AS JSON))`

## Joins
When two Data Stores share a column name, give each an alias and prefix every column
(`FROM A AS c JOIN B AS o ON o.k = c.k`); without aliases the join is **refused** (ambiguous).

## Accepted statements (QA matrix, run completes / status 50)
Exactly one statement per run. Accepted:
- **SELECT** - plain, `AS` alias, `WHERE`, `IN (subquery)`, `EXISTS`.
- **JOIN** - incl. table-aliased `a.col = b.col`.
- **WITH ... AS** (CTE), incl. **WITH RECURSIVE**.
- **UNION / UNION ALL** - as arms of a SELECT.
- **GROUP BY**, **ORDER BY ... DESC**, **COUNT(*)** and the other aggregates, **LIMIT**.
- **INSERT INTO ... VALUES** (single and multi-row), **INSERT ... SELECT** (copy rows).
- **UPDATE ... SET ... WHERE** (affected-rows count).
- **DELETE FROM ... WHERE** (affected-rows count).
- **REPLACE INTO** (delete+insert; reports 2 affected on an overwrite).
- `@parameter` binding - constant and variable, bound as data.

## Write mechanics
- **INSERT and REPLACE must fill `CreatedById` and `UpdatedById`** (pass a user GUID as a
  parameter); a missing required column fails with "A required column has no default value
  and was not supplied."
- An `UPDATE` through Query Store **does not refresh `UpdatedOn`**.
- A `REPLACE` counts as a new row, so it **resets** the created-by / created-on values.

## Refused (QA matrix, status 40 / done-with-errors) - each with a clear message, never a raw DB error
- **Multi-statement / stacked**: `SELECT ...; DROP ...`, comment-hidden (`--`, `#`), `; SELECT 1`.
- **DDL**: `DROP/ALTER/TRUNCATE/RENAME/CREATE TABLE`, incl. case-obfuscated (`dRoP`).
- **Privileges**: `GRANT`.
- **Session / txn / lock / prepare**: `SET`, `START TRANSACTION`, `COMMIT`, `LOCK TABLES`,
  `HANDLER`, `PREPARE`, `USE`.
- **File / advisory lock / system schema**: `INTO OUTFILE`, `INTO DUMPFILE`, `LOAD_FILE()`,
  `GET_LOCK()`, `information_schema.*`, `mysql.user`, `performance_schema.*` - including
  UPPERCASE / backtick / spaced / comment-split spellings.
- **Obfuscated primitives**: executable comments `/*! ... */`, versioned `/*!50000 ... */`.
- **Nested system-schema refs**: a subquery `EXISTS(SELECT ... information_schema)` or a
  `UNION` arm reaching `mysql.user`.
- **Other non-whitelisted verbs**: `DO` (e.g. `DO SLEEP(0)`), `SHOW` (e.g. `SHOW GRANTS`),
  comment-only / empty query.
- **Error-based extraction**: `EXTRACTVALUE`, `UPDATEXML`.
- Plus: unparseable SQL, and a query that runs past Time Out.

Query Store only ever touches the Data Stores of the workspace the process runs in.

## Error handling
- On failure the step routes to its **error port**; wire an error branch and capture the
  message in an `Error`-typed variable.
- **Test Action** runs the step alone (the vertical tab on the properties panel).

## Authoring a Query Store node with the tool (process-create / process-edit)

The builder emits the whole node from a friendly `queryStore` field on an action (no need to
hand-write the chip encoding above). Verified live end-to-end in an org workspace across
SELECT, JOIN across two Data Stores + GROUP BY/SUM, INSERT/UPDATE/DELETE/REPLACE, a list
parameter, and a refused statement routed to an error branch.

```json
{"id": "q", "action": "Query Store", "queryStore": {
  "sql": "SELECT c.{{col:Customers.Name}} AS Customer, SUM(o.{{col:Orders.Amount}}) AS Rev FROM {{ds:Customers}} AS c JOIN {{ds:Orders}} AS o ON o.{{col:Orders.CustomerCode}} = c.{{col:Customers.CustomerCode}} WHERE o.{{col:Orders.Status}} <> @cancelled GROUP BY c.{{col:Customers.Name}}",
  "params": {"cancelled": "Cancelled"},
  "resultRows": "rows", "totalCount": "count"}}
```

- Tokens: `{{ds:StoreNameOrId}}` = a table chip, `{{col:StoreNameOrId.ColNameOrId}}` = a column
  chip. Names resolve to ids live from Data Store metadata (`prepare_ctx` fetches
  `/api/DataStore`); a GUID passes through. An unknown name fails with a clear error.
- `@param` stays literal in the SQL and is bound by `params` (bare = literal, `{var}` = a
  process variable). A column alias (`c.`, `o.`) is plain text before the column chip.
- `timeout` (60-1800, default 1800); `resultRows` -> a list-of-Json variable, `totalCount` ->
  an Integer. For a write, bind `totalCount` (affected rows); Result Rows is empty.
- INSERT/REPLACE: include `CreatedById`/`UpdatedById` (a user GUID param). List param: use
  `JSON_CONTAINS` / `MEMBER OF` (see above), never `IN (@list)`.
- Error handling: add `"onError": "<handlerActionId>"` to route the step's error port; give the
  error path its own convergence (a second Stop) - a single Stop takes one input port, so two
  branches into one Stop is refused by the BE validator ("Action has too many input ports").
- The generated node's designer config mirrors the runtime (Query -> `ds.<id>[.<col>]`,
  Parameters -> `{id,destination,source}`), so it shows configured in the Process Designer.
