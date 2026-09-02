# PROCESIO API corrections register

Places where the platform's own API reference, or the obvious reading of it, is **wrong**.
Each entry is a case where believing the documentation produces working-looking code that
is silently incorrect. Add to this file the moment a correction is found; a correction that
lives only in a chat is lost at the next compaction.

Format: what the reference says, what is actually true, and what believing it costs.

---

## 1. Flow-instance variables come back under `defaultValue`, not `value`

**Endpoint:** `GET /api/FormProcess/{formTemplateId}/{processTemplateId}/{processInstanceId}/variables`
(and the flow-instance variable shape generally).

**The obvious reading:** a variable object carries its runtime value in `value`.

**Actually:** the endpoint returns variable **definitions**. The runtime value is in
**`defaultValue`**. There is no `value` key at all. The object is
`{id, contextId, dataType, type, name, defaultValue, isList, isError, isRequired}`.

**What believing it costs:** every output reads as `None`. That is indistinguishable from
"the process produced nothing" and from "the form is wired to nothing", which is precisely
the defect a form-contract gate exists to catch. So the false reading **manufactures the
exact failure you are testing for**, and it fails in the safe-looking direction: you
conclude the build is broken when it is fine, or you "fix" a non-problem and ship the real
one. Verified live: a run returning status 50 with a fully populated report showed `None`
for all nine outputs until the read moved to `defaultValue`.

**Applies to:** anything reading form or flow outputs programmatically. Flatten to
`{name: defaultValue}` at the boundary so no caller can misread it.

---

## 2. The form launch route's second path segment is the INSTANCE, not the process template

**Endpoint:** `POST /api/FormProcess/{formTemplateId}/{processTemplateId}/launch`

**The reference says:** the second segment is `processTemplateId`.

**Actually:** it is the **published flow-instance id**. The give-away is in the reference
itself: the request body (`LaunchFlowPayload`) already carries `flowTemplateId`, which
would be redundant if the path also carried it. The process-side equivalent
(`POST /api/Projects/instances/{instanceId}/launch`, body `{flowTemplateId, connectionId}`)
has exactly the same shape. Verified live: launching with the instance in that slot
succeeds; the run finishes and its outputs populate.

**What believing it costs:** the submission never runs, or runs detached from the instance
the files were uploaded to, so a form submission with file inputs cannot be exercised at
all. Since that submission is the only test that catches a form wired to nothing, believing
the reference here removes the one gate that finds the defect.

---

## 3. An empty analytics array is not evidence that nothing ran

**Endpoint:** `GET /api/Resources/analytics/instances/{id}/details` (and the `.../processes/{id}/details` sibling).

**The obvious reading:** an empty array means the instance did no work.

**Actually:** the endpoint is **eventually consistent**, so an empty read taken immediately
after a run proves nothing. Worse, it can be empty **permanently**, because analytics recording
is a per-workspace switch that defaults off.

**The rule.** Never call a result void on this endpoint alone. Re-read it, and corroborate
against **`actionsConsumed`** from `GET /api/Projects/{id}/history`. Treat a result as void
**only when both signals agree**: analytics empty on re-read **and** `actionsConsumed` 0. One
signal is an opinion; two agreeing is a finding.

**Measured, 12/08/2026.** Seven instances re-read 10 to 25 minutes after execution:

| Signal | Result |
|---|---|
| `analytics/instances/{id}/details` | `[]`, 0 rows, on all 7 |
| `actionsConsumed` from `/history` | **16** on all 7 |
| Independent proof | all 7 returned complete variable outputs and correct reconciliation figures |

The two signals disagreed on every instance, and the correct verdict was **ran**. Trusting the
empty array would have voided seven good runs.

**Why it was empty, and why re-reading would never have fixed it here:**
`GET /api/ResourceTrackingConfig` for that workspace returns
`isRecordingEnabled: false`, with `timeAnalyticsEndDate` and `timeAnalyticsStorageLimit` both
null. So analytics was not lagging, it was switched off. Check that config before spending time
waiting for a delayed read to fill: with recording disabled, `actionsConsumed` is the only
available evidence that work happened.

**One reader trap worth avoiding.** This endpoint returns a **bare JSON array**, not the usual
`{result: ...}` envelope. Code that does `body.get("result", body)` throws on a list and can be
mistaken for an API failure. Handle both shapes at the boundary.

## 4. Cross-references to corrections held elsewhere

These are documented in full in their own notes; listed here so this register is the single
index.

