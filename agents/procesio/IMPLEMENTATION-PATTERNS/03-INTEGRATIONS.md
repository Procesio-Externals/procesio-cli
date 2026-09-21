# Integration patterns (generalized)

Patterns learned from how a production PROCESIO workspace builds its integrations: webhook intake, ERP API
sync, SFTP document storage, deterministic and LLM document extraction, Excel intake, HTML→PDF contract
generation. The file contains no client, vendor, person or business values. Where a pattern names PROCESIO or
the OpenAI API, the named platform's behaviour *is* the knowledge.

Each entry has five parts: **Pattern** / **Problem** / **Mechanics** / **When** / **Pitfalls**.

---

## A. PROCESIO scripting mechanics

### A1. One marker per variable in a Node script
- **Problem**: PROCESIO substitutes `{{var}}` (stored as `<%var%>`) **textually** anywhere in the code. A marker
  repeated in a comment injects the whole payload there too, which can be a multi-MB base64 or HTML, and breaks
  the script.
- **Mechanics**: declare every input once, at the top (`const x = {{x}};`). In comments, refer to the variable
  by plain name, never by marker syntax.
- **When**: always. It matters most for large payloads.
- **Pitfalls**: example snippets pasted into header comments are the usual cause.

### A2. Injection quoting by type
- **Problem**: the substituted text must be valid JS whatever the value is.
- **Mechanics**: JSON/object/list goes in **bare** (`const o = {{json}};`). String goes in quotes
  (`"{{s}}"`). Large HTML goes in **backticks**, which is safe only if the template contains no backtick or `${`.
  Booleans can arrive empty, and `const b = ;` is a syntax error, so normalize them through a `toBool()` that
  accepts `true/"true"/1/"1"/"da"/"yes"`.
- **When**: every Node.
- **Pitfalls**: a string containing `"` or a newline breaks double quotes. Very large values (100 KB+) can
  arrive **empty** through JS injection. Use native actions or SQL parameters for them.

### A3. Detect unreplaced placeholders
- **Problem**: when a variable is not bound, the script receives the literal `<%name%>` text, which is non-empty and so
  passes `if (x)` checks.
- **Mechanics**: `isPlaceholder = v => typeof v === "string" && /^<%[^%]*%>$/.test(v.trim())`. Treat a match
  as empty and report "marker not replaced" in the error envelope.
- **When**: optional inputs and reusable scripts.
- **Pitfalls**: an optional input referenced by marker but never declared as a process variable stays a literal
  forever.

### A4. Uniform result envelope + boolean extractor
- **Problem**: a Node's JS error does not take an error port. The action "succeeds" and writes the error to its
  Error output, so downstream Decisionals see garbage.
- **Mechanics**: every script returns `{e_ok, e_notOk, errorMessage, …payload}` from a pre-built skeleton,
  uses a `fail(msg)` helper and never throws. A two-line follow-up Node (or Extract Objects) pulls `e_ok` as a
  Boolean for the Decisional. Also bind each Node's Error output and branch on it.
- **When**: every parsing or validation Node.
- **Pitfalls**: returning `null` on failure. Callers then cannot tell "no data" from "crashed".

### A5. Defensive input normalizer
- **Problem**: the same logical value reaches a script as an array, an object, a JSON string, a double-serialized
  string or a `{rows|data|result}` wrapper, depending on the upstream action (SQL list, Extract Objects, subprocess
  output).
- **Mechanics**: `safeJsonParse` in a loop (up to 3 levels), unwrap one-element outer arrays, walk known wrapper
  keys, and read fields with multi-casing fallbacks (`Text|text`, `Position.Xleft|left|x`).
- **When**: any script that consumes another action's output.
- **Pitfalls**: over-lenient parsing can hide an upstream contract change. Log a warning when a fallback path
  is used.

### A6. ISO dates before DateTime variables
- **Problem**: PROCESIO does not parse `dd.MM.yyyy`. Assigning it to a DateTime variable yields **null**, with
  no error.
