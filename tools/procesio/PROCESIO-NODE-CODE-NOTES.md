# PROCESIO — Node `Code` interpolation safety, and the credential-free run-history actions

Two hard-won build facts, generalized. Keep the specifics (datatype ids, action names,
param shapes) — they are the knowledge, not incidental to one case.

## 1. `<%N%>` substitution into a Node's `Code` is TEXT substitution, and only an OBJECT value is safe

A Node `Code` parameter binds variables to `<%0%>`, `<%1%>`, … in a `variable` list
(`[{id:N, variableId:…}]`); at run time each `<%N%>` is replaced **in the source text
before parsing**. What the replacement text is depends on the variable's **datatype**, and
the four contexts behave differently (measured, one hostile string `` IN${(6*7)}"q\Z `` in
each):

| how the value is written in the Code | a hostile STRING value | verdict |
|---|---|---|
| bare `const v = <%0%>;` | raw text → syntax error (the node fails) | unusable for strings |
| double-quote `const v = "<%0%>";` | a `"` in the value closes the string → syntax error | UNSAFE |
| **backtick `` const v = `<%0%>`; ``** | **`${…}` EXECUTES** (`${(6*7)}`→42); a backtick breaks the script | **UNSAFE — code injection** |
| **Object/Json datatype, bare `const o = <%0%>;` then read `o.field`** | JSON-encoded by the platform → the value is a proper JS literal, everything escaped | **SAFE** |

**So: a `"type":"string"` input spliced into a Code template is the injection signature.**
`${…}` only fires inside backtick template literals, so backticks are the dangerous case,
but double-quote and bare are not safe either (a quote/backslash/newline still breaks
them). The **only** injection-safe transport is an **Object/Json** variable
(datatype `0317bfee-b2f5-4bde-bfe8-121212121220`): the platform JSON-serialises it on
substitution.

**The fix ("structure transport"):** route scalar inputs through ONE Object input rather
than N String inputs. Declare one Object variable (e.g. `sifParams`), have the form/caller
populate its keys, and read `params.field` inside the node via bare Object injection. When
converting an existing process, rewrite the consuming nodes to read from the Object,
rebind their `Code` `variable` list to it, renumber the output placeholders, and **remove
the old String inputs** (a leftover `isRequired:true` String input makes publish reject a
run that omits it: `373 "Missing required input for variables: …"`). The values are
unchanged, so a deterministic output stays byte-identical.

⚠ **A null-valued injection is itself a defect.** When a bound variable is **null** at run
time, `<%N%>` substitutes **empty text**: `const v = <%N%> || x;` becomes `const v = || x;`
→ SyntaxError, which the platform **captures** (the instance still finishes status 50) and
the node's output is null — a silent failure. Any `<%N%>` whose variable can be null
(an optional output var, a file descriptor set on only one branch) must be written
**`[<%N%>][0]`** — `[][0]` = `undefined` on a null injection, `[value][0]` = value
otherwise. Read a node's error variable to catch this (`"Unexpected token '||'"` /
`"Unexpected token ';'"`).

## 2. A process can read its own workspace's run history in-flow, with NO credential

Three `isProcesioAction` built-ins carry **zero credential parameters** (the Call API v1/v2/v3
path needs a bound REST credential, which does not travel with a pack — avoid it):

- **Get Recent Instances** (`actionId cf514e01-…`) — inputs `Page Number` + `Page Item Count`
  (required Integers; 0 = all), optional `Select Process` (flow-list) / `Process Template Id`
  / `Status type`; outputs `Result` and `Total Count`. ⚠ `Result` comes back as a **LIST of
  run rows** (`{Id, Status, UpdatedOn}`, PascalCase), **carrying NO variable values** — the
  outcome is per-instance. Read `Total Count`, not the row count (a short page reads like a
  stable total).
- **Count Recent Instances** — outputs `Process Instances Count` (Integer); optional process-id
  list (empty = whole workspace) + `Status type`.
