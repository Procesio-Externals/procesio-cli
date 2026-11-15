# PROCESIO plugin for Claude Code

Lets your own AI assistant build, run, validate and audit PROCESIO processes, forms and documents.

This folder is the plugin: four Agent Skills and the listing icon. It holds only Markdown, JSON and one image. Nothing in it runs on your computer by itself.

## Install

```
/plugin marketplace add Procesio-Externals/procesio-cli
/plugin install procesio@procesio-cli
```

## Connect PROCESIO

The skills work through the `procesio-cli` command line tool and its MCP server. You add the server yourself, so you pick the exact release that runs. With [uv](https://docs.astral.sh/uv/) on the machine:

```
claude mcp add procesio -e UV_PYTHON_PREFERENCE=system -- uvx procesio-cli==0.1.6
```

`UV_PYTHON_PREFERENCE=system` tells uv to use a Python you already installed. On Windows, that avoids interpreters Smart App Control blocks.

Then ask Claude to connect PROCESIO. The procesio-setup skill gives you the command that stores your API key or password in your operating system's own secret store. You type the secret into your own terminal, so it never passes through the chat.

## What is inside

- `procesio-cli`: building, running, validating and auditing processes, forms and connectors through the CLI or the MCP server.
- `procesio-setup`: credentials and environments.
- `procesio-platform-advisor`: fit, sizing and architecture questions.
- `sql-server-optimizer`: reviewing the SQL a process runs. Its metadata export scripts are Markdown files you copy and run yourself.

Your credentials go only to the PROCESIO installation you configure.

Source, issues and the Apache-2.0 licence: https://github.com/Procesio-Externals/procesio-cli.
Platform documentation: https://docs.procesio.com.
