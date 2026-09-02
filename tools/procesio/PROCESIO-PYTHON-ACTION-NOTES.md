# PROCESIO `Python` scripting action — libraries, I/O, and the model problem

What the platform documents about the **Python** scripting action, and the traps that
follow from it. Everything here is **vendor-documented** unless a line says otherwise;
none of it has been executed against a live instance from this framework. Companion notes:
[`PROCESIO-NODE-MODULE-WHITELIST.md`](PROCESIO-NODE-MODULE-WHITELIST.md) (probed live) and
[`PROCESIO-CUSTOM-ACTION-NOTES.md`](PROCESIO-CUSTOM-ACTION-NOTES.md).

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
> status 50 — the run looks completely healthy while the payload is gone. A
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
> yields `Unexpected identifier` — which is why a string input has to ride inside
> an object wrapper (`{"v": "..."}`) and be unwrapped in the script.

## Preinstalled libraries

`matplotlib 3.7.0`, `beautifulsoup4 4.12.0`, `scipy 1.10.1`, `PyPDF2 3.0.1`,
`pandas 2.0.3`, `pdfplumber 0.11.4`, `spacy 3.8.4`, `staticmap 0.5.7`, `pillow 12.1.1`.

**The same documentation page contradicts this list.** An earlier callout on it says the
Python action "has a list of available libraries to be used: JSON, Base64". Treat the
nine-package table as the current statement and the callout as stale, and **verify by
importing before designing against any of them** — the two readings differ by everything.

**No route to add a library is documented**, and `pip install` appears nowhere in the
documentation corpus. Assume the set is closed.

## What is NOT documented — check before relying on any of it

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

## I/O mechanics — two traps

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

## Working with files — the base64 bridge

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
| `xx_ent_wiki_sm` 3.8.0 | **MIT** (weights) | multilingual, **WikiNER languages — European, no Arabic** | **4**: LOC, MISC, ORG, PER |

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

> ## ⚠ An object-typed input reports its shape as `{}` — and a bare string reaches the API as an empty body
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
> the `Call API` body is null, so the platform posts an **empty body** — and the
> remote service answers **200**. The instance reaches status 50. Read from the
> status alone, the run is indistinguishable from a document in which the
> detector correctly found nothing. The tell is in the response body, where a
> well-built service says so (`warnings: ["empty input"]`, zero chunks). Read
> the body, not the status, and check an early-stage variable — a null where a
> local computation should have produced a value means the input never bound.
>
> The same trap applies to any required object input: a script that validates
> its config (`if (!cfg || !cfg.recognisers) throw`) takes the whole chain down
> when the caller omits it, and the run still reports as completed.
