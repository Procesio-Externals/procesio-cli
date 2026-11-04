# PROCESIO `Python` scripting action - libraries, I/O, and the model problem

What the platform documents about the **Python** scripting action, and the traps that
follow from it. Everything here is **vendor-documented** unless a line says otherwise;
none of it has been executed against a live instance from this framework. Companion notes:
[`PROCESIO-NODE-MODULE-WHITELIST.md`](PROCESIO-NODE-MODULE-WHITELIST.md) (probed live) and
[`PROCESIO-CUSTOM-ACTION-NOTES.md`](PROCESIO-CUSTOM-ACTION-NOTES.md).

> **Superseded in part by live runs (2026-10).** The section "Live behaviour of the four
> script actions" at the end of this file was measured on PROD, and it overrides the
> documented I/O below where they differ: Python no longer wraps its output in `{"result"}`.

> ## ⚠ A scripting action that returns an ARRAY must bind "List Result"
>
> Verified live on a `Node` action, 31/08/2026; the property pair is the same
> shape on the scripting actions generally.
>
> A scripting action exposes **two** result properties, and they are not
> interchangeable:
>
> | property | binds |
> |---|---|
> | `Single Result` | a scalar or an object |
> | `List Result` | an **array** |
>
> Returning an array while bound to `Single Result` stores **null**. There is no
> error on the action, no error variable is set, and the instance still reaches
> status 50 - the run looks completely healthy while the payload is gone. A
> sibling action publishing a COUNT from the same object succeeds, which makes it
> worse: the run reports "3 entities" beside a null entity list.
>
> The receiving variable must ALSO be declared `isList: true`. Both halves are
> required and each fails the same silent way on its own.
>
> **Diagnosing it from downstream.** When a later action reports a JavaScript
> parse error such as `Unexpected token ';'`, that is a NULL upstream variable,
> not a syntax problem. `<%N%>` is a TEXTUAL substitution into the script source,
> so a null variable interpolates to nothing and what the engine compiles is
> `var o = ;`. Read that error as "the variable upstream is empty" and look at
> what wrote it. By the same mechanism a raw string interpolates UNQUOTED and
> yields `Unexpected identifier` - which is why a string input has to ride inside
> an object wrapper (`{"v": "..."}`) and be unwrapped in the script.

## Preinstalled libraries

`matplotlib 3.7.0`, `beautifulsoup4 4.12.0`, `scipy 1.10.1`, `PyPDF2 3.0.1`,
`pandas 2.0.3`, `pdfplumber 0.11.4`, `spacy 3.8.4`, `staticmap 0.5.7`, `pillow 12.1.1`.

**The same documentation page contradicts this list.** An earlier callout on it says the
Python action "has a list of available libraries to be used: JSON, Base64". Treat the
nine-package table as the current statement and the callout as stale, and **verify by
importing before designing against any of them** - the two readings differ by everything.

**No route to add a library is documented**, and `pip install` appears nowhere in the
documentation corpus. Assume the set is closed.

## What is NOT documented - check before relying on any of it

- **The Python version.** Stated nowhere. This matters more than it looks: library and
  model wheels pin interpreter and framework ranges, so an unknown interpreter cannot be
  reconciled with a pinned dependency on paper.
- **Network access.** Never mentioned, and no HTTP client is on the list (no `requests`,
  no `httpx`). Do not assume a script can reach out.
- **A writable path.** The docs say plainly that files cannot be added in a Python script.
  Nothing describes a temp directory, a working directory, or a cache.
- **Persistence between invocations.** Nothing survives, as far as the documentation says
  anything at all.
- **Timeout, memory ceiling, payload size.** None documented. The Node action documents a
  timeout; the Python action documents none.

## I/O mechanics - two traps

**Output is whatever the script PRINTS**, wrapped as `{"result": ...}`. To get at the
value, follow the action with a **JSON Mapper** using query `$.result`. Design for that
extra hop rather than binding the Python output directly.

**⚠ Input is textual substitution into the source before execution.** The documentation is
explicit: PROCESIO "replaces the variable with the value of the variable and then utilizes
it within the code". So `x = <%myvar%>` pastes the raw value into the script.

The consequence is the same one recorded for the Node action, and it bites hardest exactly
where scripting looks most attractive: **any script whose input is untrusted, multi-line,
or quote-bearing text is unsafe through a raw scalar substitution.** A stray quote breaks
the script; a crafted string executes. **Pass untrusted text through a JSON or object
channel** so it arrives escaped, and treat even that as unverified until measured.

