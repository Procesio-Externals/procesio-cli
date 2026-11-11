# Changelog

All notable changes to PROCESIO CLI + Agent are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is generated into the public repository from the PROCESIO monorepo; edit it
there, not here.

## [Unreleased]

### Added
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

### Changed
- The plugin runs procesio-cli 0.1.6 (`plugin/pyproject.toml` and `plugin/uv.lock`).
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

### Fixed
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
