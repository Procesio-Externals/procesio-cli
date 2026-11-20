# Changelog

All notable changes to PROCESIO CLI + Agent are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is generated into the public repository from the PROCESIO monorepo; edit it
there, not here.

## [Unreleased]

### Added
- Embedding forms in other web pages with the PROCESIO form SDK: `form-embed` checks a form
  can be embedded (public, published, enabled) and what the environment's form runtime
  supports, lists the field names to prefill and the trigger ids a page can run, and returns a
  snippet (html, module, react) or a complete test page. The form guide's chapter 12 and the
  procesio-cli skill cover options, events, prefill, page requests and testing.
- Forms load their data when they open: a form config's top-level `events` are the form's own
  triggers (`load`, `beforesubmit`, `aftersubmit`), and a Data Store READ or saved query on
  `load` fills tables and dropdowns with no click and no process. READ filters take a short
  form (`{"column", "op", "field" | "value"}`), and `rows` aimed at a dropdown fills its
  options. Every form action warns when the form is a draft, which its link does not serve.
- Form Data Store writes are built and checked the way the form runtime runs them: `add`,
  `update` and `delete` map columns to form values and return `success`. The build reads the
  store's columns and refuses an unknown column, an update with no filter (it never changes
  anything) or of a key column, and warns when a delete with no filter maps a non-key column.
  The notes cover multi-statement saved queries run from a form.
- A form build warns when a saved query with no `LIMIT`, or a READ above 200 / 100 rows, fills a
  table or a dropdown (the backend does not limit a form read), and the notes give the
  versions saved form queries need (Web-Api v3.3.0, form-runtime v1.34.0).
