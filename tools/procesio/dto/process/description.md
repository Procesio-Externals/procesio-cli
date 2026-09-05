# Process (Flow) sub-tool

Build a runnable PROCESIO **process** from a compact config. The builder is
data-driven: every action is resolved against the live action catalog (231+
templates incl. custom/connector actions), so it covers **all** actions without
per-action code.

## Config

```json
{
  "title": "Greet",
  "variables": [
    {"name": "name", "type": "string", "direction": "input", "required": true},
    {"name": "greeting", "type": "string", "direction": "output"}
  ],
  "actions": [
    {"id": "concat", "action": "Concatenate", "params": {
        "List of strings to concatenate": {"template": "Hello <%0%>", "vars": ["name"]},
        "Result": {"var": "greeting"}
    }}
  ],
  "edges": [["start", "concat"], ["concat", "stop"]]
}
```

- **variables** — `VariableDto`. `type` (primitive) or `model` (data-model name/id);
  `direction` input(10)/process(20)/output(30); `isList`, `required`, `default`.
  Input variables are the run payload; output variables come back in the run result.
- **actions** — each `{id, action, name?, params}`. `action` is a catalog template
  **name** (or id). `params` maps a property **label** (or id) to a binding. Omit
  `name` and the builder auto-labels the node from what it does — `GET /users` (Call
  API), `For each items`, a `Node`'s leading `//` comment, `SELECT clients` (Execute
  Query), `Generate <file>` — falling back to the template name; duplicates get a
  ` 2`/` 3` suffix. The label is cosmetic (every reference is by id) and is
  re-evaluated on every build/edit, so an explicit `name` is the way to pin one.
