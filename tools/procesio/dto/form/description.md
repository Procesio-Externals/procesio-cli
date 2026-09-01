# Form Template sub-tool

Create/edit/publish a PROCESIO **form**. The layout is a tree of controls in
`Data.elements`. **Proven live (2026-06-24):** the runtime renders from `elements`
— the encrypted `Data.code` blob is NOT needed (a form with `code:""` rendered
fine), so forms are fully buildable server-side.

## Config

```json
{
  "name": "Registration",
  "type": "general",
  "browserTitle": "Register",
  "elements": [
    {"type": "heading",  "label": "Registration Form"},
    {"type": "paragraph","label": "<p>Please fill in your details.</p>"},
    {"type": "input",    "label": "Full Name", "name": "fullName", "required": true, "placeholder": "John Doe"},
    {"type": "number-input", "label": "Age", "name": "age"},
    {"type": "select",   "label": "Country", "name": "country", "options": ["Romania", "USA"]},
    {"type": "radiobox", "label": "Plan", "name": "plan", "options": ["Free", "Pro"]},
    {"type": "checkbox", "label": "Subscribe", "name": "subscribe"},
    {"type": "textarea", "label": "Comments", "name": "comments"},
    {"type": "section",  "label": "Group", "children": [ {"type": "input", "label": "Nested"} ]},
    {"type": "button",   "label": "Submit", "submit": true}
  ]
}
```

- **elements** — each control: `type` + common props (`label`, `name`, `required`,
  `placeholder`, `tooltip`, `readonly`, `visible`, `default`). `options` for
  select/radiobox/dropdown (strings or `{name,value}`). `children` for containers
  (section/columns/column/tabs/tab). `configs` (object) sets any raw config key.
- **control types** (from harvested goldens): heading, paragraph, input, textarea,
  number-input, datetime-input, select, dropdown, radiobox, checkbox, button,
  divider, section, columns, column, tabs, tab, table, image, file-upload,
  file-viewer, icon, list, approval, … (see `dto/form/elements/`).
- **type** — `general` (1) or `usertask` (0). **publish** — Status PUBLISHED(1)/DRAFT(0).

## Events, triggers, tasks, themes (Phase 2)

- **events** — per control: `"events":[{"on":"click","do":"js","code":"alert(1)"}]`.
  `on` ∈ click/input/change/focus/blur/hover/ready/open/close/tabchange/rowadded/
  rowdeleted/paginated/stepchange/nextstep/previousstep/beforeapprove/afterapprove/
  beforereject/afterreject/beforeapprovalsubmit/afterapprovalsubmit/messagesfetch/
  messagesent (each fires on a control that has that slot; type/key verified vs
  ui-builder trigger.ts + EventType enum).
  `do` ∈ **map** (`mapping:[{to,value|from}]`), **process** (`processId,syncRun,
  inputs:[{to,from}],outputs`), **js** (`code`), **form** → EventAction.TRIGGER_FORM
  (`formId`,`mapping`).
- **tasks/assignees** — `assignee`/`assigneeReplacement` on section/tabs/table;
  `approver`/`approverReplacement` on the `approval` control.
- **theme** — `"theme":{"--c-primary":"#0039e3","--p-form":"24px"}` overrides the
  form theme variables (colors, fonts, spacing, per-control styling). ~190 vars in 18
  groups (see `data_shell.json` / `docs_info/form-theme.ts`).
- **form CSS / JavaScript** — the designer's "Switch to code" editor:
  `"css":"...", "javascript":"..."` (or `"code":{"css","javascript"}`). Encrypted into
  `Data.code` (CryptoJS AES; key in Credential Manager `procesio/form-code-key`). Empty →
  `code:""`. See `code_cipher.py` + `FORM-STYLING-NOTES.md`.
- **per-component style** — on any field/container control:
  `"style":{"--h-input":"50px","--c-input-background":"--c-neutral--50"}`. Only the
  control's CSS-group vars are valid (input/number/datetime/textarea/select → Input group);
  color vars take a theme color variable, not a hex. Stored as enabled CSSProperty[] in the
  element's `style` config.
- **all properties** — any control config is settable via the named convenience
  keys (label, placeholder, required, options, src, width, …) or the raw `configs`
  passthrough; containers nest via `children` (built FLAT with `parentId`, the
  structure PROCESIO renders).
- **table** — `{"type":"table","label":"Items","columns":[{"key":"product","label":"Product","cell":{"type":"input"}},{"key":"qty","label":"Qty","cell":{"type":"number-input"}}]}`
  builds the table + a row + the cell controls (wired via `childrenIdPerColumn`).
  Also `section`/`columns`(+`column`)/`tabs`(+`tab`) containers with `children`.