| Correction | Where |
|---|---|
| `GET /api/Actions?getFullAction=true` stalls while `=false` is fast, **and switching to `=false` is silently destructive** because live stub entries win over complete bundled ones in `catalog_index` | `PROCESIO-API-NOTES.md` |
| Attribute-path binding (`{var, path}`) fails on a schemaless Json object: the API demands the attribute be a DataModel GUID | `PROCESIO-NODE-MODULE-WHITELIST.md` |
| `File To JSON` rejects a `.csv` by extension; the CSV reader is `Read Range from CSV`, which coerces numerics and destroys leading zeros | `PROCESIO-NODE-MODULE-WHITELIST.md` |
| `XLS To XLSX` rejects SpreadsheetML 2003 outright | `PROCESIO-NODE-MODULE-WHITELIST.md` |
| `Send Email` cannot be saved without a bound SMTP credential, by either an empty field or a variable | `PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md` |
| `GET /api/FormTemplate/{id}` never returns, so every form read-modify-write stalls | `PROCESIO-FORM-API-HANG-NOTE.md` |
| Two Decisional branches cannot target the same node: "Duplicate connection port" | `PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md` |
| `POST /api/Transport/import` refuses with `403 "workspace migration"` via the API, while the UI import of the same bundle succeeds | this file, section 5 |
| `POST /api/Workspace` returns HTTP 500 while creating the workspace anyway | this file, section 5 |

---

## 5. Transport import refused, and workspace creation lies about failing

**`POST /api/Transport/import` → `403`, body `"workspace migration"`, while the UI import of
the same bundle succeeds.** Reproduced against three targets: two freshly created
sub-workspaces and **the source workspace the bundle was exported from**. User permissions
are byte-identical across all three, so it is not a role gap, not a plan gate, and not an
artefact of a half-provisioned workspace: importing the same file through the web UI into one
of the refused workspaces worked. It is the documented API path specifically. Export works
normally throughout. ~~**Use the UI for imports until this is resolved.**~~

⚠ **WITHDRAWN 2026-08-24. The 403 was a MALFORMED REQUEST, not a permission gate.** The
same import succeeds through the API with the documented multipart part name
(`importedData`, not `file`) and the seven required boolean headers. The endpoint answers
**403 with body `MIGRATE` on ANY error**, so the status could never have identified the
cause, and the conclusion above was drawn from a request that could not express the
question. Do NOT route imports through the UI on the strength of this section.

### Import preserves identifiers, so cross-object references survive

Measured by diffing the source flow against the imported one (UI import, fresh workspace):

| Carried across unchanged | Evidence |
|---|---|
| Flow id | **not reminted**, identical GUID |
| Variables | 24/24 ids, directions, datatypes and defaults |
| Actions | 19/19 ids, names, and catalogue template ids |
| Parameter values | byte-identical, including a 21,409-character Node body with every `<%N%>` placeholder |
| Injection bindings | 37 variable references, each still resolving to the same variable id |
| Error ports | 3 `variableErrorId` bindings intact |
| Graph | 23 edges identical |
| Form | arrives with its **original id** |

Only `workspaceId` changed. Both a direct run and a full form submission then succeeded in
the destination workspace. **Because ids are preserved rather than regenerated, a form's
input and output maps keep pointing at the right process variables by construction**, which
is what makes multi-object apps packageable at all.

**`POST /api/Workspace` → `500`, body `"Unable to create sub-workspace!"`.** Originally
recorded as creating the workspace anyway: it appeared in `GET /api/Workspaces` and was
usable for reads, and `DELETE /api/Workspace/{id}` also returned `500` with an uncertain
outcome.

**Re-tested later and the create-anyway behaviour did NOT reproduce.** Five attempts across
four request shapes all returned the same 500 and created nothing — the master's
sub-workspace count and the account-wide workspace list were identical before and after. So
this may be fixed, and the 500 may now be a clean refusal.

The discipline stands either way, because the 500 says nothing about the outcome: **treat it
as "unknown outcome, verify by listing", never as a failure**, or a retry manufactures
orphans. Note the message is identical for every input, so it distinguishes nothing — not a
malformed body, not a permission problem, not a quota.

---

## 6. Fingerprinting a flow: hash CANONICALLY, never the raw export bundle

**The obvious reading:** a `.procesio` export is the artefact, so sha256 of that file
identifies a flow version and can gate a change.

**Actually:** the bundle carries a **top-level `TimeStamp` recording when the export ran**,
so two exports of an untouched flow hash differently. A raw-bundle digest can never
reproduce, and a change-detection gate built on it fires on every run.

**Measured, 12/08/2026.** Two exports of the same untouched process, taken about two
seconds apart, were **byte-identical except for `TimeStamp`** (found at offset 193790 of
193807; both files the same length):

| Artefact hashed | Reproduces |
|---|---|
| Raw `.procesio` bundle | **No** |
| Bundle with `TimeStamp` removed, keys sorted (canonical) | **Yes** |
| The `Flows[0]` object alone | Yes |

**The canonical method, use this one.** Parse the bundle, drop the top-level `TimeStamp`,
re-serialise with sorted keys, sha256 that. Corroborate with two signals that do not move
on their own: the flow's `updatedOn` (compare to the second) and the action count.

```python
d = json.loads(open(path, encoding="utf-8").read())
d.pop("TimeStamp", None)
sha = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
```

**Current canonical fingerprints, 12/08/2026:**

