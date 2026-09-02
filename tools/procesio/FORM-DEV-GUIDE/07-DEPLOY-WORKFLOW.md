# 07 — Shipping it: tooling, testing, recovery

How the CSS and JS get onto a live form without destroying it, how to test before
you publish, and how to get back when you do not.

---

## 1. Never use `form-edit` to restyle an existing form

`form-edit` is a **desired-state** editor: it rebuilds the whole DTO from a config.
Pointing it at a large hand-authored form to change one thing means re-declaring
every element — or losing them. On a form with a hundred-plus hand-built elements,
that is the end of the form.

Use the **surgical** actions. Each does a read-modify-write on the live DTO and
touches exactly one thing:

| Action | Touches | Everything else |
|---|---|---|
| `form-get-code` | nothing (read) | — |
| `form-set-code` | `Data.code` only | elements, theme, data model, events byte-identical |
| `form-get-element-events` | nothing (read) | — |
| `form-set-element-event` | one element's one event config | every sibling byte-identical |
| `form-get-element` | nothing (read) | — |
| `form-set-element-config` | one element's plain configs | every sibling byte-identical |

Every write path maps the GET's camelCase onto the PUT's PascalCase envelope
explicitly, so an unexpected extra field is never echoed back.

### `form-set-element-config` — content and per-field rules belong in the DTO

`label`, `placeholder`, `required`, `regex`, `visible`, `tooltip`, `defaultValue`.
Rewriting a banner from the form-level JS instead is a trap worth naming: it is
invisible in the designer, it has to be re-applied on every render, and it fights the
runtime's own MutationObserver.

```bash
# long HTML from a file, so the copy lives under version control
python scripts/run-tool.py procesio form-set-element-config \
  --id <form-id> --element idhead --set-file label=elements/idhead.html --dry-run

# scalars are parsed as JSON when they parse, so this stores a real boolean
python scripts/run-tool.py procesio form-set-element-config \
  --id <form-id> --element intro1 --set visible=false
```

Two refusals it makes on purpose, both before writing anything:

- **a config the element does not already carry.** Adding one would also need a
  data-model attribute whose id equals the new config's id; without it the designer
  renders raw guids and values never flow ([01](01-ANATOMY.md) §5).
- **an event config.** Those go through `form-set-element-event`, which resolves
  process-variable names to guids and enforces one event per trigger.

Config **ids are preserved** on every rewrite — a fresh id there breaks every value
path pointing at that attribute.

## 2. The loop

```bash
# 1. Pull the current code down to files
python scripts/run-tool.py procesio form-get-code --id <form-id> \
  --css-out form.css --js-out form.js

# 2. Edit form.css / form.js locally, in a real editor, under version control

# 3. Preview the write without performing it
python scripts/run-tool.py procesio form-set-code --id <form-id> \
  --css-file form.css --js-file form.js --dry-run

# 4. Ship
python scripts/run-tool.py procesio form-set-code --id <form-id> \
  --css-file form.css --js-file form.js
```

Success looks like:

```json
{"updated": true, "css_bytes": 24157, "javascript_bytes": 28793, "elements": 135}
```

**Check `elements` on every write.** It is the count on the DTO you just PUT back.
If it ever drops, you are not doing what you think you are doing — stop.

### Omitting one side preserves it

Passing only `--css-file` keeps the existing JavaScript untouched, and vice versa.
Restyling never silently drops the behaviour layer.

### Every overwrite is recoverable from the tool output

`form-set-code` returns the **previous** decrypted css/js under `previous`. Pipe the
output to a file when you are doing something risky, and a mistaken overwrite is a
copy-paste away from being undone:

```bash
python scripts/run-tool.py procesio form-set-code --id <form-id> \
  --js-file form.js > /tmp/last-write.json
```

## 3. Credentials

Two different secrets that look alike — both short opaque tokens:

| Secret | What it does |
|---|---|
| the workspace **API key** (name + value) | gets you **at** the form (auth) |
| `agents-and-tools:procesio:form-code-key` | gets you **into** `Data.code` (AES passphrase) |

```bash
python scripts/set-credential.py procesio form-code-key
```

