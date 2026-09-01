# procesio-cli

A command-line toolkit for building on the [PROCESIO](https://procesio.com) platform:
an API client that knows the platform's DTOs, auth mechanics, and flow model, plus the
tools around it that you need on your second day.

The toolkit is also designed to be driven by an AI coding assistant. You describe what
you want in your own words, and the assistant calls these tools to produce a working
process.

Licensed under Apache 2.0.

## Contents

The repository ships seven tools, two agents, and two skills.

### Tools

| Tool | What it does |
| --- | --- |
| `procesio` | The platform API: processes, forms, documents, custom actions, and environments. 463 actions. |
| `connector-builder` | Turns API documentation into a PROCESIO custom action. Custom actions are the platform's main extension point, so this is the fastest route from a third-party API to something a process can call. |
| `web` | Real-browser form testing. A form isn't done until every control has been driven live and the runtime diagnostics are clean. |
| `xlsx` | Workbook inspection. The PROCESIO Node allowlist ships no xlsx library, so this has to happen outside a process. |
| `sqlserver` | Reads the SQL Server database a SQL action talks to, so you can see what a process actually wrote. |
| `mysql` | The same, for MySQL. |
| `dashboard` | A loopback-only browser console for setup: store credentials in the operating system's store, edit configuration, see what's missing, and run a tool. |
| `framework-map` | Renders everything installed as one bilingual page. 472 actions, in categories. |

### Agents

| Agent | What it does |
| --- | --- |
| `procesio-expert` | Platform knowledge: capabilities, use cases, feasibility evaluation, and implementation practice. |
| `sql-server-optimizer` | Reviews SQL that a process runs. Inlining flow variables into SQL text is both injection-prone and the wrong action configuration, and this is what catches it. |

## Before you start

You need:

- Python. For the supported versions, see `pyproject.toml`.
- [uv](https://docs.astral.sh/uv/).
- A PROCESIO account and an environment you can call.

Windows, macOS, and Linux are all supported. The test suite runs on all three in CI.

## Install

```bash
git clone https://github.com/Procesio-Externals/procesio-cli.git
cd procesio-cli
uv sync
```

## Set up credentials

Start the setup dashboard:

```bash
python scripts/run-tool.py dashboard
```

The dashboard opens on the loopback interface only. Use it to store credentials, edit
configuration, see what's still missing, and run a tool. It's the shortest path from
clone to a working install.

Credentials never live in the repository. Each one goes into the credential store that
your operating system provides, and the toolkit picks the store for you:

| Platform | Store |
| --- | --- |
| Windows | Credential Manager |
| macOS | The login Keychain |
| Linux desktop | The desktop keyring, both GNOME and KDE |
| Headless | An encrypted file |

A headless server has no session keyring, so the fourth store is a single file encrypted
with a passphrase, using scrypt and Fernet. The toolkit writes it atomically at mode
`0600`. The store is read and write, so storing a credential works there the same way it
does on a laptop. A wrong passphrase raises an error rather than returning an empty
store.

Every credential carries the same identity on every platform:

```text
agents-and-tools:<tool>:<secret>
```

## Run a tool

Every tool runs through the same entry point:

```bash
python scripts/run-tool.py <tool> <action> [options]
```

For example, to render the framework map:

```bash
python scripts/run-tool.py framework-map
```

To list the actions a tool exposes, open the framework map or run the tool with no
action.

## Tests

The repository carries its own test suite, a secret scanner, and a GitHub Actions
workflow that runs both on Linux, macOS, and Windows.

```bash
uv run pytest
```

## How this repository is maintained

This repository is generated, not forked. PROCESIO develops the toolkit in an internal
monorepo and exports it here with a publication tool that copies files byte for byte, at
identical paths. Two consequences matter to you as a contributor:

- A change upstream reaches this repository by re-running one command, so this tree
  doesn't drift out of date.
- A patch you send here is ported upstream by mapping its path, then comes back verbatim
  on the next publish.

Two files in the tree carry marked regions that the export drops. Apart from those, a
public file is byte-identical to its internal counterpart, which is why a patch applies
in both directions without translation.

## Contributing

Issues and pull requests are both welcome.

Keep changes at existing paths where you can. A file that moves, or a new transform
between the two trees, is a file whose future patches stop applying by path alone.

By contributing, you agree that your contribution is licensed under Apache 2.0, under
the terms in section 5 of the license.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
