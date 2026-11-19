# PROCESIO form queries - saved Data Store SQL on a form template

A form template can carry its own **saved Data Store queries**: SQL statements stored on the
template, bound to Data Store tables and columns, taking named parameters. An element event
runs one by id. The browser never sends SQL: the runtime sends the query id and the parameter
values, and the server runs the stored text. Data Stores are MySQL-backed, so the dialect is
MySQL (the statement rules are those of the Query Store action, `PROCESIO-QUERY-STORE-NOTES.md`).

Verified against a live environment, 2026-11.

## Use it instead of a process for reads

When a form only needs Data Store rows, a saved query (or a READ event) is the way, not a
process with a Data Store or Query Store action. Measured on production (2026-11-19, a 200-row store, 50 rows returned, 25 runs each): a saved query answers in a median of 29 ms and a row READ in 33 ms, one call each; the same read through a one-action process takes a median of 266 ms over two calls (publish, then a synchronous launch) and leaves a process instance per click. In the browser the click took about 55-80 ms against 210-290 ms. A real process has more than one action, so the gap only grows. Verified end to end on
production the same day: saved through `form-create`, kept by the server, run anonymously
on a public form, and a click in the browser filled a dynamic table.

**Versions, final shape, row limits** (from the form-runtime team, 2026-11-19). The shape is
final: `queryId` on the event, the queries on the form template. Saved queries need **Web-Api
v3.3.0, form-runtime v1.34.0 and user-playground v1.117.0** (`procesio server-build` reads an
installation's Web-Api version). The backend does not limit the rows a form read returns:
keep **200 rows for a table or dynamic row and 100 for a dropdown, select or radio group**
(`LIMIT` in a query, `countPerPage` on a READ). The builder warns when a query with no LIMIT,
or a READ above those numbers, fills one of them. `sourceType` is mandatory for options built
from rows: `JSON` (verified) or `static-list` both read a list of `{label, value}` objects.

**Older builds do not have it.** Production has had it since at least 2026-11-19. Check
before relying on it elsewhere: on a build without saved form queries, `GET api/FormTemplate/{id}` has no `queries` key at all, there is no
`api/Form/dataStore/query/{id}` route, and a save that carries `Queries` answers 200 and stores
none. The form and its QUERY events are kept, pointing at a query that does not exist.
`form-create` and `form-edit` compare the read-back with what they sent and warn ("did not
keep its saved queries"); `form-set-saved-statement` fails with `not_persisted`. (Seen on
Main-PROD on 2026-11-15; the feature was built and checked against DEV.)

Three different things, do not confuse them:

- **Data Store event, READ/ADD/UPDATE/DELETE** - point-and-click row operations on ONE store
  from a form event (`FORM-DEV-GUIDE/06-PROCESS-INTEGRATION.md`, "Data store from a form").
- **Form query** (this note) - the same event with operation `QUERY`: stored SQL over one or
  more stores, with parameters.
- **Query Store action** - SQL from a PROCESS step, not from a form.

## On load, in a dropdown, and what the designer saves

Built in the designer and run in the form runtime on production (2026-11-19):

- **A form loads its data with no click.** The form's own triggers (Form settings > Events:
  onLoad, onBeforeSubmit, onAfterSubmit) take a Data store operation like any element. They
  are saved in `Data.events` as `{id, type, action, config}`, `type` = `FORM_LOAD` /
  `FORM_BEFORE_SUBMIT` / `FORM_AFTER_SUBMIT`, with the same `RUN_DATA_STORE_OPERATION` config
  an element event has. Several onLoad events all run when the form opens (a READ and a QUERY
  together: two calls, about 60-110 ms each). In a config: top-level `"events": [{"on": "load",
  "do": "datastore", ...}]`.
