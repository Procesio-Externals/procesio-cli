# File, Excel, PDF and archive actions: measured behaviour

Measured on PROCESIO cloud (2026-10) by running each action in a throwaway process and checking
the output files with openpyxl / PyMuPDF. Companion to `PROCESIO-API-NOTES.md` (the CSV/XLSX
empty-shape section there) and `PROCESIO-GET-FILE-DATA-NOTES.md`.

## Options that are 1-based

- `Encoding` (Read Files Content, Object To File, List To File, File To String) and `Line Ending`
  (Object To File, List To File) are selects whose option values start at **1** (UTF8 = 1,
  Windows CRLF = 1, Unix LF = 2, Mac CR = 3). A value of 0 still runs, but the designer shows the
  field as empty, which looks broken on screen.
- `Keep` in Copy Paste: All = 1, Values = 2 (the default), Style = 3, Formulas = 4. A value of 0
  creates the destination cells but leaves them empty, and the run reports success.

## Excel

- **Export To XLSX** names its only sheet `Sheet1` and writes text cells as inline strings
  (`t="str"`), numbers as numbers, with a header row when `Export header` is on.
- **Apply Formula** writes the SAME formula text into every cell of the range: `=D2*2` on
  `C2:C5` puts `=D2*2` in all four cells, it does not shift references the way Excel's fill does.
  It writes only into cells that already exist; cells the sheet does not have are skipped
  silently and the action still succeeds. The formula must start with `=` ("Invalid formula:
  Formula must start with '='"). No value is calculated: Read Range afterwards returns the old
  cached value under `Values` and the formula (without `=`) under `Formulas`. To fill a column,
  export it first (a placeholder attribute) and use a position-independent formula such as
  `=INDEX(D:D,ROW())*1.19`.
- **Split Workbook To CSV** fails with `Invalid sheet name: <name>!` on any workbook produced by
  Export To XLSX, even after Rename Sheet; the same call works on a workbook written by another
  tool (openpyxl). **Split Workbook** (to XLSX parts) works on Export To XLSX output and names the
  parts `<name>(Part1).xlsx` ... (a header and 4 rows at 2 rows per part gave 3 parts).
- **XLS To XLSX** produces a workbook whose text cells are marked as shared-string references but
  hold the text inline: PROCESIO's own Read Range then fails with `The input string '<text>' was
  not in a correct format.` and openpyxl refuses the file. Numeric cells convert.
- **Get Named Range** returns the sheet and the range (`Prices`, `A1:B3`) of a workbook-level
  defined name. **Get Last Used Row** returns a 1-based row index including the header.
- **Parse OLE Date**: `45580` -> `2024-10-15T00:00:00`.

## CSV and text files

- **Export To CSV**: the `Column order` setting (one column per line) neither reordered nor limited
  the columns in a test; all attributes came out in model order.
- **Read Range from CSV** keys every cell by its column letter (`{"A": ..., "B": ...}`), numbers
  typed as numbers.
- **List To File** writes the items back to back with NO separator, whatever `Line Ending` says:
  a list of three strings became `Ana PopRadu IonescuMaria Stan`; a list of objects becomes
  concatenated pretty-printed JSON objects (`}{`). Use Object To File on the whole list instead
  (a JSON array) when the file must be read back.
- **Object To File** expects a single Object: binding a list of a data model raises the designer's
  data-type-mismatch warning, while a `json` variable holding an array is accepted.
- **Read Files Content** returns a list of the `FileContent` model
  (`a09d55c4-c26a-40b3-951d-77c3d4fffe18`): `{name, mimeType, content}`; binary files come back as
  mis-decoded text, not as an error.

## Archives

- **Zip** takes a list of files (bind a list variable; Split Workbook and Unzip outputs work).
- **Unzip** opens a password-protected zip (ZipCrypto, made with 7-Zip) with the `Password` field.
- **Untar** and **Unrar** (a `.rar` made with WinRAR) return the file list with the right names and
  mime types.

## PDF

- **Merge Files** names the result `<first>.pdf_<second>.pdf.pdf`; **Select Pages** /
  **Remove Pages** append `_Selection.pdf` / `_Leftover.pdf`. A page selection of `1` works.
- **Is Valid (PDF)** returns `Validation Output` (boolean) and `Validation Reason`; it does not fail
  the action. **Is Valid (JSON)** and **Is Valid (XML)** have no output: invalid input FAILS the
  action (`JSON/JArray input is not valid`; for XML the parser message), so they need an error path.
- **Extract Text** gives each word a `Position` in PDF points from the bottom of the page
  (`Xleft`, `Xright`, `Ytop`, `Ybottom`, `Ymid`, `PageRow`, `PageRowWordOrder`).
- **Area Mapper**: a box (`BetweenXLeft/XRight/YTop/YBottom` in the same coordinates, YTop > YBottom)
  plus `MaxNoOfRowsPerTarget` maps reliably; read the coordinates from Extract Text's words.
  `IsOnTheRightOfWord` / `IsOnTheLeftOfWord` did not behave as their names suggest in a test
  (they returned words from neighbouring rows), so prefer boxes.
- **Extract Embedded Files** returns the attached files with their names; **Acroform Insert Image**
  finds the field by name and reports it in `Debug` (`Found on page 1 and updated successfully.`).
- **Extract Embedded Files, measured on real files (2026-11).** Each list item is a `FileDataModel`:
  `id`, `name`, `mimeType`, `size`, `path`, `hash` (the embedded file of a ZUGFeRD PDF comes back as
  `factur-x.xml`, `text/xml`). Behaviour by input:

  | Input | Result |
  |---|---|
  | PDF with attachments | list filled, status 50 |
  | valid PDF with no attachment | action succeeds, the list variable stays **null**, not `[]` |
  | any other extension | action fails: `Pdf file extension should be '.pdf', found => .xml` |
  | damaged PDF | action fails: `Could not find the startxref within the last N characters.` |

  So give the action an `onError` branch (the run then ends at status 50), and read the list in a Node as
  `[<%0%>].flat().filter(Boolean)`: a null variable then gives an empty array instead of the syntax error
  `const e = ;`. Binding a list in a Node's Code raises the designer's data type warning and still runs.
- **To take one file from such a list**, use **Get Element** with its `Result` bound to a File variable. The
  index must be an `integer` variable (a `number` one is refused with statusCode 142). `File To Base64` then
  reads it. On an empty list Get Element fails with `Index exceeds the list's size.`, so find the index first.
- **Is Valid (PDF) checks the extension first**: `Input file extension should be '.pdf', found => .xml`.
- **Hash takes a File directly** (`Input File`, `Hash`: `SHA256`) and returns lowercase hex, equal to
  `sha256sum` of the bytes. Prefer it to hashing base64 in a script, which puts the whole file into the source.
- **Reading the file name in a script:** a File variable arrives in a Node as an object, so `f.name` works.
  Decide by extension from there; the action failures above are then only the unexpected cases.

## Cloud storage

- The AWS S3 actions (Put / Get / Copy / Move / Delete Object, Delete by Keys / Prefix, List
  Objects, List Keys, Object Exists, Get Metadata) take `Access Key`, `Secret Key`, `Region` and
  `Bucket` as plain fields, not a credential.
- **Azure Storage** is one action with an Azure Storage credential, `Resource` (Blob / Container)
  and `Operation`; the Operation list stays empty until a credential is chosen.

## Run view

- File variables appear as named file chips with a download button; a list of files also gets
  **Download all**. A long value is cut to one line; clicking it opens a viewer with the full,
  pretty-printed value and Download / Copy to clipboard buttons (Escape closes it).
