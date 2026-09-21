# 04 — Interaction recipes

Working patterns for the things a professional form actually needs: reading and
writing values, hiding controls, gating navigation, turning static markup into a
control, per-field validation, localized messages, feedback. Every snippet here
runs **inside the runtime payload** described in
[02-CODE-INJECTION.md](02-CODE-INJECTION.md) and assumes its helpers:

```js
var D = document;
function q(s, r) { return (r || D).querySelector(s); }
function all(s, r) { return Array.prototype.slice.call((r || D).querySelectorAll(s)); }
```

---

## 1. Read a field's value

```js
function isFilled(el) {
  if (q('input[type=checkbox], input[type=radio]', el)) {
    return !!q('input:checked', el);
  }
  var f = q('input, textarea, select', el);
  return !!(f && String(f.value || '').trim());
}
```

Checkboxes and radios are checked-state, everything else is `.value`. Always
`.trim()` — a space is not a value.

## 2. Write a value: **click the control, never set the property**

The renderer is Vue-bound. Setting `input.checked = true` or `input.value = 'x'`
behind Vue's back changes what the user sees and **does not update the form's
value** — the field looks filled and submits empty. Click the real control:

```js
function radioFor(kind) {
  var hit = null;
  all('.form-builder--radiobox label').forEach(function (l) {
    if (hit) { return; }
    if (norm(l.textContent).trim() === kind) { hit = l; }
  });
  return hit;
}

var label = radioFor('individual');
if (label) { label.click(); }         // Vue sees this and updates the model
```

For text inputs, if you genuinely must write programmatically, set the value **and**
dispatch the events Vue listens for:

```js
function setText(el, value) {
  var f = q('input, textarea', el);
  if (!f) { return; }
  f.value = value;
  f.dispatchEvent(new Event('input',  { bubbles: true }));
  f.dispatchEvent(new Event('change', { bubbles: true }));
}
```

Prefer to avoid this entirely. If values come from a process, let the event's
`outputMap` write them natively — see [06](06-PROCESS-INTEGRATION.md).

### Clearing a radio group

A radio cannot be un-clicked. Clear the model where it is reachable, then the DOM:

```js
function clearChoice() {
  var PF = window.ProcesioForm;
  if (PF && PF.data && PF.data.fields) {
    var f = PF.data.fields;
    for (var k in f) {
      if (norm(k).indexOf('clienttype') > -1 && f[k]) { f[k].value = ''; }
    }
  }
  CHOICES.forEach(function (c) {
    var l = radioFor(c), i = l && q('input', l);
    if (i && i.checked) { i.checked = false; }
    var dot = l && q('.pds-c-radiobox', l);
    if (dot) { dot.classList.remove('pds-c-radiobox--is-checked'); }
  });
}
```

**Do not re-dispatch `change` here.** On a Vue-bound group that handler reads the
option's value and would simply re-select what you just cleared.

## 3. Hide a control — one class, `display: none`

```css
.ux-gated { display: none !important; }
```

```js
el.classList.toggle('ux-gated', shouldHide);
```

**`display: none`, not `visibility` or `opacity`.** A control you can still reach
with Tab but cannot see is a worse bug than a visible one — it traps keyboard users
in an invisible field. Hide the **whole element wrapper**
(`b.closest('.form-builder--element')`), not just the inner button, so no empty row
is left behind.

## 4. Gate a navigation button on a condition

Hide the button's host rather than disabling it — a disabled control invites
clicking; an absent one reads as "not yet".

```js
function gateNext(ready) {
  var next = q('.ux-nav--next');
  if (!next) { return; }
  var host = next.closest('.form-builder--stepper--buttons--next') || next;
  host.classList.toggle('ux-gated', !ready);
}
```

The `|| next` fallback matters: the host wrapper is not guaranteed to exist in
every renderer version, and falling back to the button itself keeps the behaviour
correct rather than silently doing nothing.

### Gate the form's own tail buttons on the phase