- **A dropdown takes rows too.** `rows` mapped to a select's `sourceValue` fills its options,
  but only if the select has a `sourceType` (`JSON`): with none, the runtime builds no option
  and the dropdown says "No data available", with no error. **The designer does not set it**
  when you map rows to the select, so a form built only in the designer gets an empty
  dropdown. Each row becomes `{name: row.label or row.name, value: row.value}`, so alias the
  columns: `SELECT Sku AS value, Product AS label ...` (an alias that matches no column keeps
  its own spelling). The builder sets `sourceType` when `rows` names a select or radio group.
- **A parameter can take a typed value**, not only a form field: the designer stores it as
  plain text on the right (`{"left": "@minqty", "right": "50"}`). In a config:
  `{"left": "@minqty", "value": "50"}`.
- **"Execute query" makes a new query per event**, named "Query N" until renamed: the
  designer has no list of the form's existing queries to pick from. A table or a column goes
  into the SQL as a chip, inserted with Ctrl+I or the Insert key in the query editor (typing a
  table name gives plain text, which the save accepts and the run cannot resolve).
- **Save in the designer makes the form a draft, and a draft is offline.** Save sends the
  whole template with `status: 0`; the public link then answers "Form not found" and the
  anonymous read `GET api/FormTemplate/{workspaceId}/{id}` 400, code 501 "User is not
  authorized for the requested action.", for a public form. Publish is the same PUT with
  `status: 1`. `form-create` and `form-edit` publish unless the config says
  `"publish": false`; the surgical writers keep the status they read, and every form action's
  `warnings` say when the form is a draft.
- **A designer tab open while the API writes keeps its old copy.** Navigating to the same
  designer URL does not reload it; its next Save sends the old template and drops what the
  API wrote, with no conflict. Reload the page before saving in the designer.

## Add, Update, Delete (built in the designer, run in the form runtime on production, 2026-11-19)

A row operation maps **a column (left) to a form value or a typed value (right)**, and its only
output is `success`. The designer saves:

```json
{ "dataStoreId": "<store>", "operation": "ADD",
  "inputMap":  [ { "id": 0, "left": "Sku", "right": "<form value path>" },
                 { "id": 1, "left": "Category", "right": "test" } ],
  "outputMap": [ { "id": 0, "left": "success", "right": "<form value path or empty>" } ],
  "filters": [], "queryId": null, "areFiltersConfigured": true }
```

`left` is the column's display name; the designer lists only the store's own columns, never
the system ones. A typed value on the right is stored as text and written as that value (a
number column gets a number). Each operation is one call of about 80-200 ms.

| Operation | What it does | Rules |
|---|---|---|
| **ADD** | writes ONE new row from the mapped columns | takes no filters. It fills `CreatedOn`, `UpdatedOn`, `CreatedById` and `UpdatedById` itself (with the form owner when the form is public): unlike a saved query, it needs no audit columns mapped. A key that already exists gives `success: false`. |
| **UPDATE** | sets the mapped columns on the rows the filters match | **needs filters.** With none, the runtime targets the rows whose every mapped column already equals the new value, so nothing changes; and a mapped primary key column is refused by the server: `400`, code 502, "Primary key columns cannot be updated from this endpoint: <column>". Filter on the key, map only the columns that change. `UpdatedOn` / `UpdatedById` move. |
| **DELETE** | deletes the rows the filters match | with no filter it deletes the rows whose every mapped column equals the mapped value: map only the key column(s), or one non-key column deletes every row that shares its value. |

A failed operation shows the runtime's generic toast ("Something went wrong! The data store
operation couldn't be completed. Check your configuration and try again."), whatever the
cause. Map `success` to a field and show your own message from it.

In a config: `{"on": "click", "do": "datastore", "operation": "add", "dataStoreId": "<id>",
"inputs": [{"left": "Sku", "right": "<field>"}, {"left": "Category", "value": "test"}],
"outputs": [{"left": "success", "right": "<field>"}]}`; `update` and `delete` take `filters`
like a READ. `form-create` / `form-edit` read the columns of every store the form writes and
refuse an unknown column, an UPDATE with no filter or of a key column, and warn about a DELETE
with no filter that maps a non-key column.

