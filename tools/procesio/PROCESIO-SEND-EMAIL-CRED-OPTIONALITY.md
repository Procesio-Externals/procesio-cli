# PROCESIO `Send Email` — credential optionality (why a "permanently optional email branch" can't ship credential-less)

Live-probed on the `Send Email` action (`c7673492-…`) while building a **zero-credential**
marketplace template (must import and run with no credentials configured). The question: can
an email branch be built that runs when an SMTP credential + recipient are present and is
skipped cleanly when they are not — inside a template that ships with **no** SMTP credential?
Answer: **no, not via the API.** `Send Email` requires a real, bound SMTP credential just to
**save**. Evidence (each from `process-create --dry-run`, which runs FE then BE validation):

| Attempt | Result |
|---|---|
| `Send Email` with **no** credential bound | **FE blocks**: `REQUIRED` — *"Please make sure that the action is defined/configured properly."* on badge **"Send Email - Select SMTP credentials"**. (BE was empty.) |
| Credential field bound to a **variable** (`{var:...}`) instead of a literal | FE passes, but **BE blocks**: *"Nullable object must have a value."* |
| Bind a **mock/dummy** credential GUID | Rejected by policy — a credential that doesn't resolve is a support ticket on import; never do this. |
| Keep a gated `Decisional` **without** a `Send Email` (both branches → one `Join`) | **BE blocks**: *"Duplicate connection port! SourceId … DestinationId …"* — two ports from one source to the same destination are illegal. |

## Consequences (rules)

- **`Send Email` is only saveable with a real, bound SMTP credential GUID** (a literal
  credential instance id). Neither empty nor variable-bound satisfies validation.
- Therefore, in a template that must run with **zero credentials**, the email node **cannot
  be part of the shipped flow** — and neither can a "placeholder" gated `Decisional`, because
  a Decisional's two branches must go to **two distinct targets**; with no `Send Email` to be
  the second target, both would collapse onto the `Join` → "Duplicate connection port".
- **Ship the flow linear** (no `Send Email`, no decorative `Decisional`/`Join`). Keep the
  optional recipient **input variable** so the future email step has its trigger. The
  zero-config run reaches `Stop` and produces its file outputs with no credential in play —
  outputs never depend on a credential, which is the template standard.
- This is a genuine **template-standard** finding, not a one-card quirk: any credential-less
  marketplace template that wants an *optional* notification must add it **post-import**, not
  ship it dormant.

## Add the gated email branch AFTER import (manual UI recipe, once an SMTP credential exists)

The gated branch *is* valid once there is a credential to bind (case and default then have
two distinct targets):

1. Create/adopt an **SMTP credential** in the workspace (Credentials → new SMTP).
2. On the canvas, after the file-producing step, add a **Decisional** "Has Recipient?" with a
   single case `SubmitterEmail IS_NOT_EMPTY`.
3. In the **true** branch add **Send Email**: bind the SMTP credential; `To = SubmitterEmail`;
   set Subject/Body; **Map attachment = [ExcelFile, PdfFile] as a `list<File>`** (a single
   `File` silently drops the attachment though the run still returns status 50).
4. Wire **Send Email → Join**; wire the Decisional **default → Join**; **Join → Stop**. Two
   distinct targets (Send Email vs Join) — no duplicate-port error.