Buttons that belong to a later view (a generated contract, a confirmation screen)
are often visible on a fresh load because the form's own logic only hides them
inside a click handler that has never run. Gate them on an observable phase:

```js
function gateTail() {
  var filling = !!q('.form-builder--stepper');   // stepper on screen = still filling in
  tailButtons().forEach(function (b) {
    var host = b.closest('.form-builder--element') || b;
    host.classList.toggle('ux-gated', filling);
  });
}
```

## 5. Turn static markup into a control (description cards as a selector)

The pattern: the radio group is the *real* control but carries no explanation; the
descriptive cards carry everything and are what people aim at. Make the cards
clickable, hide the radio group, keep the radio as the source of truth.

```js
function wireChoiceCards() {
  choiceCards().forEach(function (card) {
    var kind = choiceKind(card.textContent);

    if (!card.getAttribute('data-ux-choice')) {        // idempotent: wire once
      card.setAttribute('data-ux-choice', kind);
      card.setAttribute('role', 'button');             // it is a control now —
      card.setAttribute('tabindex', '0');              // say so, and be reachable
      card.classList.add('ux-choice');

      var pick = function (e) {
        e.preventDefault();
        if (radioChecked(kind)) { clearChoice(); }     // 2nd click deselects
        else { var l = radioFor(kind); if (l) { l.click(); } }
        schedule();
      };
      card.addEventListener('click', pick);
      card.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { pick(e); }
      });
    }

    var on = radioChecked(kind);                       // state read from the RADIO
    card.classList.toggle('ux-choice--on', on);
    card.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}
```

Then hide the raw group: `radioHost.classList.add('ux-gated')`.

**The state is always read back from the real control**, never remembered on the
card. That is what keeps the two in sync when the renderer rebuilds the step.

Locating the cards without ids — match on content, and require a discriminator that
separates the descriptive card from the radio label itself:

```js
function choiceCards() {
  return all('.form-builder--column .form-builder--element').filter(function (el) {
    if (q('.form-builder--element', el)) { return false; }     // leaves only
    var t = norm(el.textContent);
    return !!choiceKind(t) && t.indexOf('i am requesting a contract') > -1;
  });
}
```

## 6. Replace button text with an icon

```js
var ARROW = {
  next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" ' +
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
        '<path d="M5 12h14"/><path d="M12 5l7 7-7 7"/></svg>'
};

function decorateNav() {
  var box = q('.form-builder--stepper--buttons');
  if (!box) { return; }
  all('.pds-c-button', box).forEach(function (btn) {
    if (btn.getAttribute('data-ux-nav')) { return; }              // already swapped
    var label = norm(btn.textContent);
    var isPrev = label.indexOf('back') > -1 || btn.classList.contains('pds-c-button--small');
    var isNext = label.indexOf('continue') > -1 ||
                 btn.classList.contains('pds-c-button--solid-primary');
    if (!isPrev && !isNext) { return; }
    var kind = isPrev && !isNext ? 'prev' : 'next';
    var name = kind === 'prev' ? 'Back to the previous step' : 'Continue to the next step';
    btn.setAttribute('data-ux-nav', kind);
    btn.classList.add('ux-nav', 'ux-nav--' + kind);
    btn.setAttribute('title', name);
    btn.setAttribute('aria-label', name);       // the glyph alone is not a name
    btn.innerHTML = ARROW[kind];
  });
}
```

**Identify by text AND by variant class.** Text alone breaks when the form is
retitled or translated; the class alone breaks when two buttons share a variant.
Requiring either, and disambiguating when both match, survives both.

**`aria-label` is not optional here.** Replacing the only text with a glyph removes
the button's accessible name; without the label a screen reader announces "button".

## 7. Per-field validation with your own rules

The platform validates required/format at its level. Add rules that read as
*guidance*, in a different colour from the platform's own error so the two never
compete:

