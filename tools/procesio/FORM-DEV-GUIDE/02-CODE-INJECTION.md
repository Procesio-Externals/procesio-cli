# 02 — How form-level CSS and JavaScript actually run

**This is the prerequisite for everything else.** The execution model is not what
it looks like from the designer, and code written on the wrong assumption appears
to work on first load and then quietly stops.

---

## 1. Where the code lives

`Data.code` is the designer's "Switch to code" editor. It holds one object:

```json
{"JAVASCRIPT": "…", "CSS": "…"}
```

stored **AES-encrypted**: CryptoJS `AES.encrypt(text, passphrase)` — i.e. OpenSSL
AES-256-CBC, key + IV derived by `EVP_BytesToKey(MD5, 1 iteration)`, serialized as
`base64("Salted__" + salt + ciphertext)`. The passphrase is a **static key, one per
installation**, stored in the OS credential store per environment
(`agents-and-tools:procesio:form-code-key@<environment>`, see
[07](07-DEPLOY-WORKFLOW.md) §3) and never in a file.

There is **no plaintext CSS/JS field on the DTO**. The frontend holds `code` as a
plaintext `{JAVASCRIPT, CSS}` object in memory; the host webapp does the AES step.
Confirmed with the platform team: no unencrypted path exists.

**`{"JAVASCRIPT": null, "CSS": null}` is a normal decrypt result**, not a corrupt
blob — it is the designer's initial state, so every form that never opened "Switch
to code" carries it. Normalize `null → ""` before doing anything involving a length
or a concatenation.

## 2. The CSS - injected as a `<style>`, SCOPED to the form (changed in v3.0.0, 2026-10)

The renderer prepends a `<style>` element inside the form root, and since prod
user-playground v1.115.0 (ui-builder 0.185.0) it **scopes** the CSS first: every
selector is rewritten to `sel:where([data-form-css-scope=<id>], ...)`, so a rule
matches only the form root and what is inside it. The earlier rule here (a style
element is document-scoped, so page-level selectors work) is no longer true.

What no longer matches:

- rules for `body`, `html`, `:root`, the host page's chrome and the builder;
- `:root` custom properties, which therefore no longer reach the form. Declare them
  on a selector for an element inside the form instead;
- tooltips and date-picker popups, which no longer get the form CSS.

What changes on the way in:

- comments and CSS the scoper cannot parse are dropped, with no error, so when a
  rule seems to do nothing, check that it survived;
- `@keyframes` and `@font-face` are moved into a layer.

What is still global:

- a `<style>` inside a paragraph's or heading's HTML;
- `@import`;
- JS that injects a `<style>` into `window.parent.document` (the runtime pattern in
  §4 can do this when a rule genuinely has to reach the page).

How the rewrite works (verified live): the **last compound** of every selector gets
`:where([data-form-css-scope="<formId>"], [data-form-css-scope="<formId>"] *)` appended.
So `.card {}` becomes `.card:where(...)`, `#app *` becomes `#app :where(...)`, `:root {}`
becomes `:root:where(...)` and `html, body {}` becomes `html:where(...), body:where(...)`.
`@keyframes`, `@import` and `@media` wrappers survive, and the rules inside `@media` are
rewritten the same way. The attribute sits on the form-builder elements
(`.form-builder-view--content` and `.form-builder--form`).

**What breaks: UI the JS renders OUTSIDE the form container.** A full-page app, a modal
or an overlay appended to `document.body` gets no styles at all, and `:root` variables and
`html` / `body` rules stop applying, because `<html>` and `<body>` are not inside the
scope. A form whose UI stays inside the form container is not affected.

**The fix (verified live on full-page forms):** before mounting, copy the scope id from
the form container onto `<html>`. Then `:root:where([attr])` matches and every element on
the page matches `[attr] *`:

```js
var host = document.querySelector('[data-form-css-scope]');
if (host && !document.documentElement.hasAttribute('data-form-css-scope'))
  document.documentElement.setAttribute('data-form-css-scope',
                                        host.getAttribute('data-form-css-scope'));
```