- A form that needs Data Store rows reads them itself: a Data Store event on the element
  (READ, or QUERY running one of the form's saved SQL queries), not a process. The guidance
  says so wherever forms are built, and the agent's `audit` reports `datastore-read-only` for
  a process that only reads a Data Store. Measured on production: a saved query answers in
  about 30 ms in one call, the same read through a one-action process in about 270 ms, with a
  process instance per click. Production keeps saved form queries now.
- `node-edit-batch` applies several node edits to a process in one save (one validation, one
  lint, one save), whole or not at all. Every node writer holds a lock on the process from its
  read to its save, in a folder every tool call shares (`AAT_LOCK_DIR`).
- `--brief` on the create and edit actions returns an outline instead of the whole object,
  and `form-update --changes-only` lists what a save changes, value by value.
- The MCP server can publish named tools with their own argument schemas beside the generic
  ones (`AAT_MCP_SURFACE`: generic, typed or both; generic stays the default).
- The form guide has a recipe for a full canvas app inside a form, and notes on showing PDFs
  in your own layout and on checking identity on the server for form-facing processes.
- `web`: a browser that cannot start because Windows blocks Playwright's Chromium comes back
  with the remedy in the error (`details.hint`).
- The MCP bridge's turn log writes JSON lines with the same keys as the platform's services, and
  a tool call no longer re-reads every manifest.
- Process documentation stays true through every change. `process-edit` asks to restate the
  process purpose when actions are added, removed or changed or the inputs/outputs change
  (`PROCESS_DESCRIPTION_REVIEW`), and an area's text when one of its actions changed
  (`AREA_TEXT_REVIEW`); `groups` on an edit works per area (name only the areas a change
  touched, or `remove: true`). The surgical writers (`node-insert`, `node-delete`,
  `node-set-param`, `node-set-query`, `node-replace-text`, `node-add-binding`,
  `node-bind-var`, `node-set-error-port`, `sql-convert`, `variable-*` on inputs/outputs) take
  the same documentation through `--doc` and refuse without it; areas are re-fitted after each
  of them and `node-insert` places the new action in free canvas. A change made by hand in the
  designer after the tool's last save is reported as `ACTION_CHANGED_SINCE_DOCUMENTED`.
  `put-projects` reports the documentation of what it sends.
- Self-documenting processes. `process-create` and `process-edit` write the process purpose
  (`description`), each action's purpose in the process (`actions[].description`, stored as the
  designer's Description field) and, past 3 actions besides Start and Stop, titled areas on the
  canvas (`groups`, drawn as rectangles behind the actions they group). A save without them is
  refused with `documentation_missing`; `--allow-undocumented` saves anyway. An edit keeps what
  it does not restate while it is still true, and asks again for an action that changed, a new
  action, or an area that lost one.
- `process-docs` reads one process's documented intent and gaps; `workspace-docs` does it for
  every process in a workspace.
- `process-screenshot` saves the Process Designer view of a process as a PNG: headless, signed
  in with the profile's own session, every action and area framed at real scale. Areas are
  fitted to where the designer draws an action (its stored position is the icon's top-left),
  so they sit evenly around their actions with every label inside.
- Area shapes follow their actions through `relayout-process`, `layout-flow` and every save
  that arranges the canvas. `flow-lint` reports a `documentation` block, `flow-digest` opens
  with the purpose and the areas, and the agent's `audit` and `verify` report the documented
  intent.
- Forms run saved Data Store queries: `form-create` / `form-edit` author them, an element event
  runs one and maps its rows into a table, and `form-get-queries` reads which elements run each.
  `PROCESIO-FORM-QUERIES-NOTES.md` has the run-time rules.
- `variable-delete` removes an unused variable from a live process.
- The web driver opens one browser per persistent profile (a second Chromium on the same
  profile reset its storage), and a `<profile>.headed` marker makes every opener of that
  profile run headed and off-screen.
- Notes: For Each one-call-per-row pattern, a Node without outbound DNS fetching through Call
  API, per-record settings that travel with the record, what custom-action upload refuses,
  poll windows below the schedule tick, reading outside text without `String.raw`, a form
  input's autofill background, and the Node engine's input-size limit (about 8 MB refused).
- `form-set-element-event --on signed | declined | completed` wires the document-signing
  triggers, and `form-get-element-events` lists them. An event slot saved as a bare list
  no longer makes `form-get-element-events` fail.
- `credential-copy` copies a credential from another workspace into `--workspace-id`. It
  tests the connection there and saves only if that passes, and it refuses a name the target
  already uses. Property values stay in memory: no file, argument or output holds them.
- `procesio server-build` reads the Web-Api build an installation runs (version and commit)
  from its public `/health`.
- Uploads (`run-process-with-file`, `run-form-with-files`) retry with backoff while PROCESIO
  answers 215 `FILE_LIST_LOCKED`. Sign-in refusals 406, 423 and 428 come back as their own
  error codes with a hint.
- `form-create` and `form-edit` warn when the server does not keep a form's saved queries.
- The bundled action catalog has Upload Bulk (SFTP), and the notes list the credential types
  prod offers.

### Changed
- The Claude Code plugin is now skills only. The plugin directory refuses a local MCP server,
  scripts and package files from an organization it has not Verified, so `plugin/` no longer
  starts the server: its README gives the one command that adds it
  (`uvx procesio-cli==0.1.6`). The skills keep only `name` and a one-line `description` in
  their frontmatter, the SQL helpers ship as Markdown, and the capacity calculator stays in
  the repository. CI checks `plugin/` against these rules (`scripts/check-plugin.py`).
- The bundled API reference has PROCESIO's signing corrections. `OrderMode` is gone, a
  signer can send their own signature spot, and 409 712 now means "try again".
- `FORM-DEV-GUIDE/11-DOCUMENT-SIGNING.md` says what the designer and the fill page do.
  It also covers what a process can't do (choose the signers), the statuses, limits and
  error codes.
- A signature spot per signer is optional since form-runtime v1.33.0, so the signing lint
  no longer warns about a signer without one. It warns only about the design that gets
  stuck on a public form: a FILLER with no spot while `setupEditable` is off.
- `PROCESIO-API-NOTES.md` covers custom and tiny URLs in the web app, the slow first load
  of the Completed tab under Assigned to me, and Form Trigger and approval tasks raised by
  a process. `PROCESIO-PYTHON-ACTION-NOTES.md` covers building a PDF/A-3 with an embedded
  file.
- The bundled API reference adds `credentialDefaults`, the credential `label` filter and the
  read-only `be_id` / `be_value` keys, each marked as not on prod yet. Web-Api v3.2.0 ignores
  `label` with no error and returns every row, so don't rely on that filter yet.
- `PROCESIO-CUSTOM-ACTION-NOTES.md` covers Action-Core 2.2: what it adds, and why a package built
  against a newer Action-Core than the host doesn't load.
- A form built over the API gets the designer's full default theme, and its step functions
  (`goToNextStep`, `goToPreviousStep`) can be called from form code.
- `formlint` flags a `type=number` selector, which no longer matches the number field.
- Notes cover the Web-Api v2.79.1 and v2.80.0 step and the later production changes.

### Fixed
- `form-edit` kept a form's own events but left them pointing at the elements it replaced,
  so an onLoad read filled nothing after an edit. It now points them at the rebuilt elements by
  name, and warns about one whose element is gone.
- `form-edit` kept none of a form's own events (onLoad, before and after submit), so editing a
  form whose designer had added one deleted it with no warning. It keeps them now unless the
  config lists `events`.
- A Data Store event no longer reads the left side of its maps as a form field, so a field
  named like an output (`count`) stays as it is; and a saved query run only by a form-level
  event is no longer reported as run by none.
- A process's list output mapped to a dynamic table by name now reaches the table's row
  source. The builder wrote the bare name, so the table stayed empty with no error.
- Form readers accept an event slot stored as a bare list: `form-digest` no longer reads an
  older form as having no process calls, `form-set-element-chains` no longer crashes on one,
  and the linter checks it.
- A list for a repeatable argument (such as `--bind`) reaches the tool as one flag per item
  when it comes from an MCP caller.
- Canvas areas on a crowded canvas: a group's rectangles grow from its first action and never
  overlap each other or cover another area's action, a header that would run into the row above
  is trimmed instead of splitting the group, and an area drawn as more than 2 rectangles is
  reported as `AREA_FRAGMENTED`. Overlapping rectangles read back by wiring, so a re-fit keeps
  each action in its area and leaves no stale rectangle behind.
- The fan-lanes layout pass no longer squeezes a long branch to less than one column per action
  (names ran into each other).
- `process-screenshot` leaves room for the designer's expanded left panel, which hid the left
  part of the canvas.
- `process-edit` stops without writing when the live process can't be read. A failed read used
  to give every variable a new id and left the removal check nothing to compare against, which
  broke every form map with no error. `--dry-run` still previews and names the failure in
  `live_read_failed`.
- `stop-instance`, `get-instance-status` and `get-instance-output` now require
  `--flow-template-id`, and their generated wrappers (plus the data retention delete) require
  `--flowTemplateId`. The API spec marks it optional, but these calls fail without it and the
  errors never name it. A refused stop now says to check that id, and the notes no longer claim
  the API can't stop a run.
- `procesio_get_run_status` and `procesio_get_run_output` take a required `process_id`. Without
  it they could never read a run.
- A Decisional condition joined with "or" was written as NONE, so the engine ignored every
  condition after it. It is written as OR now, and `flow-lint` reports `DECISIONAL_TRUNCATED`
  on a process built the old way.

## [0.1.6] - 2026-11-03

### Added
- `procesio features` lists the optional modules an installation has switched on (Forms,
  Data Store, Execution Environment). Calling a module that is off now fails with the
  error code `feature_disabled` and a hint to check `procesio features`. Before, it was a
  bare HTTP 400.
- Document signing in forms. This adds the `document-signing` element template and
  `procesio form-signing-upload-document`, which stores the PDF a form asks people to sign
  and points the element at it. Lint rules check signing designs, and
  `FORM-DEV-GUIDE/11-DOCUMENT-SIGNING.md` has the recipe.
- A form element spec takes `classes`. It sets the CSS class setting that every control
  now has.
- `web perf-probe --direct` drives the browser in-process while the serializing broker is
  stopped.
- A neutral form kit (`tools/procesio/assets/form-kit/`), a method for redesigning a form,
  and a guide to optimizing a workspace.

### Changed
- When the PROCESIO Web API refuses a request, the error shows the API's own message, code
  and target.
- The form element templates follow ui-builder 1.46.0, which is what forms.procesio.app
  runs. They add icon, side panel, stepper and chart settings.
- The built-in environments are now `Main-PROD`, `Main-QA` and `Main-DEV`. The old
  `Internal-*` names still resolve.
- Node and variable edits keep the canvas layout and the process's stored validity flag.
- `web perf-probe` scales its navigation timeout with the CPU throttle. When another
  process owns the browser session, it says so plainly.
- The setup guide explains that a PROCESIO API key has two parts and that a personal
  workspace needs no workspace id. A note claiming personal workspaces cannot use forms
  has been corrected.
- The endpoint index covers 296 operations. The bundled API reference is split by domain.
- New notes cover the PROCESIO 3.1 and 3.2 production release: the signing contract, Data
  Store collation on new and older stores, workspace refusals and OAuth2 authorization.
- More notes describe what the web app does on screen: the designer, For Each layouts,
  approval forms and the task inbox, webhooks, SMTP and Send Email, and plan limits.
- The plugin runs procesio-cli 0.1.5 (`plugin/pyproject.toml` and `plugin/uv.lock`).

## [0.1.5] - 2026-10-29

### Fixed
- A `{var, path}` binding into a nested model made by "Create from JSON" now resolves.
  Such inner models are private: `GET /api/DataTypes/{id}` answers 400 when asked for
  one directly. The builder now reads their attributes from the parent model.

### Changed
- The plugin runs procesio-cli 0.1.4 (`plugin/pyproject.toml` and `plugin/uv.lock`).
- Notes that named the project a lesson came from now describe it in general terms.
- New notes cover what takes the error path, Throw and the process timeout, how
  Decisional, Join and Delay behave in the designer and at runtime, and private versus
  public data models.

## [0.1.4] - 2026-10-29

### Added
- `procesio node-repair-designer` repairs a process with nodes the designer cannot draw,
  such as a node without `configuration` or one with a shape the canvas does not know.
- `web render-image` renders a local HTML file to a PNG, JPG or WebP of an exact size.
  Pillow is now part of the `browser` extra, because WebP needs it.

### Changed
- A save of a process the designer cannot draw is refused with `designer_unrenderable`.
  That process would still run. Its canvas and every instance view would stay blank,
  though, and nothing else catches it.
- Example environment names in the agent guide, the dashboard and its tests are now
  `Acme-*`.
- The plugin's `plugin.json` sets documentation, support, terms and privacy links. Its
  `pyproject.toml` keeps only `package = false` under `[tool.uv]`.
- New notes cover running and debugging a process, and Process Designer shortcuts.

## [0.1.3] - 2026-10-27

### Added
- A `procesio-cli` command, the package's own name, that starts the chat MCP server, so
  `uvx procesio-cli==<version>` runs it with no extra arguments. The registry entry for
  PyPI uses that form.

### Changed
- The plugin ships `plugin/uv.lock`, which pins its runtime release and every dependency
  with hashes, and starts the server as `uvx procesio-cli==<runtime>`, the bare form a
  plugin directory's locked install accepts.

## [0.1.2] - 2026-10-27

### Changed
- The plugin's launcher is now just `uvx --from procesio-cli==0.1.2 procesio-mcp-chat`.
  The interpreter preference moved to `UV_PYTHON_PREFERENCE` and `UV_PYTHON` in its
  environment, and the pin files are no longer passed from the plugin folder: a plugin
  directory could not verify the version pin through them.

## [0.1.1] - 2026-10-27

### Changed
- The Claude Code plugin moved to `plugin/`. It now installs the exact PyPI release
  (`uvx --from procesio-cli==0.1.1`) instead of building the repository, ships four
  skills and a listing icon, and no longer picks up the repository's agent docs as
  subagents. The marketplace entry points at `./plugin`.
- First release published to PyPI, so `pip install procesio-cli` and `uvx` work without a
  clone.

### Added
- Each release attaches an MCPB bundle and is listed in the official MCP Registry as
  `io.github.Procesio-Externals/procesio-cli`.

## [0.1.0] - 2026-10-27

First public release of PROCESIO CLI + Agent.

### Added
- The PROCESIO CLI: every platform API action as a subcommand, plus a generic `request`
  for anything not wrapped.
- A local MCP server, so an AI coding assistant can drive the platform over stdio.
- Agent Skills carrying the build, verify and audit method.
- Credentials in the operating system's secret store, never in a file.
- Irreversible actions stop and ask before they run.
