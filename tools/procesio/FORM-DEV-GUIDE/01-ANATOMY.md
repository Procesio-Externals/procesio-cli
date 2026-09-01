# 01 — Anatomy of a PROCESIO form

What the DTO contains, what each part is for, and which parts are load-bearing for
runtime behaviour. Read this before you touch a form programmatically; the two
sections that cause the most silent breakage are **value paths** and the **data
model mirror**.

---

## 1. The envelope

```
GET  /api/FormTemplate/{id}     -> camelCase body
PUT  /api/FormTemplate          -> PascalCase envelope, full DTO
POST /api/FormTemplate          -> create (the client supplies the Id)
PATCH /api/FormTemplate/{id}?state=   -> publish/unpublish
```

**The casing flips between the two directions.** The GET returns
`{id, name, isPrivate, type, status, state, assignees, customUrl, data}`; the PUT
wants `{Id, Name, IsPrivate, Type, Status, State, Assignees, CustomUrl, Data}`.
Map explicitly — echoing back an unexpected extra field from the GET is how a PUT
starts failing for reasons nobody can see. The canonical map lives in
`handlers/form_code.py::_PUT_KEYS`.

`Status = 1` (PUBLISHED) + `State = true` publishes. A `CustomUrl` gives the form
its public short link (`forms.<host>/{tinyUrl}`).

## 2. `Data` — the five parts that matter

```
Data = {
  elements   : [ … ],   // the control tree (PLAINTEXT) — this is what renders
  dataModel  : { … },   // a mirror of elements, used for value addressing
  theme      : [ … ],   // ~190 CSS variables in 18 groups, form-wide
  code       : "…",     // AES-encrypted { CSS, JAVASCRIPT }  (see 02 + 07)
  messages   : { … },   // platform copy
}
```

**`elements` alone is enough to render.** Proven live: a form with `code: ""` and
modified elements rendered the modified elements. The encrypted code blob is a
presentation/behaviour layer on top, never a requirement.

## 3. `elements` — a FLAT list with `parentId`

PROCESIO does **not** nest children inside a parent element. Every control is a
top-level entry in one flat array and points at its parent:

```json
{
  "id": "<guid>",
  "type": "input",
  "parentId": "<guid of the column/step/section>",
  "section": "header" | "body" | "footer",
  "configs": [ {"id": "<guid>", "key": "label", "value": "CNP"}, … ]
}
```

- **`section`** decides where in the shell it renders. `heading` defaults to
  `header`, `button` to `footer`, everything else to `body`.
- **`type`** must be one of the known control types. The full list is the file
  names in `dto/form/elements/*.json`:

  `approval, assignee, button, chart, chat, checkbox, column, columns,
  datetime-input, divider, dropdown, dynamic-table-row, file-upload, file-viewer,
  heading, icon, image, input, list, number-input, paragraph, radiobox, section,
  select, side-panel, signature-pad, static-table-row, step, stepper, tab, table,
  tabs, textarea`

  Each of those `.json` files is a **captured golden**: a real element of that type
  with every config present and valid. Building a new element = clone the golden,
  assign fresh ids, override the semantic configs. Never hand-author an element
  from scratch — you will omit a config the renderer silently depends on.

### Layout containers

`columns` → `column` → controls. A `stepper` contains `step` elements; each `step`
contains the controls of that step. `section`, `tabs`/`tab`, `table` +
`static-table-row`/`dynamic-table-row` follow the same parent/child pattern.

## 4. `configs` — where all the meaning lives

A config is `{id, key, value}` (some carry `category`). The keys you will actually
set:

| Group | Keys |
|---|---|
| identity | `name`, `id`, `label`, `placeholder`, `tooltip`, `info-text` |
| behaviour | `required`, `readonly`, `visible`, `regex`, `defaultValue`, `min`, `max` |
| control-specific | `rows`, `mode`, `multiple`, `searchable`, `clearable`, `hasNow`, `maxFileSize`, `canAdd`, `canRemove`, `addText`, `variation`, `outlined` |
| options | `sourceType` (`static-list` \| `JSON` \| `URL`) + `sourceValue` |
| media/link | `src`, `url`, `alt`, `title`, `width`, `height`, `linkUrl` |
| submit | `submit`, `disabledIfFormIsInvalid` |
| tasks | `assignee`, `assigneeReplacement`, `approver`, `approverReplacement` |
| **value** | `value` — the live field value (see §5) |
| **styling** | `style` — a `CSSProperty[]`, per-element CSS variables |
| **events** | `on…Events` — see §6 |

### The `style` config (per-element styling)

`{key: "style", category: "styling", value: CSSProperty[]}` where each property is
`{label, value, cssVariable, type, enabled}`. The runtime applies **only**
`enabled: true` entries.

- Valid variables for a type = that type's CSS group in the theme (the first theme
  group whose `types` include the element type — so input / number / datetime /
  textarea / select all share the **Input** group).
- For `type == "css-variable-select"` (colours) pass a **theme variable**
  (`--c-neutral--50`), not a hex: the runtime emits `var(<value>)`. Plain variables
  (heights, paddings) take raw values.