## Form JavaScript: fields are keyed LOWERCASE (critical, 2026-07-27)

**`ProcesioForm.data.fields` keys are the field name LOWERCASED** (and a UI save re-derives them). JS is case-sensitive, so a camelCase reference like `ProcesioForm.data.fields.locuiesteDetalii` (or `.zonaFormular`, `.actProprietate`) is `undefined` — the event fires but silently does NOTHING (this cost days on Uranus 100: a UI save lowercased the keys and every camelCase visibility/hide/file-wrap toggle broke, while the config still looked perfect). **ALWAYS reference form fields case-insensitively** in any control/FORM_LOAD RUN_JAVASCRIPT. Prelude, then use `fld(name)`:

```js
var F=ProcesioForm.data.fields;var _fl={};for(var _k in F){_fl[_k.toLowerCase()]=F[_k];}
function fld(n){return _fl[String(n).toLowerCase()];}
var x=fld("locuiesteDetalii"); if(x){ x.visible=need; x.required=need; }
```

Applies to EVERY field reference: visibility toggles, submit-button hide/show, file-value wrapping, reading another field’s `.value`, etc. (`f.locuieste` only “works” because it has no uppercase letter to lose.)

## Control wiring cookbook (verified live 2026-06-29)

- **image** — `src` must be a LIVE url (a 404 shows the alt text as broken "brand"). Use
  `{"type":"image","src":"https://…","alt":"…","width":200}`.
- **dropdown** — it is an action MENU, not a value field. Populate via
  `configs:{items:[{id:<guid>,icon:"content_copy",label:"Duplicate",type:"BUTTON"},{type:"DIVIDER"}]}`.
- **file-viewer** — `src` is `URL_OR_FILE` → accepts a plain URL. Preview a doc with
  `{"type":"file-viewer","src":"https://…/x.pdf","configs":{"viewerType":"INLINE","allowedFileTypes":["pdf"],"viewerHeadline":"…"}}`.
  Empty src renders "Field source not set".