```js
var RULES = {
  cnp:     [/^\d{13}$/,        'The personal number has exactly 13 digits.'],
  ciserie: [/^[A-Za-z]{2}$/,   'The series is exactly 2 letters.'],
  cui:     [/^(RO)?\d{2,10}$/i,'The tax code has 2 to 10 digits, with or without RO.'],
};

function validate(el, key) {
  var rule = RULES[key];
  var f = q('input, textarea', el);
  var v = String((f && f.value) || '').trim();
  var bad = !!(rule && v && !rule[0].test(v));    // empty is NOT invalid — that's "required"
  el.classList.toggle('ux-invalid', bad);

  var msg = q('.ux-rule', el);
  if (bad && !msg) {
    msg = D.createElement('small');
    msg.className = 'ux-rule';
    msg.textContent = rule[1];
    el.appendChild(msg);
  } else if (!bad && msg) {
    msg.parentNode.removeChild(msg);
  }
  return !bad && !!v;                              // "ok" = present AND well-formed
}
```

An empty value is a *required* problem, not a *format* problem — flagging it as
malformed while the user is still typing is hostile. Note the create/remove pair:
the function is idempotent, so it can run on every keystroke.

```css
.ux-invalid .pds-c-input-group--wrapper {
  border-color: #C77700 !important;
  box-shadow: inset 3px 0 0 #C77700 !important;    /* amber: present but malformed */
}
```

## 8. Localize the platform's validation copy

The control library emits English. Rewrite the messages in place:

```js
var MSG = [
  [/^\s*this field is required\.?\s*$/i, 'Acest câmp este obligatoriu.'],
  [/^\s*invalid email\.?\s*$/i,          'Adresă de e-mail invalidă.'],
  [/^\s*this field is invalid\.?\s*$/i,  'Valoare invalidă.'],
];

function localize() {
  all('.pds-c-input-group--message--is-error, [class*="message"][class*="error"]')
    .forEach(function (n) {
      var t = n.textContent;
      for (var i = 0; i < MSG.length; i++) {
        if (MSG[i][0].test(t)) { n.textContent = MSG[i][1]; return; }
      }
    });
}
```

**Anchored regexes** (`^…$`), so a message that merely *contains* the English
phrase is not mangled. Rewriting `textContent` (not `innerHTML`) keeps it safe.
This runs inside `refresh()`, so a message re-rendered by the platform is
re-localized on the next pass.

## 9. Per-field helper text

```js
var HINTS = [
  ['personal number', 'Exactly <b>13 digits</b>, as printed on the ID document.'],
  ['e-mail',          'You will receive the <b>confirmation</b> here.'],
];

function addHint(el) {
  if (q('.ux-hint', el)) { return; }              // idempotent
  var lbl = q('.pds-c-input-group--label', el);
  var text = hintFor(lbl ? lbl.textContent : el.textContent);
  if (!text) { return; }
  var s = D.createElement('small');
  s.className = 'ux-hint';
  s.innerHTML = text;                              // your own literals — safe
  el.appendChild(s);
}
```

`innerHTML` is acceptable **only** because the string is your own literal. Never
build one from a field value or a process result.

## 10. Completion feedback

```js
fields().forEach(function (el) { el.classList.toggle('ux-filled', isFilled(el)); });
```

```css
.form-builder--element.ux-filled
  .pds-c-input-group--wrapper:not(.pds-c-input-group--wrapper--is-error) {
  border-color: rgba(64, 153, 32, .45);
  box-shadow: inset 3px 0 0 rgba(64, 153, 32, .5);   /* INSET: cannot overhang a column */
}
```

Use an **inset** shadow. An outer glow overhangs the column boundary and collides
with the neighbouring field on a two-column layout.

## 11. A toast the rest of the form can call

```js
window.UXToast = function (message, kind) {
  var t = D.createElement('div');
  t.className = 'ux-toast' + (kind ? ' ux-toast--' + kind : '');
  t.textContent = message;
  D.body.appendChild(t);
  raf(function () { t.classList.add('ux-toast--in'); });     // next frame: transition runs
  setTimeout(function () {
    t.classList.remove('ux-toast--in');
    setTimeout(function () { if (t.parentNode) { t.parentNode.removeChild(t); } }, 400);
  }, 4200);
};
```