Run it inside the same "wait until the form's elements exist" loop the code already
uses: the attribute only appears once the form has rendered. Setting the attribute only
on your own mounted root is NOT enough when the CSS uses `:root` variables or `html` /
`body` rules. `form-set-code` warns when the JS mounts on `document.body`, or the CSS
styles `:root` / `html` / `body`, without propagating the attribute.

The scoping broke forms that mount UI outside the container when it shipped, and a revert
was under discussion at the time of writing (2026-10-21). The fix above is harmless if the
scoping is reverted, so apply it regardless; drop the lint only once a revert is in prod.

The branding class is also filtered: `js/form-builder/css.ts` replaces that
literal class string with a random number so it cannot be hidden.

## 3. The JavaScript — the part that surprises everyone

> Form-level JS is replayed by the renderer as a **synthetic `RUN_JAVASCRIPT`
> event**, on mount **and on every re-trigger**, inside a **throwaway sandbox
> iframe whose window is destroyed and rebuilt each time.**

Three consequences, and every one of them has bitten:

1. **Nothing survives the run.** Listeners, `MutationObserver`s, timers, module
   state — all die with the iframe. Code that "worked once and then stopped" is
   almost always this.
2. **It runs more than once.** Every re-trigger executes the whole file again.
   Un-guarded code installs a second copy of every handler; symptoms are doubled
   toasts, doubled ripples, doubled process launches.
3. **The sandbox is not the page.** `document` inside the sandbox is the iframe's
   own. The real form is in `window.parent.document` — the platform confirms this
   itself: the JS slot's shipped boilerplate reads
   `console.log(window.parent.document); -> to access the DOM`.

**Sandbox lifetime (v3.0.0, 2026-10).** At most **5** form-fill sandboxes are live at
once; one is destroyed after **60 s** with no messages; and a run counts as finished
after a **100 ms** quiet period. So work a run starts and leaves pending (a
`setTimeout`, a slow `await`) may outlive the run's own lifetime and be lost with
its sandbox. Finish the run's work promptly, and put anything long-lived in the
parent-page runtime of §4.

## 4. The pattern that works: installer + runtime

Write **two layers**. The file itself is only an *installer*; the real code is a
function that gets injected once into the parent document, where it keeps its own
scope and lives as long as the page does.

```js
function UX_RUNTIME() {
  if (window.__uxFormRuntime) { return; }   // guard #2: the payload
  window.__uxFormRuntime = true;

  /* …everything: listeners, MutationObserver, timers, state… */
}

/* -- installer: put the runtime in the parent page, exactly once ------------ */
(function () {
  try {
    var W = window.parent && window.parent !== window ? window.parent : window;
    var D = W.document;
    if (!D || !D.body || D.getElementById('ux-runtime')) { return; }   // guard #1
    var s = D.createElement('script');
    s.id = 'ux-runtime';
    s.textContent = '(' + UX_RUNTIME.toString() + ')();';
    D.body.appendChild(s);
  } catch (e) {
    // Cross-origin parent, or no parent at all: nothing to install, and the CSS
    // layer still stands on its own.
  }
})();
```

Why each piece is exactly this way:

- **`fn.toString()`** carries the source across the boundary with no escaping
  problems. Do not build the payload as a string literal — you will fight quoting
  forever and every edit risks a syntax error you cannot see until runtime.
- **Two guards, not one.** The DOM id guard stops a second `<script>` from being
  appended; the `window.__uxFormRuntime` flag stops a second *execution* if the
  script somehow runs again. They protect different failures.
- **`window.parent !== window`** — the same file must also work when it is not
  framed (a preview, a local replica). Falling back to `window` keeps one code
  path for both.
- **The `try/catch` is deliberate.** A cross-origin parent throws on `.document`.
  There is nothing to do about it and nothing to report: the CSS layer still
  works, so the form degrades rather than breaking.

