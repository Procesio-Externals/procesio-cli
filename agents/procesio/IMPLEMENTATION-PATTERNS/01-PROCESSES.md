# Process-building patterns (generalized)

These patterns were distilled from a production PROCESIO workspace (form-driven request intake,
agent review, multi-party e-signing). They contain no client-specific values. Each entry gives the
pattern, the problem, the mechanics, when to use it and its pitfalls. **Refines** marks an entry that
sharpens or corrects a rule in `agents/procesio/PROCESIO-BEST-PRACTICES.md` (BP) or
`PROCESIO-BUILD-AND-TEST-PLAYBOOK.md` (PB).

---

## P1. Dual outcome flags for form bindings (`e_ok` + `e_not_ok`)
- **Problem:** a form output binding cannot negate a boolean, yet a result usually has to show one
  element and hide another.
- **Mechanics:** declare two Boolean outputs with pessimistic defaults (`e_ok=false`,
  `e_not_ok=true`). One Map Data at the very end of the happy path flips both. The form binds
  `successPanel.visible ← e_ok` and `inputPanel.visible ← e_not_ok`. Any early exit (error port, empty
  guard) leaves the defaults, so the UI shows the "not ok" state automatically.
- **When:** every process a form calls to decide visibility.
- **Pitfalls:** optimistic defaults (`e_ok=true`) turn every crash into a false success. Keep one
  casing for boolean literals (`true`, not `True`). Inside JSON results, don't switch the name to
  `e_notOk`.
- **Refines BP §9 / §5:** this is the cheapest way to surface failure to the user without extra calls.

## P2. Render display blocks server-side as one inline-styled HTML string
- **Problem:** status cards, dashboards, receipts and error banners need rich layout, but forms only
  bind scalars.
- **Mechanics:** a Node builds one root `<div>` with **inline styles only** (no `<style>`, no classes,
  no JS), SVG icons inline, a palette constant object and `escapeHtml` on every value, then
  `return html`. Bind it to `Paragraph.label`. For static messages a Map Data literal is enough.
- **When:** any read-only visual summary. The same builder can feed Generate Document for a PDF.
- **Pitfalls:** for HTML→PDF use tables + SVG, not flex/grid. Escape `'` too (`&#39;`) so the HTML
  can later be stored through an `N'…'` SQL literal. Never let the node return null: render the error
  into the HTML instead.

## P3. Selector feeds as `{label, value}` lists
- **Problem:** select and dropdown controls need `sourceValue` in a fixed shape. DB rows don't have
  that shape.
- **Mechanics:** one query per list, then one Node:
  `(Array.isArray(rows)?rows:[]).map(r=>({label:r.X, value:r.X}))`. Put all lists for one form step
  in **one** "render" process that returns every list plus the classification flags, so a single
  click fills the whole step.
- **When:** any form step with more than one data-driven selector.
- **Pitfalls:** one Node per list is copy-paste. Write one Node that maps a dictionary of result
  lists, or one SQL that returns every list as a JSON column. That also meets BP §10 (fewer actions).

## P4. Whole-form-in, SPEC-driven reshaping server-side
- **Problem:** form element names change between form versions (`SelectN` / `InputN`, renamed ids).
  Mapping in the form is brittle and spread across many places.
- **Mechanics:** pass the whole form instance (`instance / flow / fields`) as one JSON input. A single
  Node holds a declarative SPEC object (`target.path: "Element.value"`) plus directives for the hard
  cases:
  - first available source among renamed elements
  - repeating rows
  - a value taken from the active branch of a cascading selector
  - a value derived from section visibility

  It also records `warnings[]`, a `SCRIPT_VERSION` marker, and `e_ok/errorMessage` inside a
  try/catch.
- **When:** any form with more than about 20 fields that feeds a DB or document.
- **Pitfalls:**
  - Keep exactly one copy of the engine (a Utils process). Forking it per flow produces divergent
    versions.
  - An automatic `SelectN`↔`InputN` fallback must be disabled where the twin id exists with a
    different meaning.
  - Inactive branches keep stale values, so read only from the branch the controlling selector
    points to.

## P5. Server-owned identity: overwrite the client-supplied key
- **Problem:** a form can send any id. The primary key must come from the server.
- **Mechanics:** right after reshaping, run Generate GUID **into the id attribute of the form object**
  (Generate GUID can target an attribute path), then persist.
- **When:** every create/submit from a public or guest form.
- **Pitfalls:** return the generated id to the form (receipt number) so later steps (signature, file
  uploads) are keyed to the same record.