The form-code passphrase is **platform-wide**: it decrypts the code blob of every
form on the platform, and it cannot be cheaply rotated. Treat it accordingly — never
in a file, never in a chat, never in a log.

### Diagnosing a decrypt failure

A wrong passphrase and a corrupt blob are indistinguishable at the API layer: both
surface as a `UnicodeDecodeError` after AES has run and emitted garbage. To tell
them apart, round-trip `encrypt_code` / `decrypt_code` with a throwaway key. If that
works, the cipher is fine and the **key** is wrong.

## 4. Test on a replica, not on the live form

The most expensive mistake available here is publishing straight to a live process
or a live public form. Two levels of testing, and both are cheap:

**A local HTML replica.** Save a rendered copy of the form, inline your CSS and JS,
and open it in a browser. Because the installer falls back to `window` when there is
no parent frame ([02](02-CODE-INJECTION.md) §4), the same file runs unchanged. This
catches the majority of DOM and timing bugs, and it lets you *measure* a transition
instead of guessing:

**Replicate the whole flow, not one screen.** A single-step mock cannot exercise the
two things most likely to break — the step gate and whatever bridges the DOM to the
platform's field model — so those are exactly what nothing tests. A replica worth
building carries: a fake `window.ProcesioForm.data.fields` with the DTO's own names,
`required` flags and regexes; the form's own element-event visibility logic; the REAL
`data-element-id` values; and a step change that **destroys and rebuilds** the controls
(`box.innerHTML = …`), because that is what makes "state stored on a node" fail here
the same way it fails live. Give it a harness row of buttons for the states that are
otherwise unreachable (pick each branch, simulate the process result landing, fill the
current step) and a `?raf=timeout` switch so it can be driven in a background tab.

```js
// in the page console — prove the class actually lifts
setTimeout(() => console.log('at120',
  box.classList.contains('ux-leaving'), getComputedStyle(box).opacity), 120);
setTimeout(() => console.log('at600',
  box.classList.contains('ux-leaving'), getComputedStyle(box).opacity), 600);
```

Run the same navigation **twice** and confirm nothing accumulates — a second copy of
a listener, a class that never clears, a growing node count.

**A duplicated process**, for anything on the process side. `procesio` can duplicate
a process; change the copy, run the copy, and promote the change only once it works.
Editing a live process that a public form is calling means every submission in
flight is your test.

**State plainly what you verified.** "Verified on the local replica" and "verified on
the live form" are different claims. Do not let one stand in for the other.

## 5. Keep the source under version control — outside the framework

The CSS and JS are the form's real source. `Data.code` is a deployment target, not a
repository: it is encrypted, it has no history, and it cannot be diffed.

Keep the files in the user-data area (`context-state-knowledge/resources/...`), not
in `tools/` — a specific client's form is user data, and the framework/user-data
boundary is hard. What belongs in the framework is the **generalized** knowledge:
this guide.

Alongside the CSS and JS, keep the process artifacts that are equally
un-round-trippable — prompts, request bodies, the process definition — so a rebuild
does not start from a screenshot.

## 6. Write the reasoning into the file, at the top

Both files should open with a header stating **how the thing runs** and **which rules
must never be broken**, with the symptom attached. This is not decoration: `Data.code`
carries no history and the next person to open it — including you, in three months —
has no other way to know.

```css
/* Two rules this file must never break, both learned on the live form:
   - NO `overflow: hidden` on `.form-builder--form` — it kills page scrolling.
   - NO `transform` on `.form-builder--form` — it makes the card the containing
     block for `position: fixed` descendants, so the renderer's pinned footer
     lands on top of the content. Entrances animate opacity only. */
```

The test for a good comment here: it names the **symptom** a future reader would
otherwise chase, not just the rule.

## 7. Before you touch a shared form

- Confirm the form id and the workspace, out loud, before the first write.
- `form-get-code` first, always — even when you are sure the form has no code. The
  output *is* your backup.
- One change per write when debugging. Two changes in one write means a regression
  has two suspects.
- After any change to a manifest or a contract, update the manifest in the same
  commit (Hard rule 4) and re-run the tool's tests before publishing.
