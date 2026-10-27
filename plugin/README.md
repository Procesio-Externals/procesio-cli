# PROCESIO plugin for Claude Code

Lets your own AI assistant build, run, validate and audit PROCESIO processes, forms and documents.

This folder is the plugin: the MCP server configuration, four Agent Skills and the
listing icon. The code is the `procesio-cli` package on PyPI. `pyproject.toml` names
release 0.1.3, and `uv.lock` pins it and every dependency to exact
versions with their hashes. The server starts as `uvx procesio-cli==0.1.3`,
and an install that honours the lock installs exactly those files and nothing newer.

## Install

```
/plugin marketplace add Procesio-Externals/procesio-cli
/plugin install procesio@procesio-cli
```

[uv](https://docs.astral.sh/uv/) has to be on the machine. On first use, ask Claude to
connect PROCESIO: the procesio-setup skill gives you the command that stores your API key
or password in your operating system's own secret store. You type the secret into your
own terminal, so it never passes through the chat.

## What is inside

- The `procesio` MCP server, 21 tools to build, run, validate and audit processes, forms
  and connectors. It runs locally over stdio, so it works in Claude Code and Cowork.
- Skills: `procesio-cli` (operating PROCESIO through the CLI or MCP), `procesio-setup`
  (credentials and environments), `procesio-platform-advisor` (fit, sizing and
  architecture questions) and `sql-server-optimizer` (reviewing the SQL a process runs).

The credentials it uses are yours and go only to the PROCESIO installation you configure.

Source, issues and the Apache-2.0 licence: https://github.com/Procesio-Externals/procesio-cli.
Platform documentation: https://docs.procesio.com.
