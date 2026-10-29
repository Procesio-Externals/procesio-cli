# Changelog

All notable changes to PROCESIO CLI + Agent are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is generated into the public repository from the PROCESIO monorepo; edit it
there, not here.

## [Unreleased]

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
