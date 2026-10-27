# Changelog

All notable changes to PROCESIO CLI + Agent are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is generated into the public repository from the PROCESIO monorepo; edit it
there, not here.

## [Unreleased]

### Changed
- The plugin starts its server with `uv run --locked` against `plugin/uv.lock`, which
  pins the runtime release and every dependency with hashes, instead of `uvx` with only
  the top-level version pinned.

## [0.1.2] - 2026-10-27

### Changed
- The plugin's launcher is now just `uvx --from procesio-cli==0.1.2 procesio-mcp-chat`.
  The interpreter preference moved to `UV_PYTHON_PREFERENCE` and `UV_PYTHON` in its
  environment, and the pin files are no longer passed from the plugin folder: a plugin
  directory could not verify the version pin through them.

## [0.1.1] - 2026-10-27

### Changed
- The Claude Code plugin moved to `plugin/`. It now installs the exact PyPI release
  (`uvx --from procesio-cli==0.1.2`) instead of building the repository, ships four
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
