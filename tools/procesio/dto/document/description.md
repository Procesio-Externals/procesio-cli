# Document Template sub-tool

Create/edit a PROCESIO **document template** — HTML with `<%placeholder%>`
variables, rendered to PDF/DOCX by the **Generate Document** action in a process.

## Config

```json
{
  "name": "Invoice",
  "body": "<div>Hello <%clientName%>, your total is <%total%>.</div>",
  "pageSize": "A4",
  "orientation": "portrait",
  "variables": [
    {"name": "clientName", "type": "string"},
    {"name": "total", "type": "double"}
  ]
}
```

- **body** — author it as raw HTML; reference variables with `<%name%>` (default
  delimiters, overridable via `placeholderStart`/`placeholderStop`). The builder does
  NOT store it raw — it mirrors PROCESIO's document editor: HTML-entity-encoded
  (`&lt;%…%&gt;`) and collapsed to a single line. That editor format is what lets the
  renderer's DOM walk recognise and clone a repeating list `<tr>`; a raw multi-line body
  pushed via the API renders list cells as "Unknown" (see `_encode_body` in `builder.py`).
- **variables** — `DocumentVariableDto`. `type` (primitive) or `model`; `isList`,
  `isInput` (default **false** — template vars are destinations FILLED BY Generate
  Document, not flow inputs; `isInput:true` stops the designer expanding a `list<model>`
  var's attributes, so the repeating table can't bind), `isOutput`.
- **orientation** — `portrait` (0) or `landscape` (1). **pageSize** — e.g. `A4` (valid values
  below).

## API contract (verified live 2026-06-24)

- **Create:** `POST /api/DocumentTemplate` — client-supplies `id`, returns empty.
- **Get:** `GET /api/DocumentTemplate/{id}`.
- **Edit:** `PUT /api/DocumentTemplate`.
- **Delete:** `DELETE /api/DocumentTemplate/{id}`.

## Using a document in a process

Add a **Generate Document** action: bind "Select Document Template" to the template
id (REQUIRED — without it the action 502s "Missing document information"; the
`HTML string` property is an OUTPUT, not an input), map the template variables via
"Map Document Data", choose "Save document as" (PDF=1/HTML=2) and "File Name", and
capture "Document Output" into a File variable. Run the process and read the output
file from the instance (`GET /api/File/download`).

## Scalar binding works; list-bound repeating tables ALSO work

**Verified live:** scalar `<%name%>` placeholders bind and render correctly; the
designer shows them as resolved chips. Bind a body image with `<img src="<%url%>">`.

**Repeating tables over a `list` model work too** (proven by the Round 12 decisive
render test in `PHASE4-E2E-NOTES.md`). A single `<tbody><tr>` whose `<td>`s carry
`<%listVar.attr%>` placeholders (`<%hits.title%>` -> `<%hitsId.attrId%>`) is cloned
once per list element — that one `<tr>` IS the repeating syntax. The fresh-model run
emitted one row per list item (3 hits -> 3 rows), zero "Unknown".

**Put the header row in `<thead>` and the repeating `<tr>` in `<tbody>`.** Generate
Document fails a list table whose header row sits in `<tbody>` with "Sequence contains no
elements" (checked at v3.0.0, 2026-10).

**Feed the typed list — no scripting required.** Declare a process variable typed as
the item model with `isList:true` and a `DefaultValue` that is a JSON array of
objects (or supply any already-populated list var); it hydrates into the typed list
at runtime. In the Generate Document `docMap`, map the doc's list variable to that
process list variable with `destination.attribute = null` — one mapping binds the
whole list to the table.

**Critical — create the data model with ALL attributes up front (`POST /api/DataTypes`).**
The earlier "Unknown" / `Unable to find attribute <id>` failures were NOT a platform
limit — they were a stale compiled model. Attributes added later via the
`/api/DataTypes/attribute` edit path are MISSING from the runtime's COMPILED model,
so the designer renders those cells as "Unknown" chips and Generate Document throws
`Unable to find attribute <id> ... ensure the data model attributes are defined
correctly` at render time. A model created with every attribute in the initial
`POST /api/DataTypes` compiles correctly and renders. (Round 12: a fresh 6-attribute
model + identical `<%hits.attr%>` table -> status 50, valid PDF, all rows; the
original attribute-edited model -> status 40, attribute-resolution error.)

**HTML-string shell — still a valid alternative** (use when the layout itself is
fully dynamic, not just the rows):
1. A document = a single `<%htmlContent%>` placeholder (one `string` variable).
2. A Scripting action builds the FULL HTML (header, table rows, image) as a string,
   output into an envelope model `{result: string}` (a JS output is wrapped
   `{result: v}`, and `result` maps cleanly only when it is a **primitive**).
3. Generate Document `docMap`: `htmlContent <- {var: htmlEnv, path: [result_attr_id]}`.
The `<%htmlContent%>` placeholder substitutes the raw HTML -> the PDF renders the full
branded layout, table and image. (Proven live: `AAT_BriefShell` + `AAT_Process_SearchGenerate`.)

## The designer re-save normalises the HTML (Tiptap, v3.0.0, 2026-10)

The document designer replaced Froala with **Tiptap 3**. The save payload is unchanged
(entity-encoded `body`, delimiters, `documentPageSize`, `documentPageOrientation`,
`variables`), but saving a template from the UI NORMALISES its HTML, so a body the tool
wrote is not byte-stable once someone opens and saves it in the designer:

- header rows move into `<thead>` (also leading all-`<th>` rows found in `<tbody>`);
- runs of spaces become `&nbsp;`, and empty blocks get a `<br>`;
- `break-*` CSS becomes `page-break-*`;
- `on*`, `srcdoc` and `javascript:` attributes are stripped;
- `<style>`, `<script>`, `<form>` and `<svg>` are kept verbatim as raw HTML;
- placeholders inside attributes or raw HTML are left as written;
- `fr-*` classes are kept (the PDF is still styled with Froala's stylesheet);
- a leaf `<section>` / `<header>` becomes a `<div>`;
- entities are no longer double-decoded.

Compare a template before and after a designer save by these rules, not byte for byte.

**Header, footer and page-number markers.** The body carries them as a LEADING
`<style class="pup-c-template-page-number">`, a LEADING
`<header class="pup-c-template-header" data-height>`, and a TRAILING
`<footer class="pup-c-template-footer">`. Keep each in its position when editing a body.

**Valid `documentPageSize` values** (the config's `pageSize`): `A0`-`A9`, `B0`-`B10`, `C5E`,
`Comm10E`, `DLE`, `Executive`, `Folio`, `Ledger`, `Legal`, `Letter`, `Tabloid`, and `""` (the
designer's Default). An unknown value is silently reset to Default on the next UI save, so the
builder maps a size to its canonical spelling and refuses an unknown one.

**PDF styling is pinned.** Generate Document and HTML to PDF embed the **Froala 5.5.0** CSS in
the PDF, and the HTML-string output links the `froala-editor` package at version 5.5.0 instead of `@latest`. Document
CSS is kept as written, and a `url(data:image/png;base64,...)` is no longer truncated.
