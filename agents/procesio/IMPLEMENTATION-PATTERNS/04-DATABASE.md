# Database patterns for PROCESIO ↔ SQL Server (generalized)

These are reusable techniques taken from a production PROCESIO workspace backed by Azure SQL. They contain no client names, no business table names and no data values. Each entry follows the same shape: **Pattern / Problem / Mechanics / When / Pitfalls**. The first group (1–14) is worth copying. The last section (15) lists anti-patterns found in the same database, so they are not repeated.

---

## 1. Whole-form JSON orchestrator procedure

**Problem.** A multi-step web form produces one large nested object. Writing it from the flow as a dozen separate SQL nodes gives no atomicity, no shared validation and a flow that is hard to read.

**Mechanics.**
- The flow makes one call, `EXEC schema.usp_X_SaveFormObject @form_json = @form_json`, which passes the whole object serialized.
- The orchestrator validates, generates all keys, opens **one transaction**, and calls small sub-procedures, one per detail table. Each sub-procedure does `INSERT … SELECT … FROM OPENJSON(@form_json, '$.section') WITH (...)`.
- It commits and returns the resulting root row.

**When.** Any form or wizard submit that touches more than one table.

**Pitfalls.**
- Sub-procedures must **THROW** on data errors (`IF @@ROWCOUNT <> 1 THROW 500xx`). Only the orchestrator turns errors into result rows (see 3).
- Keep `SET XACT_ABORT ON` so an error inside a nested EXEC dooms the transaction.

## 2. Pre-flight error collection before any write

**Problem.** Failing on the first error forces the user through fix-and-retry loops, and a partial write leaves junk rows behind.

**Mechanics.**
- `DECLARE @Errors TABLE (error_step, error_code, error_message, sql_error_number, sql_error_line, sql_error_procedure)`.
- Run every check as its own `IF … INSERT @Errors`. Checks include required fields, enum values, a JSON shape check on the selected branch (for example, "person type = company but the company id is empty"), and a duplicate or retry check.
- Then `IF EXISTS (SELECT 1 FROM @Errors) GOTO ErrorOutput`, before `BEGIN TRANSACTION`.
- Use stable UPPER_SNAKE error codes.
- A pure helper procedure that validates part of the input returns `@error_code` / `@error_message` as OUTPUT parameters instead of throwing, so the caller can add them to the same list.

**When.** Every writer called from a form.

**Pitfalls.**
- A `NULL NOT IN (...)` test evaluates to UNKNOWN and silently falls through to the else branch. Test `IS NULL OR … NOT IN (...)`.
- Validate the branch that was actually selected, not only the discriminator.

## 3. One result contract for success and failure

**Problem.** PROCESIO's `Execute Query` returns a list of row objects. If success and failure return different shapes, or success returns nothing, every flow needs fragile branching.

**Mechanics.**
- Every procedure returns **the same columns** in every outcome: `e_ok BIT, error_step, error_code, error_message, sql_error_number, sql_error_line, sql_error_procedure`, followed by the data columns.
- On failure the data columns are `CAST(NULL AS <type>)`. On success the `error_*` columns are NULL.
- Writers return one row on success and one row per error on failure. Readers return exactly one row.
- In the flow: `Get Element [0]` → Decisional on `e_ok`. For multi-row error output, use a JS check such as `list.every(r => r.e_ok === true)`.

**When.** Every procedure a flow calls.

**Pitfalls.**
- Use one result family per database. Mixing `e_ok` with `result='isOK'` and with "JSON in a single column" forces a different parser for each procedure.
- The CATCH branch must produce the same columns as the success branch.

## 4. Guarded state-machine updates

**Problem.** A root record moves through statuses. A step can run twice, run out of order, or run against a record that is already further along.

**Mechanics.**
- Inside the transaction, each step does `UPDATE root SET <pointer> = @key, status = '<next>' WHERE id = @id AND status = '<prev>'; SET @rc = @@ROWCOUNT; IF @rc <> 1 THROW 5001x, 'State machine: …', 1;`.
- Flows that advance the status later use the same guard: `WHERE id = … AND status = '<expected>'`.

**When.** Any lifecycle column: requests, approvals, integration steps.