> ## ⚠ `<%N%>` runs over text it already substituted, which opens a script injection path
>
> Measured on a `Node` action with two Json inputs, 2026-11, by echoing both values.
>
> | variable 0 | variable 1 | what the script saw |
> |---|---|---|
> | `{"text": "x<%1%>y"}` | `1` | `{"text": "x1y"}` |
> | `{"text": "before <%1%> after"}` | `{"marker": 42}` | `Invalid or unexpected token`: the object's quotes ended the string |
> | `{"text": "plain"}` | `{"text": "before <%0%> after"}` | unchanged |
>
> So the placeholders are replaced in index order, and a value holding `<%M%>` with a higher index receives
> variable M at that spot. A value in one variable can therefore close a string and turn the text of another
> variable into code. It needs a script with two or more variables, and text from outside in the earlier one: an
> uploaded file, a form field, a mail, a webhook. A one-variable script is not affected.
>
> **What held up against a test file with this text in its fields:**
> - Neutralise the marker where outside text enters: replace `<%` with `< %` in everything read from the file.
>   Do it in a Python or one-variable Node step, and for every other outside value a later script reads, the file
>   name included.
> - Hand outside text to a script as base64 or inside a Json variable. `String.raw` around `<%N%>` breaks on a
>   backtick in the text, and then every step after it fails too.
> - For several form fields, one `String To Base64` with a template (`<%0%>|~|<%1%>|~|<%2%>`) gives a single safe
>   value for a Node to decode and split. A null variable comes through as an empty string. Put free text last and
>   rejoin it, in case it holds the separator.
> - Because a script error does not fail the run, gate before any write: one step reads the expected output, and a
>   Decisional refuses the write when it is missing. Without this gate a broken check still inserted a row with an
>   empty status and raised a task, and the instance ended at status 50.

## Working with files - the base64 bridge

A Python script cannot open a file. The documented mechanism is a bridge through process
variables:

```
File variable → [File to BASE64] → string → <%var%> → Python script
Python string result → [Base64 to File] → File variable
```

That is the platform's intended file channel for **every** scripting action, not just
Python. It is not a file system, and it makes the file content transit the script's source
text, so the substitution trap above applies to it directly.

## ⚠ `spacy` is on the list; a spacy MODEL is not

This is the trap worth writing down, because "the NLP library is available" reads as a
capability and is not one.

- **`spacy` ships no model.** `import spacy` succeeds and `spacy.blank("en")` gives a
  tokeniser whose `.ents` is empty forever. **A library without a model does no NER.**
- **Models are separate packages** and none is documented as preinstalled. Loading one at
  runtime would need **network** (undocumented) and **a writable cache** (documented
  absent), then would need to survive between invocations (undocumented). `spacy.load`
  takes a directory path, so bytes arriving over the base64 bridge still need somewhere to
  land.
- Sizes are real: `en_core_web_sm` 3.8.0 is **12.8 MB**, `xx_ent_wiki_sm` 3.8.0 is
  **11.1 MB** (measured from the wheels). A model re-fetched per invocation is a cost line,
  not a detector.

**Before promising NER on this route, execute exactly one thing: `spacy.load` on a
plausible model name.** Everything else is downstream of that answer.

### Model facts worth having to hand, all read from the wheels' own metadata

| Model | Licence | Languages | NER labels |
|---|---|---|---|
| `en_core_web_sm` 3.8.0 | **MIT** (weights) | **English only** | 18: CARDINAL, DATE, EVENT, FAC, GPE, LANGUAGE, LAW, LOC, MONEY, NORP, ORDINAL, ORG, PERCENT, PERSON, PRODUCT, QUANTITY, TIME, WORK_OF_ART |
| `xx_ent_wiki_sm` 3.8.0 | **MIT** (weights) | multilingual, **WikiNER languages - European, no Arabic** | **4**: LOC, MISC, ORG, PER |

**Package licence and training provenance are different questions, and a compliance review
will ask about both.** `en_core_web_sm` ships MIT weights and a `LICENSES_SOURCES` file
recording that its training corpus, OntoNotes 5, is **"commercial (licensed by
Explosion)"**. `xx_ent_wiki_sm` is trained on WikiNER under **CC BY 4.0**. Read the shipped
licence files, not the package licence alone.