- **multiple file-upload / array-valued controls** — a `file-upload` (or `select`) with `multiple:true`, plus `list`/`table`/`dynamic-table-row`, are ARRAY-valued: the builder types their `value` config **`isList:true` + default `[]`** (helper `_value_is_list`) AND the DM `value` attribute `isList:true`. REQUIRED — else the runtime emits a SINGLE object for one uploaded file and a `List<File>` process input fails AT LAUNCH: `Error generating fileId … item is not an array: StartObject` (statusCode 373). Confirmed by Liza; locked by `test_form_events.py`.
- **conditional field visibility (show/hide one field based on another's value)** — verified live
  2026-07-24 (confirmed by Liza). A `RUN_JAVASCRIPT` **INPUT** event on the trigger control that
  toggles the target field's `.visible` AND `.required` together. TWO things that MUST be right,
  or it silently fails:
  1. **The target field must start REGISTERED.** Set the field `visible:true` in the config so
     PROCESIO instantiates it, then hide it on load with a **form-level `FORM_LOAD`
     `RUN_JAVASCRIPT`** (`ProcesioForm.data.fields.<field>.visible=false; …required=false;`). A
     field that starts `visible:false` is NEVER instantiated → `ProcesioForm.data.fields.<field>`
     is `undefined` → the toggle throws `Cannot set properties of undefined (setting 'visible')`
     and the field can never appear. (This is the whole bug — NOT that hiding "destroys" the
     element; a registered field toggles both ways fine.)
  2. **A radio/select `.value` is a plain STRING** (the selected option's text, e.g.
     `"Nu, e închiriat…"`), NOT an object — compare it directly, no `typeof v==='object'` /
     `v.value` / `v.label` handling.
  Event code: `var f=ProcesioForm.data.fields; var v=(f.locuieste.value||''); var need=(v.indexOf('Nu')===0); var x=f.locuiesteDetalii; if(x){x.visible=need; x.required=need;}`.
  Guard the read (`var x=…; if(x){…}`). Toggling `.required` with `.visible` keeps a hidden field
  from blocking submit. NOTE: PROCESIO's `rules-visibility` config ("Visibility:" panel) is NOT a
  field-condition rule — it's only user-access (`all`/`task-assignees`/`custom`); use the JS event
  above for value-driven visibility.
- **chart** — types `bar`/`line`/`combo`/`pie` (+ flags `donut`/`stacked`/`horizontal`/`smooth`).
  Data via `configs`: `categoriesSourceType:"JSON"` + `categoriesSourceValue` = a JSON STRING of
  labels; `seriesSourceType:"JSON"` + `seriesSourceValue` = a JSON STRING. Cartesian series =
  `[{name,data:[..],type?,smooth?,yAxisIndex?}]` (combo sets per-series `type`+`yAxisIndex` for
  dual-axis); pie/donut series = flat `[{name,value}]`. `colors` is a JSON-string array. Canonical
  examples: `docs_info/Exports/charts.procesio`.
- **side-panel** — set `configs:{buttonText:"…",sidePanelTitle:"…"}`; its `children` render a
  full mini-form inside the slide-over. AVOID `select`/`dropdown` inside a side-panel: their
  pop-up overlay mis-positions and offsets the panel layout (the panel is a fixed/transformed
  container). Use `radiobox`/`checkbox`/`input` (inline) for choices in a side panel.
- **chat (reply via a process)** — verified live 2026-06-29. The chat renders from its `value`
  array (`Chat.component.vue`: `messages = JSON.stringify(attrs.value)`); a static mount `value`
  does NOT render, but a reactive value-write does. Wire the reply on **`messagesent`**:
  `events:[{"on":"messagesent","do":"process","processId":…,"syncRun":true,"inputs":[{"to":"history","from":"<chatName>"}],"outputs":[{"to":"<chatName>","from":"<msgsVar>"}]}]`.
  On send the chat appends the user message to `value` then fires the event, so `history`
  (<- chat value) already includes it; the process returns the FULL updated array -> written back
  to chat value -> re-renders. The chat value attr is auto-typed json+isList (builder `_VALUE_LIST`).
  Produce the array with a **Node** action (`return msgs;` -> bind `List Result` = a clean array;
  JS `setOutput` wraps `{result}` and won't map cleanly — see process `description.md` Scripting).
  Message schema (team-confirmed): required `_id, content, senderId, roomId, timestamp`(string).
  A bot reply's **`senderId` = `"procesio"`** (baked-in bot user → renders on the other side; user
  messages use the live currentUserId); **`roomId` MUST equal `rooms[0].roomId`** or it's filtered
  out → "No messages"; **do NOT set a `date` field** (it created empty date-separator badges — use
  `timestamp`). The component creates USER messages with `timestamp:""` (empty), so user bubbles
  show no time — since the process returns the whole list, **backfill any empty `timestamp`** (e.g.
  `for (m of msgs) if(!m.timestamp) m.timestamp="HH:MM"`) before returning. **Local time:** the Node
  action runs server-side in UTC, so a raw `new Date()` shows SERVER time, not the user's. Pass the
  browser UTC offset into the process and compute local time: a hidden `input` field set by form JS
  (`-new Date().getTimezoneOffset()` minutes), added to the chat's RUN_PROCESS `inputs` (e.g.
  `{to:"tzOffset", from:"tzoffset"}`), then in Node `const d=new Date(Date.now()+off*60000)` and read
  `d.getUTCHours()/getUTCMinutes()` (correct regardless of server TZ). Optional: `username,
  date, system, avatar, seen`. `onMessagesFetch` fires ONCE on
  mount to load history; `onMessageSent` → process returns the ENTIRE list. Wire the reply on
  `messagesent` only (reusing the reply process on `messagesfetch` stuck the chat on "loading" in
  testing). Set `configs:{userId, rooms:[{roomId,roomName,users}]}`.
- **CSS stacking gotcha:** never put `animation`/`transform`/`opacity<1`/`filter` on the
  control wrapper `.form-builder--element` — each becomes its own stacking context that traps
  a select/dropdown overlay (the `.multiselect__content-wrapper`, z-index 50) UNDER the later
  sibling controls (it renders transparent / behind, e.g. behind a button). Verify overlay
  stacking with `document.elementFromPoint` (web tool `eval` step).
- **interactive widgets (5-star rating, char counter, live greeting)** — done in form-level
  JavaScript, NOT a control. The JS runs inside `iframe.trigger-sandbox`, so the form doc is
  `window.parent.document`; build into a control wrapper by id (e.g. `#starIcon`) and keep it
  alive with a small `setInterval` (tabs render lazily). DON'T force a font on `#app *` — it
  turns Material-Icons ligatures (info/close) into literal text; scope fonts to text elements.
