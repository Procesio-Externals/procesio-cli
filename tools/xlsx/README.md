# xlsx

Read local Excel (`.xlsx` / `.xlsm`) workbooks. No credentials — operates on
local files. Built from a one-off script per the "scripts become tools"
directive, so reading Excel files is now a reusable, registered capability.

Native Google Sheets are read with the **google-sheets** tool; this tool is for
`.xlsx` blobs (e.g. files downloaded from Drive with `google-drive download-file`).

## Actions

```powershell
# List sheets + dimensions
python scripts/run-tool.py xlsx list-sheets --path "C:\path\book.xlsx"

# Read one sheet as a JSON 2D array (empty rows skipped, trailing blanks trimmed)
python scripts/run-tool.py xlsx read-sheet --path "C:\path\book.xlsx" --sheet "Data" --max-results 100

# Dump the whole workbook to readable text
python scripts/run-tool.py xlsx dump --path "C:\path\book.xlsx" --save out.txt
```

## Typical pipeline (Drive .xlsx -> read)

```powershell
python scripts/run-tool.py google-drive download-file --file-id <ID> --save book.xlsx
python scripts/run-tool.py xlsx dump --path book.xlsx --save book.txt
```

## Notes
- Cell values are JSON-safe; dates/times come back as ISO strings.
- UTF-8 throughout (Romanian diacritics etc. are preserved).
- `read-sheet` returns `{sheet, rows, truncated}`; `truncated` is true when
  `--max-results` capped the output.
