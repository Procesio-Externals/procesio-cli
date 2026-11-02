# 10 - Redesigning a form, or a family of forms: the method

The other chapters explain each mechanism. This one gives the order to use them in, and the
decisions between them. It comes from a family of six production forms rebuilt on one design
system: account gates, a multi-step intake with AI extraction, an e-signature flow, a final
submission to an ERP, an admin panel and lists, all on a renderer we do not control.

Start your code from [`assets/form-kit`](../assets/form-kit/README.md).

---

## 1. The order of work

1. **Pull everything.** `form-get`, `form-get-code`, `form-digest`, and the definition of every
   process the form calls.
2. **Write the analysis** (§2) and get the owner's decisions before building anything.
3. **Pick the target:** a copy or the form itself (§8).
4. **Layer the sources** (§3): kit, family, form.
5. **Build a replica** that runs the real chains ([07](07-DEPLOY-WORKFLOW.md) §4), with one switch
   per state and per failure.
6. **Ship surgically** (§8), read the form back, compare it with the plan.
7. **Verify on each level** (§9) and write down what was verified where, with the rollback.

Steps 2 and 5 feel skippable and pay for themselves first. The analysis found a button with no event
and a data load that ran for anonymous visitors. The replica found a validation that could never
pass in one branch, which no anonymous browser can reach.

## 2. Read before you draw: the analysis file

One file per form, kept with its sources. It answers, from the definitions rather than from memory:

- **The gate.** Which process decides who sees what, every outcome it can return, and what happens
  on an outcome with no case. A role the check does not handle shows a blank page.
- **The data.** What loads when, sync or async, and whether it loads before or after the gate.
- **The actions per state.** For each status: what the user can do, which chain runs, in what order.
- **The side effects.** What is written before an external call that can fail. A retry path needs
  this answered first.
- **The findings,** each with its risk, separate from the plan.
- **The plan and the owner's decisions,** dated. Later rounds go at the bottom, so the file stays
  the history of why the form looks the way it does.

## 3. One look, three layers

| Layer | Holds | Changes when |
|---|---|---|
| critical import | hides the topbar, sets the page colour, unscoped, from the first frame | almost never |
| kit | tokens, shell, card, skeleton, atoms, header, toasts, loader, background, effects | the design system changes |
| family | what forms of one audience share: account states, header navigation, counters, run reading | a second form needs it |
| form | what only this form does | every round |
| generated | the loop and reduced-motion gates, from all of the above | every build |

JavaScript follows the same split: the runtime function holds the form's logic, and the kit is
pasted inside it at build time.

**Per form, keep:** `src/`, `dist/`, `build.py`, `ids.json`, `backup/`, `test/`, and a README with
the deploy log. Sources live in the user-data area, never in the framework
([07](07-DEPLOY-WORKFLOW.md) §5).

**Move code to a shared layer the second time it is needed,** verbatim. Prove the first form's output
stays byte-identical. Older forms may keep their copy until their next rebuild; do not rebuild a
working form only to tidy it.

## 4. What must not change, and how to prove it

Say it before the first edit: no element name, id, value, event map, condition, variable, data
model or table column changes. Then check it by machine. After a deploy, compare the GET with the
backup: the configs that differ must be exactly the planned ones, and every other `Data` key
identical. An added control adds one data-model attribute, so check that too.

Stay on the platform's rails:

- Choices click the real control, so maps and processes fire as for a mouse
  ([04](04-INTERACTION-RECIPES.md) §2).
- Fields are filled only by the processes' output maps. The runtime reads them.
- Hidden controls stay rendered and unseen, never `visible: false`, when a script clicks or measures them.

A redesign still changes behaviour in places. List each deliberate change in the README with its
reason, so a reviewer can tell a decision from a regression.

## 5. Which pattern for which need

