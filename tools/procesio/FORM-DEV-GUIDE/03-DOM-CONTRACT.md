# 03 — The runtime DOM: selectors, structure, and what you may rely on

The reference you need open while writing CSS or any `querySelector`. Two selector
families, two very different levels of trust.

---

## 1. The two families

### `.form-builder--*` — the renderer's own classes. **Trustworthy.**

They live in this platform's own SCSS, they are stable, and they are the ones to
build on.

| Selector | What it is |
|---|---|
| `.form-builder--form` | the card — the outermost form container |
| `.form-builder--form-body` | the scrolling body inside the card |
| `.form-builder--element[data-element-id]` | **one control** — the unit you iterate |
| `.form-builder--columns` / `--column` | layout containers |
| `.form-builder--stepper` | the stepper as a whole |
| `.form-builder--stepper--container` | the **active step's content** |
| `.form-builder--stepper--nav` / `--nav--item` | the platform's own step indicator |
| `.form-builder--stepper--buttons` | the nav button bar |
| `.form-builder--stepper--buttons--next` | the next-button host |
| `.form-builder--input` / `--select` / `--checkbox` / `--radiobox` / `--file-upload` | control wrappers by type |
| `.form-builder--file-upload--description` | the dropzone's helper line |
| `.form-builder--button` | a button control |

### `.pds-c-*` — the design system. **Use with care.**

These come from the `@procesio/procesio-design-system` npm package, whose internals
are **not in this repo**. Only the ones the renderer's own SCSS references are safe;
anything deeper must be verified against a live render before you rely on it.

| Selector | What it is |
|---|---|
| `.pds-c-input-group--wrapper` | the box around an input |
| `.pds-c-input-group--wrapper--focused` | focused state (also use `:focus-within`) |
| `.pds-c-input-group--wrapper--is-error` | platform validation error state |
| `.pds-c-input-group--label` | **the field's label** — your primary identification handle |
| `.pds-c-input-group--message--is-error` | the error message node |
| `.pds-c-input-group--square` | the checkbox square |
| `.pds-c-radiobox` / `.pds-c-radiobox--is-checked` | radio dot and its checked state |
| `.pds-c-button` / `.pds-c-button--solid-primary` / `.pds-c-button--small` | buttons and variants |
| `.pds-c-step--header--circle` `[--active]` | the platform stepper's circles |
| `.pds-c-step-connector` | the line between them |
| `.pds-c-modal--dialog--upload-icon` | the upload glyph |
| `.form-builder--select .multiselect__tags` / `.multiselect__option--selected` | the select is vue-multiselect underneath |

## 2. Structural facts you can build on

**A control is `.form-builder--element[data-element-id]`.** Elements nest (a column
is also an element), so "a leaf control" is:

```js
function fields() {
  return all('.form-builder--element[data-element-id]').filter(function (el) {
    return q('input, textarea, select', el) &&              // has a real control…
      !q('.form-builder--element[data-element-id]', el);    // …and is a leaf
  });
}
```

**The active step's content is `.form-builder--stepper--container`.** Its direct
element children are the controls of the current step — that is the handle for
staggered entrances and for the leave/arrive transition:

```css
.form-builder--stepper--container > .form-builder--element { … }
```

**Controls are recreated, not hidden** (`v-if`). So:
- entrance animations re-fire on every step change — free, and desirable;
- **exit transitions are impossible** — by the time you would animate it out, the
  node is gone. Animate the *container*, not the departing control ([05](05-STEPPER-AND-MOTION.md) §4);
- never store state on a node; recompute it ([02](02-CODE-INJECTION.md) §6).

## 3. Identify fields by LABEL, not by id

Element ids change whenever a control is rebuilt in the designer. Labels are what
the form actually promises to the person filling it in, and they change only when
the meaning changes.

```js
function norm(s) {                    // fold diacritics + case + whitespace
  return String(s || '').toLowerCase()
    .replace(/[ăâ]/g, 'a').replace(/[îi]/g, 'i').replace(/[șş]/g, 's')
    .replace(/[țţ]/g, 't').replace(/\s+/g, ' ');
}

var LABELS = [
  ['repciserie', 'id doc representative — series'],   // ORDER MATTERS:
  ['ciserie',    'id doc — series'],                  // the longer, more specific
  ['cnp',        'personal number'],                  // label must be tested FIRST
];

function fieldKey(el) {
  var lbl = q('.pds-c-input-group--label', el);
  var n = norm(lbl ? lbl.textContent : el.textContent);
  for (var i = 0; i < LABELS.length; i++) {
    if (n.indexOf(LABELS[i][1]) > -1) { return LABELS[i][0]; }
  }
  return null;
}
```

**Order the list from most specific to least.** A substring match on a shorter
label will swallow the longer one — `'id doc — series'` matches inside
`'id doc representative — series'`, so the representative's field would be keyed
wrongly if it came second.

Normalize diacritics on **both** sides of every comparison. A form written in
Romanian will otherwise match `ț` against `t` and fail for no visible reason.

## 4. Detect state from TEXT when class matching is unreliable

Step wrappers come from the design-system package, and matching them by class has
already failed once on a live form. Reading the visible text of the step container
is more robust, because the banner text is the form's own content:

