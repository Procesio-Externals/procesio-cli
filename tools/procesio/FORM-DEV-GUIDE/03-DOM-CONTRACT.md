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

### Platform defaults that fight a redesign (measured 2026-10-22)

- **The page scrolls in `.form-builder-view--content`**, not in `body` or `main`. Fixed UI
  you mount on `body` sits above it; give that element the top padding a fixed header needs.
- **`.form-builder--section--container`** carries a 1px border, a light background, a 4px
  radius and 16px padding even when the section's own `style` config sets none. Reset all
  four, or every redesigned section sits inside a faint grey box.
- **`.form-builder--button` has a fixed height** (the theme's button height, 40px). Make the
  `<button>` taller and anything you append after it overlaps it; set `height: auto` on the
  wrapper. Its `.pds-c-button--dropdown` sibling is an empty split-button part; hide it.
- **A paragraph's HTML is rendered through DOMPurify into the live page, next to Bootstrap.**
  Generic class names in authored markup collide with Bootstrap rules: an SVG `<circle
  class="badge">` vanished because `.badge:empty { display: none }`. Prefix every class.

### File viewer (INLINE) and signature pad: what is inside

- File viewer: `.form-builder--file-viewer` > `--container` > `--container--viewer` (the
  internal scroller, `max-height` around 640px) > `.vue-pdf-embed`, one `<canvas>` per page.
  While a file loads the container shows `--container--loading`; a bad file shows
  `--container--failed`; no `src` yet shows `--container--empty-message`. "Empty" also shows
  briefly while a process-output file is still being fetched, so wait a few seconds before
  you treat it as final. Count rendered pages by counting the canvases.
- Signature pad: `.form-builder--signature-pad` > `--canvas-wrapper` > `canvas`, then a
  footer with the platform's Clear button. The pad paints a white background into the canvas,
  so ink = any pixel clearly darker than white (sample a downscaled copy after `pointerup`
  and after Clear). A `ResizeObserver` **clears and redraws** the pad whenever the canvas
  size changes, so never animate the canvas or its wrapper's padding; set the size once.

### Table + dynamic-table-row: what is inside (measured on a live form, 2026-10-22)

A table with a dynamic row renders TWO `table.pds-c-table`: the Table control's own (header
only) and, inside its `tbody`, the dynamic row's table, whose `thead` exists but is
`display: none` (`--no-header`). Each item of the dynamic row is nested:
`div.form-builder--table-dynamic-row--container--item[data-row-index]` > `td.form-builder--table-static-row`
> `tr.form-builder--table-static-row--container` > **`tr.pds-c-table--row`** > `td.pds-c-table--cell`.
Both of those `tr` are **`display: flex`**, so the cells are flex items, not table cells: widths
set on `td` act as flex-basis and the header table (a real table) does not line up with them on
its own. Make the header row flex too (`thead.pds-c-table--header > tr { display: flex }`), give
`th:nth-child(n)` and the row's `td:nth-child(n)` the same `flex: 0 0 <w>`, let one column take
the rest (`flex: 1 1 auto; min-width: 0`) in both, and give both rows the same 1px border (the
header's transparent): the label then sits exactly over its column (measured: every left edge
and width equal to the pixel). Style the ROW as the card (border, radius, background), not the
cells.

- Helper rows `tr.pds-c-table--row.pds-c-table--row--before/--after` also carry
  `pds-c-table--row`: select data rows with
  `tr.pds-c-table--row:not(.pds-c-table--row--before):not(.pds-c-table--row--after)`, as a
  DESCENDANT (they are not children of `tbody`).
- Every header cell has the id `th<columnKey>` (`thstatus`, `thid`); map a column by that id in
  the ROW's own table (`tr.closest('table')`). Counting `thead th` under the control counts both
  tables. The first column is the index column when `hasIndexColumn` is on.
- A cell's text sits in `.form-builder--table-cell > … > .form-builder--table-cell--container--text`;
  `.form-builder--table-cell` is a ~54px block. To relabel a cell the renderer owns (translate a
  status, shorten an id), never rewrite the text node (Vue patches it back): put the label in a
  data attribute on the `td`, hide `.form-builder--table-cell` in that `td`, and paint
  `td[data-x]::after { content: attr(data-x) }`.
- A control placed in a column (the row's button) renders once per row with the SAME
  `data-element-id`; find "this row's button" from the row.

### File-upload used as a download (process output)

`.form-builder--file-upload` > `.pds-c-modal--upload` > `.pds-c-modal--dialog--content` > … >
`.pds-c-modal--dialog--content--action` (`--first` holds the file name, `--actions--icon` is the
download icon). With no file the same control shows the upload drop zone instead, which invites
an upload on a read-only screen: hide it with
`.form-builder--file-upload:not(:has(.pds-c-modal--dialog--content--action))`.

**Driving it from your own download menu (measured 2026-10-22).** The download icon is
`i.pds-c-modal--dialog--content--action--actions--icon[role=button][aria-label="Download file"]`
(text `download`; an editable control also has a delete icon next to it, so select by the label,
never by position). Clicking it makes no request: the platform already holds the file it fetched
after the run ([06](06-PROCESS-INTEGRATION.md) §3c), wraps it in a `Blob` of the real type
(`application/pdf`, `…wordprocessingml.document`), calls `URL.createObjectURL` and clicks an
`<a download="<file name>">` on that `blob:` URL. `element.click()` on the icon works while the
control's host is `display: none`, so the visible UI can be one custom menu per document while
the file-upload controls stay rendered (`visible: true`, see [01](01-ANATOMY.md)) and unseen. The
file name for the menu is the text of `.pds-c-modal--dialog--content--action--first`.

**Print from the same file.** There is no print action. Arm a short window, click the PDF
control's icon, keep the `Blob` your `URL.createObjectURL` wrapper sees with a `pdf` type, and in a
wrapper of `HTMLAnchorElement.prototype.click` cancel that one `blob:` click (the platform may
revoke its own URL right after, so make a fresh one from the kept Blob). Load it into a hidden
same-origin `<iframe>` and call `contentWindow.print()` on load. Measured: in Chrome the frame
loads as `application/pdf` and `print()` opens the dialog with nothing saved. Where
`navigator.pdfViewerEnabled === false` (PDF viewing turned off, and Playwright's default
headless shell) the frame does not render the PDF, it DOWNLOADS it under the blob's GUID, so
skip the frame there and let the normal download run. Safari and Firefox print such a frame
blank or refuse it: open the PDF in a new tab instead (inside the click, or the pop-up blocker
stops it).

**A menu inside the kit's document card is clipped** by the card's `overflow: hidden` (it is there
only for the rounded corners). Put the radius on the bar (top) and on the viewer scroller (bottom)
and let the card overflow, or the open menu is cut at the card's edge on a phone.

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