**Pitfalls.**
- Unguarded `UPDATE … SET status = 'x' WHERE key = …` in flows breaks the machine. A replay or an out-of-order run silently regresses the state.
- Document the state list in the procedure header and keep it in sync with the code. Doc drift here is common.

## 5. Echo OUTPUT parameters as result columns

**Problem.** A PROCESIO SQL node reads only the result set, so OUTPUT parameters are invisible to the flow.

**Mechanics.**
- Sub-procedures use OUTPUT parameters to talk to the orchestrator (`@rows_inserted`, `@items_json`).
- The orchestrator exposes them in its final SELECT: `@nr_rows AS rows_inserted, @items_json AS items_json`.
- A child list that the next steps need (for example, one row per recipient with its own token) is returned as a **JSON array string column**. The flow parses it with `JSON.parse` in a JS node.

**When.** Whenever the flow needs counts or generated ids.

**Pitfalls.**
- Build the echoed JSON from the same in-memory rows that were inserted (an IDENTITY-ordered table variable), not by re-reading the base table. That guarantees the order and the exact truncated values.

## 6. Always-one-row reader with a fixed JSON skeleton

**Problem.** Consumers such as document generators, code nodes and templates break when keys disappear, when lists are null, or when the query returns zero rows.

**Mechanics.**
- Start from a driver row, `FROM (SELECT @id AS req_id) q LEFT JOIN root … LEFT JOIN detail …`, and emit `FOR JSON PATH, WITHOUT_ARRAY_WRAPPER, INCLUDE_NULL_VALUES` using dotted aliases (`[section.sub.field]`) that mirror the form object 1:1.
- Default every list to `JSON_QUERY(ISNULL((SELECT … FOR JSON PATH), '[]'))`.
- Add `TOP (1)` as a guard: a duplicated key would multiply the joined row, and FOR JSON would then glue two objects together into invalid JSON.
- Return `e_ok, error_code, …, payload_json` as one row.
- Include `_proc_version` and a `warnings[]` array for anomalies that are not errors, such as orphan pointers or inferred values.
- A JSON column stored as a string is re-emitted as a real array with `JSON_QUERY(CASE WHEN ISJSON(col)=1 THEN col ELSE '[]' END)`.

**When.** "Get the whole request" readers that feed templates or later steps, especially when the output must be interchangeable with the original form object.

**Pitfalls.**
- With FOR JSON PATH, columns that share a prefix **must be adjacent**. Otherwise the object is emitted twice.
- `JSON_QUERY` over malformed text raises an error. Wrapping it in `CASE` turns the output into an escaped string. Filter with `ISJSON` upstream, into a variable or table variable, and call `JSON_QUERY` directly in the SELECT.
- Heavy blobs (HTML, base64) should be **opt-in** through `@include_x BIT = 0` flags, with `has_x` / `length_x` columns so the flow can branch without loading them.

## 7. Root row with pointers to its detail rows

**Problem.** A request is made of several sections, some 1:1 and some 1:N, filled at different times.

**Mechanics.**
- The root row holds one GUID pointer column per section. The detail tables use `id = <that GUID>`.
- In 1:N sections every child row carries the same GUID, which acts as a group key.
- Readers follow root → pointer → detail. An orphan check is simply `pointer IS NOT NULL AND NOT EXISTS (detail WHERE id = pointer)`.

**When.** Form-shaped data whose sections are optional or depend on a discriminator (for example, person type or product type).

**Pitfalls.**
- Children have no back-reference and no row identity, so add both: a request id or FK, and a per-row `nr` order column. Without an order column, "the order SQL Server returns" is not guaranteed, and rebuilt lists can reorder between reads.
- Index the group-key and pointer columns, and put a unique constraint on any per-row token.

## 8. Zipping parallel JSON lists into rows

**Problem.** The form sends several parallel arrays for the same N items (address[], identification[], technical[], quantities[]), linked by an `id` in each element. Older payload versions send a single object instead of an array.

