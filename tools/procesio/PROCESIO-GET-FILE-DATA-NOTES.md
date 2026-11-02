# Get File Data, and a criteria loop over spreadsheet rows (measured 2026-10-29)

How to read an Excel or CSV workbook into a typed list with the `Get File Data` action
(`21fd98d3-4357-475c-a691-06ab992f10a0`), and the designer checks a row-by-row "alert on the rows that match"
flow runs into. Measured on a live workspace with a five-row `.xlsx` written by openpyxl.

## The action

- Three settings: `File to process:` (a File variable, `d6c23275-…`), `Store data as` (a LIST variable of a data
  model, `3d670c16-…`) and `Column Definition` (`a0973f35-…`): one row per column, the workbook's header text
  mapped to an attribute of that model. Header text must match exactly; a duplicate header imports only the first.
- String and number cells both come back (prices as numbers, names as strings) from an openpyxl-written `.xlsx`,
  unlike `Read Range`, which reads string cells of such a file as `""` (see PROCESIO-API-NOTES.md, "CSV/XLSX
  read-actions"). For a list of typed rows, Get File Data is the better reader.
- A Double attribute fed `1250` reads back as `1250` (no `.0`) when inserted into text, while a Double PROCESS
  VARIABLE with default 500 renders as `500.0` in the same text. Keep amounts that go into an email in the row.

## Building it over the API: the builder writes Column Definition only half

`process-create` with `"Column Definition": {"value": [{columnName, attribute: {attributeId, nextAttribute}}]}`
saves, but the designer flags `REQUIRED` on badge "Get File Data - column definition". Two layers must carry it
(shape read from a designer-saved export):

- parameter: `variable: [{id: 2, variableId: <the Store data as variable>, attribute: null}]`, value = the list above;
- designer layer (`customData.configuration[].settings[]` with id `a0973f35-…`): `value: {variable: <same id>,
  rows: [{id: <new guid>, columnName, attribute: "<variableId>.<attributeId>"}]}`.

GET the process, patch both, set `isValid: true` (client-set; a run is refused with 373 "Process needs to be valid"
otherwise) and PUT it back. After that FE validation is clean and `run-process-with-file --file var=path` works.

## Loop and decision checks the designer applies (the API gate does not)

- The last action inside a `For Each` must connect back to the For Each; without it BE answers 391
  "Action has too few output ports." on that action.
- A Decisional condition comparing a Double attribute with an Integer variable passes BE validation and
  `process-fe-validate`, yet the designer's Validate reports "Please make sure condition's types match." and Run
  stays disabled. Give both operands the same type (Double and Double).
- A Decisional with one case and no Default inside a For Each moves on to the next row when the case is false; no
  second branch is needed.
- Opening a Send Email or Decisional properties panel in the designer marks the process changed: Run is disabled with
  the tooltip "Please validate the process to ensure consistency checks before running." Validate, then Save, then Run.

## Running it from the designer

The Run dialog shows a File input as a drop zone with a "Choose file" button. No `<input type=file>` exists until the
button is clicked, and a synthetic drop event on the zone is ignored. For a scripted recording see
tools/tutorial-capture/TUTORIAL-CAPTURE-RECIPE.md (file pickers).
