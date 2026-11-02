# Optimizing an inherited workspace (generalized)

The other pattern files describe how we build. This one covers what we learned **changing** a
production workspace someone else built: auditing it, making it faster, making failures recoverable,
and shipping changes without breaking people who use it that day. It contains no client values.

Each entry has **Problem** / **Mechanics** / **When** / **Pitfalls**, plus **Evidence**, which says how
far to trust it: *measured* (seen on a real run), *read* (inferred from a definition), or *built, not
run* (it exists, that path never executed). Treat the last two as proposals until you have seen them work.

---

## A. Know what you have

### O1. A census first, then verify each finding
- **Problem**: a workspace of dozens of processes cannot be read end to end, and impressions from a
  sample are wrong in both directions.
- **Mechanics**, in order:
  1. Dump and digest everything (`flow-digest`, `form-digest`, the schema), as in [00-INDEX](00-INDEX.md).
  2. Count: inline SQL nodes, real error ports, process ids nothing resolves, processes with no caller,
     disabled nodes, Decisionals without a Default, duplicate titles, heap tables.
  3. Tag each finding *verified* or *inferred*, and check every one against the raw definition.
  4. Query the log tables. They show what really happens, and often that the log itself is broken (O7).
  5. Date the findings and recheck before acting on one.
- **When**: before the first change in a workspace you did not build.
- **Pitfalls**:
  - "No caller" does not mean dead: a webhook or a schedule may call it.
  - A digest can hide what the raw form has. Two conditioned events on one trigger looked like a double
    run until the raw form showed their conditions exclude each other.
  - A finding goes stale. One said nothing wrote a date, and a later dump of the process did write it.
  - Findings about a schema apply to the database you read, which may not be the workspace's (O2).
- **Evidence**: measured on one audit (91 processes, 9 forms, 51 tables): 146 of 176 SQL nodes pasted
  values into the text, and 0 error ports across 22 Call API, 30 SFTP and 111 SQL nodes. The `audit`
  action cannot produce these counts yet: see [todo/procesio-audit-census.md](../../../todo/procesio-audit-census.md).

### O2. Confirm which database a process really touches
- **Problem**: a local read profile and the workspace's credential can point at different databases
  with different columns and rows. Every check through the wrong one is false comfort.
- **Mechanics**: compare through the process's own credential. Without direct access, read and migrate
  with `customaction-test --action "Execute Query"`, one batch per call: split a script on `GO`.
- **When**: before you trust any database read, and before writing a migration.
- **Pitfalls**: test and production often differ in exactly the columns you are debugging. Name the
  database in every finding.
- **Evidence**: measured. The local profile read a different database from the workspace's credential.

---

## B. Make it faster

### O3. One call per view, and a read never regenerates
- **Problem**: every `RUN_PROCESS` from a form costs seconds, and a detail view that rebuilds its
  documents on each open pays for that work again on every read.
- **Mechanics**: give each view one process that returns everything it needs. Serve stored artefacts,
  and regenerate only when an input changed.
- **When**: any view that feels slow. Count its calls before you optimize a query.
- **Pitfalls**: a sync step keeps every button disabled for its whole run, so a slow read also blocks
  the page.
- **Evidence**: measured. 3-4 s per call through a form; one view spent 16.5 s of 31.7 s on three calls
  ([FORM-DEV-GUIDE/08](../../../tools/procesio/FORM-DEV-GUIDE/08-PITFALLS.md)). One detail open took ~33 s
  with all buttons locked, because only the terminal status read the stored copy.

### O4. Sync or async: choose on what must happen next
- **Problem**: async returns control at once but leaves later events in the chain racing its outputs.
  Sync is ordered but locks the form.
- **Mechanics**: if a later event in the same chain needs the outputs, run sync. If the user should keep
  working, run async and have the runtime follow the run.