**Mechanics.**
1. **Normalize** each sub-node into an array: `CASE WHEN j IS NULL THEN '[]' WHEN LEFT(LTRIM(j),1)='{' THEN '['+j+']' ELSE j END`, stored in a `@lists (name PK, arr)` table variable.
2. **Guard against duplicates**: `GROUP BY list, ISNULL(TRY_CONVERT(INT, JSON_VALUE(value,'$.id')), [key]+1) HAVING COUNT(*)>1 → THROW`.
3. `elem` CTE: every element of every list, with `item_key = id, or position+1`.
4. `keys` CTE: `SELECT DISTINCT item_key`. This is the **union** of keys, so no list is the "driver".
5. One CTE per list that shreds its element with `OPENJSON … WITH`.
6. `FROM keys LEFT JOIN each CTE ON item_key` → INSERT one row per item.

**When.** Repeating groups in low-code forms, and any backward-compatible payload evolution from object to array.

**Pitfalls.**
- A duplicate id would multiply rows through the joins. That is why the guard in step 2 runs first.
- Map empty strings to NULL (`NULLIF(x,'')`) on date and numeric fields.

## 9. Reading large JSON safely

**Problem.** `JSON_VALUE` returns NULL (in lax mode) for values longer than 4000 characters, which silently loses big embedded strings. Low-code nodes also sometimes pass the wrapper object `{"field": "<json string>"}` instead of the inner string.

**Mechanics.**
- For long values use `SELECT @v = [value] FROM OPENJSON(@doc) WHERE [key] = 'field'`.
- To **auto-unwrap**, check whether a key expected at the top level is missing and a single known wrapper key is present. If so, replace `@doc` with that key's value and re-validate it with `ISJSON`.

**When.** Any procedure that receives a serialized object from a code node.

**Pitfalls.**
- Declare the target variables `NVARCHAR(MAX)` so that an oversized value **raises a truncation error** on insert, rather than being cut silently on assignment.

## 10. Canonical JSON strings for nested selections

**Problem.** A nested, loosely shaped list (selected items, co-signers) has to be stored in one column and read back reliably.

**Mechanics.**
- Normalize before storing: `SELECT ISNULL(TRY_CONVERT(INT, JSON_VALUE(v,'$.id')), [key]+1) AS id, JSON_VALUE(v,'$.a') AS a, … FROM OPENJSON(@src) ORDER BY CONVERT(INT,[key]) FOR JSON PATH, INCLUDE_NULL_VALUES`. This fixes the keys and their order, drops foreign keys and fills missing ids.
- `ISNULL(…, '[]')`, because FOR JSON over zero rows returns NULL.
- Wrap the list together with its metadata in one object (`FOR JSON PATH, WITHOUT_ARRAY_WRAPPER`). Use the union of columns across variants so the stored shape is the same whichever variant was chosen.
- Read it back with `CROSS APPLY OPENJSON(col, '$.items') WITH (...)`.

**When.** Small, bounded child lists where a separate table is not justified.

**Pitfalls.**
- Check `LEN()` against the column width and fail with a clear message that says which column to widen, rather than failing with a generic truncation error.

## 11. Singleton configuration table fed by a webhook

**Problem.** An external system pushes a full configuration document (tariffs, rates) that replaces the previous one.

**Mechanics.**
- Validate with `ISJSON`.
- Read scalars with `JSON_VALUE` and arrays/objects with `JSON_QUERY`, storing the latter raw.
- For a key that may be either null or an object, use `COALESCE(JSON_QUERY(...), JSON_VALUE(...))`.
- Upsert: `IF EXISTS (SELECT 1 FROM cfg) UPDATE cfg SET … ELSE INSERT`.
- Wrap it in a transaction and TRY/CATCH, and return one row of status.

**When.** Reference data that is replaced as a whole.

**Pitfalls.**
- Keep the history: add `valid_from` and keep old rows instead of overwriting them in place. Contracts generated earlier may need the tariffs that were valid at the time.
- Protect the endpoint. The API key must not sit in a readable table (see 15).

## 12. Compile safety for optional schema elements

**Problem.** A procedure must deploy on databases where an optional column has not been added yet, while static SQL fails at CREATE with "Invalid column name".

**Mechanics.**
- Detect the column with `COL_LENGTH('schema.table','col') IS NOT NULL`, then touch it only through `sp_executesql` with typed parameters.
- Truncate to the real width with `LEFT(x, ISNULL(NULLIF(COL_LENGTH(...), -1)/2, 4000))`, so a long value cannot abort the whole transaction.
- Ship a read-only `00_verificare_*.sql` pre-check that lists missing columns before any deploy.