The `raf` before adding the class is what makes the entrance animate: a class set
in the same frame as the insertion produces no transition. Exposing it on `window`
lets per-element event JS ([01](01-ANATOMY.md) §6) call it too.

## 12. Ripple on any button

```js
D.addEventListener('pointerdown', function (e) {
  var btn = e.target && e.target.closest && e.target.closest('.pds-c-button');
  if (!btn) { return; }
  var r = btn.getBoundingClientRect();
  var size = Math.max(r.width, r.height);
  var ink = D.createElement('span');
  ink.className = 'ux-ripple';
  ink.style.width = ink.style.height = size + 'px';
  ink.style.left = (e.clientX - r.left - size / 2) + 'px';
  ink.style.top  = (e.clientY - r.top  - size / 2) + 'px';
  btn.appendChild(ink);
  setTimeout(function () { if (ink.parentNode) { ink.parentNode.removeChild(ink); } }, 620);
}, true);
```

One delegated listener covers every button that will ever exist, including ones the
renderer has not created yet. The button needs `position: relative; overflow: hidden`.

## 13. Drag state on a file dropzone

```js
['dragenter', 'dragover'].forEach(function (t) {
  D.addEventListener(t, function (e) {
    var z = e.target && e.target.closest && e.target.closest('.form-builder--file-upload');
    if (z) { z.classList.add('ux-drag'); }
  }, true);
});

['dragleave', 'drop'].forEach(function (t) {
  D.addEventListener(t, function () {
    all('.form-builder--file-upload.ux-drag').forEach(function (z) {
      z.classList.remove('ux-drag');
    });
  }, true);
});
```

The clear pass sweeps **all** zones rather than the event's target: `dragleave`
fires on children too, and targeted removal leaves zones stuck in the drag state.

## 14. Scroll to the top of the card on a step change

```js
if (active > -1 && active !== lastStep) {
  if (lastStep > -1) {                       // not on first paint
    var card = q('.form-builder--form');
    if (card && card.scrollIntoView) {
      card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
  lastStep = active;
}
```

Guarding on `lastStep > -1` stops the page from scrolling itself on the initial
render, which reads as the page fighting the user.

## 15. Gate a button whose click runs a chain of events

A button's `onClickEvents` is an ordered chain (e.g. `RUN_JAVASCRIPT` →
`RUN_PROCESS` → `MAP_FORM_DATA` → `RUN_JAVASCRIPT`). A validation placed in the
first `RUN_JAVASCRIPT` **cannot stop the rest of the chain** — a throw or `return`
there ends only that block; the process still launches. Two layers:

1. **Capture-phase guard in the runtime** (form-level JS, injected per §4 of
   `02-CODE-INJECTION.md`): `document.addEventListener('click', fn, true)`, match
   the button by `closest('[id="<button-id>"]')`, and on invalid state call
   `preventDefault()` + `stopImmediatePropagation()` + `stopPropagation()`.
   Document capture runs before the Vue handler on the button, so **no** event of
   the chain fires. Expose the rules as one `check()` on `window`.
2. **Gate inside the chain's last block** (the one that navigates): re-run the same
   `check()` and `throw` before `nextButton.click()`. This is the fallback when the
   runtime did not load; the rules still live in one place.

Same trick for a checkbox that must not be ticked: intercept its click in capture
phase and `preventDefault()`. Do not rely on `input.disabled` alone — a Vue
re-render of the row can reset it. To untick a checkbox programmatically, `click()`
it (setting `.checked = false` does not reach the Vue model).

Checkboxes inside a `dynamic-table-row` repeat the same DOM `id` on every row —
select them with `querySelectorAll('[id="<id>"]')` and read the row's other
columns from the enclosing row's cells, in `tableColumnsSourceValue` order
(the cell markup is not yet confirmed on a live render — check it before relying
on the column index).