| Need | Use | See |
|---|---|---|
| Platform chrome gone from the first frame | critical import, a header mounted on `<body>` | [02](02-CODE-INJECTION.md), [08](08-PITFALLS.md) |
| No empty card during the account check | a CSS-only skeleton keyed on the state paragraphs | [08](08-PITFALLS.md) |
| Account states | one state card per section, plus runtime cards for "no access" and "check failed", with a ceiling | §2 |
| Two to six fixed options | tiles that click the real option; two or three exclusive options read better as a sliding switch | [04](04-INTERACTION-RECIPES.md) |
| Several steps | a navigator showing status by colour and word; Previous / Next hidden, still clicked by scripts | [05](05-STEPPER-AND-MOTION.md) |
| An action not possible yet | keep it visible and grey; a click says what is missing | §11 |
| Upload with AI extraction | a dropzone, one tracked state per upload, a tag on filled fields, the refusal in the dropzone | [06](06-PROCESS-INTEGRATION.md) §7 |
| Data the runtime needs | a hidden button it clicks, a hidden input for a JSON answer; never the form-load body | [08](08-PITFALLS.md) |
| A long run | a modal fed by a hidden poll button reading a progress row the process writes per step, with a ceiling and a retry | [06](06-PROCESS-INTEGRATION.md) §3b |
| A list that goes stale | a refresh button; refresh by itself once when a fresher read disagrees with the row | §6 |
| Downloads | the upload controls rendered unseen, your menu clicks their icon | [03](03-DOM-CONTRACT.md) |
| Admin actions in a form | a command written to a hidden input, wait out the debounce, click a hidden button, one call at a time; the procedure re-checks the caller | [06](06-PROCESS-INTEGRATION.md) §3b |
| A loader that tells the truth | progress measured from the network log | [05](05-STEPPER-AND-MOTION.md) §5 |
| A link to another form | the direct address in the same workspace | [09](09-NAVIGATION-AND-HOSTING.md) §1 |

## 6. Lists: decorate the native table, or draw from the answer

**Decorate** when each row needs the platform's own button or checkbox. Cells keep their values and
get chips and icons on top ([03](03-DOM-CONTRACT.md)).

**Draw your own** when rows are read-only and people need to search, filter or read many columns. The
native table holds only the current page, so nothing built on the DOM can search all rows.

To draw a list safely:

1. **Read the rows from the run's answer** (`runOf()`), and walk it to find the array: a value can be
   a JSON string inside a variable. Reading a sync answer is verified live; an async form-load answer
   has only run on a replica, so treat that path as unproven until someone checks it signed in.
2. **Handle the two ways the first read misses.** The form-load run may end before the network hook
   exists, or its answer may not carry the rows. In both cases the native table has rows and you have
   none. Ask once more through a hidden refresh button, because a run the runtime starts is always readable.
3. **Keep the native table as the fallback.** Hide it with a rule that depends on an `<html>` attribute
   the runtime sets, so the data stays reachable if the script never runs. The network log caps a body
   (600 KB in the kit), and a cut answer cannot be parsed: show the plain table with a note.
4. **Read the data as written, not as you expect.** A process may store a placeholder such as
   `--not-used--` in columns that do not apply; an empty value and a text date are normal. Parse dates
   defensively: unknown formats stay as text and sort last.
5. **Compress the columns.** Twelve raw columns became four (who, contact, what, when), with every
   field in the row's detail. Sensitive identifiers belong in the detail, not in the list.
6. **Repaint only when something changed:** build a key from the data stamp, filters, page and open
   row, skip the paint when it matches, and put the focus back after a repaint.
7. **While loading, show dashes, never zeros.** A zero reads as a result.

## 7. A visitor's text is hostile in an agent's browser

Forms are often public, and agent pages show what the public typed. That text reaches a logged-in
browser, where a script could act as the agent.

- Every value goes through an escape function, into text or attribute positions only.
- `tel:` and `mailto:` only after a shape check. Otherwise show plain text.
- `textContent` for toasts and messages that quote a value.
- Put a row with markup in a name and an offer into the replica's test data, and assert that nothing ran.
- Nothing about a client in the console, in `localStorage` or in a debug helper; debug helpers return
  counts and flags.

CSS and `visible` are not access control. A public form that loads rows on `FORM_LOAD` sends them to
every visitor, whatever the page then hides. A condition such as `isConfirmed IS_TRUE` on a text
default passes for everyone ([08](08-PITFALLS.md)). Check the caller inside the process, and return nothing
to anyone else ([O14](../../../agents/procesio/IMPLEMENTATION-PATTERNS/05-OPTIMIZING-A-WORKSPACE.md)).

## 8. Shipping

**Copy or in place:**

| Situation | Target |
|---|---|
| People use the form daily, or its chains write data | `form-duplicate`, work on the copy, switch links after sign-off ([07](07-DEPLOY-WORKFLOW.md) §4) |
| Low traffic, presentation only, the owner asked for it | the form itself, with a backup |

**Patch from a plan.** For more than a few configs, write the intended changes to a file and let a
small script diff them against a fresh GET. It refuses anything outside the plan, and a second run
reports `already_applied`. That turns "did it land?" into a check.

**The order with new controls:** `form-add-element` → `form-set-element-event` → labels with
`form-set-element-config` → build with the real ids → `form-set-code`. The CSS that hides a new
control needs its id, and the id exists only after the first step.

**Before the first write:** a fresh GET, and compare `updatedOn` with your backup. Someone may have
saved in the designer.

