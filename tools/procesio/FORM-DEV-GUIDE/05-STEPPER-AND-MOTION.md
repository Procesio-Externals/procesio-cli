# 05 — Custom stepper, step transitions, and the loader veil

The moving parts of a form that feels finished: a step indicator you control, a
transition that gives the step change a direction, a loader that hides the
renderer's rebuild, and entrance animation for the arriving controls.

All of it rests on one fact from [03](03-DOM-CONTRACT.md): **the renderer destroys
and rebuilds a step's controls (`v-if`) rather than hiding them.** You cannot
animate anything out. You can only animate the *container*.

---

## 1. Why replace the platform's stepper at all

The platform's `.form-builder--stepper--nav` renders only once the stepper's `steps`
config names the real step elements — while it holds placeholder names the page has
**no indicator at all**. And even when present, it offers no hook for progress
states, sonar pulses, or check marks.

Two valid strategies:

| Strategy | When |
|---|---|
| **Style the platform's nav** (`.form-builder--stepper--nav--item`, `.pds-c-step--header--circle`) | you only want colour/scale changes and want zero maintenance |
| **Draw your own rail and hide theirs** | you want full control over structure, states, labels, animation |

If you draw your own, hide theirs — do not leave both:

```css
.form-builder--stepper--nav { display: none !important; }
```

A common symptom of forgetting: "why is there a second, native stepper next to
mine?" — it appeared the moment the `steps` config was saved with real step names.

## 2. Build the rail — and steal its labels from the platform

```js
function ensureRail() {
  var body = q('.form-builder--form-body');
  if (!body) { return null; }
  var rail = q('.ux-rail', body);
  if (rail) { return rail; }                 // idempotent: build once

  /* The native nav is hidden in CSS, but its LABELS are the form's own and stay
     correct as steps are renamed — copy them onto the rail before replacing it,
     rather than maintaining a second list that can drift. */
  var nav = q('.form-builder--stepper--nav');
  if (nav) {
    var labels = all('.form-builder--stepper--nav--item', nav)
      .map(function (it) { return String(it.textContent || '').trim(); })
      .filter(Boolean);
    if (labels.length === STEPS.length) {
      labels.forEach(function (t, i) { STEPS[i].label = t; });
    }
  }

  rail = D.createElement('div');
  rail.className = 'ux-rail';
  rail.innerHTML =
    '<div class="ux-rail__steps">' +
      STEPS.map(function (s, i) {
        return '<div class="ux-rail__step" data-i="' + i + '">' +
                 '<span class="ux-rail__dot">' + (i + 1) + '</span>' +
                 '<span class="ux-rail__label">' + s.label + '</span>' +
               '</div>';
      }).join('') +
    '</div>';

  body.insertBefore(rail, body.firstChild);
  return rail;
}
```

The label-copying is the load-bearing idea: your rail's labels come from **the
form's own configuration**, so renaming a step in the designer updates the rail
with no code change. The `length === STEPS.length` guard means a mismatch falls
back to your hard-coded labels instead of producing a shifted list.

## 3. Paint it

```js
function paintRail(active) {
  var rail = ensureRail();
  if (!rail) { return; }
  // Unknown step: leave the rail exactly as it was rather than showing a wrong
  // position. Wrong information is worse than a stale frame.
  if (active < 0) { return; }
  all('.ux-rail__step', rail).forEach(function (st, i) {
    st.classList.toggle('is-done',    i < active);
    st.classList.toggle('is-current', i === active);
    var dot = q('.ux-rail__dot', st);
    if (dot) { dot.textContent = i < active ? '✓' : String(i + 1); }
  });
}
```

CSS for the three states — circles and connectors only, no surrounding card:

```css
.ux-rail__steps { display: flex; align-items: flex-start; gap: 0; }

.ux-rail__step {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  flex: 1 1 0; min-width: 92px; position: relative; text-align: center;
}

/* connector, drawn from this dot back to the previous one */
.ux-rail__step::before {
  content: ""; position: absolute; top: 15px;
  left: calc(-50% + 17px); width: calc(100% - 34px); height: 2px;
  border-radius: 2px; background: var(--ux-line);
  transition: background-color var(--ux-slow) var(--ux-ease);
}
.ux-rail__step:first-child::before { display: none; }
.ux-rail__step.is-done::before,
.ux-rail__step.is-current::before { background: var(--ux-accent); }

.ux-rail__dot {
  position: relative; width: 32px; height: 32px; flex: 0 0 32px;
  border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700;
  color: var(--c-neutral--500); background: #fff; border: 2px solid var(--ux-line);
  transition: background-color var(--ux-mid) var(--ux-ease),
              border-color var(--ux-mid) var(--ux-ease),
              color var(--ux-mid) var(--ux-ease),
              box-shadow var(--ux-mid) var(--ux-ease);
  z-index: 1;                                   /* above the connector */
}

.ux-rail__step.is-done .ux-rail__dot {
  background: var(--ux-accent); border-color: var(--ux-accent); color: #fff; font-size: 15px;
}

.ux-rail__step.is-current .ux-rail__dot {
  background: var(--ux-accent); border-color: var(--ux-accent); color: #fff;
  box-shadow: 0 0 0 5px var(--ux-ring);
  animation: ux-sonar 2.6s var(--ux-ease) infinite;
}

@keyframes ux-sonar {
  0%, 100% { box-shadow: 0 0 0 5px  var(--ux-ring); }
  50%      { box-shadow: 0 0 0 10px rgba(37, 120, 233, .06); }
}
```