**Other NER stacks are absent**: no `transformers`, no `torch`, no `gliner`, no `stanza`,
no `flair`. Any design that assumed a transformer-based or zero-shot detector inside the
Python action needs a different home for it.

## Where the compute runs, and why it matters for sizing

A Python action executes **inside the Execution Environment**. An external detector behind
a Call API is I/O wait, which at least raises the question of releasing the EE while it
waits. **In-action inference never raises that question: the EE is held for the whole
computation.** So moving model work into a Python action trades an integration for
occupancy, and the fleet sizing has to be recomputed rather than inherited.

> ## ⚠ An object-typed input reports its shape as `{}` - and a bare string reaches the API as an empty body
>
> Verified live on a `Node`-based flow driven through `run-process`.
>
> `get-process-payload` is the authority on what a process expects, and it
> distinguishes the two cases: a string-typed input renders as `""`, an
> object-typed one as `{}`. An input showing `{}` is **not** a string variable,
> whatever its name suggests, and the scripts downstream will unwrap it (the
> convention here is `{"v": "<the string>"}` unwrapped as `text.v`). Passing the
> bare string instead interpolates unquoted into the `<%N%>` textual
> substitution and the node throws.
>
> **Why this is worth a note rather than a shrug: the failure arrives as a
> plausible success.** Every node in the chain throws, so the variable feeding
> the `Call API` body is null, so the platform posts an **empty body** - and the
> remote service answers **200**. The instance reaches status 50. Read from the
> status alone, the run is indistinguishable from a document in which the
> detector correctly found nothing. The tell is in the response body, where a
> well-built service says so (`warnings: ["empty input"]`, zero chunks). Read
> the body, not the status, and check an early-stage variable - a null where a
> local computation should have produced a value means the input never bound.
>
> The same trap applies to any required object input: a script that validates
> its config (`if (!cfg || !cfg.recognisers) throw`) takes the whole chain down
> when the caller omits it, and the run still reports as completed.

## Live behaviour of the four script actions (measured on PROD, 2026-10)

One probe process with Node, Python, Ruby and Javascript actions, run synchronously, then the
same actions driven in the designer. Everything below was observed, not read in the docs.

**Shared shape.** Node, Python and Ruby have `Code`, `Timeout` (10 to 180 s, default 60),
`Single Result`, `List Result`, `Stdout` and `Error`. Javascript has `Code` and a required
`Output`, nothing else.

| | Node | Python | Ruby | Javascript |
|---|---|---|---|---|
| hand a value back | `return v` | top-level `return v` (the code runs as a function body) | `return v` | `setOutput(v)` |
| what the output variable gets | `v` as is | `v` as is (a list of dicts arrives as a JSON array) | `v` as is | `{"result": v}` |
| print / log | `console.log` -> `Stdout` | `print` -> `Stdout` | `puts` -> `Stdout` | none |
| libraries | `require()` from the documented list | the preinstalled set (`pandas` imported, version 3.0.5, while the docs table says 2.0.3) | gems (`liquid` and `json` used; runtime Ruby 3.3.12) | none: `require` is undefined |
| variables in `Code` | any type | **text variables only** | **text variables only** | any type |