- **Mechanics**: convert to `yyyy-MM-dd` (or full ISO) in code before mapping. For comparisons, parse to
  `Date.UTC(...)` millis with one shared function, so server timezone does not matter. Build interval
  bounds as 00:00:00.000Z / 23:59:59.999Z.
- **When**: any date from documents, Excel or forms.
- **Pitfalls**: injecting a DateTime variable straight into JS gives an unpredictable string format. Map it to a
  String variable first.

### A7. HTML feedback cards as output strings
- **Problem**: forms need rich, consistent inline feedback without a front-end code change.
- **Mechanics**: the process returns an HTML string (inline-styled card with icon, title and message) in an output
  variable bound to a form HTML element. Keep a fixed palette (info / warning / error) and HTML-escape every
  dynamic value.
- **When**: validation results, extraction warnings, empty states, previews (e.g. an inline SVG timeline).
- **Pitfalls**: unescaped model or user text becomes markup (see D6). A truncated card literal renders broken.

---

## B. Inbound webhook intake

### B1. Webhook variable triplet + API-key subprocess
- **Problem**: a webhook needs body, headers and query params, plus a reusable authentication gate.
- **Mechanics**: declare input variables `<name>` (typed body), `<name>_header` (JSON), `<name>_params` (JSON).
  Headers arrive as **arrays** (`headers["X-Api-Key"][0]`), with a case-sensitive key lookup. A reusable
  "check key" subprocess returns `isValid`, and the parent throws a fixed message when it is false. Every later stage also
  returns a Boolean the parent gates on (`isPayloadOk`, `isDbOk`, `isFileOk`), and each gate has its own
  Throw message.
- **When**: machine-to-machine intake.
- **Pitfalls**: keep the expected key in a credential or hash it, never as plaintext in an app table. A process
  can lose its webhook binding and still look complete in the designer, so check the flow's webhook binding
  and not only the variable naming.

### B2. Typed file + reference body, upsert by reference
- **Problem**: the sender re-posts corrected documents for the same business object.
- **Mechanics**: the body has a File attribute and a reference id. `SELECT` the master row by reference: a new one
  goes to the INSERT subprocess, an existing one to the UPDATE subprocess (delete children, reinsert, update master
  dates). Stamp the run id (`ProcessInfo`) into the master row for traceability.
- **When**: idempotent document intake.
- **Pitfalls**: do the delete-and-reinsert in one stored procedure transaction. Write DB and file store in an
  order you can compensate (store the file first, then commit the DB, or record both states).

### B3. Bulk JSON to a stored procedure
- **Problem**: row-by-row INSERTs from a For Each are slow, non-atomic and injection-prone.
- **Mechanics**: build the full JSON in one Node and run `EXEC schema.usp_Import @payload = <json>`. The procedure
  shreds it with `OPENJSON` inside a transaction.
- **When**: tabular payloads (tariff grids, price tables, lookup lists).
- **Pitfalls**: bind `@payload` as a parameter. Inline `N'{{json}}'` breaks on the first apostrophe.

---

## C. Outbound REST/ERP integration

### C1. Token from store + refresh subprocess
- **Problem**: the ERP issues session tokens from a username/password login.
- **Mechanics**: `get_token` returns the cached token object. `refresh_token` logs in
  (`x-www-form-urlencoded username/password`), extracts the token object and replaces the cache. Calls send the token
  in whatever header the API wants (possibly a custom header, not `Authorization`).
- **When**: session-token APIs without OAuth.
- **Pitfalls**: call refresh **on 401/expiry** automatically. A refresh that nothing calls makes every expiry a
  business failure. Login secrets belong in a credential, not in a DB table.

### C2. Base64-wrapped JSON body
- **Problem**: some ERPs expect `{"data":"<base64 of the JSON payload>"}`.
- **Mechanics**: typed data model (Map Data) → `Object To String` → `String To Base64` → raw JSON body
  template `{"data":"<%b64%>"}`.
