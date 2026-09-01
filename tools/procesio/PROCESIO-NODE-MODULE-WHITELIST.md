# PROCESIO `Node` (NodeJS) sandbox — module whitelist & I/O mechanics

What the platform's **`Node`** action (`e0fc20c3-e333-554c-a062-f64894db51dd`) can and
cannot `require`, how data enters and leaves it, and the consequences for building file
outputs. Probed live against a NodeJS `Node` action (`Timeout` 60–300; top-level `return`
sets the result). Reuse these facts before designing any Node-heavy flow (grouping,
dedupe, report/file generation) — they decide the whole architecture.

## Module availability — the sandbox is heavily locked down

Probed `require()` for each; **every external npm module failed** with
`Cannot find module '<name>'`:

| Probed | Result |
|---|---|
| `xlsx`, `exceljs`, `xlsx-populate`, `write-excel-file`, `node-xlsx` | ❌ not installed |
| `fast-xml-parser`, `xmlbuilder2` | ❌ not installed |
| `jszip`, `pako` | ❌ not installed |

Builtins are almost all blocked. Two are present:

| Builtin | `fs` | `zlib` | `buffer` | `child_process` | `os` | `path` | `crypto` | `https` |
|---|---|---|---|---|---|---|---|---|
| Available | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |

`process` is also restricted — reading `process.version` throws
`Cannot read properties of null (reading 'version')`. **Rule: assume a Node action has the
JS language plus `crypto` and `https`, and nothing else until probed.** No filesystem, no
`Buffer`, no compression, no shelling out, no npm. Guard any `process`/global reference in a
`try/catch` or it aborts the whole action.

> **CORRECTED 31/08/2026.** This file previously read *"only `crypto` is present"* and
> *"assume a Node action has the JS language + `crypto` only"*, while
> [PROCESIO-API-NOTES.md](PROCESIO-API-NOTES.md) recorded, from its own live probe, that
> **`require('https')` also works** and that an async `return new Promise(...)` resolves.
> Both were live-probe records, neither cited the other, and the narrower falsified rule sat
> in the file a reader opens to look module availability up. **The lesson generalises: a
> probe result states what was probed, not what exists.** `https` was never in this file's
> probe set, so its absence from the table was an untested gap being read as a negative
> result. When a note says "only X is present", record the probe set beside it.

## Consequence for Excel: build the .xlsx in pure JS (no library)

Because there is **no `Buffer`/`zlib`/xlsx lib**, and because the catalogue's `XLS To XLSX`
converter **rejects** SpreadsheetML 2003 (verbatim: *"The supplied data appears to be a raw
XML file. Formats such as Office 2003 XML are not supported"*), the only way to emit a
genuine **single-file, multi-sheet** `.xlsx` is to author the OOXML package by hand inside
the Node action:

- Build each part's XML as a string (`[Content_Types].xml`, `_rels/.rels`,
  `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/worksheets/sheetN.xml`), using
  `t="inlineStr"` cells so no `sharedStrings`/`styles` parts are needed.
- Pack them into a **ZIP with STORED (method 0, uncompressed) entries** — a stored ZIP
  needs only CRC-32 (implementable as a pure-JS table) and correct local-header /
  central-directory / EOCD byte layout; **no compression, so `zlib` is not required**.
- UTF-8-encode strings by hand (no `Buffer`), CRC-32 by hand, base64-encode the byte array
  by hand, then feed that base64 to the catalogue action **`Base64 To File`**
  (`6fad5599-…`) → a real `.xlsx` File (MIME
  `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`).

This was verified end to end (openpyxl re-opened the result: correct sheet names, string
headers, numeric cells typed as numbers). It is the **preferred multi-sheet path** — one
file, real sheets, only two actions (`Node` + `Base64 To File`) — and beats the fallbacks:
`Export To XLSX` writes **one sheet from a list**; `Create Workbook`/`Insert Sheet` create
only **empty** sheets (no catalogue action writes data into an existing sheet). A reusable
pure-JS writer (`AAT_XLSX.build(sheets)`) lives with the VAT-reconciliation build assets.

## How data ENTERS a Node — `<%N%>` injection, materialised

A Node reads flow variables only through **`<%N%>` placeholders in the `Code`** (bind the
`Code` param with `{template, vars:[...]}`; index is global across the action's params):

- A **list/object** variable injects as its **actual JSON value** — `var rows = <%0%>;`
  yields the real array/object (verified: a parsed CSV list arrived as a JS array of
  objects). So one Node can consume several upstream datasets at once.
- A **string** variable injects as a **bare, unquoted token** — you must quote it yourself:
  `var p = "<%1%>";`. Consequently a caller-controlled string is injected into source
  before your code runs; treat it as untrusted (a stray `"` breaks the script). Prefer
  passing untrusted text inside a JSON list/object channel (JSON-escaped) rather than as a
  raw quoted scalar.
- An **optional number** with no value injects as **nothing** (`var t = <%5%>;` →
  syntax error). Give optional numeric inputs a default, or don't inject them.

## How data LEAVES a Node, and why you often need extractor Nodes

A Node has exactly three output props: **`Single Result`** (scalar/object, raw — no
wrapper), **`List Result`** (list), **`Error`** (string; note scripting errors are also
reported here, they do **not** take the error port). `Javascript` instead wraps as
`{result: v}` — prefer **`Node`** for clean typed output.

**Attribute-path binding does NOT work on a generic Json/Object variable.** Binding a
downstream param to `{var:"bundle", path:["reportHtml"]}` fails BE validation with
`Error converting value "reportHtml" to type 'System.Guid'` — the platform expects the
attribute to be a **DataModel attribute GUID**, which a schemaless Json object doesn't
have. So you cannot fan a single Node's object result out to several consumers by sub-path.
Two ways around it:

1. **Extractor Nodes** (used here): the producing Node returns the whole bundle to a
   process var; a tiny Node per consumer injects the bundle and `return`s the one field it
   needs as a clean `Single Result`, which binds directly. Cheap and reliable; keep large
   strings (HTML, base64) out of the re-injected bundle so they aren't serialised N times.
2. Define a **DataModel** (`datatype-create`) for the bundle so its attributes have GUIDs,
   then `{var,path}` binding resolves.

## CSV reading — `Read Range from CSV`, not `File To JSON`

`File To JSON` (`fd9d7d38-…`) **rejects non-JSON**: `File extension should be '.json',
found => .csv`. Use **`Read Range from CSV`** (`9c9cc774-…`): params `CSV file` (file),
`Range` (e.g. `A1:Z1000` — clips to actual data, no empty padding), `Values` (output). It
returns a **list of row objects keyed by column letter** (`{A,B,C,D,…}`), **row 0 is the
header row**, and numeric-looking cells arrive as **JS numbers**. Read the header row to map
column-name → letter so the flow is robust to column reordering and can detect optional
columns.
