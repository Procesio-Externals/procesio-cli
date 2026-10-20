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

## A Guid column is BINARY(16), and a guid-shaped STRING parameter is packed into 16 bytes

A Data Store `Guid` column is a MySQL `BINARY(16)`: `LENGTH(col)` returns 16 and `CHARSET(col)`
returns `binary`. Everything below follows from that, and from the binding layer typing a
parameter by the SHAPE of its value rather than by the column it is written to.

**A parameter whose value looks like a GUID (`8-4-4-4-12` hex) is typed Guid and packed to its 16
bytes before it reaches the column**, including when the column is a String. Two outcomes, both
bad:

- the packed bytes are not valid in the column's charset - any byte >= 0x80, which is EVERY real
  RFC 4122 UUID, because the variant byte is 0x80-0xbf - so the statement is refused with
  *"One or more values are incompatible with the column type."* (MySQL's `1366 Incorrect string
  value` underneath);
- the packed bytes happen to be valid UTF-8, so **the write SUCCEEDS and the column now holds 16
  bytes of binary instead of the 36-character string.** Nothing warns. Read it back and you get
  16 garbage characters, `CHAR_LENGTH` is 16, and every `LIKE` or `SUBSTRING` on it is meaningless.

The one-character minimal pair that isolates it (`...-4444-5555555555ff` refused,
`...-4444-55555555557f` accepted) shows the rule is byte validity, not the guid version or
variant. It fires wherever the parameter is used, including as a function argument
(`CONCAT('', @v)`), and only when a row is actually written: the same statement whose WHERE
matches nothing is accepted. The REST row endpoint (`POST /api/DataStore/{id}/rows`) behaves the
same, so it is the platform's typing rule and not one endpoint's bug. It has nothing to do with
length: a 29 KB string in the same column is accepted.

**The fix is to type the column Guid**, not to work around the binder. `datastore-update` adds a
column to an existing store in place (send the full metadata DTO with the existing columns, each
keeping its `columnId`, plus the new one); rows already in the store are preserved. Where a column
genuinely cannot be typed (one `Value` column holding everything from a timezone name to a data
URI), prefix the parameter and strip it in SQL with `SUBSTRING(@v, 2)`.

### The platform and MySQL spell the same Guid column differently

The 16 bytes are stored in .NET `Guid.ToByteArray()` order, so MySQL's own UUID functions
disagree with the designer on every value:

    SELECT g, BIN_TO_UUID(g) FROM <store>
    -- 1f0d8533-cf4c-44d8-b805-a4d3d6aaca4d   what the platform shows
    -- 33850d1f-4ccf-d844-b805-a4d3d6aaca4d   what MySQL reads from the same bytes

It is symmetrical on writes: `SET g = UUID_TO_BIN('<what the designer shows>')` succeeds and
stores a DIFFERENT guid, silently. Round-tripping needs either a bound parameter, or this reorder:

    LOWER(CONCAT_WS('-', HEX(REVERSE(SUBSTRING(g,1,4))), HEX(REVERSE(SUBSTRING(g,5,2))),
                         HEX(REVERSE(SUBSTRING(g,7,2))), HEX(SUBSTRING(g,9,2)),
                         HEX(SUBSTRING(g,11,6))))

### Reading and writing a Guid column

- **write it with a PARAMETER, never a literal.** A 36-character literal is 36 bytes into a
  `BINARY(16)`, so MySQL raises `1406 Data too long` and the platform reports *"values exceed the
  maximum allowed length"*, which points at the wrong thing. `UUID_TO_BIN('...')` fits, but see
  the byte order above before using it.
- **copying a text column into it fails the same way** (`SET g = SUBSTRING(v,1,36)` is still 36
  bytes). Move such values with one parameterised UPDATE per row, and clear the text column in a
  SEPARATE statement, because a Guid parameter and a String column in one statement is the very
  thing the packing rule refuses.
- **`CAST(<guidcol> AS CHAR)` returns NULL** - plain MySQL, not the platform. Converting binary to
  a character set yields NULL when the bytes are not valid in it, which for 16 guid bytes is
  almost always (`CAST(_binary'hello' AS CHAR)` gives `hello`, `CAST(UNHEX('84FF') AS CHAR)` gives
  NULL). Use `BIN_TO_UUID()` or `HEX()`, or select the column on its own.

## Four traps found porting a real schema onto Data Stores

**`Total Count` is ROWS RETURNED, never a value in them.** `SELECT COUNT(*) AS N ...` reports
Total Count = **1**, because it returned one row - the `N` inside it is not what you read. A
"does this exist" test written as `COUNT(*)` therefore can never answer "no". Write it so the
row itself is the answer: `SELECT 1 AS N FROM <store> WHERE <match>` gives Total Count 1 or 0.

**A column alias is re-cased to match a column of the STORE being queried.** `SELECT 1 AS txt,
2 AS zzz` against a store that has a `Txt` column returns `Txt` and `zzz`: the alias matching a
column name case-insensitively is rewritten to the store's spelling, one that matches nothing is
left alone. Which aliases survive therefore depends on which store the statement happens to
touch, and the same query against a store with a `Name` column turns `name` into `Name`. The
external SQL actions do NOT do this (`SELECT 1 AS name` returns `name`), so a query ported from
one to the other silently changes a key the page reads. Either alias to something no column is
called, or rename it back in a Node.

**`INSERT ... SELECT <aggregate> ... WHERE <guard>` inserts even when the guard is false.** An
aggregate with no `GROUP BY` returns exactly one row whatever the `WHERE` matched, so the
classic "allocate the next id" insert
(`SELECT COALESCE(MAX(id),0)+1 ... WHERE <should we insert?>`) writes a row with id 1 when the
guard was meant to stop it - and the next real insert then fails on the unique key. Put a guard
that does not depend on the scanned rows in **`HAVING`**, which filters the aggregated row.

**A `{var, path}` parameter binding only works for a typed model.** The path is emitted as a
data-model `attributeId`, so pointing it at a field of an ordinary Json variable fails at run
with `Error converting value "<field>" to type 'System.Nullable`1[System.Guid]'`. A Node cannot
hand a Query Store node a bag of values to index into: give the Node's result a real data model,
or pass each value as its own variable.

## Mixing a Guid column with text makes the whole result column binary

`COALESCE(<guidcol>, <textcol>)` returns a binary column, because MySQL's type aggregation makes
any expression with a BINARY operand binary. That part is stock MySQL (a plain server returns
`binary` from `COLLATION(COALESCE(UUID_TO_BIN(UUID()), 'text'))`). What the platform adds is the
rendering, and it guesses from the LENGTH of the bytes: exactly 16 bytes are shown as a guid,
anything else as base64. So ordinary text arrives as `bWloYWlAZXhhbXBsZS5jb20=`, and a
16-character string arrives looking exactly like a guid (`Europe/Bucharest` as
`6f727545-6570-422f-7563-686172657374`). Nothing errors, so a settings page simply fills with what
look like ids.

**Fix it in SQL with `COALESCE(BIN_TO_UUID(<guidcol>), <textcol>)`**, which keeps the result
column character-typed and leaves the plain rows alone. An earlier version of this note said no
expression mixes them safely and the two columns had to be merged in a Node; that was wrong. Use
the byte reorder above instead of `BIN_TO_UUID` when the string has to match what the designer
shows.

## The engine under a Data Store, and what follows from it

`SELECT VERSION()` through a Query Store node returns a stock **MySQL 8.0.46**, and `@@sql_mode`
is MySQL's own default with `STRICT_TRANS_TABLES` included. Before reporting a Query Store
behaviour as a platform bug, run the same expression against any stock MySQL 8: several of the
sharpest-looking ones are the engine's, and the mapping layer only obscures them.

- **Strict mode explains the write/read asymmetry.** It turns a conversion warning into an error
  in data-change statements only, so a parameter that compares fine in a `SELECT` (`CAST('' AS
  SIGNED)` is 0 with `1292 Truncated incorrect INTEGER value`) makes the same comparison fail in
  an `UPDATE`. An explicit CAST cannot rescue it, because the cast is what truncates. A guard for
  "do nothing unless this field was filled in" therefore has to be a Decisional in front of the
  node, never a WHERE inside it.
- **The timezone tables are not loaded**, so `CONVERT_TZ` returns NULL for every NAMED zone while
  fixed offsets work. Stock MySQL packages ship this way, and `mysql.time_zone_name` cannot be
  read to confirm it (system schemas are blocked). A fixed offset is not a timezone, so
  DST-correct arithmetic has to leave SQL for a script node, where JavaScript `Intl` carries the
  database MySQL does not.
- **The platform replaces the MySQL error with one of two sentences**, so `1406`, `1366`, `1292`
  and `1093` all arrive as *"values exceed the maximum allowed length"*, *"values are incompatible
  with the column type"* or *"The query could not be executed."* When a statement is refused for
  no visible reason, bisect it against the MySQL error list rather than the Query Store docs.
- **A Data Store export carries the schema, not the rows.** An imported store arrives empty, so
  ship a seeding process alongside any pack that is meant to be run in another workspace.

## Placeholder numbering is per-ACTION, and counts the outputs

`<%N%>` indices are handed out across a whole action, including the endpoint and the
output-bound properties, so a request body lifted off a live node arrives numbered `1-8, 11, 12`
with the gaps belonging to the node's own Response Body / Status. Feed such a template back with
a contiguous variable list and the unmatched `<%11%>` stays in the source: the request body is
then invalid JSON (`The Call Api request body has invalid Json format for RAW type value`), and
a script fails at parse time with `Unexpected token '<'`.

When authoring, number each property's placeholders **from 0 over its own variable list** - the
builder assigns the action-wide indices itself. Renumber a lifted template before reusing it.

## Call API `Request Parameters` is an OBJECT, and only sometimes

- With variables bound, pass `{"template": <the object>, "vars": [...]}` - and pass the OBJECT,
  not the same JSON as a string: a string template with variables is stored as text and the
  runtime refuses it with `Error setting value to CallApi RequestParameters property`.
- With NO variables, `{"template": …, "vars": []}` is also left as text; use the literal form
  `{"value": <the object>}` instead.

Lift the credential, verb, endpoint and body off the live node rather than retyping them, and
match the node by its **verb or endpoint, not its name** - porting renames nodes, so a name
lookup silently finds nothing the second time.

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

## Upsert, guarded writes, and SELECT * keys (measured 2026-10-17)

- `SELECT * FROM {{ds:Store}}` returns rows keyed by the columns' display names, plus the
  system columns (`CreatedOn`, `UpdatedOn`, `CreatedById`, `UpdatedById`); strip those in the
  Node that shapes the result.
- An upsert keyed on the primary key is one statement:
  `REPLACE INTO {{ds:Store}} ({{col:Store.Key}}, {{col:Store.A}}, CreatedById, UpdatedById, CreatedOn, UpdatedOn)
  VALUES (@k, @a, @uid, @uid, UTC_TIMESTAMP(), UTC_TIMESTAMP())`, with `@uid` a user GUID parameter.
- A write that must only happen when an upstream check passed can carry the check in SQL:
  `REPLACE INTO ... SELECT @a, @b, ... FROM DUAL WHERE @flag <> '__invalid__'` (the Node that
  validates returns the sentinel for every column when invalid), so no Decisional branch is needed.
- `UPDATE ... SET col = CASE WHEN (col IS NULL OR col = '') THEN @t ELSE col END` keeps a
  first-set timestamp (e.g. when a lead was first acknowledged).

## Seeding a store from one statement, idempotently

An export carries a Data Store's COLUMNS and not its ROWS, so any pack meant to run elsewhere
has to seed its own reference data. Two things make that one statement instead of hundreds:

- **`JSON_TABLE` works.** Pass the rows as a single JSON string parameter and read them as a
  table, so several hundred rows insert in ONE round trip:

      INSERT INTO {{ds:Store}} ({{col:Store.A}}, CreatedById, UpdatedById)
      SELECT jt.c_A, @uid, @uid
      FROM JSON_TABLE(@j, '$[*]' COLUMNS (c_A VARCHAR(80) PATH '$.A')) AS jt
      WHERE NOT EXISTS (SELECT 1 FROM {{ds:Store}} AS existing)

- **The `NOT EXISTS` guard against the target store is allowed here and is genuinely
  idempotent.** Verified: run against an already-populated store it affects 0 rows and raises
  nothing, and the row count is unchanged. This is the one place the target table MAY be named
  in a subquery - an UPDATE or DELETE doing the same thing hits MySQL 1093 instead. Note it is
  an all-or-nothing guard: a partially filled store is left alone, not topped up.

**A `JSON_TABLE` column name is a plain identifier, so a reserved word breaks it.** A column
declared as `Key VARCHAR(100) PATH '$.Key'` fails with the platform's generic
*"The query contains invalid SQL syntax."* and no hint as to which word is the problem. Declare
every column under a safe alias (`c_Key`) and map it in the SELECT list; that also covers a
column added later whose name happens to be reserved.

**`CreatedById` / `UpdatedById` are required on any INSERT** and the all-zero guid is accepted,
which is what a seed should carry: a real user id in an exported pack is a stranger's id at the
destination. The error when they are missing is unusually good - it names the column:
*"The required column 'CreatedById' has no default value and was not supplied."*

## Write the statement over lines, always

A Query Store node IS one statement, so an unreadable statement is an unreadable node. SQL built
by concatenating strings arrives as a single line, runs perfectly, and shows in the designer as
one row scrolling off the screen - 3375 characters in the worst case measured here.

**The builder now lays it out on the way in** (`tools/procesio/sqlformat.py`, called from
`_build_query_store`). The formatter only moves whitespace OUTSIDE string literals, treats
`<%N%>` and `{{ds:...}}` / `{{col:...}}` as opaque words, and compares its output's token stream
against the input before returning - handing the input back unchanged if they differ, because a
formatter that can alter a statement is worse than none. It leaves an already-multi-line
statement exactly as written.

`flow-lint` raises **UNREADABLE_STATEMENT** / **UNREADABLE_SCRIPT** for a statement or script
body over ~160 characters on one line that reached the flow some other way (a hand-set parameter,
an import). The lint flags and never rewrites: reflowing someone else's code is not its job.

**A script is REFUSED, not reformatted.** SQL can be laid out safely because only whitespace
outside string literals moves and the token stream is verified afterwards; a script cannot,
because rewriting someone's JavaScript or Python risks changing it. So the builder raises on a
`code-editor` body over ~160 characters on ONE line and names the property, and the author lays
it out. Keep a script multi-line, one statement per line; a single line is fine only when it is
genuinely one short expression (`return String(x || '')`).

The same rules apply to the external SQL actions.

## A column comes back base64 when its EXPRESSION resolves to binary

Symptom: a text column arrives as one base64 blob. Decoded, it is the right sentence with raw
bytes sitting where a value should be. It reaches wherever that column was going - a calendar
event description, an email body - so it is the user who finds it, not a test.

The encoding follows the SQL type of the WHOLE expression, and MySQL derives that by collation
coercibility, so WHICH arguments are present decides it. Measured over a real store:

| Expression | Comes back as |
| --- | --- |
| `<Guid column>` alone, or `CONCAT('', <Guid column>)` alone | the canonical GUID text |
| `CONCAT(<varchar column>, CHAR(10), <Guid column>)` | **base64**, the guid as 16 raw bytes |
| `CONCAT('x', '
', 'id=', CONCAT('', <Guid column>))` | **base64**, same |
| `CONCAT('a', CHAR(10), 'b')` - literals only | **base64** |
| `CONCAT(<varchar column>, CHAR(10), 'b')` | text |
| `CONCAT('a', CHAR(10), <varchar column>)` | text |
| `CONCAT(<varchar column>, CHAR(10 USING utf8mb4), 'b')` | text |
| `CONCAT('url?id=', <the conversion below>, '&x=1')` | text, canonical GUID |

Two rules, in order of how often they bite:

- **A Guid column inside a larger expression forces the whole column binary.** It renders as text
  only when it IS the column - `CONCAT('', g)` works alone because the layer can still attribute
  the result to a Guid chip, and contributes raw bytes the moment anything else is concatenated,
  even with character columns present. This is the one that actually breaks things, and nothing
  warns.
- **`CHAR(n)` returns a binary string, but only decides the result when every other argument is a
  literal.** One real character column in the expression keeps it character. So `CHAR(n)` is a
  latent hazard rather than the usual cause: a statement that reads fine today turns binary the
  day someone simplifies the surrounding columns out of it. `CHAR(n USING utf8mb4)` removes the
  hazard and costs nothing, which is worth doing on sight - but do not diagnose a base64 column by
  blaming it first; look for the Guid.

### Converting a Guid column to text inside an expression

The storage is `BINARY(16)` in .NET `Guid.ToByteArray()` order, so the first three groups are
little-endian and `BIN_TO_UUID` does not agree with the designer. `HEX()` is what makes the result
CHARACTER data, which is the point:

```sql
LOWER(CONCAT_WS('-',
  HEX(REVERSE(SUBSTR(g, 1, 4))),
  HEX(REVERSE(SUBSTR(g, 5, 2))),
  HEX(REVERSE(SUBSTR(g, 7, 2))),
  HEX(SUBSTR(g, 9, 2)),
  HEX(SUBSTR(g, 11, 6))))
```

Verified against the same row read through the rows API, and the text it produces MATCHES the
binary column in a filter or a typed parameter - which is what makes it usable in a link the
product later looks the row up by.

**A placeholder is not reusable, so this needs five chips per Guid.** `<%N%>` indices bind
`Variable[]` positionally and nothing substitutes the same index twice; the way to name one column
five times is five chips pointing at it, which a config's `{{col:Store.Column}}` token does
naturally (one index per occurrence). `node-set-param` refuses this edit by design - it holds the
placeholder set fixed - so reach for `node-set-query`, which rewrites the statement and
regenerates its chips together.

### Why it matters beyond cosmetics

A link assembled this way carries the identifiers the product will later match the row by. Get the
encoding wrong and the link is not merely ugly: the bytes land raw, they include characters that
cannot survive a URL (quotes, newlines, control bytes), and the page the link opens can never find
the record. A customer then has a cancel link that does nothing - and the way that surfaces is a
second booking next to the first, with the first still marked active.

## JSON_VALID does NOT protect a CAST ... AS JSON in the same expression

Reading a JSON payload that came from an HTTP response is the normal case, and an HTTP response
is not always JSON: an auth failure answers with a page, a gateway answers with text, a timeout
answers with nothing. So the parse has to be defended, and the obvious defence does not work:

```sql
-- STILL ERRORS on a non-JSON payload: the guard does not stop the cast being evaluated
JSON_VALID(@payload) AND EXISTS (SELECT 1 FROM JSON_TABLE(CAST(@payload AS JSON), ...) AS t ...)
```

Measured: with `@payload` = `Unauthorized`, or empty, the step fails with "The query could not be
executed." A statement that only runs every few minutes inside a scheduled flow then takes the
whole flow down, repeatedly, for a reason that has nothing to do with the data it was written for.

Sanitise the VALUE before it reaches the cast instead, so the cast never sees anything else:

```sql
CAST(IF(JSON_VALID(@payload), @payload, '{}') AS JSON)
```

With that, the same six payloads (a valid object, a valid array, an object with the array missing,
plain text, an empty string, and the real thing) all evaluate to a plain false and the step
succeeds. Worth probing with exactly that spread before shipping a JSON predicate: the two that
break are the two nobody writes a test for.

## A scheduled reconciler should key on the remote's own state, not on a notification

A pattern that works, from a booking product whose calendar events live in a third-party
calendar: the reconciling flow re-reads each future record's remote object every couple of
minutes and releases the local record when the remote says it is gone. Three signals, and all
three are needed:

| Remote says | Means |
| --- | --- |
| HTTP 404 / 410 | the object was deleted outright |
| 200 with the object's own status `cancelled` | cancelled in place |
| 200, status still live, but the invited party's `responseStatus` is `declined` | the person is not coming, though the object survives |

The third is the one usually missed, and it is the only one that distinguishes "they declined" from
"nothing happened". Match the decline on the invited party's OWN address rather than on "any
attendee declined", or one guest's decline cancels the host's meeting. The guard costs one extra
parameter and is worth it.

The broader point: no webhook is involved and none is needed. The remote object IS the state, so
re-reading it converges no matter which of the two sides acted, and a missed notification cannot
desynchronise anything. The cost is that a reader who looks between two ticks sees the old value -
so when verifying, re-read after a tick rather than concluding the mechanism is broken.

## A value injected into a JSON body must carry the JSON escape, not the character

A statement that builds text for an HTTP body is building part of a JSON document, because a Call
API body template substitutes the value RAW into a string:

```json
{ "description": "<%7%>" }
```

So a real newline in that value is a literal newline inside a JSON string, which is invalid JSON.
The request is then malformed and the call does nothing - and because the loop around it carries
on, the flow still reports success. The symptom is an absence: no event, no error, nothing in the
logs.

The value therefore has to contain the two characters `\` and `n`, which the JSON parser turns
back into a newline. From MySQL that means a doubled backslash in the literal, `'\n'`, since
`'\n'` is MySQL's own escape and produces the character itself. Easy to get wrong through a
generator: check the stored statement, not the generator's input - `\n` and `\n` look identical
in most error-reporting and one of them silently means "newline".

Keep the real character where the text is PARSED rather than embedded: splitting a pasted list on
newlines still wants `CHAR(10 USING utf8mb4)`. Same statement, two different answers, decided by
where the string is going.

### Why this one hides: one bug can mask another

The same statement had the base64 fault described above, and base64 contains no newlines and no
quotes - so while the column was being base64-encoded, the body it fed was always valid JSON and
the create worked. Fixing the encoding is what made the newlines real and broke the call. Neither
bug was visible while the other stood.

The lesson is procedural: after repairing how a value is ENCODED, re-test every consumer of that
value, not just the one whose output looked wrong. The repair changes the bytes, and something
downstream was relying on the broken shape without anyone knowing.

## Coerce EVERY parameter, or the one you skipped is the one that breaks

A write statement fed from a form usually wraps its parameters defensively - `CAST(@n AS SIGNED)`,
`NULLIF(@s,'')`, `COALESCE(CAST(NULLIF(CAST(@n AS CHAR),'') AS SIGNED), 0)`. The failure mode is
the single parameter that was left bare, because a form does not send typed values: it sends
strings, and an untouched control sends an EMPTY string. An empty string into a boolean or numeric
column answers:

```
One or more values are incompatible with the column type.
```

The step fails, the flow ends at status 40, and every output variable is null.

Two things make this hard to spot from the outside. The statement looks careful - eight parameters
guarded, one not - so a reader skims past it. And the user-visible symptom is not an error message
but a false negative: a page that reads an output variable to decide what to say gets null and
reports that nothing happened, which is true but says nothing about why. Reproduce by sending
every parameter as `""`, which is what a form with untouched controls actually sends; typed values
will keep passing and hide it.

Coerce a boolean by VALUE, not by cast: `CAST('true' AS SIGNED)` is 0 in MySQL, so casting the
string a select sends would silently deactivate everything. Map it:

```sql
CASE WHEN LOWER(CAST(@flag AS CHAR)) IN ('1','true','yes')  THEN 1
     WHEN LOWER(CAST(@flag AS CHAR)) IN ('0','false','no')  THEN 0
     ELSE <the default> END
```

And pick the ELSE per statement, not once: on an INSERT a blank should take the form's own default,
while on an UPDATE a blank means "the control did not come through", so it must keep the stored
value (`ELSE <the column>`) - otherwise editing a name silently re-activates something the owner
had switched off. Keeping the column there needs a second chip for it, since a placeholder cannot
be repeated.

### A related trap in the page, not the query

When a statement's result is the only thing a page inspects to decide its message, check what that
result MEANS. A chain of guarded statements where each one is a no-op unless its branch applies
will report the affected-row count of whichever node is bound to the output - typically the last
one - so a successful INSERT can report 0 while an UPDATE reports 1. A page that treats
"not null" as success is then right by accident, and a page that treats "greater than zero" as
success calls every create a failure.

### Auditing a panel for both faults at once

Worth doing in one pass rather than discovering them a click at a time. Two checks, and the first
needs the column type or it drowns in noise:

- **Uncoerced writes.** List every `@param` sitting in an INSERT value position or an UPDATE SET,
  resolve the chip it is written to, and report only those whose column is NOT a string. A string
  parameter into a string column is harmless; everything else is a statement waiting for an empty
  control. On a real panel this cut 56 raw hits down to 2 genuine ones, and a comparison in a
  WHERE is not a write - exclude it or it reads as a false alarm.
- **New-record guards.** Find every create guarded on an id and check what the panel sends for a
  NEW record. `IS NULL` only accepts an empty field; a panel that marks "new" with `0` never
  inserts, and a panel that marks it with `''` works - the same codebase can contain both, so the
  guard has to be read against its own page, not in the abstract. `COALESCE(..., 0) = 0` accepts
  either and is the form to standardise on.

- **A data-model input.** Before auditing the statements at all, check whether the process takes a
  data model as a form-facing input: a form publishes only top-level variables, so those parameters
  are NULL no matter how the SQL is written. See "A form publishes only TOP-LEVEL variables" in
  PROCESIO-RESOURCE-MODEL-NOTES.md. This one outranks the other two, because it makes a correct
  statement look wrong.

A third pattern shows up in the same audit and is worth knowing even though it is not a failure:
when several guarded statements share one flow, only one of them is usually bound to the output,
so the page sees that statement's row count and nothing else. A create then reports 0 while
succeeding. That is survivable if the page treats "no value at all" as the failure signal, since a
genuine fault ends the flow and leaves every output unset - but it means the row count itself
carries no information, and anyone who later tests it for `> 0` turns every create into a reported
failure.

### "It stopped showing" is a data question before it is a code question

A page that deliberately hides a block when its value is empty looks exactly like a page
that has broken. Both show nothing, and the second reading is the tempting one because
something was changed recently. Read the stored value first; it costs one query and it
decides which half of the system to open.

Two cheap checks settle it, in this order:

- **Is the value there?** If the row is empty, the renderer is probably doing its job.
  Hiding a block whose text is missing is normal and correct - it stops a half-filled
  settings page from showing an orphan image or a stray heading - so an empty block is
  evidence about the data, not about the code.
- **Was it EVER there?** A key-value settings table carries a per-row updated timestamp,
  and that is the whole history you need. Rows written seconds apart in one run are the
  seed. If the fields in question still carry the seed timestamp, nothing erased them:
  they were never filled, and "it used to work" is a memory of a different build. If they
  carry a later timestamp than their neighbours, something did write over them, and the
  timestamp says when.

The same timestamps answer a bigger question for free: **if no two keys that a single save
would touch share a timestamp, that save has never successfully run.** A panel whose save
has never run is worth knowing about before trusting it with real content.

### A settings save erases what the page did not send

The sibling of the rule above, and the reason to check the statement before inviting
anyone to use the page. A settings panel usually writes every key in one `CASE` over the
key column. Each branch that writes its parameter straight through will blank its row
whenever that control arrives empty - and a control arrives empty for ordinary reasons: a
collapsed section, a tab the page never populated, a field the person never opened. So
pressing Save to change one field can quietly clear a dozen others.

Guard every branch, not the few that look important:

```sql
WHEN '<key>' THEN COALESCE(NULLIF(@p<n>,''), <the value column>)
```

A partly guarded statement is the dangerous shape, because the protected keys survive
every test and hide the behaviour of the rest. Count the branches against the key list and
make the guarded number equal the total.

The cost is that a value can no longer be cleared from the page, since a blank control and
a deliberate erase arrive identically over the wire. That is the right trade for settings:
clearing is rare and recoverable, silent mass erasure is neither. Where clearing must be
offered, give it its own explicit control rather than inferring it from emptiness.

**Verify it the way it will fail:** run the save with every field empty and diff the table
before and after. Nothing may change. That test fails loudly on a partly guarded statement
and passes on a fully guarded one, which is exactly the distinction no amount of reading
reliably catches.

### A setting that holds a URL rots, and a dead one is worse than an empty one

The same renderer that politely hides a block with no text will happily emit an
`<img>` for a URL that no longer resolves, so the careful empty-value handling buys
nothing once a stale address is stored. Addresses taken from a marketing site or a
social network are the ones that go: a CDN path changes on the next site rebuild
(`410 Gone`), and an image served from a social profile is signed and hotlink-blocked
(`403`), so it works in the browser where it was copied and nowhere else.

Check the address before writing it, not after someone reports the page looks broken:
one request for the status, the content type and the size. Prefer an asset served from
somewhere under the owner's control, and when there is no good address, store nothing -
a block that hides itself reads as deliberate, a broken image reads as neglect.

Worth re-checking whenever restoring content from an older record: the text survives
indefinitely, the links beside it usually have not.

#### When there is no stable host, embed the image instead of linking it

A small decorative asset - a logo mark, an avatar - does not need a host. Encoded as a
`data:` URI it travels inside the setting itself, so there is no address to go stale, no
CDN to block the request, and nothing to re-point after a site rebuild. It is the honest
answer to the previous rule rather than a workaround for it.

Two things make it practical:

- **Size the image to the box it is drawn in, not to the file you were handed.** A
  portrait rendered in a 56px circle needs 112px for a high-density screen and no more.
  A 1.8 MB source became under 7 KB of `data:` text at that size; the same image embedded
  at its original resolution would be unusable. Encode to a format with alpha that
  compresses well, and the result is smaller than most of the page around it.
- **The field's own validation will refuse it.** A URL control typically carries a
  pattern like `^https?://.+$`, which a `data:` URI fails, so the panel rejects a value
  the renderer would have been perfectly happy with. Widen the pattern to accept both
  shapes when adopting this, or the setting can only ever be written from behind the page.

Verify it the same way as a link: read the row back and compare it byte for byte with
what was sent (a long value is exactly the kind that gets truncated silently), then load
the page and check the image reports a non-zero natural size rather than merely existing.

### A reconciler's lag reads as a broken integration

When the remote record is created by a sweep rather than at the moment of the action, the
page says "done" and the calendar, inbox or ledger stays empty for a minute or two. The
person checks straight away, sees nothing, and reports it broken. Two separate sweeps in
series double it: an end-to-end wait of two to four minutes is normal with two reconcilers
on a two-minute timer, and it is not a fault.

Before touching anything, settle it with the data: **the id the remote system returns on
creation, stored on the row, is proof the record exists.** If every row carries one, the
integration is working and the complaint is about latency. Only a row that is finished but
has no remote id is a real miss, and that distinction takes one query.

The timestamps then measure the lag directly: the gap between the row being written and
the field the sweep fills tells you what the real wait is, per booking, without
instrumenting anything.

The design choice is worth stating where users can see it. A page that promises a calendar
invitation should say it arrives within a couple of minutes, or the work should move into
the action itself. Silence about the delay is what turns a normal wait into a bug report,
and it costs nothing to fix in the confirmation text.

### A table column can show a field the query never returned

Worth knowing before concluding a filter is ignored. A list is often painted through a
mapping step that computes display-only fields - a formatted timestamp in the reader's
zone, a label resolved from a code - which exist nowhere in the query result.

That makes a table fragile in a specific way: when several controls refill the same table
and only some of them run the mapping, the others hand over rows that are correct but
missing the one field the column renders. The column comes back blank, or the control
keeps what it had, and it reads as "the button did nothing" rather than "the button
painted unformatted rows".

So when a filter looks ignored, check in this order, because each step is cheaper than the
one after it:

1. **The data.** A filter that matches nothing and a filter that never ran look identical
   on screen. Run the query behind it with the same argument and count the rows first.
2. **The parameter.** Whether the control's value reaches the query at all.
3. **The repaint.** Whether the control that refills the list computes the same display
   fields as the path that first filled it. Every writer of one list should go through one
   shared mapping; two writers that format differently is a defect waiting for a user to
   find it.

A related trap in the same family: a filter whose value is read from a hidden carrier
field rather than from the visible control. The carrier exists because the visible control
holds a different shape (a timestamp where the query wants a day), but nothing copies one
into the other unless a step is wired to do it, and a filter reading an empty carrier
silently returns everything.

#### A step that reads the run's output needs the run marked synchronous

In an event chain, the flag that makes a process run synchronously is a tri-state in
practice: true, false, and never set. Never set is not the same as true. A chain written as
"run the query, then paint what it returned" works on a fast day and paints the previous
result on a slow one, which is the worst kind of defect to chase because it reproduces
only under load.

So whenever a later step in a chain reads a variable the run fills, check the flag on the
run rather than assuming it, and set it explicitly. It costs one field and removes a whole
class of intermittent "the button shows stale data" reports. The same check is worth
running across every chain at once: a list of each run with its flag takes seconds to
produce and the odd one out is usually the one nobody set.
