# PROCESIO `For Each` — construction quirks and the loop-timeout trap

The `For Each` action is template id **`dbef0804-66a9-4f8f-872c-ece1b89b8fdb`**.
Body membership is by **`ParentId`** (a child action's `parentId` == the loop's
id), never by an enclosing edge, and only `TemplateId` identifies the action —
`ActionTemplateName` is `null` on ~half of the corpus's For Each nodes and
`ActionName` is free text.

## ⚠⚠ A programmatically-built For Each is missing two parameters a designer-built one has

> ✅ **FIXED IN THE BUILDER (E-160, 28/08/2026).** `dto/process/builder.py` now
> materialises the two template-default output params at build time, so a `For Each`
> built through `process-create` / the compact config **iterates out of the box** — no
> post-create splice. See `_template_default_params` and the "the fix" section below.
> The description that follows is the diagnosis that led there; the workaround at the
> bottom is retained only as history and is **no longer needed**.

Read from live flows, the same `For Each` template carries a **different
parameter set** depending on how it was created:

| built how | `tabPropertyId` suffixes present | Action timeout |
|---|---|---|
| **designer (GUI)** | `…55f8c7` (For Each Item), `…adae8b` (In List), `…df9db1` (Action timeout), **`…61724e` = `"-1"`**, **`…808b0d` = `"2010-01-01T00:00:00.0000000Z"`** | commonly 600 |
| **programmatic** (compact config → `process-create`, or hand-built flow JSON) | `…55f8c7`, `…adae8b`, `…df9db1` only | whatever you set |

The programmatic build path **omits `…61724e` and `…808b0d`**, and they are **not
defaulted in on save/validate** — the flow validates and creates cleanly with
three parameters.

## ⚠⚠ The failure mode: the loop times out without iterating a populated list

A For Each carrying only the three parameters has been observed to **fail to
iterate a list that is demonstrably populated and correctly bound**, returning:

```
status 40
{"errorMessage": "Foreach timeout exceeded!", "actionName": "...", "actionType": "For Each"}
```

after the loop's `Action timeout` seconds, **writing nothing** — no body child
executes even once. This was isolated hard:

- The `In List` parameter **is** bound (its `variable[0].variableId` points at the
  list variable) — verified by reading the created flow back; it is not a
  null/unbound-list problem.
- The list variable **is** populated at runtime — the same run that times out
  returns the list (e.g. 3 elements) in its output variables.
- A **no-loop** flow proves the pieces are healthy: the list-producer Node yields
  the elements, a Node reads them, and a Data Store `InsertRows` writes a row —
  all at **status 50**. Only inside the For Each does it hang.
- Reproduced in a **minimal** For Each (one Node → the loop → one Data Store
  `InsertRows` body child), independent of the body's contents and of whether the
  body's `InsertRows` binds the loop item directly or a pick-Node-derived scalar.

## ⚠⚠ CONFIRMED (causal test done): the two parameters ARE the cause, and the timeout is NOT

The leaf-diff causal test is now performed. Splice **EXACTLY** `…61724e` = `"-1"`
and `…808b0d` = `"2010-01-01T00:00:00Z"` onto a live 3-parameter loop via
`put-projects`, **change nothing else**, re-run, and judge on rows landed:

| the same loop, only these two parameters differ | body executions | status |
|---|---|---|
| 3-parameter (as `process-create` builds it), populated list | **0** | 40 `Foreach timeout exceeded!` |
| **+ `…61724e` + `…808b0d`** (Action timeout left **unchanged**) | **3** (full) | 50 |

Measured twice, independently: **0 → 3 on a minimal loop**, and **entry 3 / body 3 /
real inserts 3 of 3** on a two-loop diff flow.

- ⚠⚠ **The Action timeout does NOT matter.** The designer loop's `…df9db1` is 600
  and the programmatic one's is 120; the splice **held it at 120** and the body ran.
  The two output parameters alone are sufficient — do **not** raise the timeout as
  part of the "fix" (that would be two changes at once and mis-attribute the cause).
- ⚠⚠ **Both are OUTPUT parameters** (`direction 2`, type `ignore`): `…61724e`
  "Zero based list index" (the current-iteration counter) and `…808b0d` "Action
  start time". A loop with no index slot has nowhere to advance the iteration index,
  consistent with never entering the body — mechanism plausible, the *measurement*
  is that adding exactly these two flips 0 → N.