- **params binding** — one of:
  - literal: `"hi"` / `{"value": 5}` → `Value=literal, Variable=[]`
  - variable: `{"var": "name"}` → `Value="<%0%>"`, `Variable=[{0, <id>, attr}]`
    (works for both input properties and **output capture** — bind a var to an
    output-direction property to receive the action's result)
  - variable + attribute path: `{"var": "obj", "path": ["field", "sub"]}`
  - multi-var template: `{"template": "Hi <%0%> <%1%>", "vars": ["a", "b"]}`
- **edges** — `["fromId", "toId"]` (or `{from, to, Type, Config}` for branch ports).
  `start`/`stop` are reserved ids (auto-injected). Omit `edges` for a linear chain.

## API contract (verified live 2026-06-24, 4Export)

- **Validate@source:** `POST /api/Projects/validate` — empty body = valid (the oracle).
- **Create:** `POST /api/Projects` with the `FlowRequestDto`. Returns **empty**; the
  flow persists with the **client-supplied `Id`** (unlike DataTypes, the server does
  not assign it). `--dry-run` returns the DTO + the validate result.
- **Get:** `GET /api/Projects/{id}` → `{ "flow": ... }`.
- **Edit:** `PUT /api/Projects` (desired-state: the whole flow is rebuilt and replaced).
- **Run:** `POST /api/Projects/{id}/run?runSynchronous=true` body `{payload, connectionId:null}`
  → `{instanceId, status, variable, error}`. `status==50` = STATUS_FINISH.

## Advanced (Phase 2)

- **onError** — `{"id":"call","action":"Call API","params":{…},"onError":"handler"}`
  routes the action's error port to `handler` and captures the error in an
  ErrorDataModel variable. (Start/Stop/Join/ForEach have no error port.)
- **Join** — `{"id":"j","action":"Join"}` converges branches (accepts many inputs);
  wire each branch into it, then `j`→stop. Pinned to the flow-control Join template.
- **Scripting** (verified live 2026-06-29, 4Export) — inputs inject by index `<%0%>`
  (an array/object injects as a JSON literal, so `const h = <%0%>;` is valid). **A STRING
  injects as a BARE token, not a quoted literal — wrap it yourself: `const s='<%0%>';`.
  Without quotes you get `const s=SDSDX0GM6L;` → ReferenceError → the Node returns null
  silently (verified 2026-07-22, Uranus 100 P1).**
  **ALWAYS bind the scripting action's `Error` OUTPUT property to a (string) variable**
  (`"Error": {"var": "myErr"}`, alongside `Single Result`/`List Result`) — a script failure
  is captured there so it can be debugged. This is a STANDING directive for every Node /
  Javascript / Python action. It is the Error OUTPUT, NOT the error PORT / `onError` branch
  (that's a different, heavier convergence mechanism — do not use it just to capture an error).
  Output conventions differ **per language**:
  - **Javascript** — `setOutput(v)`; the single `Output` port wraps as `{"result": v}`.
    `v` can be anything (incl. an array/object) but the consumer **must unwrap `.result`**.
    `{"action":"Javascript","params":{"Code":{"template":"setOutput(<%0%>*2)","vars":["n"]},"Output":{"var":"out"}}}` (`out` typed `json`).
  - **Node** — top-level **`return v;`** (NOT `setOutput`). Two clean (un-wrapped) output
    ports: bind **`List Result`** for an array (`out` typed `json`+`isList:true`) or
    **`Single Result`** for a scalar/object. **`Timeout` is required** (number, 60–300; a
    missing/zero Timeout fails the run with `value ('00:00:00') must be greater than '00:00:00'`).
    `{"action":"Node","params":{"Code":{"template":"return <%0%>.map(x=>x*2);","vars":["arr"]},"Timeout":60,"List Result":{"var":"out"}}}`.
    → **Node is the way to emit a clean typed list/object** (e.g. a chat message array);
    Javascript cannot (it always wraps). Python: `print(v)` → `Output` = `{"result":"<stdout>"}`.
- **docMap** (Generate Document) — `{"id":"gd","action":"Generate Document","params":{"Select Document Template":"<docId>","Save document as":"2","File Name":"out","HTML string":{"var":"html"}},"docMap":{"<docVarName>":"<procVarName>"}}`
  maps document variables to process variables; run and read `html`/the file output.
- **Data Store node** (`{"action":"Data Store","params":{"Select Data Store":"<storeId>","Operation":"<op>", …}, "dsMap":{…}, "dsWhere":[…]}`) — row-level ops on a native Data Store. `Operation` is the option **value** (`SelectRows`/`InsertRows`/`UpdateRows`/`DeleteRows`), never the label. Verified live end-to-end (SELECT filters, INSERT writes):
  - **`dsMap`** (Set Values, Insert/Update) — `{"<columnName>": binding}` per column. A bare string/number is a **LITERAL**; use `{var}` / `{var,path}` / `{value}` otherwise. The row targets its column **by NAME**. Supply EVERY required column (a missing required column fails at run: `required column '<c>' cannot be null`); system columns (`CreatedOn`/`UpdatedById`/…) are auto-filled. `InsertRows` writes **element 0 of a list only** — there is no native batch, so loop a `For Each` to write many rows.
  - **`dsWhere`** (Where, Select/Update/Delete) — `[{"column","op","value"}]` ANDed, or `{"logic":"and|or","conditions":[…]}`. `op` is a decisional operator name (`equals`, `notEquals`, `contains`, `greaterThan`, …). The runtime value is an ARRAY of `InputDataStoreDecisional` (the SAME condition tree a rule `Decisional` uses — left operand is the column literal, right is the value/variable), **not** the REST filter group. A SELECT with no `dsWhere` returns ALL rows.
  - **`Result Rows`** output must bind a **NON-LIST** variable (a `list`-typed var → HTTP 500 `Nullable object must have a value.`); it still returns the rows as a list. Bind `Affected Rows` (int) to read an insert/update/delete count. Managed with the `datastore-*` tool actions (create store, add/get/delete rows).
- **For Each (loop body)** — give a `For Each` action an `id`, then mark each body
  action with `parent:"<forEachId>"`. The body actions are parented to the loop frame
  (`ParentId` = the For-Each node) and the For-Each renders as an `area`. A `For Each`
  **cannot be nested directly inside another `For Each`** — put a `Call Subprocess` (or
  `Trigger Subprocess`) inside the loop and place the inner `For Each` in that subprocess.
  `{"id":"loop","action":"For Each","params":{"For Each Item":{"var":"items"}}}` +
  `{"id":"step","action":"Map Data","parent":"loop"}`.
- **Rule-based `Decisional`** (diamond, NOT the AI one) — `branches:[{name, to, when:[{left,
  op, right?, logic?}]}, {to, default:true}]`. `op` is a STRING operator: `IS_NOT_EMPTY` /
  `IS_EMPTY` (left only), `EQUALS` / `DOES_NOT_EQUAL`, `CONTAINS` / `DOES_NOT_CONTAIN`,
  `GREATER_THAN[_OR_EQUAL_TO]`, `LESS_THAN[_OR_EQUAL_TO]`, `IS_TRUE` / `IS_FALSE`,
  `BELONGS` / `DOES_NOT_BELONG`. Each case AND the default get a branch port; a case that
  skips work should route to a `Join` that the happy path also reaches (Stop takes one input).
  Example "do nothing unless cod arrives": `{"action":"Decisional","branches":[{"name":"Are
  cod","to":"work","when":[{"left":{"var":"cod"},"op":"IS_NOT_EMPTY"}]},{"to":"join","default":true}]}`.
  A non-default case with no `name` is auto-labelled from its condition (`amount > 1000`,
  `cod present`); the AI variant is labelled from its natural-language `condition`. An
  explicit `name` always wins, and the label is re-evaluated on every build/edit.
- **`Trigger Subprocess` = fire-and-forget** (vs `Call Subprocess` which waits). Same
  `subprocess:{target,inputs,outputs}` shape; use it when the parent needn't wait for the
  child (e.g. Drive upload / email / sheet-append side effects while the form already has
  its generated file outputs). Outputs generally aren't captured (it doesn't await).
  **Fire-and-forget hides failures: a broken/failing child never fails the parent run**, so
  a headless `status==50` is NOT proof the child worked — verify a subprocess side effect
  with `Call` (awaited) or by checking the effect directly.
- **Subprocess input mappings require the PARENT side to be a plain VARIABLE.** A subprocess
  input row maps a parent variable id -> a subprocess input var. A raw **literal**
  (`{"value": x}` or a bare scalar) or an **attribute-path** (`{"var": x, "path": [...]}`)
  lands a non-variable token in the mapping's `process` field. PROCESIO tolerates that for
  `Call` at runtime, but the live designer marks a **`Trigger Subprocess`** INVALID
  ("Mapping of required subprocess variable (X) is missing"), which **blocks the launch**
  (`statusCode 373`). The builder auto-fixes **literals**: each literal subprocess input is
  hoisted into a synthetic `_sublitN` process variable (its DefaultValue = the literal, which
  IS delivered at runtime) and the binding rewritten to that variable — so literal inputs are
  safe for Trigger. **Attribute-paths are NOT auto-hoisted** (that needs a computed value, not
  a default): to pass `someObj.attr` to a subprocess input, first compute it into a plain
  variable (a `Node`) and map that variable — otherwise keep that call a `Call Subprocess`.
  (Our static validators — `process-fe-validate`, `flow-lint`, `POST /api/Projects/validate`
  — all MISS the literal/path Trigger defect; only the live Angular designer catches it.)
- **Call/Trigger Subprocess** — `subprocess:{target,inputs,outputs}` on a `Call
  Subprocess` / `Trigger Subprocess` action. `target` = the subprocess flow GUID;
  `inputs` maps `subInputVarId -> parentBinding` (sub-process variable ids are GUIDs,
  e.g. from `read-flow-graph` on the target flow; the parent side resolves by name);
  `outputs` maps `parentVarName -> subOutputVarId`.
  `{"id":"call","action":"Call Subprocess","subprocess":{"target":"<flowGuid>",
  "inputs":{"<subInVarGuid>":{"var":"x"}},"outputs":{"y":"<subOutVarGuid>"}}}`.
- **Canvas** is auto-laid-out left-to-right by the deterministic layout engine
  (`tools/procesio/layout/`) as the final build step — happy path straight, branches
  fanned, error handlers on a low lane, For-Each frames sized to their body.
- **Edit keeps the layout stable.** On an edit, existing actions stay where they are
  (positions carried over by name + array order); only the `relayout` scope is re-tidied.
  `relayout`: `"all"` (re-tidy everything) | `"none"` | `"new"` | `[actionId,…]` |
  `{new:bool, actions:[…], edited:[…]}`. Default on edit: place NEW actions only, leave
  the rest untouched. (For a one-off tidy of a specific action on an existing process, the
  `layout-flow --only <id>` tool is the zero-ambiguity path — it uses real action ids.)

## Invariants

- **Node shape is dictated by the action** (`CustomData.type` ← the catalog `shape`);
  the builder never sets a shape per action. **Decisional fan-out is unlimited** (N cases
  + an optional default). Both are locked by `tests/test_process_invariants.py`.

## Gotchas

- Ports live on the **source** action's `Ports[]`; a `00000000…`→Start entry edge is required.
- `CustomData` is designer metadata (position/icon/config) — not load-bearing for
  execution, but included so the flow opens cleanly in the UI.
- The bundled catalog (`dto/data/action_catalog.json`) is the offline default;
  `prepare_ctx` fetches the live workspace catalog at build time for custom actions.
- **Call API version — use the unversioned `"Call API"` (the LATEST/live one).**
  `/api/Actions` exposes `Call API` (`cd8bd0bc-…804de`), `Call API v1/v2/v3`; there is
  **no `v4` action** — "Call API - v4" is only a palette FOLDER (the current generation),
  and `v1/v2/v3` are frozen pins (base + v1 sit under a "To be decommissioned" folder).
  Real production flows use the unversioned `Call API`; it has the richest outputs
  (`Response Status` / `Response Body` / `Response Headers` / `Response File`, plus
  `Verb`, `Endpoint`, `Request Parameters`, `Time Out`). Bind the credential to
  `Select REST API credentials` (`{"credential":<gid>}`); the API-key credential
  auto-injects its key. **Do NOT pin `Call API v3`** — its output props are named
  `Status Output` / `Body Output` and it is an older generation. (Verified live 2026-07-14
  building the google-search migration — see `[[aat-to-procesio-migration]]`.)

## AI Decisional

Routes on natural-language conditions evaluated by an LLM. An action with `params` (the AI
config) + `branches` (each case's plain-English `condition` + target, plus one `default`).
Needs an **"AI OpenAI Compatible"** credential (create with `credential-create`).

```jsonc
{"id": "ai", "action": "AI Decisional",
 "params": {
    "Select AI Configuration": "<credential id>",
    "Model": "gpt-4o-mini",
    "Endpoint": "1",                        // 1 = Chat Completions, 2 = Responses
    "User Prompt": {"template": "Classify: <%0%>", "vars": ["ticket"]},
    "Timeout (seconds)": 60,
    "LLM Response": {"var": "aiResult"},    // OUTPUT — the structured decision
    "Temperature": 0, "Top P": 1, "Max Output Tokens": 1024,
    "Presence Penalty": 0, "Frequency Penalty": 0, "Seed": "", "Store": false},
 "branches": [
    {"name": "Refund", "to": "n1", "condition": "Is the customer asking for a refund?"},
    {"name": "Bug",    "to": "n2", "condition": "Does this describe a software bug?"},
    {"to": "n3", "default": true}]}
```

Each case `condition` is a plain-English sentence; the model picks the first true case.
`name` is the optional designer label (default `Case N`). Every case AND the default get their
own branch edge (the default carries the `isDefault` marker), so route each target to its own
successor — a `Stop` takes only ONE input; converge branches with a `Join` if they must merge.