- Non-stylable types (heading, paragraph, divider, image…) have no style group.

### `visible` is NOT a hide

`Element.component.vue` renders under `v-if`. Setting `visible: false` **removes
the node from the DOM** — it is not hidden, it is destroyed. Consequences run
through this whole guide: entrance animations re-fire on every step change (good),
exit transitions are impossible (the node is already gone), and any state you
attach to a node must be recomputed rather than remembered.

## 5. The data model mirror, and value paths

Every control is backed by a data-model attribute. The structure is three levels:

```
root "form"        id = formId
└── "fields"       id = 11223344-5566-7788-99aa-aabbccddeeff   (CONSTANT across all forms)
    └── <element>  id = elementId
        └── attrs  one per config, INCLUDING `value`
```

A process addresses a form field by the full path:

```
{dmRootId}.{FIELDS_NS}.{elementId}.{valueConfigId}
```

**Two id rules that are not optional**, both verified against real production
forms:

1. The value segment must be the element's **own `value` config id** — not a fresh
   guid. With a fresh id the process-designer's "Form variable" selector shows
   `Unknown`.
2. Every data-model attribute id must equal the element's **config id for that
   key**. Measured on a real form: 15/16 attributes resolved with reused ids,
   0/16 with fresh ones.

Get this wrong and nothing errors — the designer just renders raw guids and values
never flow.

## 6. Events on an element

Each trigger has its own config key whose value is `{debounce, events: [...]}`:

```json
{"key": "onInputEvents",
 "value": {"debounce": 0,
           "events": [{"id": "<guid>", "type": "INPUT",
                       "action": "RUN_PROCESS", "config": { … }}]}}
```

**A fresh element carries the key with a `null` value.** That is what "no handler"
looks like — it is not an error and not a missing field.

### Trigger → config key → event type

| `on` | config key | `type` |
|---|---|---|
| click | `onClickEvents` | `CLICK` |
| input / change | `onInputEvents` | `INPUT` |
| focus / blur / hover | `onFocusEvents` / `onBlurEvents` / `onHoverEvents` | `FOCUS` / `BLUR` / `HOVER` |
| ready | `onReadyEvents` | `READY` |
| open / close | `onOpenEvents` / `onCloseEvents` | `SIDE_PANEL_OPEN` / `SIDE_PANEL_CLOSE` |
| tabchange | `onTabChangeEvents` | `TAB_CHANGE` |
| rowadded / rowdeleted | `onTableRowAddedEvents` / `onTableRowDeletedEvents` | `TABLE_ROW_ADDED` / `TABLE_ROW_DELETED` |
| paginated | `onPaginationChangedEvents` | `TABLE_PAGINATED` |
| stepchange | `onStepChangeEvents` | `STEPPER_STEP_CHANGE` |
| nextstep / previousstep | `onNextStepEvents` / `onPreviousStepEvents` | `STEPPER_NEXT_STEP` / `STEPPER_PREVIOUS_STEP` |
| beforeapprove / afterapprove | `onBeforeApproveEvents` / `onAfterApproveEvents` | `BEFORE_APPROVE` / `AFTER_APPROVE` |
| beforereject / afterreject | `onBeforeRejectEvents` / `onAfterRejectEvents` | `BEFORE_REJECT` / `AFTER_REJECT` |
| beforeapprovalsubmit / afterapprovalsubmit | `onBeforeApprovalSubmitEvents` / `onAfterApprovalSubmitEvents` | `BEFORE_APPROVE_OR_REJECT` / `AFTER_APPROVE_OR_REJECT` |
| messagesfetch / messagesent | `onMessagesFetchEvents` / `onMessageSentEvents` | `CHAT_MESSAGES_FETCH` / `CHAT_MESSAGE_SENT` |

Source of truth: `dto/form/builder.py::_EVENT_KEY` / `_EVENT_TYPE`, verified against
the renderer's `trigger.ts` `TriggerKey` enum and `FieldEvents.component.vue`.
**Never re-derive this table in new code** — import the builder's maps, as
`handlers/form_events.py` does. A wrong event type is silently accepted by the API
and simply never fires.

### Event actions

| `action` | config |
|---|---|
| `RUN_JAVASCRIPT` | `{code: "<js source, plaintext>"}` |
| `RUN_PROCESS` | `{processId, inputMap[], outputMap[], syncRun}` — see [06](06-PROCESS-INTEGRATION.md) |
| `MAP_FORM_DATA` | `{mapping: [{id, left, right}]}` |
| `TRIGGER_FORM` | `{formId, mapping: [...]}` |

## 7. Where the four styling surfaces live

| Surface | Scope | Where |
|---|---|---|
| Theme | whole form, by control type | `Data.theme` — ~190 CSS variables |
| Per-element style | one control | that element's `style` config |
| Element event JS | one control, one trigger | that element's `on…Events` config (**plaintext**) |
| Form-level CSS + JS | whole form | `Data.code` (**encrypted**) |

The last one is where all serious work happens; the rest of this guide is about it.