## 16. One click from a JS decision to a no-code reaction: the trigger field

The common wish: a JS validator decides, and on success the no-code layer locks the
step's fields, swaps Validate for Modify, reveals the next step and moves to it, all
from **one** click. The obvious chain (`JS validator` → `MAP_FORM_DATA when
<flag> EQUALS 1`) does not do that. Verified on a live form, three renderer facts
decide the design:

1. **An `input`/`number-input` value reaches the form model 500 ms after the DOM
   write** (`Element.component.vue`, `onInputDebounced`). A MAP condition later in
   the same chain reads the value from before the JS ran, so the first click never
   passes. That is why these forms end up with "validate twice, then confirm".
2. **A field's own `onInputEvents` chain fires when that value lands**, including
   a value written by JS through the native setter, and its conditions see the
   new value. This is the hand-off point.
3. **While a button's chain runs, the whole form is locked** (every element is
   `disabled`), so JS cannot click another form button mid-chain. The stepper's
   own Next/Previous are not form elements and still work.

The pattern that follows, measured at about 0.8 s from click to the next step:

```
Validate click:  loader.show → validator (writes flag "1"/"0") → request(flag, branch)
request(...):    if flag is "1": remember a pending request, write the clicked
                 button's branch ("person", "company"…) into a hidden text
                 input `step-flow-branch`, then increment a hidden number-input
                 `step-flow-trigger` (native setter + input/change/blur, branch first)
trigger onInput: MAP when <flag step N> EQUALS 1 AND step-flow-branch EQUALS <branch>
                     → lock step N, Validate hidden, Modify shown, step N+1 visible
                 (one MAP per step and branch; only the clicked one matches)
                 → JS advance(): only with a pending request: click Next, reset
                   scroll, hide the loader
Modify click:    MAP (unconditional): unlock step N, flag N = 0, swap the buttons,
                 hide steps N+1…, and reset them (unlock, flags 0, Validate shown)
```

Rules that keep it safe:

- **Only `request()` writes the trigger field.** Do not use the flag fields as
  triggers. A MAP that writes a field fires that field's `onInput` chain
  immediately, with no debounce. The Modify MAP and any reset would then start a
  second chain in parallel, and the two chains' JS blocks share one sandbox iframe.
- **The trigger always changes** (increment it): a flag still at `1` from an
  earlier pass would not change and would not fire anything.
- **`advance()` moves on only with a pending request**, and a watchdog (a few
  seconds) hides the loader if the trigger chain never comes.
- **The button states its branch; never infer it from a Boolean form variable.**
  When a step has variants (person / company, electricity / gas), the Validate
  button that was clicked IS the branch, so it writes it. Measured live, a
  condition on a Boolean form variable is not reliable here:

  | variable holds | `IS_TRUE` | `IS_FALSE` |
  |---|---|---|
  | the text `"false"` / `"False"` (the designer's default) | **passes** | fails |
  | `null` | fails | passes |

  Any non-empty text counts as true. Variables that a render process fills later
  still hold that text until the process result lands, and on a form with two
  variants both "IS_TRUE" branches ran: two lock MAPs fought over which Modify
  button to show, and the wrong one then unlocked the other variant's fields.
  `formlint` (every `form-update` / `form-add-element`) and
  `form-set-element-chains` now warn about this condition.
- **Previous needs no handler.** A MAP-set `disabled`/`visible` survives the
  renderer destroying and rebuilding the step, so a step you come back to is still
  locked and still shows Modify. The stepper's own Next stays available there,
  because the following step is visible.
- **A hidden step drops out of the stepper**, and Next exists only while a later
  step is visible. Hiding steps N+1… on Modify therefore removes Next until step
  N is validated again.

Wire the chains with `form-set-element-chains` (a plan of ordered events per
element). It keeps the existing validator blocks by id and builds the MAP blocks
and conditions from element and variable names. Prove the mechanism on a small
public copy of the flow before touching a live form. [07](07-DEPLOY-WORKFLOW.md) §4
has the recipe.
