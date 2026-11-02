# Reading documents with an LLM inside a PROCESIO process (measured 2026-10-29)

How to turn a PDF (an invoice, an order, any business document) into typed data with a model,
and how to decide whether to trust the result. Built and run with the `procesio` tool on
invented documents. Complements the `Extract Text` section of `PROCESIO-API-NOTES.md`.

## The chain

`Extract Text` -> `Node` (rebuild lines, build the request body) -> `Call API` (POST
`/chat/completions` on an OpenAI-compatible endpoint) -> `Node` (parse, check, score) ->
`Decisional` on the score -> wherever the document goes next (a Data Store, a task).

- **The model is called with a plain `Call API` and a `REST API` credential.** The
  `AI OpenAI Compatible` credential type is what `AI Decisional` uses; `Call API`'s
  `Select REST API credentials` takes a `REST API` credential. Bearer auth = `API key authentication`, `Key`
  `Authorization`, `Value` `Bearer <key>`, `Header` true; base URL `https://api.openai.com/v1`,
  endpoint `/chat/completions`.
- **Build the whole request body in the Node and ship it as one string.** Return
  `JSON.stringify({model, temperature: 0, response_format: {type: 'json_object'}, messages})`
  into a String variable and bind it into the RAW body as `<%0%>` (`Request Parameters`
  given as `{template, vars}`). Templating document text straight into a JSON body breaks on
  the first quote or newline. `json_object` mode requires the word JSON in the messages.
- **Keep the instructions in a process variable** and read them in the Node with
  ``String.raw`<%1%>` `` (survives quotes, apostrophes and newlines; not backticks).

## Rebuild the lines before the model sees them

`Extract Text`'s `Text` field concatenates the printed lines with no separator, so a label
runs into its value ("Invoice numberHD-55127"), which costs the model accuracy. Each entry
in `Words` carries `Position` (`Xleft`, `Ymid`, `PageRow`, ...). Grouping by `PageRow`
is NOT enough: words on one printed line that differ in baseline (a bold label next to a
regular value, a two-column header) land in different rows. What works: sort words by
`Ymid` descending, start a new line when `Ymid` moves by more than about 4 points, then sort
each line by `Xleft` and join with spaces. That reproduced every line of multi-column test
invoices.

## The confidence score must come from checks, not from the model

Do not ask the model how sure it is. Compute the score in the second Node from checks the
process can make itself, each failure lowering the score and adding a written reason:
required fields present, every line `quantity x unit price = amount`, lines summing to the
net total, net + VAT = total, the document addressed to your own VAT id, and any business
rule (for example a domestic supplier that should have used the national e-invoicing channel).
Route on the score with a `Decisional` against a threshold variable. Tell the model to copy
values exactly as printed and never to correct or recompute them: a model that "fixes" a
wrong total hides exactly the document a person needs to see.

## Failure handling that is easy to miss

- **An HTTP error answer from the model's API is a success for `Call API`.** A 401 or 429
  comes back in `Response Body` and the run continues (same rule as any `Call API`: only a
  connection failure or time-out takes the error path). Parse defensively: if
  `choices[0].message.content` is missing or not JSON, set the score to 0, keep the API's
  `error.message` as the reason, and send the document to a person. Do not let the parse
  throw: the Node then returns null and every downstream binding is empty (a Data Store
  insert fails on a null primary key).
- **Give the checked result a data model.** A `{var, path}` binding (in a `Decisional`
  condition or a Data Store `dsMap`) on an untyped `json` variable fails the back-end
  validator with `Error converting value "<attr>" to type 'System.Guid'`; the attribute
  path resolves through a data model. Type the Node's output variable with a model whose
  attributes match the fields.
- **Type `Extract Text`'s output variable as a list of `object`**, not a list of `json`: the
  designer-parity check flags `json` ("binds Json; this property expects list<Object>").
  Binding that list into a `Node`'s Code still raises an advisory `TYPE_MISMATCH` in the
  `procesio` tool's FE check ("expects Object"); the back end accepts it and the run works.