- ⚠⚠ **The omission is in OUR builder, not the platform (E-158 refinement — A-42
  WITHDRAWN as a platform defect).** The two output parameters are the `For Each`
  template's **own default-valued settings**: the live action catalog shows template
  `dbef0804` declaring `61724e` "Zero based list index" with default `value` `"-1"`
  and `808b0d` "Action start time" with default the `2010-…Z` sentinel — both
  `direction 2`, `type ignore`, **`isRequired false`**. The DESIGNER materialises every
  template setting into the flow; the compact-config builder
  (`dto/process/builder.py::_action_parameters`) is **binding-driven** — it emits one
  parameter per config *binding* and never walks the template's settings — so a param no
  one binds (a runtime-written output with a default) is never emitted. Neither API path
  defaults it in on save. **So the fix belongs in the builder: materialise the template's
  default-valued output settings** (at minimum emit these two for `For Each`; generally,
  any `direction:2/type:ignore` setting carrying a template `value`). Because the
  validator keys on `isRequired`, a 3-param loop validates + creates clean and only fails
  at runtime with the generic timeout — a genuinely platform-side rough edge, but a minor
  quality/parity note, not the "build path is broken" claim.
- ✅ **DONE (E-160). The builder now materialises them.** `dto/process/builder.py`
  gained `_is_template_default_output` (predicate: `direction:2` or `type:ignore` with a
  non-empty scalar `value`) and `_template_default_params` (walks the template, emits
  `{TabPropertyId, Value:<default>, Variable:[]}` for each such setting not already
  produced by a binding, deduped by `TabPropertyId`), called in `build()` after the
  binding-driven / doc-mapper / decisional / subprocess params. It is **template-driven,
  not a For-Each special-case**: `For Each` gains `61724e`/`808b0d`, and `Call
  Subprocess`'s `a03fe2` started-flow slot (the only other member of the class in the live
  233-action catalog) is subsumed — already emitted by `_build_subprocess`, so the dedupe
  makes it a no-op there. Proven a TRANSFORM (a process with no such setting builds
  byte-identical; `For Each` differs by exactly the two params appended) and proven LIVE
  (a loop built by `process-create` iterates 3, no splice; both loops of a two-loop flow
  iterate → status 50, where the E-150 single-loop splice left status 40). ⚠ A separate,
  larger class is NOT fixed: 40 actions carry INPUT-side (`direction:1`) template defaults
  the builder also drops when unbound — untested whether it matters; see
  `todo/procesio-builder-input-default-materialisation.md`.
- ⚠ **`put-projects` cannot create — it is PUT/edit only.** A create DTO (fresh
  client-supplied Id) PUT to `put-projects` returns HTTP 400 / statusCode 502 "missing or
  incorrect resource parameters" and persists nothing; creation is **POST /api/Projects**
  (what `process-create` wraps). As a save path `put-projects` stores the parameter set
  literally — it does NOT materialise template defaults either. So there is no alternative
  API build path that carries the two params for you; a loop built + saved via
  `put-projects` iterates iff they are present (measured 0→3 on the same object).
- ✅ **Workaround (HISTORY — no longer needed since E-160):** before the builder fix,
  the way to iterate was, after `process-create`, to read the flow back, append the two
  parameter objects to the loop action's `parameters`, and `put-projects` (verify by
  reading the loop's `parameters` back — 5 present, originals unchanged — before running).
  The builder now emits the two at create, so this post-create splice is retired. ⚠ One
  fact from it that still applies to any read-back diff: **on save the platform
  normalises `…808b0d` from `"…00.0000000Z"` to `"…00:00:00Z"`** — the same parameter;
  tolerate the trailing-precision reformat when you diff a stored loop.

The parameter objects to append (authoritative `parameters`-array form):
`{"tabPropertyId":"99e8766d-d6be-4948-8f57-1f141f61724e","value":"-1","variable":[]}`
and `{"tabPropertyId":"9d2d3483-f04b-48ac-9dea-2ef7ae808b0d","value":"2010-01-01T00:00:00.0000000Z","variable":[]}`.

## Diagnosing a For Each that "does nothing"