| Process | Workspace | Actions | updatedOn | Canonical sha256 |
|---|---|---|---|---|
| WPS SIF Generator `904f9214-0b55-4650-b82c-4ac8a969e4da` | `81e52d67` | 9 | 12/08/2026 05:14:36 | `c5fdbb212f0e7615e87932dfeffb173467eac8bc543cf2abf4a5c295f6ad5c1c` |
| VAT Return Reconciliation `82f58ee9-5ca6-49cc-968a-39d13cef6bd0` (production) | `c567dd33` | 21 | 12/08/2026 04:48:48 | `04973b2768775712805b25a190ca1efe236e995bbdf52a4c12ac8fb760d140bd` |

**What each card had been hashing.** The WPS card hashed the raw bundle, which is why its
recorded digest failed to reproduce on the next session's gate. The VAT card's fingerprints
did reproduce across three readings, and since the raw-bundle digest demonstrably does NOT
reproduce for that process either (measured above), it cannot have been hashing the raw
bundle; it must have hashed a TimeStamp-free artefact. Which one was not recoverable from
local records, so it is not asserted here. Either way both cards now gate on the single
canonical method above.

**What believing the raw-bundle reading costs:** a gate that fires on every run, which
trains everyone to wave it through. That is worse than no gate, because the waving-through
becomes habit before a real change arrives.

---

## 7. `actionsConsumed: null` is NOT `0` (refines correction 3)

**The obvious reading:** `actionsConsumed` is falsy, so no actions ran.

**Actually:** `null` means the instance has **not yet appeared in `/history`**. That is
absence of evidence, not evidence of zero execution. **Only an explicit `0` counts as a
void signal.**

**Both signals lag.** Analytics returns an empty array for a period after a run that
demonstrably executed, and `/history` does not contain the instance at all for a similar
window. **Neither is a reliable immediate check.**

**The void test, complete:** a result is void only when analytics is empty **on re-read**
AND `actionsConsumed` is an explicit **`0`**. One signal is an opinion. Two agreeing is a
finding. A `null` is neither.

**What believing it costs:** code written as `if not analytics_rows and actions_consumed in
(0, None)` condemns healthy runs. Four runs on 12/08/2026 returned `actionsConsumed: null`
purely because `/history` had not caught up, while analytics on re-read showed real rows for
every one of them.

**Not yet established:** the upper bound on either lag. Re-reads used a fixed delay that
worked in every case observed, which is a working figure and not a measured limit. Until it
is measured, "empty on re-read" means "empty after however long I waited".

---

## 8. Fingerprint gate rule: proof, or a hard stop

A fingerprint gate may be passed **only** when the mismatch is PROVEN to be a measurement
defect and the proof is recorded. The proof needs all three:

1. The differing field **named** (e.g. the export `TimeStamp`).
2. The canonical values **shown equal** once that field is excluded.
3. At least **two independent signals agreeing**: `updatedOn` to the second, action count,
   canonical content hash.

**Any mismatch that cannot be explained this way is a hard stop, no exceptions.**

"Fingerprint" always means the **canonical hash, `TimeStamp` excluded** (correction 6),
never a raw-bundle digest.

**Why:** the gate exists to catch a change nobody in this session made. Passing it on
judgement rather than recorded proof removes the only guard against building on top of an
unexplained edit, and it removes it silently.


---

## 9. A 450 on `/instances/{id}/status` means the QUERY was incomplete, not that data is missing

**Endpoint:** `GET /api/Projects/instances/{id}/status`

**The obvious reading:** HTTP 400 with
`{"statusCode":450,"value":"Database requested information not found.","target":"flow"}`
means the instance record is gone, purged, or never existed.

**Actually:** the route **requires a `flowTemplateId` query parameter**. Omit it and
every instance answers 450 regardless of age, terminal status, workspace or credential.
Supply it and the same instance returns HTTP 200 with the full record and populated
variables, including the base64 content of submitted input files.

| Call | Response |
|---|---|
| `/api/Projects/instances/{id}/status` | HTTP 400, statusCode 450 |
| `/api/Projects/instances/{id}/status?flowTemplateId={processId}` | HTTP 200, variables populated |

**What believing it costs.** The message names a database and a missing record, so it
sends the reader after retention, soft-deletion or an existence problem. It cost several
sessions here, and produced a written conclusion that "retrospective instance-variable
reads fail platform-wide", which was **wrong**. The tell was available the whole time:
the tool's own run-poll loop passes `{"flowTemplateId": args.id}` on this exact route,
which is why polling during a run always worked while ad-hoc reads never did. A
difference between code that works and code that does not is worth more than any error
string.

**Two claims withdrawn** from the earlier write-up: `/instances/{id}/output` returns
HTTP 200, not a 500 wrapping a 403; and `/api/Resources/analytics/instances/{id}/details`
can return an empty array for an instance that genuinely ran, because recording is a
per-workspace switch (correction 3).
