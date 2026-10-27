# Form end-to-end verification

## Goal

Create or change a PROCESIO form and prove the user-visible behavior, process triggers, and runtime diagnostics—not merely the form DTO.

## Preconditions

- Identify workspace, form ID or create intent, public/private access, target URL, user roles, bound variables, triggered processes, and expected behavior per control/event.
- Ensure the `web` optional dependency/browser is installed and a dedicated saved session exists when authentication is required.
- Use isolated test data and avoid another person's active browser profile.

## Inspect

1. Fetch the form definition, custom URL, publication/access state, bound processes, and referenced data models.
2. Inventory tabs, controls, required fields, defaults, dynamic data, upload limits, and events (`onLoad`, submit, click, input, focus/blur, row/pagination events where present).
3. Read expected process input mappings and resulting user-visible states.
4. For a synchronous `RUN_PROCESS` event with output mappings, inspect the source-owned form-event result contract maintained beside the form DTO builder when the repository source tree is available. Then inspect the exact process-variable IDs, form field paths, process custom-response mapping, one real process variable-instance shape, and runtime writer contract. A custom response useful to an API caller is not automatically compatible with the form's native output-map writer.
5. When form JavaScript installs persistent UI behavior, confirm its listeners/timers execute in the parent document realm rather than only in the transient trigger sandbox.

## Preview and approval

- Build/edit through the structured form DTO and inspect its dry-run output where available.
- Show access changes, event-triggered writes, notifications, and public exposure before saving or publishing.
- A screenshot mockup is not approval to create or publish a live form.
- State the number of expected external submissions and the complete process-instance tree each submission may create.

## Execute

- Save the form once, re-fetch it, then open the intended URL with the `web` tool.
- Exercise every changed control and event using stable labels/selectors rather than coordinates.
- Test normal, required/empty, invalid, boundary, and role/access paths relevant to the change.
- For native synchronous result rendering, preserve existing direct process outputs and caller semantics. When the runtime writer consumes a variable-instance collection, use a compatible response envelope rather than replacing the established structured response.
- Never persist an access token or credential as a form default, in plaintext JavaScript, or in screenshots/logs.

## Verify

Pass only when all relevant layers agree:

1. Saved DTO matches intended controls, mappings, events, and access.
2. Browser interaction reaches the expected visible state with no page error, console error, failed request, or unexpected 4xx/5xx from the form's own calls.
3. Triggered processes create the expected parent/child instances and outputs/side effects.
4. A synchronous output-map claim is proven by one real native form action: submit/click once, inspect the actual response, and observe the fields update automatically. Do not call the SPA's writer manually, patch the DOM, replay the request, or substitute a previously completed instance.
5. Output-map rows still reference the intended process variable IDs after any process edit, and direct CLI/subprocess callers still receive their established response contract.
6. Reload/back/navigation and repeated submission behavior are understood; duplicate submission is prevented or handled.
7. Private/public access behaves as designed in an appropriate session.
8. Screenshots mask secret fields and evidence confirms no secret default or embedded clear token exists.

## Recovery and cleanup

Close only the browser/session started for verification. Preserve needed evidence before authorized removal of test submissions or fixtures. If exposure is broader than intended, reconcile the target and promptly perform the exact approved access reversal, then verify its state; otherwise request separate approval and report the risk. Follow `references/process-lifecycle.md`: approved containment must not wait for successful output decoding and does not establish business acceptance.

When the form writes the right backend state but fails to render the native response, keep the field gate failed: preserve the successful instance/row, inspect the real response and writer contract, repair the smallest compatible process/form layer, and submit only once under a separately approved remediation key.

## Evidence

Return form ID and URL, controls/events covered, screenshots or DOM text where useful, browser diagnostics summary, exact submit count, parent/child process instance IDs, actual response shape, native output-map result, side-effect proof, secret-exposure checks, and untested device/access paths.