- **Prove the loop's INPUT is populated before you read its zero — a wrong-shaped
  run payload reads identically to a dead loop.** If the flow's input variable is
  supplied in the wrong shape (e.g. a bare list where the process declares
  `{source, tenant}`), the input variable is left empty, any pre-loop JavaScript
  node that substitutes it via `<%N%>` dies with **`"Unexpected token ';'"`** (an
  empty token becomes `var x = ;`), the list the loop iterates comes back **null**,
  and the loop iterates nothing — indistinguishable from the parameter-omission
  hang unless you check the pre-loop nodes' error variables and the list length.
  Gate on: the pre-loop nodes ran clean AND the In-List variable is the expected
  length, THEN read the loop's body count.
- **A body node that never ran reports no error.** Clean per-node error variables
  are NOT evidence the body executed. Get positive evidence out-of-band: a Data
  Store `InsertRows` in the body writing to a disposable store, read from OUTSIDE
  the flow — a timeout can suppress every *returned* output variable (observed:
  `vars: {}` on a timed-out run), so never rely on a value returned into a flow
  variable to prove the body ran. Prove that marker can write with a **no-loop**
  run first, or its zero is uninterpretable.
- **Judge a loop on rows landed, not status.**
- **`For Each` takes ONE input port.** Two loops in sequence, or a body-exit and
  the loop-continuation both reaching the same downstream node, need a `Join`
  between them, or the back end refuses `statusCode 383 "Action has too many
  input ports."` on save.
- A **list**-returning Node binds its result via the **`List Result`** parameter
  (`…60237e88`); a scalar via **`Single Result`** (`…51b9fcdc`). Wrong one → the
  list variable is never assigned and the loop iterates null (also a timeout).

## Related Data Store facts used above

- A Data Store **must have a primary key** — `datastore-from-json` without
  `primaryKeyAttributeNames` is refused `502 "At least one column must be marked
  as a primary key."` So you cannot append identical rows as a pure log; a
  per-row distinct key is required to count iterations by row.
- Inside a For Each, per-iteration **single** `InsertRows` calls write N distinct
  rows correctly (this is the working idiom); the **collapse-to-one** failure is a
  *batch* insert of a parallel-list mapper in a single call, a different path.

## Landing N rows: the working shape, its body-port wiring, and the re-run NOOP

Confirmed end to end (a multi-row landing card, 2026-09-02): to write **N rows to a
store from one run**, loop a **model-typed list** and do **one `InsertRows` per
iteration** binding the loop ITEM's data-model attributes. Concretely:

- **The list and the item are both typed as the store's data model.** A Node emits the
  list bound via **`List Result`** (not `Single Result`); the For Each's **`For Each
  Item`** output is bound to a NON-list variable of the same model type; the body
  `InsertRows` Set-Values mapper binds `item.<attr>` exactly as the single-row splice
  does (b017 pattern), only the bound variable is the loop item, not a standalone one.
- **Body-port wiring (edges, not just `parent`).** The `parent` key on the body action
  sets ParentId (visual containment) but gives it **no ports** — ports come from edges.
  Read from a designer export, a For Each with one body child carries **two out-ports on
  the loop** (loop → continuation, e.g. the Join; and loop → body child) **plus one
  out-port on the body child back to the loop** (body → loop). So the compact-config
  edges are: `[loop, <next>]`, `[loop, <body>]`, `[<body>, loop]`. Omit the last two and
  the build validates but the body node fails with **statusCode 390/391 "Action has too
  few input/output ports."** The platform infers body-vs-continuation from the child's
  ParentId, so edge order does not matter; supply all three edges.
- **Idempotency comes free from the store PK — do NOT write dedupe logic.** Give each row
  a **deterministic natural key** (stable per input, unique within the batch, e.g.
  `<tool>:<table>:r<zero-padded-index>`). A fresh batch lands all N at **status 50**; a
  re-run of the same input replays the same keys and the store PK rejects the duplicates,
  so the instance **halts at status 40 with nothing written twice** — a clean NOOP, the
  same dup-PK guard a single-row card shows (a re-run "must be a NOOP, not a double-load"
  is satisfied by this alone). Validate the WHOLE input up front (count, shape, any
  ceiling) and emit rows only on the clean branch, so a bad input never starts a partial
  loop; then the only mid-loop halt is a dup key, which is the desired NOOP.
- **Cost scales with N.** One native `InsertRows` per row is billed per row: measured
  `timeConsumed ≈ fixed + ~14 ms × N` (vs a single-insert card that bills flat). Size the
  loop to the real table; a very large table is a v2 concern (bulk import), not this shape.