- **The `trigger-sandbox` iframe is TRANSIENT — never leave a listener or timer inside it
  (proven live 2026-08-05).** Form-level JS is executed by injecting it into an
  `iframe.trigger-sandbox` whose `srcdoc` the platform rewrites per run, and the iframe is
  REMOVED from the DOM afterwards. Removing an iframe destroys its JS realm, so every
  `addEventListener` and `setInterval` registered from that code dies with it — while any DOM
  node the code created in the parent document REMAINS. The failure is therefore silent and
  deeply misleading: the widget renders correctly at form load, then freezes at whatever value it
  last showed, with no console error and the node still on screen. It looks like "the widget
  broke on <some user action>" when in truth the action merely coincided with the teardown.
  Confirmed by a controlled A/B: an interval registered inside a transient iframe advanced 0
  ticks after removal, while one injected into the parent kept ticking.
  **The fix — hoist the code into the parent realm.** From the sandbox, append a `<script>` to
  `window.parent.document` whose body is the widget, so the closure, its listeners and its timer
  all belong to the parent window, which outlives the sandbox:
  ```js
  var D = window.parent.document;
  if (D.getElementById("my-widget")) return;      // idempotent: the sandbox may re-run
  function widget() { /* runs in the parent; `document` IS the form document */ }
  var s = D.createElement("script");
  s.id = "my-widget";
  s.textContent = "(" + widget.toString() + ")();";
  D.body.appendChild(s);
  ```
  Use `Function.prototype.toString()` rather than a hand-escaped string literal — the widget stays
  readable and there is no quote-escaping to get wrong. Give the injected `<script>` a stable `id`
  and bail out when it already exists, or a sandbox re-run installs a second copy with a second
  interval. Anything that must merely RUN ONCE at load (seeding a value, a one-shot toggle) is
  fine directly in the sandbox; only continuous behaviour needs hoisting.
  The installer pattern itself — parent realm, stable id guard, `fn.toString()` — is
  documented in full in [`../../FORM-DEV-GUIDE/02-CODE-INJECTION.md`](../../FORM-DEV-GUIDE/02-CODE-INJECTION.md)
  sections 3 and 4. What this entry adds is the controlled A/B that MEASURES the
  teardown: 0 ticks after removal inside the sandbox, versus an interval injected into
  the parent that kept running.
- **The form UI is styled with Vue SCOPED CSS — a hand-built node renders UNSTYLED (2026-08-05).**
  Every platform-rendered element carries a `data-v-<hash>` attribute and the stylesheet is written
  as `.pds-c-message[data-v-<hash>] { display:flex; … }`. A node built with `createElement` has no
  such attribute, so the scoped rules never match it: copying the platform's class list alone is
  NOT enough. The symptom is a widget that works but looks wrong — in the observed case the message
  container fell back to `display:block`, stacking the icon above the text instead of beside it,
  while the identical-looking native node next to it was `flex`. **Never hardcode the hash** (it
  changes on every frontend rebuild). Instead **clone an existing native node of the same kind**
  and overwrite its text — `cloneNode(true)` carries the scope attributes, the exact inner markup
  and the theme, for free:
  ```js
  var tpl = document.querySelector(".pds-c-message-info:not(.my-widget)");
  var node = tpl ? tpl.cloneNode(true) : buildFallback();   // fallback: also set inline display:flex
  node.classList.add("my-widget");
  ```
  Exclude your own node from the template query or the second render clones the clone. Also mirror
  the native inner structure when hand-building: the icon is a `<div class="pds-c-message--icon">`
  WRAPPING an `<i class="material-icons …">`, and the text is a `<div class="pds-c-message--text">`
  — not `<i>`/`<span>` carrying those classes directly.
  **Prefer avoiding the whole problem:** when a control has a config that renders the node natively
  (e.g. a non-empty `info-text`), set it in the designer and have the widget merely rewrite that
  node's text. Two forms that differ only by such a config will otherwise diverge visually while
  running byte-identical JS — which reads as "the same script broke on the other form".
- **`info-text` is NOT writable from `ProcesioForm.data.fields` (verified live 2026-08-05).**
  The runtime renders it from the element's STATIC config array
  (`Element.component.vue`: `v-if="getConfigValueByKey(element.configs,'info-text')"`), not from
  the reactive field-value object. The field object exposes only `value`, `visible`, `required`,
  `readonly` — so `…fields.<name>.infoText = …` is a silent no-op, and there is no
  `setConfigValue`-style API exposed to form JS. Two consequences: (a) drive any live text
  (character counters, running totals, remaining-quota hints) by writing the **DOM node**, not a
  config; (b) when `info-text` is EMPTY the message component is never rendered at all (`v-if` on
  a truthy value), so there is no node to write into — either set a non-empty `info-text` in the
  designer so the platform renders `.pds-c-message-info`, or create that node yourself. A robust
  widget does both: reuse `host.querySelector('.pds-c-message-info')` if present, else append a
  node carrying the platform's own classes
  (`pds-c-message pds-c-message-info pds-c-message-small pds-c-message-ghost pds-u-m--t--8`)
  so it inherits the theme. **The control's DOM `id` equals its `name` config** and sits on the
  `.pds-c-input-group` wrapper, not on the `<input>`/`<textarea>` — so `getElementById(<name>)`
  then `.querySelector('textarea')` is the reliable way in, and renaming the field breaks the
  selector. Bind updates with a capturing `input` listener filtered to that element (cheap: it
  only acts on the one field) plus a small `setInterval` for lazy/re-rendered containers; guard
  the write with an `if (node.textContent !== next)` so the interval costs nothing when idle.
  A DOM-injected node survives the element's normal re-renders (validation state changes), but it
  is invisible to the designer — it lives only in the form JS.