- **When**: only when the target API demands it.
- **Pitfalls**: map the body as a typed data model, not by string concatenation, so a field rename shows up in
  the designer.

### C3. Response envelope → Boolean + id + message
- **Problem**: HTTP 200 does not mean the business write succeeded.
- **Mechanics**: three tiny Nodes on the response. (1) `ok = StatusCode===200 && StatusMessage==="OK"`.
  (2) id = `Result.status[0].<id_field>`, throwing if missing. (3) error text = `Result.Message` or a
  generic localized fallback. Branch on (1).
- **When**: every write call.
- **Pitfalls**: also bind the **HTTP status code** of the Call API and wire its error port. Otherwise a
  timeout or 5xx looks the same as a business reject.

### C4. Numbered step chain with lookup-first idempotency
- **Problem**: creating a customer in an ERP takes a dependency chain (partner → site/meter → contract →
  site-on-contract → price lines → billing settings), and a re-run must not duplicate anything.
- **Mechanics**: an orchestrator calls numbered subprocesses `0..N`. Each gets the request JSON + token + the ids
  from earlier steps and returns `(id, ok)`. Inside each step: `GET by business key` → if found, reuse and
  mirror locally; else `POST` → extract the new id. After each step, a Decisional goes to the next step or
  to a Throw.
- **When**: multi-entity provisioning in any external system.
- **Pitfalls**: every create step needs a lookup, and one missing step duplicates on retry. When the check
  reads only list element `[0]`, it must match the business key rather than trust position.

### C5. Progress row per run
- **Problem**: after a failure at step k you need to know what exists remotely and resume.
- **Mechanics**: at start, insert one row (run id, business key, `step='[0/N]'`, status). Each step updates
  `step`, `status` (`<step>_ok` | `error`) and a per-step meta column (local mirror GUID or error text). Mirror
  tables hold the external ids.
- **When**: any multi-step external sync.
- **Pitfalls**: write it **with parameters**, because error text from the external system contains quotes. Make
  the orchestrator read the row and skip completed steps; otherwise it's only a log.

### C6. One credential per environment, switched centrally
- **Problem**: nodes bound to a TEST credential one by one make going to PROD a manual re-bind of every node.
- **Mechanics**: route all calls through a small set of wrapper subprocesses and switch the credential there
  (or by an env parameter), or keep separate flow copies per env produced by an export/import step.
- **When**: from the first call onward.
- **Pitfalls**: an unused PROD credential lying next to TEST-bound nodes is a sign the switch was never
  designed.

---

## D. Document extraction

### D1. Deterministic PDF table parsing from word geometry
- **Problem**: issuer-generated PDFs (price grids) have stable layouts but no text structure, and LLMs misplace
  numbers in wide tables.
- **Mechanics**: `Extract Text` gives pages with `Words[]` and positions. Rebuild visual rows by **clustering
  on the vertical midpoint** (tolerance about 1 unit), or by the engine's row index when it exists. Anchor on a
  header word, take the rows below it, and keep "data rows" = text label left of the first number + at least K
  numbers. Return `{e_ok, …rows}`.
- **When**: machine-generated documents from a known issuer.
- **Pitfalls**: diacritics differ, so match on NFD-folded lowercase text. Headers wrap across lines, so anchor on
  one distinctive word, not the full title. Separators such as an en-dash can fall into another row cluster, so
  make them optional in regexes and re-emit a canonical one.

### D2. Ragged tables: map numbers by X to column centres
- **Problem**: rows with missing cells shift values left under index mapping.
- **Mechanics**: take the row with the most numbers as the template, whose X positions are the column centres. Assign
  each number to the nearest centre and leave missing columns as `null`. Count only numbers inside the table's
  X band, which keeps out sidebar text (addresses, ids) on the same line.
