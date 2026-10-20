# PROCESIO — HTML to Word (.docx) inside a process

How to produce a real Word document from the same HTML that `Generate Document` turns into a
PDF, and the platform facts that decide the design. The converter is
[`assets/html2docx/html2docx.js`](assets/html2docx/html2docx.js), guarded by
`tests/test_html2docx_asset.py`.

## Why the obvious routes fail

- **`Generate Document` has no Word output.** Its `Save document as` select offers exactly
  `PDF` (value `1`) and `HTML` (value `2`). There is no DOCX option to switch to.
- **Saving the HTML bytes as `.doc`/`.docx` does not work.** `String To Base64` -> `Base64 To
  File` with a `.docx` name gives Word a file it either refuses (a `.docx` must be a zip) or
  imports through its HTML importer (`.doc`). That importer ignores most class-based CSS from a
  `<style>` block, so a document styled the way generated HTML usually is (classes, `colgroup`
  widths in %, wrapper padding) comes out with wrong fonts, margins, table widths and spacing,
  while the PDF of the same HTML looks right.
- The PDF side is not a neutral reference either: the PDF renderer receives the HTML after a
  sanitizer that drops the DOCTYPE (so it renders in **quirks mode**: tables reset their font),
  uses **screen** CSS, ignores `@page`, and shrinks the page to fit. Match its layout rules, not
  its pixels.

## The working shape (verified live)

```
html (String) -> String To Base64 --\
                                      >-- Join -> Node (converter) -> Base64 To File -> docx (File)
htmlFile (File) -> File To Base64 --/
```

- Inject the HTML into the Node as **base64 inside double quotes** (`var HTML_B64 = "<%0%>";`).
  Base64 has no quote, backslash, backtick or `${`, so it is the one string form that cannot
  break or inject into the script. The converter decodes it.
- **`String To Base64` encodes UTF-8.** A Romanian contract with diacritics converted through
  the live process produced a `word/document.xml` byte-identical to a local run on the same
  file.
- Options travel as one **Json** input injected as `[<%1%>][0]`, which is `undefined` when the
  caller sends nothing (a bare null injection is a syntax error, see
  PROCESIO-NODE-CODE-NOTES.md).
- The Node **returns the .docx as one base64 string** in `Single Result` (500 KB+ works) and
  writes a JSON report with `console.log`, which lands in the Node's **`Stdout`** output
  property (a string, with a trailing newline). A Node has no other second output.
- A **rule `Decisional` with `IS_NOT_EMPTY` on a File variable** routes correctly: a file
  goes to the first case, an unset file falls through to the next case.
- **`Stop` accepts one input.** Wiring several branches (success, two `Throw`s) straight into it
  fails backend validation with statusCode `383` "Action has too many input ports.". Converge
  them on a `Join` first.
- A 200-270 KB contract converts in about 0.2 s inside the Node; set `Timeout` well above that
  anyway (180) for documents with many images.

## What the converter does (so a change keeps the same rules)

- Parses HTML, applies a browser default sheet, presentational attributes (`align`, `bgcolor`,
  `border`, `cellpadding`, `width`, `<font>`), every `<style>` block and inline styles with
  normal CSS precedence (specificity, order, `!important`). Media queries are evaluated as
  **screen** at A4 width, like the PDF renderer; `@page` is still read from `@media print`
  blocks, because that is where authors put page setup.
- **Page margins** = `@page` margins (default 1 cm, the PDF renderer's) **plus** the horizontal
  margin/padding of `body` and of a single wrapper element under it. Folding the wrapper into the
  margins gives an editable Word document instead of every paragraph carrying a left indent.
- **Line spacing:** a unitless CSS `line-height` L becomes Word "multiple" `L / f`, where `f` is
  the font's normal line height (Arial and Times 1.149, Calibri 1.2207, ...). CSS 1.241 on Arial
  is Word's 1.08, which is what HTML generated from a Word original carries.
- **Tables:** fixed layout on a twips grid; widths from `<col>`, then cells, then a content
  estimate; `%` widths and margins resolve against the containing content width; negative
  `margin-left` becomes a negative table indent; `rowspan`/`colspan` become `vMerge`/`gridSpan`;
  `thead` rows repeat as header rows; cell padding becomes per-cell margins.
- Paragraph margins collapse the CSS way (max of adjacent margins), because Word adds spacing
  after and before instead of collapsing them.
- `page-break-before/after: always` -> `pageBreakBefore` (a 1 pt paragraph carries it in front
  of a table); `page-break-inside: avoid` -> keep-with-next on every paragraph but the last and
  `cantSplit` rows. An empty block with a height becomes an exact-height spacer.
- Inline backgrounds that match a Word highlight colour (`#FFFF00` ...) become highlights, so
  placeholders stay one click to clear; other colours become run shading.
- Images: base64 data URIs (PNG, JPEG, GIF, BMP) are embedded with their CSS size. `https`
  images are fetched only when the caller opts in with `fetchImages: true` AND the sandbox
  allows `require('https')`; by default (and always inside the platform sandbox, which blocks
  `require`) a remote image is left as its `alt` text and the report lists a warning. Opt-in is
  the safe default on purpose: the fetch retrieves whatever URL the HTML names, so enabling it
  on untrusted HTML where `require` resolves is a server-side-request-forgery vector.

## Known limits

Flex and grid lay out as stacked blocks, floats and absolute positioning stay in flow, inline
SVG is not drawn, `::before`/`::after` content is ignored, and side-by-side `inline-block` boxes
stack vertically. Write HTML meant for both PDF and Word with tables for side-by-side layout.
The converter flags flex, grid, float and inline SVG in the report `warnings`, so the author
sees why a layout stacked instead of guessing.

## Updating the converter in a live process

The Node `Code` is the asset file between a first-line `//` comment and this wrapper:

```js
var HTML_B64 = "<%0%>";          // bound to the html_b64 variable
var OPTIONS = [<%1%>][0];        // bound to the options (Json) input
var res = H2D.convert(HTML_B64, OPTIONS, true);
function done(r) { try { console.log(JSON.stringify(r.report)); } catch (e) {} return r.base64; }
return (res && typeof res.then === 'function') ? res.then(done) : done(res);
```

Rebuild the process with `process-edit` (the builder writes both the runtime and the designer
copy of the code). Never write a `<%` sequence anywhere in the asset, comments included: the
platform substitutes it textually. The test enforces this.

## Verifying a result

Open the generated file in real Word and export it to PDF, then compare page by page with a
browser print of the same HTML (headless Chrome `--print-to-pdf`). A `.docx` that only passes a
zip/XML check can still be one Word refuses or repairs.
