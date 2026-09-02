# Building a PROCESIO card end to end — findings from the build loop

Mechanics learned while shipping a two-process card with forms, a scripted engine and an
oracle-checked acceptance pass. These are the things that cost time and were not already
written down. Companions: [PROCESIO-RECONCILIATION-PATTERNS.md](PROCESIO-RECONCILIATION-PATTERNS.md)
(what to build), [PROCESIO-FORM-API-HANG-NOTE.md](PROCESIO-FORM-API-HANG-NOTE.md) (the form
read hang), [PROCESIO-NODE-MODULE-WHITELIST.md](PROCESIO-NODE-MODULE-WHITELIST.md).

## 1. Scale every factor KIND separately, not just money

"Integer minor units for money" is necessary and not sufficient. The moment a figure is
produced by **multiplying two configured values**, each needs its own integer scale, or the
product re-introduces the float error the minor-unit rule exists to remove.

A default factor times a country multiplier is the canonical case: `11.2 * 1.15` evaluates
to `12.879999999999999`, and any downstream exact-equality assertion then fails on a figure
that is arithmetically right. Give the multiplier its own scale — **basis points, x10000** —
and do the multiply as integers with a rounded integer divide:

```js
var factorMilli = divRound(baseMilli * markupBp, 10000);   // 11200 * 11500 / 10000 = 12880
function divRound(a, b) { return Math.floor((a + Math.floor(b / 2)) / b); }  // positive only
```

Pick the scale from the value's own precision (quantities in thousandths, rates in
thousandths, percentages and multipliers in basis points, money in cents), multiply into a
wider unit, and divide only at render. Check the widest product against `2^53` and put a row
limit in front of it, so a file large enough to break the assumption is refused rather than
silently wrong.

## 2. Never let a generated script's escape sequences cross a shell layer

Generating Node source from a script is the right way to keep the deployed code identical to
the locally tested code. But a `\n` written inside a JS **string literal** can be collapsed
into a real newline by an intervening shell, heredoc, or quoting layer. The result is a
literal that ends mid-string, and the failure surfaces as `SyntaxError: unexpected end of
string` at a line number that looks unrelated to the edit.

**Rule:** write the generator as a **file** and execute the file — never pipe the generator
source through a shell heredoc. Inside the generator, represent the escape as a token and
substitute it at write time, so no layer can interpret it:

```python
NL = chr(92) + "n"                       # the two characters \ and n, as JS source
src = template.replace("~NL~", NL)
assert "~NL~" not in src
```

Then assert the property you care about after writing: the file should contain **zero raw
newlines inside string literals**, which a grep for the escape sequence confirms cheaply.

## 3. A date control submits a LOCALISED display value, not an ISO date

A `datetime-input` bound to a string process variable does not necessarily deliver
`YYYY-MM-DD`. Given an ISO default it can render and submit a localised display value
(`"1 July 2026, 04:00"` — note the time, which is a timezone offset applied to midnight).
An engine that validates `^\d{4}-\d{2}-\d{2}$` then rejects a period the user set correctly.

Normalise defensively at the top of the engine: accept an ISO date, an ISO datetime, the
`DD/MM/YYYY` display form, and fall back to date parsing for anything else — reading the
result back in **UTC**, so an offset cannot shift the day across a period boundary. Keep a
clear fatal for what still will not parse, quoting the raw value.

This class of defect is invisible to an API-side test, because a programmatic submission
passes the payload directly and never exercises the control's own formatting. Only opening
the rendered form shows it.

## 4. The same flow comes back in two different casings

`GET /api/Projects/{id}` returns the flow **camelCase** (`variables`, `actions`, `name`,
`id`, `type`). The Transport **export** (`POST /api/Transport/export-entities`) returns the
same structure **PascalCase** (`Variables`, `Actions`, `Name`, `Id`, `Type`). Any tool that
reads a flow from both sources must accept either; a checker written against one silently
sees zero variables from the other and reports a clean pass over nothing.

## 5. Form event map rows are `left` / `right`, and `right` must have four segments

In the built form DTO, an `inputMap` / `outputMap` row is `{id, left, right}`:

- `left` — the **process variable GUID**
- `right` — the **form value path**, `formId.FIELDS_NS.elementId.valueConfigId`

A row whose `right` is still a raw field **name** is accepted by the API, renders blank in
the designer, and never carries a value. Assert `right.split(".")` has **exactly four**
GUID-shaped segments for every row, and that `left` resolves to a real variable of the right
direction (inputs to input variables, outputs to output variables). This is cheap, reads
only the DTO, and catches the whole class before a single run.

## 6. A file output and a JSON output look identical in a run result

In `run-process-with-file` output, a File variable arrives as an object
(`{id, name, mimeType, size, path, hash}`) — and so does a `json` machine-channel variable.
"Count the object-valued outputs" is therefore not a way to count produced artefacts, and an
assertion written that way fails the moment a structured output is added. Assert the file
variables **by name**, and check `size` is present and non-zero.

## 7. Form-level CSS is NOT a low-risk surface. A bad `Data.code` blob kills the form

Form-level CSS and JavaScript share one storage slot: `Data.code`, AES-encrypted with the
`procesio / form-code-key` passphrase. It is tempting to treat CSS as the safe half of that
pair, on the reasoning that the worst a stylesheet can do is look wrong. That is not the
failure mode.

If the public renderer cannot decrypt the blob it throws **`Malformed UTF-8 data`** out of
`FormWrapper.component` and **never mounts the form at all** — a spinner forever, every
control gone, the page unusable. Not "unstyled": absent. A form created with `code: ""`
renders perfectly; the same form with a `css` string can be dead on arrival, so this is
easy to introduce while believing you took the cautious option.

Combined with the `form-get` hang (every read-modify-write form action inherits it, so a
form gets ONE authoring pass over the API), the rule is:

> **Do not send `css` or `javascript` on a form you cannot afford to rebuild.** Express
> styling through `theme` and per-element `style` configs, which are ordinary DTO fields
> and cannot break the render.

Diagnose it from the browser console, not the API: creation returns a normal id and
`form-list` shows the form present and published. Only the console says why the page is
blank.

**What per-element `style` can and cannot reach.** It does apply: a `--c-input-background`
set on a textarea resolves on `.pds-c-input-group--wrapper` at runtime. But the design
system paints that wrapper's `background-color` from its own rule, so the variable is
plumbed and ignored, and the pane stays white. Colour vars must reference a theme variable
rather than a hex, so redefining a neutral in `theme` and pointing the element style at it
is the legal path — it just will not repaint a surface the design system hard-codes. Verify
the computed `background-color`, not the custom property, before believing a colour landed.

## 8. Prove the engine off-platform, in a real JS engine

The Node sources can be exercised locally under an embedded JS engine (Duktape via `dukpy`
installs from a wheel on Windows; a native-build engine such as `quickjs` needs a C++
toolchain and is not worth the dependency). PROCESIO wraps a Node action's code in a
function, so top-level `return` is legal there; locally, wrap it explicitly:

```python
dukpy.evaljs("(function(){\n" + src + "\n})()")
```

Duktape is ES5.1, which is a useful constraint rather than a limitation: writing the engine
in ES5 keeps it inside what the sandbox reliably supports, and every logic defect surfaces
in a sub-second local run instead of a multi-minute platform round trip. Feed the same
source files to both, so what runs on the platform is byte-for-byte what was proved off it.

Assert the OUTPUT, not the call: open a generated workbook with a real reader and read the
figure back out of the file. "It returned base64" and "it produced a workbook" are different
claims, and only the second one is worth making.