The connector is a `::before` on each step reaching *backwards* — that way the
first step simply suppresses it and no extra wrapper markup is needed. `z-index: 1`
on the dot keeps the line behind the circle.

## 4. The step transition: **leave → empty → arrive**

The renderer swaps the step's controls instantly, which reads as a jump. Fade the
container out before the swap, and let the arriving controls rise in.

```js
D.addEventListener('click', function (e) {
  var btn = e.target && e.target.closest && e.target.closest('.pds-c-button');
  if (!btn) { return; }
  if (!btn.closest('.form-builder--stepper--buttons')) { return; }

  /* The class is lifted on a TIMER, never on an observed mutation. Tying it to a
     mutation left the container at opacity 0 for good whenever that mutation did
     not arrive — an entire step rendered blank. A visual state must never depend
     on an event that may not come. */
  var box = q('.form-builder--stepper--container');
  if (!box) { return; }
  box.classList.add('ux-leaving');
  clearTimeout(leaveTimer);
  leaveTimer = setTimeout(endLeaving, 260);
}, false);

function endLeaving() {
  clearTimeout(leaveTimer);
  // Clear it wherever it sits: the renderer may have replaced the container.
  all('.ux-leaving').forEach(function (el) { el.classList.remove('ux-leaving'); });
}
```

```css
.form-builder--stepper--container {
  transition: opacity 220ms var(--ux-ease), transform 220ms var(--ux-ease);
}
.form-builder--stepper--container.ux-leaving { opacity: 0; transform: translateY(8px); }
```

**Read that comment twice.** This is the single most expensive bug in this whole
guide: an entire step rendered blank, permanently, because the class that hid it
was removed only in response to a DOM mutation that sometimes never arrived. Any
class that makes something invisible needs an unconditional escape — a timer, a
ceiling, a sweep.

`endLeaving` clears the class **from every node that carries it** rather than from
the node it was added to, because the renderer may have swapped the container in
between. Holding a reference to a node across a rebuild is how state gets stranded.

### The arrival: a staggered rise

```css
.form-builder--stepper--container > .form-builder--element {
  animation: ux-rise var(--ux-mid) var(--ux-ease-out) both;
}
.form-builder--stepper--container > .form-builder--element:nth-child(1)    { animation-delay: 30ms; }
.form-builder--stepper--container > .form-builder--element:nth-child(2)    { animation-delay: 80ms; }
.form-builder--stepper--container > .form-builder--element:nth-child(3)    { animation-delay: 130ms; }
.form-builder--stepper--container > .form-builder--element:nth-child(n+4)  { animation-delay: 180ms; }

@keyframes ux-rise {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: none; }
}
```

This needs **no JavaScript at all**. Because controls are recreated on every step
change, the animation re-fires by itself. Cap the stagger with `nth-child(n+4)` —
an uncapped `nth-child` ramp makes a twelve-field step take two seconds to appear.

## 5. The loader veil

Covers the card while the renderer destroys and rebuilds controls, so half-built
states (a label with no input) are never visible.

```js
function ensureVeil() {
  var card = q('.form-builder--form');
  if (!card) { return null; }
  var v = q('.ux-veil', card);
  if (v) { return v; }
  v = D.createElement('div');
  v.className = 'ux-veil';
  v.innerHTML = '<div class="ux-veil__inner">' +
                  '<div class="ux-veil__drop"><span></span><span></span><span></span></div>' +
                  '<div class="ux-veil__text">Preparing the next step…</div>' +
                '</div>';
  card.appendChild(v);
  return v;
}
```

### Two dismissal modes, and why both exist

```js
function showVeil(message, hold) {
  var v = ensureVeil();
  if (!v) { return; }
  var t = q('.ux-veil__text', v);
  if (t && message) { t.textContent = message; }
  v.classList.add('is-on');

  clearTimeout(veilTimer);
  veilTimer = setTimeout(function () {
    hideVeil();
    if (hold && window.UXToast) {
      window.UXToast('This is taking longer than usual. You can fill the fields in manually.', 'err');
    }
  }, hold ? 75000 : 2600);          // HARD CEILING — always, in both modes

  if (!hold) { settleThenHide(); }
}

/* Lift the veil once the DOM has stopped changing for a beat — that is the actual
   end of the rebuild, which no event reports. */
function settleThenHide() {
  clearTimeout(veilQuiet);
  veilQuiet = setTimeout(function () { hideVeil(); endLeaving(); }, 620);
}
```