## P6. Validate in the stored procedure, persist the messages, then Throw
- **Problem:** business validation spread across Decisionals is slow and hard to keep in sync with
  the DB.
- **Mechanics:** a single `EXEC <schema>.usp_…_Save @json` validates and writes in one transaction and
  returns a status row: `e_ok`, the generated ids, and one row per validation message on failure. The
  process branches on `e_ok`:
  - failure: For Each message → insert into a validation-log table keyed by the request id →
    `Throw` with a short message
  - success: continue with side effects (files, documents, notifications)
- **When:** multi-table inserts from one form submit.
- **Pitfalls:**
  - The SP commit is not atomic with the later side effects, so design for resume and make the
    submit idempotent (dedupe key).
  - Ids for branches that don't apply come back as the all-zero GUID. Branch on "non-empty AND not
    the zero GUID".
- **Refines BP §2 (idempotency) and §8.**

## P7. SQL values: bind, or at minimum escape in a Node first
- **Problem:** Execute Query text with `'{{var}}'` breaks on the first apostrophe in a name and is
  injectable. It is worst when the value comes from a URL parameter.
- **Mechanics:**
  - Preferred (BP §8): parameter binding.
  - If a whole JSON object must be passed as one string, run a Node first:
    `return { json_sql: JSON.stringify(obj).replace(/'/g,"''") }` and inject that into `N'…'`.
  - Validate tokens and ids taken from URLs as GUIDs before they reach SQL.
- **When:** always.
- **Pitfalls:** escaping is easy to forget on the next process that copies the pattern (seen: one
  submit path escaped, its sibling did not). Treat an unbound interpolation of user input as a defect
  in review.
- **Refines BP §8:** adds the JSON-payload-to-SP case and the "URL-sourced value" severity.

## P8. Guarded state transitions, then notify
- **Problem:** "accept" or "deny" buttons can be clicked twice or on stale data.
- **Mechanics:** `UPDATE … SET status='<next>' WHERE id=@id AND status='<expected>'`, check the
  affected rows (or re-select), and only then send the e-mail. Flip `e_ok` only on a real transition.
- **When:** every workflow status change.
- **Pitfalls:** e-mailing before the guarded update notifies the customer about a transition that
  never happened. A disabled status-update node leaves the item in the queue while the customer
  believes it is closed. Keep status names in one place (lookup table or constants), not as literals
  in every query.

## P9. One click, one orchestrating process
- **Problem:** attaching several async RUN_PROCESS actions to one button causes races (a later status
  overwritten by an earlier one, a refresh that reads before the writes).
- **Mechanics:** one process runs the steps in order (update → notify → re-read) and returns
  everything the form needs. Use **Trigger Subprocess** only for side effects the user must not wait
  for (e.g. notifying staff).
- **When:** any button whose steps depend on each other.
- **Pitfalls:** fire-and-forget hides failures. Log or flag them somewhere readable.
- **Refines BP §9:** parallel async calls feel fast but are only safe when independent.

## P10. Tokenised signer links through hash-routed form URLs
- **Problem:** external signers need a personal link to one form page with their context.
- **Mechanics:**
  - One shared request id plus a unique per-signer token column.
  - Link = `https://<forms-host>/forms/<formId>#<pageId>?req_id=<token>`. The parameter sits **after
    the `#`** because the form uses hash routing.
  - Page load calls a "verify token" process: look up by token → documents + flags.
  - Signing calls a "sign by token" process: store the signature, `status='signed'`.
  - Status lifecycle: created → sent → signed → submitted (countersign).
- **When:** multi-party approval or signature without accounts.
- **Pitfalls:**
  - The token is a bearer credential. Give it an expiry and one-time use, and never put it into SQL
    unbound.
  - Build the base URL from one setting. A literal copied into several e-mail templates and code
    nodes drifts when the form is republished.
- **Refines BP "pre-fill controls from URL query params":** the hash-routing placement and the
  security caveats.

## P11. Business-day windows computed in code, with the calendar in Python
- **Problem:** a date picker must allow only dates that give staff N working days, bounded by the
  validity of the current offer period.
- **Mechanics:**
  - Python (has `zoneinfo`, `calendar`) prints the month's days
    `{zi, data, ziuaSaptamanii, esteWeekend}` for the current and the target month.
  - A Node merges both calendars into one sorted timeline keyed by date, counts the Nth working day
    strictly after today, and returns `YYYY-MM-DDT00:00:00Z` or `""` when it falls past the period
    end.
  - The form binds min, max and default of the date input. An empty result swaps in an HTML "period
    closed" banner (P2).