- **Python and Ruby accept only text (String) variables in `Code`.** Binding a Json variable
  is refused on save with statusCode 142 "Data type mismatch" ("Action ... at parameter Code
  has a data type mismatch variable"); the designer flags it as a type mismatch. So hand them
  JSON as a text variable and parse it in the script (`json.loads('<%v%>')`,
  `JSON.parse('<%v%>')`). Single quotes around the placeholder are fine for JSON text with no
  apostrophes; the general text-substitution traps above still apply.
- **Python's old I/O is gone.** The docs still teach "the output is always
  `{"result": ...}`, add a JSON Mapper with `$.result`". Live, a `return` binds raw to
  `Single Result` or `List Result`, and `print` goes to `Stdout`; a script that only prints
  leaves `Single Result` null.
- **A list goes to `List Result`.** A pandas `to_dict('records')` returned to `List Result`
  bound to a `isList` Json variable arrived as an array of plain objects.
- **Errors never fail the run.** A `throw` (Node), `raise` (Python, Ruby) or a timeout sets
  the action's `Error` output and the instance still ends at status 50 (success); the actions
  after it run. Messages seen: Node `throw 'x'` -> `x`; Python -> `ValueError: x (line 1)`;
  Ruby -> `RuntimeError: x`; Node over its Timeout -> `Execution timed out after 10s`; Python
  over its Timeout -> `TimeoutError`. Javascript has no Error output: its failure lands in
  `Output` as `{"error": {"errorMessage", "errorContext", "lineNumber", "columnNumber"}}`.
  So check `Error` (or the Javascript `Output`) before trusting a result; a native `Throw`
  is what fails a run on purpose.
- **docs.procesio.com/how-to/javascript serves the Python article** (its body is the Python
  page), so the Javascript action has no page of its own today.

**In the designer.**
- The code box in the properties panel is narrow; with the cursor in it, **Esc opens a
  full-size editor** and Esc closes it again (the hint under the box says so).
- **Ctrl+I (Cmd+I on a Mac) opens the variable selector** in the code editor: the editor
  registers `KeyMod.CtrlCmd | KeyCode.KEY_I` (and also the Insert key). The picked variable
  is inserted as `<%name%>`; saved, it becomes `<%N%>` plus a variable binding.
- **Test Action** (the vertical tab beside the panel) runs one script action on its own,
  with test values prefilled from the variables' defaults, and it uses the panel's current,
  unsaved code. The result shows as "Test status: Finished" plus one field per bound output.

## Building a PDF/A-3 with an embedded file in the Python action (measured on PROD, 2026-11)

A hybrid invoice (ZUGFeRD / Factur-X) can be built inside this action, no connector needed. Mustang's
embedded veraPDF reported the result as valid PDF/A-3b with 0 failed assertions.

**Probe set, so a gap is not read as a negative.** Python 3.14.6. Imported fine: `PyPDF2` 3.0.1,
`pdfplumber` 0.11.10, `PIL` 12.3.0, `matplotlib` 3.11.1, `bs4` 4.15.0, `pandas` 3.0.5, `scipy` 1.18.1,
`numpy` 2.5.2, `zlib`, `hashlib`, `tempfile`, `base64`, `io`, `json`, `re`, `decimal`, `datetime`,
`xml.etree.ElementTree`. Refused with `import of 'X' is not allowed in this sandbox`: `os`, `subprocess`,
`socket`, `pypdf`, `pdfminer`, `lxml`, `reportlab`, `fpdf`, `pikepdf`, `fontTools`, `saxonche`, `xmlschema`.
So there is no XSLT 2 engine here and an official Schematron cannot run inside the action. Rules have to
be ported, or called as a service.

**Recipe.** Draw the page on a matplotlib `Figure` with `pdf.fonttype = 42` and save to `BytesIO`, which
embeds the shipped DejaVu fonts. Copy the pages to a `PdfWriter`. Add to the catalog: `/Metadata` (an XMP
stream with `pdfaid:part`, `pdfaid:conformance` and the extension schema), `/OutputIntents` with an sRGB
profile from `ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()` (588 bytes, accepted),
`/AF` and `/Names /EmbeddedFiles` pointing at a `/Filespec` with `/AFRelationship`. Set `/Info` to the same
values as the XMP. Hand text in as base64 of a String variable and return the PDF as base64 to
`Base64 To File`. `String To Base64` encodes UTF-8: German umlauts survived the round trip into a file that
passed the official validator.

**Traps, each one found by the PDF/A check, not by the process status.**

| Symptom | Cause | Do this |
|---|---|---|
| veraPDF clause 6.2.11.8, `.notdef` glyph referenced | matplotlib 3.11 forms a ligature ("fi" in DejaVu), which lands in a separate subset as CID 0 under Type 42 | pass `fontfeatures=['-liga', '-clig']` to every text call |
| veraPDF clause 6.8, MIME type missing on the embedded file | `DecodedStreamObject.flate_encode()` in PyPDF2 3.0.1 lost the stream's dictionary entries | add the `DecodedStreamObject` directly, uncompressed |
| same clause 6.8 after that fix | `NameObject('/text#2Fxml')` is escaped again on write and becomes `#232F` | write `NameObject('/text/xml')`, the writer emits `#2F` itself |
| `AttributeError: 'PdfReader' object has no attribute 'attachments'` | not in 3.0.1 | walk `/Root /Names /EmbeddedFiles /Names` to read the file back |
| PDF header is 1.3, no binary marker, no file id | writer defaults | set `writer._header = b'%PDF-1.7\n%\xe2\xe3\xcf\xd3'` and `writer._ID` to a two-item array |

Top-level names are locals of the action's function body, so helpers should return values rather than use
`global`.