### The runtime is closure-scoped — that is the point

Because the payload runs as one IIFE in the parent document, everything it declares
is private to it. Expose only what other code genuinely needs, on `window`:

```js
window.UXToast = function (message, kind) { … };   // callable from element-event JS
```

## 5. Idempotency is a property of every function you write, not just the installer

The runtime installs once, but **inside** it you are reacting to a DOM that the
renderer rebuilds constantly. Every function that touches the DOM must be safe to
run a hundred times. The discipline is: **mark what you have already done, on the
node.**

```js
function addHint(el) {
  if (q('.ux-hint', el)) { return; }        // already has one
  …
}

function decorateNav() {
  all('.pds-c-button', box).forEach(function (btn) {
    if (btn.getAttribute('data-ux-nav')) { return; }   // already swapped
    …
    btn.setAttribute('data-ux-nav', kind);
  });
}
```

A `data-*` attribute or the presence of your own injected child is the marker. Do
**not** keep a `Set` of nodes you have processed: the renderer destroys and
recreates nodes, so your set fills with corpses while the fresh nodes go
unprocessed.

## 6. The recompute loop

Because controls are recreated rather than hidden, there is no useful "on change"
event for structure. The working model is: **one idempotent `refresh()` that
recomputes everything from the current DOM, scheduled on a frame, driven by a
MutationObserver plus the interaction events.**

```js
var pending = false;

function refresh() {
  pending = false;
  /* recompute EVERYTHING from scratch: step position, gating, hints,
     validation, decorations. No incremental state. */
}

function schedule() {
  if (pending) { return; }        // coalesce a burst of mutations into one pass
  pending = true;
  raf(refresh);
}

['input', 'change', 'click'].forEach(function (t) {
  D.addEventListener(t, schedule, true);       // capture: nothing can stop it
});

var mo = new MutationObserver(function () { schedule(); });

(function start() {
  var host = q('.form-builder--form-body') || D.body;
  if (!host) { return setTimeout(start, 120); }   // the runtime may beat the render
  mo.observe(host, { childList: true, subtree: true, characterData: true });
  schedule();
})();
```

Points that matter:

- **`raf` + a `pending` flag** collapse a storm of mutations into a single pass. A
  step change fires dozens of mutations; without coalescing you run `refresh()`
  dozens of times per frame.
- **Capture-phase listeners** (`true`) cannot be blocked by a control that stops
  propagation.
- **The retry loop in `start()`** exists because the runtime can be installed
  before the form body exists.
- **`refresh()` is total, not incremental.** It never asks "what changed" — it
  recomputes the whole visible state. This is the only model that survives nodes
  being destroyed underneath you.

## 7. Reaching the platform's own model

`window.ProcesioForm` exists at runtime and exposes `.data.fields` — a map of field
state. It is reachable and occasionally the only way to do something (clearing a
radio group, for instance, since a radio cannot be un-clicked).

Treat it as a **last resort, not an API**: it is internal, undocumented, and can
change. Guard every access:

```js
var PF = window.ProcesioForm;
if (PF && PF.data && PF.data.fields) { … }
```

**Prefer clicking the real control.** The renderer is Vue-bound: setting
`input.checked` or `input.value` behind its back styles the control without ever
updating the form's value, so the field looks filled and submits empty. See
[04-INTERACTION-RECIPES.md](04-INTERACTION-RECIPES.md) §2.

## 8. Two-layer split: what goes in CSS, what goes in JS

| Put it in CSS | Put it in JS |
|---|---|
| every animation and transition | deciding *when* a class applies |
| every visual state (`.is-on`, `.ux-gated`, `.ux-invalid`) | adding and removing those classes |
| responsive rules, reduced-motion | reading values, validating, mapping |
| anything that must work if the JS fails | anything requiring knowledge of state |

The rule: **JS only ever toggles classes; CSS decides what a class looks like.**
This keeps the form presentable if the runtime fails to install (cross-origin
parent, script error) and makes every visual change reviewable in one file.