## A saved query with several statements

Statements separated by `;` run in order as one call (about 100 ms), with no transaction. The
form's `rows` / `count` come from the one statement that returns rows; put it last. Verified:
`UPDATE ... SET Qty = Qty + 1 WHERE Sku = @sku; SELECT ... WHERE Sku = @sku` updated the row
and showed it in a table with `count` = 1 (the rows returned, not the rows changed). A script
whose statements all write returns the affected-row count instead.

- **SQL writes do not maintain `UpdatedOn` / `UpdatedById`** (the row operations do). Set them
  in the statement if the form relies on them.
- Two row-returning statements are refused after the script ran (its writes are kept), and the
  timeout bounds each row-returning statement, not the script (see "What surprises" below).
- Use one for "change, then show the result" in a single click, instead of a write event and
  a read event.

## The saved query

`GET api/FormTemplate/{id}` (designer route, authenticated, `workspaceId` header) returns a
top-level `queries` list:

```json
{ "id": "<guid chosen by the client, stable across saves>",
  "name": "Find product",
  "value": "SELECT Product, Qty FROM  <%1%>\nWHERE Product = @product",
  "variable": [
    { "id": 1, "type": "dataStoreTable",  "variableId": null, "dataStoreId": "<store guid>", "attribute": null },
    { "id": 2, "type": "dataStoreColumn", "variableId": null, "dataStoreId": "<store guid>",
      "columnId": "<column guid>", "attribute": null } ],
  "parameters": ["@product"],
  "timeoutSeconds": null }
```

- **`value`** is the statement. A `<%N%>` tag stands for a Data Store table or column.
- **`variable`** holds one binding per tag, `id` = the tag number. `type` is `dataStoreTable` /
  `dataStoreColumn` (what the designer writes) or the numbers `1` / `2`. A process-variable
  binding is refused: a form query binds only tables and columns.
- **`parameters`** are the `@name`s the statement takes, stored as written (with or without the
  `@`). After the optional `@`: `[A-Za-z_][A-Za-z0-9_]*`, at most 64 characters, not declared twice in the same spelling.
- **`timeoutSeconds`**: `null` means the default of 60; allowed 1..600.
- **Vocabulary**: a *tag* is the `<%N%>` marker in the SQL, a *binding* is the `variable` entry
  behind it, a *parameter* is an `@name`. They are three different things.

### What each route returns

| Route | Queries |
|---|---|
| `GET api/FormTemplate/{id}` (designer) | the full shape above |
| `GET api/FormTemplate/{workspaceId}/{id}` (anonymous render) | `id, name, parameters, timeoutSeconds` only - never the SQL or the bindings |
| the paged form list | `queries` empty |

So an empty `queries` on a list row says nothing; read the template itself.

## Saving: a save without `Queries` deletes them, and the SQL is not checked

`POST` / `PUT api/FormTemplate` take the list as top-level **`Queries`** (PascalCase, like the
other top-level keys).

- ⚠ **The PUT replaces the whole template: a body without `Queries` deletes them.** Every save
  must carry the list. The surgical form actions echo it from the GET; `form-edit` keeps the
  live queries when its config does not mention `queries`, and replaces them when it does
  (`"queries": []` removes all).
- The save validates and answers **400 with one item per problem**, `target` =
  `queries[i] '<name>': <problem>`: a tag with no binding, a tag bound twice, an unknown binding
  kind, a process-variable binding, a Data Store that is not in the workspace, an unknown column,
  stores from different databases, a bad or duplicate parameter name, a timeout out of range,
  empty text, a missing or duplicate id or name.
- ⚠ **The SQL itself is not checked at save.** A syntax error, a wrong column or a statement the
  Data-Store service refuses surfaces only when the query runs. Run it once after saving.
- The tool checks the local half before sending (tags against bindings, parameter names, timeout,
  duplicate ids and names) and reports it in the same `queries[i] '<name>': ...` form. Workspace
  facts (does the store exist, is the column on it, same database) are the server's to check.