- **When**: any table where cells can be empty.
- **Pitfalls**: this needs at least one complete row. Recalibrate the X band when the layout changes, and keep
  it as a named constant.

### D3. Split stacked tables by the largest vertical gap
- **Problem**: two tables with identical columns sit on one page (e.g. two tax regimes).
- **Mechanics**: collect all data rows, sort them by Y and split at the largest gap between consecutive rows. The
  upper band is table 1, the lower band table 2.
- **When**: repeated tables with no distinct header between them.
- **Pitfalls**: exclude summary rows (such as a "total" or subsystem row) before measuring the gaps.

### D4. Anchored field with "first match that has data" iteration
- **Problem**: a keyword (e.g. "validity") appears several times, and only one occurrence carries the value.
- **Mechanics**: iterate **all** rows containing the anchor and take the first whose own line or next 1–2 lines
  match the value regex (e.g. a date range).
- **When**: legal and boilerplate-heavy documents.
- **Pitfalls**: "first occurrence" logic that worked on one document variant silently picks boilerplate on
  another.

### D5. Classify by content score, not file name
- **Problem**: deciding the document variant from the uploaded file name breaks when users rename files.
- **Mechanics**: normalize the full text, count hits from per-class phrase lists, and require that the winner
  beats the runner-up **and** reaches a minimum number of hits. Otherwise return "unknown".
- **When**: routing to per-variant parsers.
- **Pitfalls**: don't hard-code dimensions the text can't tell you (e.g. customer type). Take them from the
  form or the data instead.

### D6. LLM OCR with a forced strict tool call
- **Problem**: heterogeneous scans and photos (ID documents, registration certificates, utility bills) need
  typed fields, not prose.
- **Mechanics** (OpenAI Chat Completions): one `tools[]` function with `strict: true`, `additionalProperties:
  false`, **every field required but nullable**, `enum` for classifications and `pattern` for formats (13-digit id,
  ISO date, 6-digit postcode). `tool_choice` is pinned to that function. PDFs go as a `file` content part
  (`data:application/pdf;base64,…`), images as `image_url` with a data URI and `detail: high`, chosen by MIME.
  The result comes from `$.choices[0].message.tool_calls[0].function.arguments`.
- **Prompt skeleton**: role + "analyze ONLY the provided file" + "call only the function, never free text"
  + a **document-type gate** (detected type, `warning_status`, fixed warning text, all fields null for
  a wrong document) + a **cross-check against the user's form selection** + "extract only visible values; don't
  invent, enrich, search or infer; null when not confidently readable" + output casing/diacritics rules
  with examples + date conversion rules + a per-field "where it is on the document / what to strip" list +
  placeholder values ("N/A", "-", "no name") → null + "unit conversion of a visible value is not inference".