**When.** Rolling schema changes across several environments.

**Pitfalls.**
- `COL_LENGTH` returns **bytes** (halve it for nvarchar) and `-1` for MAX.
- An "optional" safety feature that is never switched on is a silent gap. Verify that it is actually live (for example, retry dedup that depends on an optional column).

## 13. Per-recipient tokens with consumed-link semantics

**Problem.** Several recipients each receive a personal link. Each must act once, and the flow must know who has already acted.

**Mechanics.**
- Group id on every row, plus a **per-row token** generated with `DEFAULT LOWER(CONVERT(NVARCHAR(36), NEWID()))` in the table variable before the insert.
- The token lookup uses INNER JOINs and returns a row **only if** the chain is complete **and** the recipient has not yet acted. "Not found", "not ready" and "already used" look identical (`[]`), on purpose.
- Define one **shared "done" predicate** in every reader and code node: `status IN (<done values>) OR <artifact column> is filled`. The second clause covers an artifact that was saved while the status update failed.
- Offer both per-row lists (one row per recipient, email first, so the result can drive a For Each) and aggregated DISTINCT recipients (`STUFF((SELECT DISTINCT ';'+x … FOR XML PATH(''),TYPE).value('.','NVARCHAR(MAX)'),1,1,'')`, or `STRING_AGG`).

**When.** Multi-party signing, approvals, surveys.

**Pitfalls.**
- Put a **UNIQUE** constraint on the token.
- The **write** must be guarded too: `WHERE token = @t AND <not done>`. A read-side check alone still lets a replayed link overwrite the stored artifact.
- Aggregate a group status from children after cleaning dirty values: `LOWER(LTRIM(RTRIM(REPLACE(… CHAR(13)/CHAR(10)/CHAR(9)/NCHAR(160) …))))`.

## 14. Deterministic fuzzy matching against a reference register

**Problem.** Free-text input (place names, entity names) must be resolved to official codes despite diacritics, abbreviations, old spellings and typos, without ever silently choosing a wrong neighbor.

**Mechanics.**
1. **Symmetric normalization.** Apply the same key function to the user input and to the register column: strip diacritics (including the decomposed NFD combining marks that macOS sends), turn punctuation into spaces, collapse spaces, UPPER, strip administrative prefixes, and expand abbreviations on word boundaries.
2. Write the key functions as **scalar UDFs with `WITH SCHEMABINDING, INLINE = OFF`**. An inline TVF with around a hundred nested REPLACEs is re-expanded at every reference and hits **Msg 8632** (the expression-services limit). Without `INLINE = OFF`, scalar UDF inlining (SQL Server 2019+) reintroduces the same expansion.
3. Keep the source **ASCII-only** by writing special characters as `NCHAR(0x….)` literals. One wrong encoding round-trip would otherwise break every replacement silently. Keep each SET to about 6 REPLACEs.
4. Match as a cascade: exact → edit distance d=1..k → prefix → reverse prefix → contains. Give each step a score and a confidence threshold, **scale the allowed distance with the name length** (short names get exact matches only), and **break ties deterministically** (smaller distance, higher administrative level, closer length, lowest code).
5. For Levenshtein in T-SQL, use two rows kept in an NVARCHAR (store d as `NCHAR(d+1)`, because `NCHAR(0)` is NULL), exit early when the whole row exceeds `@max`, and **pre-filter** on `ABS(len_a − len_b) ≤ @max`. That filter is a mathematical lower bound, so it never loses a real match.
6. Below the threshold, return a clear error plus the top-N candidates and "same name in another region" suggestions, never a guess.

**When.** Address normalization, entity matching against any official list.

**Pitfalls.**
- Real neighbors exist at distance 1 or 2, so tolerating typos on short names rounds silently to the wrong record.
- Precompute the register keys as **persisted computed columns** with an index. The functions are deterministic and schema-bound, which makes that possible, and it avoids running two UDFs over the whole register on every call.

---

## PROCESIO ↔ SQL techniques

### P1. Bind parameters. Never interpolate values into SQL text.

**Problem.** Interpolating `N'<%N%>'` into the SQL text lets any value containing `'` break the statement, and a crafted value injects SQL. Numeric placeholders written without quotes are worse.