### A designer save drops a query no event runs

⚠ The designer sends only the queries that some event references by `queryId`. A query that no
event references is **dropped by the next designer save** of that form, silently. So a query
written through the API must be wired to an element event if the form will ever be opened in the
designer. `form-get-queries`, `form-create`, `form-edit` and `form-set-saved-statement` report
such a query under `warnings`.

## The event that runs a query

It is the existing Data Store event with a new operation. Exactly as a designer save writes it
(a button's `onClickEvents` config value):

```json
{ "debounce": 0, "events": [ {
    "id": "<guid>", "type": "CLICK", "action": "RUN_DATA_STORE_OPERATION",
    "config": {
      "dataStoreId": null, "operation": "QUERY",
      "inputMap":  [ { "id": 0, "left": "@product", "right": "<form value path>" } ],
      "outputMap": [ { "id": 0, "left": "rows",    "right": "<form value path>" },
                     { "id": 1, "left": "columns", "right": "" },
                     { "id": 2, "left": "count",   "right": "<form value path>" },
                     { "id": 3, "left": "success", "right": "" } ],
      "filters": [], "queryId": "<query guid>" } } ] }
```

- `dataStoreId` is `null` and `filters` is empty: the stores come from the query's bindings.
- `inputMap.left` is the **declared parameter name**, spelled exactly as in `parameters`;
  `right` is the form value path (dotted guids).
- `outputMap.left` is one of `rows | columns | count | success`. The designer writes all four
  rows and leaves `right` empty for the ones that are not mapped.
- In a `form-create` / `form-edit` config: `{"on": "click", "do": "datastore", "operation":
  "query", "query": "<name or id>", "inputs": [{"left": "@product", "right": "<field name>"}],
  "outputs": [{"left": "rows", "right": "<field name>"}]}`. The builder resolves the query name
  to its id and field names to value paths, and fails on an unknown query, an undeclared
  parameter or an unknown output. On a live form, `form-set-element-event --action
  RUN_DATA_STORE_OPERATION --operation QUERY` does the same for one element.
- **Showing the rows in a table** takes two things, both verified in the form runtime:
  - `rows` is mapped to the **source value of the table's dynamic row** (the row element's
    `sourceValue`), not to the table's `value` and not to the row's `value`. Either of the other
    two adds one table row per result row with every cell empty, and no error, while `count` is
    still right, so the form looks half-working.
  - each table column's `key` equals the key the row carries, which is the Data Store column's
    display name (`Product`, not `product`). The cell controls' names and ids play no part.
  In a config, name the table (or its row) as the `rows` target and the builder writes the row's
  source path: `"outputs": [{"left": "rows", "right": "<table name>"}]`, with the table declared
  `"dynamic": true` and its columns keyed by the returned names. The mapping survives a designer
  save. A write followed by the list query on the same trigger refreshes the table: the events
  of one trigger run in order.
  - A process's list output (`RUN_PROCESS`) fills a dynamic table the same way, through the
    row's source; the builder resolves a table name there too (verified in the form runtime).
  - A `rows` target that names a **static** table (or its row) is refused at build: a static row
    has no source to fill, so the save would succeed and the table would stay empty. A dynamic
    table nested in a section, column or tab is wired the same as a top-level one.
  - Every dynamic row the builder writes now declares `sourceValue` in its data model, whether a
    query fills it or not, because the designer's own capture has it on every dynamic row. The
    next `form-edit` of an older form built by the tool therefore adds that one attribute to each
    dynamic row; nothing else on the table changes.

## An INSERT has to bring its own user id

A Data Store row carries `CreatedById` and `UpdatedById`, both required and without a default.
The Data Store row operations of a form fill them; a saved query does not. There is no
server-supplied parameter for the caller either, so the statement names both columns and the
form supplies the value:

- **The statement:** `INSERT INTO <%1%> (<%2%>, ..., CreatedById, UpdatedById) VALUES (@a, ...,
  @who, @who)`. Without the two columns the run answers 400 "The required column 'CreatedById'
  has no default value and was not supplied." The save accepts it: the statement is not read
  until it runs.
- **The value is a plain parameter.** A Guid-shaped string is bound as a Guid before the
  statement runs, so `@who` works and `UUID_TO_BIN(@who)` or `UNHEX(REPLACE(@who,'-',''))` fail
  (502, code 100), because the function receives binary.
- **Where the form gets it.** `@who` is mapped like any input, so the form needs a field that
  holds a user id: a read-only field with a fixed id as its default, or a control the person
  picks a user in. On a public form the visitor has no account, so the id is one the designer
  chose. Whatever is mapped is what the row records: the value is not checked against the caller.
- **UPDATE and DELETE need neither column.** An UPDATE that should record who changed the row
  sets `UpdatedById` the same way.

`form-create`, `form-edit` and `form-set-saved-statement` warn when a query inserts without the
two columns.

## Running a query: parameter names exactly as declared

`POST api/Form/dataStore/query/{queryId}` - the form-runtime route.

- Headers: `formTemplateWorkspaceId`, `formTemplateId`, optional `formInstanceId`.
- Body, optional: `{ "parameters": { "@product": "apple" } }`.
- ⚠ **Parameter names are sent exactly as declared.** An undeclared name is refused, so a
  parameter declared as `@product` is sent as `@product`. A declared name that is left out
  binds **NULL**, with no error.
- **Public form**: works anonymously and runs **as the template owner**. Anyone who can open the
  form can run its queries with any parameter values, so a query on a public form is a public
  endpoint: write it to return only what a stranger may see and to change only what a stranger
  may change.
- **Private form**: needs a signed-in caller who is working in the form's workspace. The normal
  `workspaceId` header must be sent as well, otherwise 403 code 501 "The user is not working on
  the form workspace."; signed out, 403 code 501 "The form template is private."

Response:

```json
{ "columns": [ { "columnId": "...", "name": "Product", "dataTypeId": "...", "isList": false,
                 "isPrimaryKey": false, "isRequired": false, "isSystemColumn": false } ],
  "rows": { "totalItemCount": 1, "pageNumber": 1, "pageItemCount": 1,
            "pageItems": [ { "Product": "apple", "Qty": 3, "Note": "first" } ] } }
```

- Row keys are the store's **column display names**. An alias that differs from a column only by
  case still comes back under the display name.
- For INSERT / UPDATE / DELETE, `totalItemCount` is the **affected-row count** and `pageItems` is
  empty.

| Answer | Meaning |
|---|---|
| 400, statusCode 502, target `query` | an undeclared parameter; a bound Data Store that is no longer available; two result sets ("Expected maximum one table but received 2 tables!"); a statement Data-Store refuses; a timeout ("The query did not finish within the configured time limit.") |
| 404, code 1004 | "Query not found for this form template." - the id is not (or no longer) one of the template's queries |
| 502, code 100 | "The query could not be executed." |
| code 1013 | the Forms or the Data Store feature is switched off on this environment |

## What surprises: values, limits, identity, copies

**Values**

- A JSON string, number, boolean or `null` binds as that value; an object or array binds as its
  JSON text. A date-shaped string stays a string, and MySQL converts it where the statement
  compares it with a date column.
- **An empty string is a value, not NULL.** A blank form field reaches the statement as `''`;
  write `NULLIF(@name, '')` where a blank should mean NULL. A declared parameter that is not
  sent at all binds NULL.
- Supplying one parameter twice is refused (400, code 502). Two spellings of one declared
  parameter (`x` beside `@x`, or `X` beside `x`) pass the save and are refused at every run.
- A statement must not use a parameter's name for its own variable: `SET @x = 1` with a
  parameter `x` becomes a syntax error.

**What the statement may do**