- **When**: user uploads of semi-structured documents.
- **Pitfalls**: keep the PDF and image prompt variants **in sync**. Copy-paste drift (a PDF prompt that says "treat
  as image", rejection rules present only in one variant) is common. Always **branch on the model's warning
  flag**. **Escape** model text before putting it in HTML (a document can carry prompt-injection text). Keep the
  model name in config.

### D7. Deterministic post-normalization against dictionaries
- **Problem**: even strict schemas return spelling variants (county names, abbreviations, legal forms).
- **Mechanics**: fold diacritics and punctuation into a key, then look it up in (a) canonical names, (b) the same
  without spaces, (c) short codes. Special cases get their own rule (a capital city that needs a district). Return
  exactly the DB dictionary value (including odd spacing, if the DB has it) or `""`. When one field is derived
  from another (name without legal-form suffix), strip **only** the detected form, from the end, and from the start
  for forms that prefix the name. Protect lookalikes (Roman numerals).
- **When**: any AI or OCR output that feeds selectors or DB lookups.
- **Pitfalls**: the dictionary has to match the form's selector values exactly, or the selector shows empty.

### D8. Deterministic derivations with a recorded source
- **Problem**: a value (e.g. annual consumption) is sometimes printed and sometimes has to be computed from
  other visible data.
- **Mechanics**: an ordered fallback chain (printed → period extrapolation → volume × conversion factor →
  12-month history × factor). The result is written with a `*_source` field naming the branch used. A value that
  landed in the wrong unit field is detected by the unit in its text and moved.
- **When**: derived metrics from extracted data.
- **Pitfalls**: never let the LLM do the arithmetic. Keep derivation in code, where it can be audited.

### D9. Pre-flight file validator subprocess
- **Problem**: every extractor needs the same file checks and user messages.
- **Mechanics**: subprocess `(file) → (base64, isValid, message)`: present? MIME in an allow-list? size ≤
  limit? Return localized messages. The parent wraps the message in its HTML card.
- **When**: before any paid or slow API call on a user file.
- **Pitfalls**: the MIME comes from the upload metadata, so a renamed file can lie. The model's
  document-type gate is the second line of defence.

---

## E. Files and SFTP

### E1. One folder per entity, fetch-and-normalize
- **Problem**: per-request documents must be retrievable later by a key, in a viewable format.
- **Mechanics**: path `/<DocType>/<entity-guid>/<original file name>`. Upload = create folder → upload. Fetch
  = list files → pick → download → convert to PDF (a shared `file_to_pdf` subprocess) so viewers get one
  format. SFTP listings may return paths with the chroot prefix (e.g. `/Home/...`) while actions take
  chroot-relative paths, so compare accordingly.
- **When**: attachments for workflow records.
- **Pitfalls**: "pick" must not be `list[0]`. Choose by exact name or newest timestamp, or clear the folder on
  replace. Check the create-folder and upload results.

### E2. Replace-in-place upload
- **Problem**: re-submitting a document must replace, not accumulate.
- **Mechanics**: list the folder; if it exists → delete the existing files → upload; else create → upload.
  Compute the success flag from the booleans of the branch that actually ran.
- **When**: single-current-document folders.
- **Pitfalls**: delete **all** files, not only the first. An existing but empty folder must not crash the
  "get first file name" step.

---

## F. Excel intake

### F1. Template gate + header row + data window
- **Problem**: user-filled Excel templates drift (renamed sheets, wrong tab filled).
- **Mechanics**: check that the sheet names match an exact ordered list, or return an "incorrect template" card. Header row
  at a fixed index, data from a fixed start row to `Get Last Used Row`, read range per sheet. Then validate:
  exactly one data tab is filled, and it must match the energy/product type selected in the form.
- **When**: bulk intake of line items (sites, meters, products).
- **Pitfalls**: Read Range returns column letters as keys, so turn "first row = header" into objects before
  use.

### F2. Validate rows against reference data with the consumer's own matching rules
- **Problem**: rows that pass intake but have no match downstream (e.g. operator/category with no tariff) produce
  empty cells in generated documents.
- **Mechanics**: the validator uses **exactly the same** normalization and alias rules as the document
  generator. It returns `{e_ok, errors[{row, code, message, …}], warnings[], pairs[], summary, html,
  html_warnings}` with a closed list of error codes. Errors block, warnings don't.
- **When**: before any step that consumes the rows.
- **Pitfalls**: two copies of the matching rules drift apart. Share them through the build (G2).

### F3. Full refresh of a lookup table
- **Problem**: reference lists (suppliers, operators) are maintained in Excel.
- **Mechanics**: read → header-to-objects → replace the table contents.
- **When**: admin-triggered list updates.
- **Pitfalls**: DELETE-then-INSERT outside a transaction leaves an empty table on failure. Stage into a temp
  table and swap in one procedure, with parameters.

---

## G. Document generation

### G1. Slot-based HTML template filling
- **Problem**: contracts have many optional fields, and blanks must stay visibly "to be filled".
- **Mechanics**: the template marks each fillable segment as `<span class="hl" data-k="KEY" data-b="____">…@@…</span>`.
  If KEY has a value, the span is removed and `@@` becomes the escaped value; if not, the highlighted blank stays.
  Fixed values are `{{key|default}}` tokens. Bilingual keys `x.en` fall back to `x`. Repeating tables
  (sites, tariffs, signers) are generated for N rows. HTML → PDF happens through a Generate Document template
  that takes one HTML input.
- **When**: legal and commercial documents with partial data at generation time.
- **Pitfalls**: a date that is only known at signing stays blank until the signing step, and must not be
  filled from another date (e.g. supply start).

### G2. Generated scripts, edited outside the designer
- **Problem**: per-variant generator scripts (person type × product × language) run to thousands of lines and
  share most code.
- **Mechanics**: keep templates and runtime in a repo, and have a build script emit one Node script per variant
  with a version string in its header. Paste or deploy the output, and never hand-edit it in the designer.
- **When**: more than two near-identical large scripts.
- **Pitfalls**: say in the process description where the source lives. Hand-maintained near copies (e.g. with
  and without a signature) drift.

### G3. Signature images anchored in HTML
- **Problem**: signatures from several parties must land in the right cell of repeated signature blocks.
- **Mechanics**: clean each base64 (strip the `data:` prefix and whitespace, check the alphabet and a minimum
  length, else skip). Insert an `<img>` with a max size inside a block that **reserves real height** so it does not
  overlap the next signer. Use a function replacer so `$` in the base64 is not treated as a pattern.
- **When**: multi-party signing.
- **Pitfalls**: anchor on **role markers in the template**, not on people's names in code, and load signers
  and images from a signers table. Named anchors and per-person file paths break when a signer changes.

### G4. Stored-procedure read envelope
- **Problem**: rebuilding a complex request object from many tables in every process.
- **Mechanics**: a procedure always returns **one row** `e_ok | error_code | error_message | sql_error_number |
  sql_error_line | sql_error_procedure | <object>_json`. One Node parses it into a normalized object with a
  guaranteed skeleton (every key present, null or `[]` when absent) plus derived views (unified client,
  zipped per-site records, totals, formatted dates, warnings).
- **When**: any process that reads an aggregate.
- **Pitfalls**: the Node must never return null. When parsing fails it returns the same skeleton with the error
  set.

### G5. Don't rename primary keys in place
- **Problem**: assigning a final document number by `UPDATE … SET id = <new number>` breaks references,
  and follow-up updates keyed by the new id that run before the rename silently match nothing.
- **Mechanics**: keep a surrogate id and put the business number in its own unique column. When a rename
  can't be avoided, run it first, inside the same transaction as the dependent updates.
- **When**: late-assigned business numbers.
- **Pitfalls**: check execution order on every branch. The "renumber" branch is the least tested.

---

## H. Cross-cutting rules

- **H1. SQL values are parameters.** Inline `N'{{value}}'` interpolation breaks or allows injection on the first
  quote, and HTML templates, error messages from external systems, OCR'd names and Excel cells all contain
  quotes. Use parameters or a JSON `@payload` to a procedure.
- **H2. Secrets live in credentials.** App tables holding API keys, tokens or passwords are readable by anything that
  holds the DB credential.
- **H3. Error ports on every external action** (Call API, SFTP, SQL, AI) + retries with backoff for
  transient errors + messages that name the step and the external key. A generic "An exception occurred" Throw
  gives an operator nothing to act on.
- **H4. Config in one place**: model names, base URLs, form ids, document template ids, folder roots, enum ids.
- **H5. Retire explicitly.** Mark superseded flows `(LEGACY)` / `(PROTOTYPE)`, deactivate them and remove their
  bindings. Check form bindings for process ids that no longer exist.
- **H6. Personal data exports** (national ids, phones, emails) must be filtered, access-controlled and not
  triggered on page load.
- **H7. Name carefully.** Names become tables, columns and variables. Typos (a letter swap in a class code, a
  misspelled word) propagate into schemas and mislead every later reader.