- **When:** any "earliest allowed date" rule.
- **Pitfalls:**
  - Use the business's real timezone id.
  - Include public holidays, not just weekends.
  - Compare dates as `YYYY-MM-DD` strings or regex parts, not `new Date()` local getters (they shift
    around midnight UTC).
  - Put N and the timezone in one setting.

## P12. Python action output is always `{"result": …}`
- **Problem:** a Python action's `print(x)` arrives as `{"result": "<x as string>"}`, sometimes
  double-encoded.
- **Mechanics:** in the consuming Node, unwrap repeatedly: if string → `JSON.parse`; if object with
  `result` → take `.result`; stop after about 5 levels. Or read `result` with Extract Objects when the
  value is flat.
- **When:** every Python → JS hand-off.
- **Pitfalls:** interpolate strings into Python inside quotes (`'''{{v}}'''`). The value is injected
  raw.

## P13. Same script offline and in the platform
- **Problem:** big code nodes (renderers, parsers) are hard to debug inside the designer.
- **Mechanics:** write the node as a standalone file with a `LOCAL: node preview.js payload.json`
  header. Treat an unreplaced placeholder (`/^<%[^%]*%>$/`) as empty, so the same text runs with
  sample JSON locally and with bound variables in PROCESIO. Add a `SCRIPT_VERSION` constant to the
  output.
- **When:** any node over about 100 lines.
- **Pitfalls:** placeholder-tolerance also hides a variable that was **never bound** (a literal
  `<%name%>` left in the pasted code). After pasting, check that every placeholder became a bound
  variable.

## P14. Layout-tolerant spreadsheet parsing by label
- **Problem:** tariff or price sheets from third parties move rows and columns between editions.
- **Mechanics:**
  - Read Range a generous block.
  - A Node converts whatever shape comes back into a 2-D grid (array of arrays, row objects keyed by
    letter or number, or a wrapper object).
  - Locate blocks by label prefix (`findCell(grid,"total taxe")`) and read the values to the right.
  - Parse numbers tolerantly (`"35,34 (note)"` → `35.34` + note).
  - Emit a clean JSON document and pass it to one import SP.
- **When:** any inbound Excel from outside your control, especially via webhook.
- **Pitfalls:** keep the Read Range bounds and the comments in sync, or let the parser find the used
  range. Protect the webhook with a header key that is compared to a value stored outside the process.

## P15. File-to-PDF normaliser via template placeholder swap
- **Problem:** uploads arrive as PDF or image, and downstream needs a PDF.
- **Mechanics:** if the MIME type is already `application/pdf`, pass it through. Otherwise:
  File To Base64 → render an HTML template containing a placeholder base64 image to an HTML string →
  Replace the placeholder base64 with the upload's base64 → Generate Document from that HTML.
- **When:** ID cards, invoices, any user-uploaded proof.
- **Pitfalls:** non-image, non-PDF files (docx, heic) produce a broken image, so whitelist the MIME
  types. Very large base64 values vanish when injected into Node code (BP field learning 3), which is
  why the swap happens in Replace, not in JS.

## P16. Shared-library hygiene for Utils
- **Problem:** helpers get copy-pasted into node after node: label/value mapper, first-row field
  extractor, date formatter, HTML helpers, e-mail shell, entity load chain.
- **Mechanics:** anything pasted twice becomes a `Utils/ …` process with a typed contract, or one
  multi-purpose Node that takes a dictionary of inputs. An identical load chain in three processes
  becomes one "load aggregate by id" subprocess. Company contact and legal blocks, URLs, timezones and
  lead times come from a single settings source.
- **When:** at the second copy.
- **Pitfalls:**
  - Destructive admin utilities (bulk DELETE) do not belong in the production library.
  - Empty stubs and disabled nodes should be deleted before handover.
  - Two processes with the same title make subprocess binding ambiguous. Titles must be unique.
- **Refines BP §2 "Centralize parameters" / "Modularize"** with concrete extraction triggers.

## P17. Every Decisional needs a Default that reports
- **Problem:** a Decisional with only positive cases dead-ends when no case matches. The run ends
  with default outputs and the form cannot tell "no data" from "broken".
- **Mechanics:** always wire a Default to a Map Data that sets `e_not_ok` plus a readable error
  (text or HTML banner), then route it to the common Join and the single Stop.
- **When:** every Decisional, especially classifiers (type A/B, energy X/Y, accept/deny).
- **Pitfalls:** error-port branches that go straight to a bare Stop have the same problem. Prefer
  "set error → Join → Stop".
- **Refines BP §5.**