**After the last write:** a GET compared with the plan (§4), `verified: true` from `form-set-code`,
the element count, and the form still published.

**Backups:** one folder per deploy with the DTO, the code and each write's output (they carry
`previous`), plus one rollback line in the deploy log.

## 9. The verification ladder

| Level | Proves | Cannot prove |
|---|---|---|
| Replica, on the shipped minified build and the DTO read back | wiring, every state, failure paths, layouts | the real shape of answers, platform timing |
| Live, anonymous | the CSS survives the scoper, the runtime installs, first frame, no page errors, cost | anything behind a login |
| Live, signed in, by a person | the real data path | |

Give the replica one switch per failure: check failed, refused, empty list, process failed, runtime
late, answer too big. Rerun all of it after the final build, not only the new scenarios.

Say which level each claim rests on. Headless checks on a login-gated page do not reach the signed-in
view ([07](07-DEPLOY-WORKFLOW.md) §4); name that gap in the handover, with the one check a person
should do first.

## 10. Performance: measure, then cut

A rich form can look perfect on a recent laptop and crawl on a budget one. Measure with
[`web perf-probe`](../../web/WEB-AUTOMATION-NOTES.md) at `--cpu-throttle 4`, the page as served
against variants that turn one thing off:

```bash
python scripts/run-tool.py web perf-probe --url <form> --cpu-throttle 4 \
  --variants '[{"name":"no-loops","css":"*{animation:none!important}"}]'
```

Measured on four forms at CPU x4, 1366x768:

| State | fps | main thread busy | boot CLS |
|---|---|---|---|
| as first built | 16-17 | ~104% | 1.1-1.6 |
| canvas stopped | 120 | 40-58% | |
| canvas and CSS loops stopped | | 3-6% | |
| after the work, all effects on | 120 | 41-53% | 0 |
| after the work, light tier | | 2-12% | 0 |

Attack in that order. Each line links a measured fix in [08](08-PITFALLS.md):

1. **The canvas.** Soft gradients at an eighth of the pixels, scaled by the compositor; small shapes
   at 1x and 30 fps; stop on a hidden tab ("The page runs hot").
2. **Repeating CSS animations.** Stop them behind an `<html>` attribute, generated at build time, so a new
   one is covered the day it is written (`effects_gate.py`).
3. **Paint area.** Move what moves into a pseudo-element no bigger than the moving part ("A thin
   moving strip").
4. **Boot.** Propagate the scope before the first mount ("The whole page jumps").
5. **The refresh pass.** Keep it cheap and counted; a tick that finds nothing changed must do nothing.
6. **Process calls.** Each one costs 3-4 s through a form ([08](08-PITFALLS.md)), and a sync step keeps
   every button disabled for its whole run. One call per view beats three.

Then add tiers, so a slower machine gets a lighter form instead of a slower one
([05](05-STEPPER-AND-MOTION.md) §7). Headless Chromium draws in software, so automatic tiers pick
light there: force the tier you mean to measure. On a real screen, paint cost scales with the device
pixel ratio, which a 1x headless run hides.

## 11. Review rules that kept coming back

From rounds of owner and tester feedback on real forms. Each one was a reported defect at least once.

- **One idea, one control.** The same choice looks the same on every step, and a control does not change
  shape with the data ([08](08-PITFALLS.md)).
- **One frame.** Two borders mean two wrappers. Remove one rather than restyle both.
- **One surface colour** across steps. A grey panel on one step reads as a different product.
- **Equal sizes within a group,** with titles aligned.
- **Required marks only where a validator enforces them** ([08](08-PITFALLS.md)).
- **No label that repeats the heading above it.**
- **Keep an unavailable action visible.** A missing button makes people think the page is broken; a
  grey one that says what is missing does not.
- **Status by colour and word,** with one meaning per colour across the form.
- **A tag never squeezes the text beside it.** Put it under the description.
- **An icon must mean something at a glance.** If it needs explaining, use a word.
- **One message, one look.** The same warning in two formats reads as two bugs ([08](08-PITFALLS.md)).
- **Keep the promise of the previous page:** a tile's title is the title of the page it opens.
- **Numbers line up:** `font-variant-numeric: tabular-nums`, one alignment per column.

## 12. Working next to other editors

Forms get saved in the designer by colleagues while you work, and a designer save can change more than
its author intended ([08](08-PITFALLS.md)). So:

- Compare the live code with your `dist/` before you rebuild. If they differ, someone shipped after
  you, and a rebuild would overwrite it. Find out what changed first.
- Treat the form as the truth and your sources as a proposal: fresh GET, then write.
- A form that has no sources next to it can still be read: `form-get-code` gives its CSS and JS.
