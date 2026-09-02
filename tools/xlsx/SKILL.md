---
name: xlsx
description: Read local Excel (.xlsx/.xlsm) workbooks - list sheets, read a sheet as JSON, or dump the whole file to text. No credentials.
---

# xlsx

Read local Excel (.xlsx/.xlsm) workbooks - list sheets, read a sheet as JSON, or dump the whole file to text. No credentials.

## How to call it

```bash
python scripts/run-tool.py xlsx <action> [--args]
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

## Actions

| action | required args | what it does |
|---|---|---|
| `dump` | `--path` | Dump the whole workbook to readable pipe-delimited text. |
| `list-sheets` | `--path` | List a workbook's sheets with row/column counts. |
| `read-sheet` | `--path` | Read one sheet's rows as a JSON 2D array (trailing-empty cells trimmed, empty rows skipped). |

---

Generated from `tools/xlsx/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