- **Get Instance Outputs** (`actionId 98ab31ca-…`) — the per-run outcome. Needs `Select Process`
  (flow-list = the target process id), **`InstanceId` (Guid datatype, NOT String — a String
  var is rejected on save)**, and an `Output Variables` **process-outputs** mapping (the
  selected process's output var → a local var). It wraps `GET /api/Projects/instances/{id}/output`.

**Build recipe (compact builder):** the count outputs need `"type":"integer"` (`"number"`
= Double, rejected `142 "Data type mismatch"`). `Get Recent Instances.Result` is one object
var. Express `Get Instance Outputs` with a `subprocess` key:
`{"action":"Get Instance Outputs","params":{"InstanceId":{"var":"topId"}},
"subprocess":{"target":<pid>,"outputs":{"localVar":<subOutputVarId>}}}`, and type the
`InstanceId` var as the Guid datatype via the builder's `"model":"0317bfee-b2f5-4bde-bfe8-121212121222"`
escape hatch. This lets a form → process → native-actions topology list runs, count them,
and show each run's summary with **no store, no credential, no foreign binding** — the
property a distributable pack needs. The card's side of the contract is one deliberate
OUTPUT-oriented variable (orientation 30) carrying the summary; `/status?getVariables`
returns its value in `defaultValue` and `/output` at `result.instance.variable[<name>]`
(NOT gated by `isArchived`). Proven end-to-end at UC7 E-164.

## 3. Editing a live Node's `Code` in place: fix BOTH copies (runtime param AND designer customData)

⚠ **A Node action carries the `Code` TWICE in the persisted flow**, and an in-place edit that touches
only one ships a stale card. The two copies (confirmed on a live store-write card, 2026-09-02):

- **`Flows[i].Actions[j].Parameters[k].Value`** — the RUNTIME copy. This is what the engine executes.
- **`Flows[i].Actions[j].CustomData.configuration[*].settings[*].value`** — the DESIGNER-layer copy
  (the "Code" setting the designer shows and re-materialises from).

**Why it bites.** A binding-driven / spliced `put-projects` that rewrites only the runtime parameter
(e.g. to push a corrected engine body) leaves the customData copy STALE. Consequences: (1) the standing
card RUNS correctly (runtime wins at execution), so a happy-path run looks fine and hides the drift;
(2) **`export` serialises the customData copy**, so the exported pack carries the OLD body — a handover
pack that imports a stale card even though the source card ran the new one; (3) any designer re-save can
re-materialise the runtime FROM the stale customData, silently reverting your fix.

**The discipline.** When you edit a Node's `Code` on a live flow, replace it in **both** places, then
read the flow back and assert BOTH carry the new body (grep a marker that only the new body has, and a
marker only the old one had, on the runtime `Value` AND every `customData…settings…value`). Only then is
the card — and its export — actually on the new code. This is the specific, mechanical form of the
"read back, don't trust the write" rule (a `put:true` / HTTP 200 is not evidence the body changed, and it
is certainly not evidence that BOTH copies changed). A full rebuild through `process-create` regenerates
customData from the config and so avoids the split, but changes the flow id; editing in place (to keep a
standing card's id) is exactly when you must fix both copies.

## 4. A Node's `Code` can contain literal control characters, which `argv`-based editing cannot carry

A Node body is stored as a plain string field, so it can hold **literal control characters** — in
practice `\x00`, used as a composite-key separator because it cannot collide with real data:

```js
var key = r.SupplierID + "<0x00>" + r.CNCode;   // renders as a space in every terminal and diff
```

Nothing marks such a line as unusual: a terminal, the designer and most diff views all render `\x00`
as a space. Two consequences for anyone editing a live body:

- **`node-replace-text` (and any tool that shells out) fails if `--find` or `--replace` contains one.**
  Python's `subprocess` raises `ValueError: embedded null character` and rejects the *whole* command,
  so the error names no argument and points nowhere near the line responsible. `grep` likewise reports
  `Binary file … matches` and prints nothing — pass `-a` to search a captured body.
- **Never retype such a line.** Copying it by hand substitutes a space, and the code still runs: keys
  simply stop matching, with no error at any layer.

Editing around it, in order of preference:

1. **Anchor on a NUL-free line.** Pick the nearest unique neighbouring line and insert before or after
   it, instead of rewriting the line that carries the separator.
2. **Write the separator as a source-level escape** — `"\u0000"` — so the argument you pass is entirely
   printable while the running code still builds the byte-identical key.
3. **Locate them before choosing an anchor**: capture the body (`node-params`), then print every line
   where `'\x00' in line`. Do this first; it costs one read and removes the whole failure mode.

Corollary for the code itself: keep per-record state **on the record object** (`obj._budget = …`)
rather than in a side map keyed by the composite key — then no key has to be constructed, or typed,
at all.

As always, the edit must land on BOTH copies (§3): a NUL-free anchor is what makes `--expect 2`
usable here.

## 5. A `<%N%>` in your `--find` matches the RUNTIME layer only — expect 1, not 2

§3 says an in-place `Code` edit must reach both copies. That is still true, but the expected hit
count is **not always two**, and getting it wrong looks like a successful edit that never happened.

The two layers store placeholders differently:

| layer | path | how a bound variable appears |
|---|---|---|
| runtime | `parameters[…].value` | `var f = <%6%>;` — positional placeholder |
| designer | `customData.configuration[…].settings[…].value` | `var f = 6161830e-…;` — the variable's **GUID** |

So a `--find` that contains `<%N%>` can only ever match the runtime layer: `--expect 2` fails the
assertion and — correctly — **writes nothing**. A find whose text has no placeholder matches both
and gives the familiar `replacements=2 leaves=2`.

- Placeholder in the find → `--expect 1` (plus `--allow-binding-change`, which the tool demands
  for any find/replace touching a placeholder even when the placeholder multiset is unchanged).
- No placeholder in the find → `--expect 2`.

After a runtime-layer hit the tool **regenerates the designer layer from runtime**, translating each
`<%N%>` back to its variable GUID, so both copies end up consistent from the single edit. Read back
and confirm that rather than assuming it — the check costs one call and is the whole of §3.

**A mismatched `--expect` reports the hit count it found, not an error.** Print the `put` field, not
just `replacements`: `put: false` is the difference between "edited" and "declined to edit".

**Never spell `<%N%>` out in prose inside the body.** Substitution is textual and does not respect
comments, so a placeholder written in a `/* … */` explanation is injected like any other occurrence —
it changes the binding footprint and can drop a value into the middle of your comment.

## 6. Clearing `isRequired` does not make a File input optional — a native File action rejects null

Making a File input genuinely optional takes **two** changes, and the flag is the lesser one.

1. **The Code node** must survive the absent value. A bare raw placeholder on the right of an
   assignment (`var f = <%6%>;`) becomes `var f = ;` — a SyntaxError that kills the node before any
   of its own diagnostics can run. Guard it as `[<%6%>][0]`, which yields `undefined` when absent and
   the object when present. (Quoted placeholders — `"<%1%>"` — are already safe: they collapse to `""`.)
2. **Every upstream native action that consumes the file** must be branched around. A native
   `File To Base64` fails the whole run with `Input file can't be null.` (status 40) — it has no
   tolerant mode and no parameter that changes this. Clearing `isRequired` on its own therefore
   converts a form that *blocks* the user into a run that *crashes* on them, which is strictly worse.

So the structural fix is a branch — a Decisional on "is the file null", with the encode on one leg
and an empty-string assignment to the base64 variable on the other — added via `process-edit`'s
desired-state config (there is no `node-add`). Until that branch exists, **leave the flag required**:
a required input is an honest constraint, an optional one that hard-fails is a defect.

Generalises to any native action that takes a File: test the absent case before you advertise the
input as optional.

## 7. `validate` does NOT parse the Node body — syntax-check it yourself

`node-replace-text` validates and flow-lints before it PUTs, and it will report `isValid: true` for a
body containing a **syntax error**. The platform validator checks the flow graph and parameter
shapes; it never parses the JavaScript. So a missing brace sails through validate, through the PUT,
and through publish.

At run time the node does not throw a catchable error — the body fails to compile, so the node's own
top-level `try { OUT = run(); } catch` never executes and the node returns **null**. What you see is
a downstream failure with a misleading message:

```
node: Write Workbook | type: Base64 To File
msg: Base64 string can't be null.
```

The named node is fine. The producer three steps upstream is the one that failed, silently. Read the
producer's output variable: `recon: null` with every text pane also `null` is the signature.

**Always syntax-check after editing a body**, with the placeholders neutralised so a real parser can
read it:

```bash
python scripts/run-tool.py procesio node-params --id <flow> --node <node> > nc.json
# extract the body, then:  src = re.sub(r'<%\d+%>', '0', body)
# wrap it in a function so `return` at top level is legal, and:
node --check nc.js
```

`node --check` reports the line. Do this before the run, not after: a run costs minutes and points
at the wrong node.

### The specific way this happens: a line-range FIND swallows an enclosing brace

Extracting `--find` as a slice of lines (`L[start:end]`) is convenient and dangerous. If the slice's
last line is a `}` that closes an **enclosing** block rather than one opened inside the slice, the
replacement must re-emit it. It is invisible in review because both the FIND and the REPLACE look
internally balanced:

```js
if (outer) {                 // opened BEFORE the slice
    var x = f();             // <-- slice starts here
    if (inner) { ... }
  }                          // <-- slice ends here: this closes OUTER, not inner
```

Prefer a FIND anchored on syntactically complete text. When a line range is unavoidable, count braces
across the FIND and the REPLACE and require the deltas to match before writing.

## 8. Inserting an action into a live flow: two edits, and a casing trap

`node-insert` exists now. Two things make a hand-rolled version go wrong, and both fail *silently*
— the flow still validates.

**Ports live on the SOURCE action.** An edge is `{sourceId, destinationId}` stored on the node it
leaves. So inserting X between A and B is two edits, not one: give X a port to B, then repoint A's
port at X. Do only the first and X is unreachable; do only the second and everything after A is
orphaned. Neither is a validation error.

**The DTO builder emits PascalCase; a live flow is camelCase.** `_action_node()` returns
`{Id, FlowId, Ports, Parameters, CustomData}` — the CREATE shape — while `GET /api/Projects/{id}`
returns `{id, flowId, ports, parameters, customData}`. The API accepts both, so splicing one into
the other is accepted and then renders inconsistently in the designer. Convert with
`nodeparam.to_live_action()`, which also lowercases each `parameters` row
(`TabPropertyId` → `tabPropertyId`).

Refused rather than guessed: an anchor with more than one outgoing port. Which branch the new node
belongs on is a design decision.

**Related, and the reason this tool had to exist:** `process-edit` is a desired-state rebuild, so
adding one action to a 22-node flow through it means re-expressing the whole flow — including a
70 KB Node body — as config. `read-flow-graph` is an offline reader and does not produce that
config, so there is no round-trip.