- **Quiet-timer mode** (`hold` falsy) — for a step change. There is no event that
  says "the rebuild finished", so the signal is *the DOM going quiet*. Every
  mutation while the veil is up restarts the timer:

  ```js
  var mo = new MutationObserver(function () {
    schedule();
    if (q('.ux-veil.is-on') || q('.ux-leaving')) { settleThenHide(); }
  });
  ```

- **Held mode** (`hold` truthy) — for work whose end the DOM cannot announce, such
  as a network call that takes seconds of silence. The quiet heuristic would lift
  the veil almost immediately. A held veil is dismissed **explicitly by whoever
  raised it**.

**Both modes have a hard ceiling.** A failed call must never strand the form behind
an opaque overlay; when the ceiling fires, the veil lifts *and the user is told
what to do instead*. Same principle as the leave-class timer: never let visibility
depend on something that might not happen.

```css
.ux-veil {
  position: absolute; inset: 0; z-index: 20;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-start;
  border-radius: 20px;
  background: rgba(247, 250, 254, .82);
  backdrop-filter: blur(3px); -webkit-backdrop-filter: blur(3px);
  opacity: 0; pointer-events: none;
  transition: opacity var(--ux-fast) linear;
}
.ux-veil.is-on { opacity: 1; pointer-events: all; }

/* The card is often taller than the viewport, so centring the indicator inside it
   can park it below the fold. Sticky keeps it on screen wherever the reader is. */
.ux-veil__inner { position: sticky; top: 40vh; display: flex; flex-direction: column;
                  align-items: center; gap: 18px; }
```

The veil is `position: absolute` inside the card — which requires
`.form-builder--form { position: relative }` and **must not** use `overflow: hidden`
to clip its corners (that kills page scrolling — [03](03-DOM-CONTRACT.md) §5). Give
it the same `border-radius` as the card instead.

### The indicator itself — concentric ripples

```css
.ux-veil__drop { position: relative; width: 46px; height: 46px; }

.ux-veil__drop span {
  position: absolute; inset: 0; border-radius: 50%;
  border: 2px solid var(--ux-accent); opacity: 0;
  animation: ux-ripple-out 1.6s var(--ux-ease-out) infinite;
}
.ux-veil__drop span:nth-child(2) { animation-delay: .4s; }
.ux-veil__drop span:nth-child(3) { animation-delay: .8s; }

@keyframes ux-ripple-out {
  0%   { transform: scale(.25); opacity: .9; }
  100% { transform: scale(1);   opacity: 0;  }
}
```

Three identical spans with staggered delays produce a continuous ripple from one
`@keyframes`. `transform` + `opacity` only, so it composites on the GPU.

## 6. State-change motion on controls

Every animation should be tied to a state change; nothing decorative should move on
its own except at most one slow ambient effect.

```css
/* Error: one short shake, then a steady state. */
.pds-c-input-group--wrapper--is-error {
  background: #FFF7F7;
  animation: ux-shake 400ms var(--ux-ease) both;
}
@keyframes ux-shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-4px); }
  45% { transform: translateX(3px); }
  70% { transform: translateX(-2px); }
}

/* A message arriving */
@keyframes ux-msg-in { from { opacity: 0; transform: translateY(-3px); } to { opacity: 1; transform: none; } }

/* A checkbox/radio committing */
@keyframes ux-check { 0% { transform: scale(.7); } 60% { transform: scale(1.2); } 100% { transform: scale(1); } }

/* A sweep across the primary action on hover */
.pds-c-button--solid-primary::after {
  content: ""; position: absolute; top: 0; left: -140%; width: 55%; height: 100%;
  background: linear-gradient(100deg, transparent, rgba(255,255,255,.3), transparent);
  transform: skewX(-18deg); pointer-events: none;
}
.pds-c-button--solid-primary:hover::after { animation: ux-sweep 720ms var(--ux-ease-out); }
@keyframes ux-sweep { to { left: 140%; } }
```

Keep three duration tokens and two easings and use nothing else — that consistency
is most of what makes a form read as designed rather than decorated:

```css
--ux-fast: 160ms;   /* hover, focus, colour */
--ux-mid:  300ms;   /* state changes, entrances */
--ux-slow: 520ms;   /* the card, long connectors */
--ux-ease:     cubic-bezier(0.22, 1, 0.36, 1);
--ux-ease-out: cubic-bezier(0.16, 1, 0.3, 1);
```