- Nothing guards rows. An UPDATE or DELETE without a condition is accepted and does what it
  says, and a statement may set a primary key.
- A script that returns two result sets is refused **after it has run**: its writes are kept,
  only the output is thrown away. Put the row-returning statement last and only once.
- Two result columns with one name collapse, the last one wins. Alias them apart with `AS`.
- A backslash-escaped quote inside a literal and a double-quoted string literal are refused.
  Write a quote as `''` and string literals in single quotes.
- For a statement that returns no rows the count is the rows **matched**, not the rows changed:
  an UPDATE that sets a value a row already has still counts it.
- A statement that names no Data Store runs in the caller's own Data Store database.

**Limits**

- The timeout bounds each row-returning statement, not the script. When it expires, what the
  earlier statements wrote stays. The message is "The query did not finish within N seconds."
- A run is never retried, because a query can write. Retrying from the tool is the caller's
  decision and repeats every write.
- The client must wait longer than the server may run. `form-run-saved-statement` waits the
  query's `timeoutSeconds` (60 when null) plus 30 s, and never less than 120 s. A client that
  gives up first reports a failure for a statement that still commits, and the retry that
  follows writes a second time.
- A row cap, where the deployment sets one, **fails** the request; it does not truncate. The
  default is unlimited, and the form route adds no cap of its own.
- The 1..600 seconds range is the deployment's maximum, 600 unless configured lower.
- Nothing meters or rate-limits the route.

**Who runs it, and when it answers**

- A public form runs the query as the template owner, a private form as the signed-in caller.
  A signed-in person outside the workspace is treated on a public form as the anonymous
  visitor is.
- The template must exist and be enabled (`State`).
- On a private form an owner-scoped caller also needs the `FormInstance.Update` permission. A
  `formInstanceId` is honoured on a private form only for a form admin or the current step
  assignee.
- In a personal workspace a query reaches only the caller's own stores: another person's
  store is refused as not available.

**Copies and saves**

- A save is all or nothing: when one query is refused, nothing is written, the form's content
  included. `null` for `Queries` stores none, exactly like leaving it out.
- A query name is non-blank, at most 128 characters and unique regardless of case.
- A binding whose tag is not in the text is stored as sent and never checked, at save or at run.
  The tag rules (one binding per tag, a table or a column) apply to the tags the text uses.
- **Duplicate** keeps the query ids and the bindings, which still name the original stores.
- **Import does not run the save's checks.** An imported form whose bindings name stores of the
  source workspace is accepted and then refused at every run (400) until each query is re-bound
  and saved. After an import, run every query once.
- A binding whose store or column was deleted is refused at run until the query is saved again
  with a valid binding.

**More run errors**

| Answer | When |
| --- | --- |
| 409, code 1006 "The query violates a unique key constraint." | an INSERT repeats a key |
| 503, code 100 "The Data Store service is currently unavailable." | the service is down |
| 400, code 1005 | the `formTemplateId` header is empty |
| 400, code 1013, the target naming the flag | the Forms or the Data Store feature is off |
| 502 or 500, code 100 "The query could not be executed." | Data-Store failed internally |

A message relayed from the Data Store service arrives as one line of at most 500 characters.

## The tool actions: running a saved statement is a write

| Action | Does |
|---|---|
| `form-get-queries --form-id` | read the queries and which elements run each |
| `form-set-saved-statement --form-id --name ...` | add or change ONE query in place; checks it, saves, reads back |
| `form-delete-saved-statement --form-id --query-id` | remove one; refused while an event still runs it, unless `--allow-referenced` |
| `form-run-saved-statement --form-id --query-id --params` | run one through the runtime route, after checking the parameter names against the declared ones |

⚠ **Running a saved statement is a write.** The stored SQL can be an INSERT, UPDATE or DELETE and
the action name cannot say which, so the reversibility gate classes every run as irreversible
(data loss) and asks for approval. For the same reason the write and run actions are named
`saved-statement`, not `query`: the gate treats the word `query` in an action name as a read.