- **When**: every `RUN_PROCESS`.
- **Pitfalls**: our notes disagree on what an async run does to the rest of its chain. Until the probe in
  [todo/procesio-async-chain-probe.md](../../../todo/procesio-async-chain-probe.md) settles it, never let
  a later event depend on an async output. Whether a hidden poll can run during an async run also stays open.
- **Evidence**: measured cost of sync (~33 s locked); the races themselves were read from definitions.

---

## C. Make failures recoverable

### O5. Non-empty is not success
- **Problem**: a subprocess can answer a failure with a filled error envelope. `IS_NOT_EMPTY` passes it,
  and the flow goes on to external writes with empty data.
- **Mechanics**: gate on the envelope's explicit flag (`e_ok`), never on presence.
- **When**: before any external write.
- **Pitfalls**: test the gate with an id that does not exist (O17), not only with a good one.
- **Evidence**: measured. An unknown id returned a non-empty envelope; the stricter check stopped the
  run before its first external call, and run history confirmed it.

### O6. Order the side effects
- **Problem**: a flow that marks the record done and then calls the external system loses the record when
  the call fails: it leaves the list, and nobody can retry.
- **Mechanics**: prepare what can be undone, write externally, commit locally in one transaction, then
  notify. After the external commit nothing is fatal: a failed notification sets a warning output.
  The error message says which side holds the data.
- **When**: every flow that writes to two systems.
- **Pitfalls**: an e-mail sent before a guarded update tells people about a change that may not happen.
- **Evidence**: the failure read from definitions; the new order's failure path measured, its success
  path built, not run.

### O7. A log write that matches nothing fails silently
- **Problem**: an `UPDATE` that hits no row raises no error, so a run log can look healthy while recording
  nothing. Cloned flows make it worse: they keep the old key and the old table.
- **Mechanics**: after cloning a process family, check every table and key name. Check `@@ROWCOUNT` on log
  writes. In an audit, group the log table by status.
- **When**: any process family built by copying another.
- **Pitfalls**: an error write that updates a row the failed step never created is lost too. Create the
  row first (O8).
- **Evidence**: measured. 40 of 40 log rows sat at the initial step. Cause, read from definitions: one step
  keyed on a copied path, one updated the legacy table, one wrote nothing.

### O8. A progress row a screen can trust
- **Problem**: a live progress view needs more than the log of [C5](03-INTEGRATIONS.md).
- **Mechanics**:
  - Create the row at the very start, and write `<step>_running` before each step.
  - Key it on a value that cannot change mid-run; if a step renames the record, pass a separate effective id.
  - Stamp the instance id, so the reader can reject a previous attempt.
  - Read through a small read-only process. Poll one call at a time.
  - Use a soft ceiling ("this takes longer") and a hard one in the page. A process timeout was never seen
    to stop a run, so the page must not wait for one.
- **When**: a run long enough that people would otherwise reload.
- **Pitfalls**: writes done only when a step ends cannot show what is running now.
- **Evidence**: an unknown key returning `{}` and the poll wiring measured. The modal under a real run:
  built, not run.

### O9. A retry needs resume plus an in-flight claim
- **Problem**: a chain-level "done" flag restarts a partial failure at step 1, and two clicks start two runs.
- **Mechanics**: skip completed steps from stored ids, look up before every create ([C4](03-INTEGRATIONS.md)),
  and claim the run with a guarded `UPDATE`, proceeding only if it hit a row.
- **When**: any retry path over external writes.
- **Pitfalls**: "already written, not written again" holds only for what you can look up.
- **Evidence**: read from a built configuration, which still lacks per-step resume and the claim.

### O10. Errors in flows a form calls
- **Problem**: a `Throw` in a form-called flow can leave the form with no output, so the page shows nothing.
- **Mechanics**: write state and return an output instead. Send each error port to a one-line fixed-message
  Node, then a Join and one error card. Branch on `Response Status`, because an HTTP error can skip the
  port. Handle a send loop per item.
- **When**: every flow behind a button.
- **Pitfalls**: the designer refuses a Node bound to an error-port variable, hence the fixed message. One
  bad address can abort a whole send loop.