**Mechanics.**
- Use the current `Execute Query` template with named `@params` in the SQL and the **Parameters config tab** mapping each `@param` to a flow variable, for example `EXEC schema.usp_X @id = @id`.
- The repo tooling does the conversion: `procesio sql-scan` then `procesio sql-parameterize --dry-run`.
- **Runtime-verify** afterwards. Structural validation does not catch an unbound `@param`.

**Stopgap, when binding is impossible.** A code node that does `JSON.stringify(obj).replace(/'/g, "''")`, while keeping the `N` prefix.

**Pitfalls.**
- Escaping HTML (`&#39;`) is **not** SQL escaping.
- A flow that passes a JSON object straight into `N'…'` is exposed.

### P2. Least privilege for the flow credential

The PROCESIO login should have EXECUTE on the procedures plus the minimum DML it needs, not `db_owner`. With injection-prone nodes, `db_owner` means an injection controls the whole database.

### P3. Consuming results in a flow

- The output is always a list.
- `Get Element [0]` → `Extract Objects` or a JS node → Decisional on `e_ok`.
- Parse JSON-string columns with `JSON.parse`.
- Procedures that return a single `result` JSON column need one more extract-and-convert step. Prefer the row contract from pattern 3.

### P4. Atomicity lives in the database

PROCESIO has no transaction that spans nodes. Any multi-statement write (for example, insert a child and then set the root's pointer to it, or delete-and-reinsert a detail set) belongs in **one procedure** with a transaction, or at least in one node with an explicit `BEGIN TRAN … COMMIT` and a way to report errors.

### P5. Procedure file conventions that keep deploys repeatable

- One procedure per file, no `GO` (the whole file is one batch), `CREATE OR ALTER`, numbered deploy order.
- A read-only pre-check script for the columns the procedure uses.
- A header that states the exact PROCESIO call, what each id parameter is **and is not**, the lookup chain, the output contract and the error codes.
- A trailing "quick test" block with positive, negative and control queries, with writes wrapped in `BEGIN TRAN … ROLLBACK`.
- A `_proc_version` string inside the returned JSON.

### P6. A run-log table for multi-step external integrations

- One row per run: `id` = the flow instance id, `business_key`, `status`, `step` as `'[n/N]'`, and one `*_meta` column per step holding either the created record id or the error text.
- Every step updates its own column plus `status` and `step`.
- Guard the transitions (pattern 4). Store the error text in its own column, not in the success column.

---

## 15. Anti-patterns seen in production (do not copy)

| Anti-pattern | Why it hurts | Do instead |
|---|---|---|
| Every column `nvarchar`: numbers, dates and flags as text | String date comparisons break once formats mix. Flags drift between `'1'`, `'true'` and `'da'`. `CAST` fails at read time. | Real types in new tables. Convert at the boundary. |
| Heaps with no PK, FK, unique constraint or index | Duplicate tokens and keys go unnoticed. Readers need `TOP (1)` guards. Every lookup is a scan. | A PK on `id`, a UNIQUE on tokens, indexes on pointer and group columns. |
| Renaming the primary key to a business number after creation | References that still hold the old id stop resolving, and a reused number violates the PK. | A separate business-number column. |
| Secrets (API keys, backend username and password, OAuth tokens) in plain tables | One injection or one over-broad SELECT leaks them. | The platform credential store or a key vault. Restrict the schema at the least. |
| Personal data (national id numbers, ID documents, IBAN, signature images) in clear text, with `SELECT *` exposed to a flow | Leaks, and no minimization or retention | Dynamic Data Masking or column encryption, column lists instead of `SELECT *`, a retention job. |
| An open-state filter on a column no flow ever writes | Lists grow forever | Every state predicate needs a writer. Test the transition that closes the state. |
| A valid procedure left unused while the flow does the same write inline | Validation and error reporting are bypassed | Call the procedure, or delete it. |
| Trailing commas and similar syntax errors in rarely used branches | The branch always fails, which shows up as an empty table | Run every SQL node at least once. Lint inline SQL. |
| A "delete everything" admin flow with no environment guard | Loses all data on one click | A `DB_NAME()` / environment check, soft delete, restricted runners. |
| Selecting columns that do not exist in disabled nodes | Re-enabling the node breaks the flow | Remove dead nodes, or fix them with the schema. |