```js
var STEPS = [
  { label: 'Applicant type', marks: ['who is requesting'] },
  { label: 'Identification',  marks: ['identification details'] },
];

function currentStep() {
  var host = q('.form-builder--stepper--container') || q('.form-builder--form-body');
  if (!host) { return -1; }
  var text = norm(host.innerText || host.textContent);
  for (var i = 0; i < STEPS.length; i++) {
    for (var j = 0; j < STEPS[i].marks.length; j++) {
      if (text.indexOf(STEPS[i].marks[j]) > -1) { return i; }
    }
  }
  return -1;                          // unknown — see below
}
```

**Return a sentinel for "unknown" and honour it.** When the step cannot be
identified, leave the indicator exactly as it was rather than guessing. Wrong
information is worse than a stale frame — a progress bar that jumps to 100% because
the match failed actively misleads.

## 5. CSS traps specific to this renderer

### A hand-built node renders unstyled: the CSS is Vue-SCOPED

Every platform-rendered element carries a `data-v-<hash>` attribute, and the rules are
written as `.pds-c-message[data-v-<hash>] { … }`. A node built with `createElement` has no
such attribute, so copying the platform's class list is **not** enough — the scoped rules
never match it. The symptom is a widget that works but looks wrong.

Never hardcode the hash; it changes on every frontend rebuild. Clone an existing native
node of the same kind instead — `cloneNode(true)` carries the scope attributes, the inner
markup and the theme for free.

Worked example, with the inner-structure details and the "exclude your own node from the
template query" trap:
[`../dto/form/description.md`](../dto/form/description.md).

### `overflow: hidden` on `.form-builder--form` kills page scrolling

The card is the scroll context. Clipping it makes the page unscrollable and the
lower half of a long form unreachable. If you need something clipped to the card's
rounded corners, **paint it as a background** — backgrounds are clipped to
`border-radius` automatically:

```css
.form-builder--form {
  background-image: linear-gradient(90deg, #1E67D2 0%, #4FA8F5 50%, #1E67D2 100%);
  background-size: 720px 4px;
  background-repeat: repeat-x;    /* MUST tile, see below */
  background-position: 0 0;
}
```

### `transform` on `.form-builder--form` breaks the pinned footer

A `transform` on an ancestor makes that ancestor the **containing block** for
`position: fixed` descendants. The renderer's pinned footer then anchors to the
card instead of the viewport and lands on top of the content. **Entrance animations
on the card must animate `opacity` only** — never `transform`, `filter`,
`perspective`, or `will-change: transform`.

### An animated background must tile

Animating `background-position` on a `no-repeat` gradient slides it off-screen and
the element goes blank for the rest of the cycle. Set `repeat-x`, make the gradient
start and end on the same colour, and travel **exactly one tile per cycle**:

```css
@keyframes tide { from { background-position: 0 0; } to { background-position: 720px 0; } }
```

### Inline styles on the form's own markup beat your stylesheet

If the form author wrote `style="border-left: 4px solid #2578E9"` in an HTML
paragraph, only `!important` can override it:

```css
.ux-choice--on [style*="border-left"] { border-left-color: #409920 !important; }
```

The `[style*="…"]` attribute selector is how you target "whatever element carries
that inline rule" without knowing its structure.

### An `<img>` icon cannot be recoloured with `color`

Icon-font-as-image services (iconify and similar) bake the colour into the URL. A
CSS `filter` only approximates the target colour and tints the whole glyph.
**Rewrite the URL parameter instead:**

```js
var want = on ? '%23409920' : '%232578E9';
var next = icon.getAttribute('src').replace(/color=%23[0-9A-Fa-f]{6}/, 'color=' + want);
if (next !== icon.getAttribute('src')) { icon.setAttribute('src', next); }
```

The equality check keeps the attribute write out of the MutationObserver loop when
nothing changed — otherwise you feed your own observer.

### The card is often taller than the viewport

Centring an overlay indicator *inside* the card can park it below the fold. Use
`position: sticky` on the inner block so it stays on screen wherever the reader is
scrolled:

```css
.ux-veil__inner { position: sticky; top: 40vh; }
```

## 6. Responsive and reduced motion

Side-by-side columns truncate every label on a phone. Cover both layout modes —
whichever the renderer uses, the other declaration is inert:

```css
@media (max-width: 760px) {
  .form-builder--columns { flex-wrap: wrap; grid-template-columns: 1fr; }
  .form-builder--column  { flex: 1 1 100%; min-width: 0; }
}
```

Honour the motion preference. One block covers the whole layer:

```css
@media (prefers-reduced-motion: reduce) {
  .form-builder--form *, .form-builder--form *::before, .form-builder--form *::after,
  .ux-toast, .ux-veil, .ux-veil__drop span {
    animation-duration: 1ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 1ms !important;
  }
}
```

## 7. Use the theme's variables, define your own on the card

Declare your design tokens on `.form-builder--form` so they cascade to everything
you write, and derive them from the theme's existing colours rather than inventing
new ones (a palette is usually a hard requirement on a client form):

```css
.form-builder--form {
  --ux-ease: cubic-bezier(0.22, 1, 0.36, 1);
  --ux-fast: 160ms;  --ux-mid: 300ms;  --ux-slow: 520ms;
  --ux-ink: #123E7E;  --ux-accent: #2578E9;  --ux-line: #D6E2F0;
  --ux-ring: rgba(37, 120, 233, .16);
}
```

The platform's own theme variables (`--c-neutral--500`, `--c-primary`, `--h-input`,
`--p-form`, `--gap-columns`, …) are available and should be preferred wherever one
exists — they keep your layer consistent with a theme change made in the designer.