- **Evidence**: the designer refusal measured; the rest read from definitions.

---

## D. Keep the contracts honest

### O11. A required-field matrix across branches and the writer
- **Problem**: a procedure requires a field in every branch, the client validator checks it in one, and a
  load process can empty the control.
- **Mechanics**: for each field the writer requires, state per branch where it comes from and when it can be
  empty. Test calendar boundaries.
- **When**: any form with branches that feeds one procedure.
- **Evidence**: measured in a run: saves failed at month end, when a load process emptied a date control.

### O12. Browser validation is a courtesy
- **Problem**: step validators in the browser feel like enforcement, and shared version guards can quietly
  leave a step unvalidated in one branch.
- **Mechanics**: the writer procedure re-runs every rule that matters ([04-DATABASE](04-DATABASE.md) §2).
- **Evidence**: ≈0.8 s per step, client-only, measured; the skipped step read from definitions.

### O13. Key people by a stable identifier
- **Problem**: a lookup on name AND e-mail turns a confirmed user into "unknown" after a name change or a
  diacritic.
- **Mechanics**: match case-insensitively on e-mail or `currentUser.id`.
- **Evidence**: read from a definition. Not measured.

### O14. A server-side re-check is a claim check
- **Problem**: a process gets no server-side identity of its caller, so the e-mail it checks comes from the
  browser.
- **Mechanics**: put the caller check in the same SQL as the read or write, and answer not-allowed and
  not-found with the same empty shape.
- **When**: every process behind a public form. It stops the data reaching every visitor by default.
- **Pitfalls**: it does not stop a determined caller who sends someone else's e-mail. Add a log and make
  actions reversible. For data that needs more, consider private forms or per-user tokens (not tried here).
- **Evidence**: measured. A non-agent got `[]`, an agent got its rows, and 16 procedure cases passed. A
  signed-in admin panel was not verified.

### O15. A write procedure answers with the fresh read model
- **Problem**: writing, then reading in a second call, costs an extra call and can show stale data.
- **Mechanics**: return one row with the outcome, the fresh list and the server time. Map a private `THROW`
  number to `CONFLICT` in the `CATCH`, so the page can say that the status moved on.
- **Evidence**: 16 procedure cases on a test database measured. The saved call itself was not.

---

## E. Change it without breaking anyone

### O16. Editing a shared process is a production deploy
- **Problem**: a fix made "for the copy of the form" also reaches every other form calling that process.
- **Mechanics**: list the callers first and back up the flow. For a large change, create side-by-side `(v2)`
  processes, point a form copy at them, and cut over by re-pointing events. Rollback is re-pointing back.
- **When**: every edit to a process more than one form or schedule calls.
- **Pitfalls**: no action lists a process's callers yet; `form-digest --out` does it offline
  ([todo/procesio-audit-census.md](../../../todo/procesio-audit-census.md)).
- **Evidence**: measured. Two fixes made for a copy reached the live form because the process was shared.
  Four v2 processes were created with nothing existing changed; that cutover has not happened.

### O17. The first run of a process with external writes
- **Problem**: the only way to see the success path is to run it, and that may e-mail a real signer.
- **Mechanics**: first run with a key that cannot exist, and prove from run history that it stopped before
  the first external call. Then use a test record with test recipients.
- **Pitfalls**: withhold the success run if test recipients cannot be guaranteed, and say so in the handover.
- **Evidence**: measured for the unknown-key stop.

### O18. Parameterization is a recurring step
- **Problem**: rebuilding a process from an inline config brings pasted values back.
- **Mechanics**: after every create or edit from a config: `sql-parameterize --all`, read `isValid`, run
  `flow-lint`, then run with an apostrophe in a value. Finish with `sql-scan`.
- **Pitfalls**: `verify` and `audit` do not check this today.
- **Evidence**: measured on new processes: lint clean, and an injection string was stored as data.
