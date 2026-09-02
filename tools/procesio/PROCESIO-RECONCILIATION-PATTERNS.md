# Reconciliation flows in PROCESIO — patterns that survive an auditor

Cross-cutting build patterns for any flow that compares two datasets and reports what
disagrees (VAT/tax returns vs invoices, bank statement vs ledger, stock file vs count,
payroll vs contract). Learned building a two-CSV reconciliation with a report output.
Companion notes: [PROCESIO-NODE-MODULE-WHITELIST.md](PROCESIO-NODE-MODULE-WHITELIST.md)
(what the Node sandbox can do), [PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md](PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md),
[PROCESIO-FORM-API-HANG-NOTE.md](PROCESIO-FORM-API-HANG-NOTE.md).

## 1. Integer minor units, always. Never floats.

Money in a reconciliation is compared for **exact equality**, and binary floats make that a
lottery: summing 472.50 + 682.50 + … and subtracting produces `315.00000000000006`, so a
"zero delta" test fails intermittently and a report shows a delta that is not real.
**Multiply every amount by 100 (or the currency's minor-unit factor) and round to an integer
at PARSE time; do every sum, comparison and delta in integers; divide by 100 only at
render.** The tolerance parameter converts to minor units too. This single decision removes
an entire class of flaky-test and wrong-report bugs.

## 2. Deduplicate BEFORE grouping — and prove the order

If duplicates are collapsed *after* the per-category totals are computed, the duplicate is
silently absorbed and the report shows a **plausible but wrong** delta. The order must be:
filter → classify duplicates → deduplicate → group → sum → compare. Engineer a fixture whose
pre-dedupe delta differs from its post-dedupe delta, and assert the post-dedupe number; the
two figures being different is what makes the test able to fail. Keep the raw (pre-dedupe)
total in the report as its own column so a reader can see what was removed.

## 3. "Duplicate" is three different findings, not one

Grouping rows by their business key and calling every repeat a duplicate destroys real data.
Classify each group, in this precedence:

1. **Any negative amount in the group** → a credit note / reversal reusing the id. Its own
   finding type; **exclude the whole group** from the deduplicated total. Precedence matters:
   check this *before* the identical-rows test, or a reversal pair gets mis-typed.
2. **All rows identical on the identity fields** → an exact duplicate. Safe to collapse; the
   amount counts **once**.
3. **Same id, disagreeing amounts** → a data-integrity **conflict**. Quarantine the whole
   group from the total, list **every** candidate row, and **never pick a winner** — choosing
   one silently invents a number the source does not support.

Define the identity key explicitly and narrowly (id + amounts + category). Descriptive
fields such as customer/description must **not** be part of it, or two legitimate rows that
differ only in a label get mis-classified as a conflict.

## 4. Report an unexplained residual; never name a row you were not given

When one side declares more than the other, you know the *amount* that disagrees, not
*which* documents are missing — the other side's line-item list is not an input. State it as
an **unexplained residual** and describe it as *consistent with* items present in one source
and absent from the other. Naming a specific missing invoice is inventing information; it is
the single fastest way to destroy trust in a reconciliation product. Keep the honesty
requirement in the code path that renders the finding text, not just in the documentation.

## 5. Separate reconciliation findings from structural signals

Two different audiences share one output and must not be mixed. **Findings** = what the data
says disagrees (duplicates, conflicts, residuals, malformed rows). **Advisory/structural
signals** = facts about the run (an optional dimension column was absent, category labels
were normalised, the filtered set was empty). Emitting both in one list makes "exactly N
findings" untestable and makes a clean reconciliation look dirty. Carry advisories in their
own channel and surface them under a "Notes" heading.

## 6. Read the period (and every parameter) from the input, and prove it

A hardcoded period passes every test written against a single-period fixture and fails in
production. Take **start and end dates as separate inputs** (a single "2026-07" string
conflates the filter scope with the report label and hides the boundary rule), filter
inclusively, and keep a separate optional label for the header. Prove it with a test that
re-runs the *same* extract under a *different* period and asserts a *different* result — if
the output is identical, the parameter is not being read.

## 7. Neutralise formula injection at render, not at parse

A CSV cell beginning `=`, `+`, `-`, `@`, TAB or CR is executed as a formula by spreadsheet
applications. Prefix such **string** cells with an apostrophe **when rendering** the report
(leave numeric cells typed), and count what you neutralised so the count can be surfaced and
tested. Doing it at parse time corrupts the comparison logic (the value is no longer the
value); doing it at render protects the reader without touching the arithmetic.

## 8. Quarantine bad rows, don't fail the run

An unparseable date or amount in one row should produce a `malformed_row` finding naming the
row index, field and raw value — and the reconciliation should complete on the remaining
rows. A run that dies on row 3 of 20,000 tells the user nothing; a run that reports two
quarantined rows and a residual that reflects them tells the user exactly what to fix.
Pair this with an explicit **row-count guardrail** that reports a finding rather than letting
a huge file die silently in a sandbox timeout (a timeout is indistinguishable from an outage).

## 9. Free provenance: the File model carries name and hash

A file variable injected into a Node exposes `{name, hash, size, mimeType, id, path}`. Put
the input filenames **and their hashes** on a Summary/Control sheet with the row counts
(total / in-period / quarantined / excluded) and the period. It costs nothing, and it makes
a report reproducible and auditable: the reader can prove which files produced these numbers.

## 10. Structure the outputs so the tests can assert values, not prose

Expose the comparison table and the findings list as **structured output variables**, not
only inside the generated report. Then acceptance tests assert returned values
(`delta_fils == 31500`) instead of grepping a PDF, and the same structure feeds the report
renderer. Report figures in minor units in the machine channel and formatted amounts in the
human channel.