- **form JS that handles dropdown/menu item clicks** — use ONE document click listener (clicks
  aren't continuous → no layout thrash/flicker; never a document-wide `input` listener or
  `setInterval` poll). **CRITICAL gotcha (verified 2026-06-29):** to detect WHICH menu item was
  clicked, do NOT substring-match `textContent` up the ancestor chain — an ancestor holds the
  WHOLE menu, so every label (incl. "Clear form") is present and a click ANYWHERE outside the open
  dropdown fires the first-matched action (this CLEARED the form on outside-click). Match only an
  element whose own text contains **exactly one** known label (a single item); ignore any node
  holding >1 (the menu container / page wrapper). Framework inputs are controlled — clear/set via
  the native value setter + `input`+`change` events (`HTMLInputElement.prototype` value setter),
  not `el.value=`. Verify by reproducing: set fields, open the menu, click OUTSIDE → fields must be
  UNCHANGED; then click the real item → it acts.
- **responsive table (no horizontal scroll)** — default cell inputs are ~fixed-width and the table
  is `table-layout:auto`, so >3 columns overflow. Force fluid equal columns:
  `#app .pds-c-table{width:100%!important;table-layout:fixed}`, `th,td{min-width:0!important;overflow:hidden}`,
  `.pds-c-input-group--field/--wrapper{width:100%!important;min-width:0!important}`,
  `[class*=table][class*=scroll], .form-builder--table{overflow-x:visible!important}`.

## API contract (verified live 2026-06-24)

- **Create:** `POST /api/FormTemplate` (`FormTemplateDto`) — client supplies `Id`, returns it.
- **Get:** `GET /api/FormTemplate/{id}`. **Edit:** `PUT /api/FormTemplate`. **Delete:** `DELETE /api/FormTemplate/{id}`.
- **Publish:** `Status=1` + `State=true` on the body (or `PATCH /api/FormTemplate/{id}?state=true`).
- **Public vs private:** DTO field `IsPrivate` (config key `isPrivate`, default false; designer
  "Make form public" toggle = `!isPrivate`). **`isPrivate:false` is necessary but NOT sufficient:**
  a form that **contains an approval control** — or has assignees/approvers — can ONLY be private;
  the platform disables the toggle and keeps it private regardless of the config value (the
  presence of the approval control, not a configured approver, triggers this). To truly make a form
  public, remove any approval control / assignees / approvers. Verify the actual toggle state in
  the designer, not just the DTO field.
- **Render:** create a CustomUrl — `POST /api/CustomUrl/FormTemplate {Type:3, EntityType:1, EntityId, Url}`
  → `tinyUrl`; open **`https://forms.procesio.app/{tinyUrl}`**. (A bare `/forms/{id}`
  has no workspace context and 404s — the CustomUrl carries the workspace.)
- **Query-param pre-fill (VALIDATED live, undocumented by PROCESIO):** the public form
  reads URL query parameters and pre-fills any control whose **binding `name`** equals
  the query key. Open `…/{tinyUrl}?<controlName>=<value>` and the control renders with
  that value. Verified 2026-07-22: a form with controls `name:"cod"` + `name:"apartament"`
  opened at `?cod=TEST123&apartament=27` rendered both inputs pre-filled. The match is on
  the control's config `name` (the field/binding name), NOT the DOM `id`/`name` (which are
  empty on the rendered `<input>`). Use this to seed a form from a link (e.g. a per-record
  token). Unmatched params are ignored.

## How it builds (template-merge)

Each control clones a captured golden element (`dto/form/elements/<type>.json`) so
every config field stays valid; the builder assigns fresh ids, pins a clean
`section`/`parentId` (golden elements were harvested from arbitrary containers),
forces `visible:true`, resets `required`/placeholders, and overrides the semantic
configs. theme/messages/dataModel/variables come from `data_shell.json`.
