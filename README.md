# PROCESIO CLI + Agent

Command-line tooling and an AI agent for the PROCESIO automation platform: drive processes, forms, documents and custom actions from a terminal or from an AI coding assistant.

Everything here talks to a PROCESIO installation over its public API. You point it at
your workspace, store your credentials in your operating system's own secret store,
and drive processes, forms, documents and custom actions from a terminal, a script, or
an AI coding assistant.

- Platform: https://procesio.com
- API and platform docs: https://docs.procesio.com

## Install

Requires Python 3.11. [uv](https://docs.astral.sh/uv/) is the quickest
route, but a plain virtualenv works the same way.

```bash
git clone https://github.com/Procesio-Externals/procesio-cli.git
cd procesio-cli
uv sync
```

The base install is four packages. Everything heavier is an optional extra, pulled
in only if you use the tool that needs it:

```bash
uv sync --extra browser      # real-browser form testing (then: uv run playwright install chromium)
uv sync --extra excel        # reading .xlsx workbooks
uv sync --extra databases    # SQL Server / MySQL queries (pyodbc also needs an ODBC driver)
uv sync --all-extras         # everything
```

## Connect it to your workspace

Credentials never live in a file in this repo. They go into your machine's own store:
Windows Credential Manager, the macOS login Keychain, or the Linux desktop keyring,
all under the name `agents-and-tools:procesio:<secret>`.

```bash
python scripts/set-credential.py procesio username
python scripts/set-credential.py procesio password
python scripts/run-tool.py procesio check-auth
```

On a headless machine there is no OS keyring to write to. Pick a store explicitly:

```bash
export AAT_CREDS_BACKEND=encrypted-file
export AAT_SECRETS_PASSPHRASE='...'      # or you will be prompted on a terminal
python scripts/set-credential.py procesio username
```

`AAT_CREDS_BACKEND=file` and `=env` read secrets your host or cluster already manages
(a mounted Kubernetes Secret, or one JSON blob) and are read-only by design, so a
container can never pretend to own the store it reads from.

## First commands

```bash
python scripts/list-tools.py                       # what is installed, and is it ready
python scripts/run-tool.py procesio --help         # every action, with its arguments
python scripts/run-tool.py procesio list-processes
python scripts/run-tool.py procesio run-process --id <process-id> --payload '{}'
```

Every tool prints exactly one JSON object on stdout and nothing else, so you can pipe
it straight into `jq` or into another script. Progress and warnings go to stderr.
Failures print `{"error": {"code", "message", "details"}}` and exit non-zero.

## Using it from an AI assistant

This repo is built to be discovered rather than memorised, which is what makes it
usable by an assistant that has never seen it before.

- `CLAUDE.md` carries a generated **capability router**: a compact map from "what the
  user asked for" to the exact command that does it. It is regenerated from the
  manifests with `python scripts/build-router.py`, so it cannot drift from the code.
- `tools/procesio/SKILL.md` is the tool's full manual, also generated from its
  manifest. An assistant reads it instead of guessing at `--help` output.
- `python scripts/list-tools.py` returns the same information as JSON, including which
  credentials are missing, so an assistant can tell "not installed" from "not
  configured yet".

Point your assistant at the repo root and let it run `scripts/run-tool.py`. Nothing
else is required.

### Or connect it over MCP, with no shell at all

There is an MCP server in `webplatform/aat_mcp/`. It speaks JSON-RPC over stdio with
no third-party dependency, and it exposes the whole registry through six generic
tools rather than one per action:

| tool | what it does |
|---|---|
| `capabilities` | list tools, agents and skills, or one capability's full argument schema |
| `run_tool` | run a tool with structured JSON arguments |
| `run_agent` | run an agent |
| `run_tool_confirmed`, `run_agent_confirmed` | the same, including irreversible actions |
| `get_skill` | fetch a skill's markdown |

Because it reads the registry, a tool you add next to `tools/procesio/` appears in
your assistant immediately, with its argument schema, and you write no integration
code for it.

Point your MCP client at the server with an absolute path to this checkout's Python:

```json
{
  "mcpServers": {
    "procesio": {
      "command": "/abs/path/to/procesio-cli/.venv/bin/python",
      "args": ["/abs/path/to/procesio-cli/webplatform/aat_mcp/server.py"]
    }
  }
}
```

On Windows the interpreter is `.venv\Scripts\python.exe`. The key name differs per
client (`mcpServers` for Claude Desktop and Cursor, `mcp` with `"type": "local"` for
opencode), but the command and args are the same everywhere. For a container there is
also an HTTP transport: `python webplatform/aat_mcp/http_server.py --host 0.0.0.0
--port 8901 --token <secret>`, which requires `Authorization: Bearer <secret>` on
every request. Do not bind it off loopback without a token.

**About the safety gate.** `run_tool` refuses an action the reversibility check calls
irreversible and returns `approval_required`, naming the `*_confirmed` path. MCP
clients mark those as ask, so a person approves each side effect and a model cannot
bypass the gate by picking the plain tool. Know what the check is: it matches English
verbs in the action name and arguments. An action whose name carries no verb it knows
comes back reversible, so silence is absence of evidence rather than a guarantee.
Treat it as a guard rail against obvious mistakes, not as a sandbox, and add verbs to
`agents/_lib/reversibility.py` when you find a gap. Set `AAT_MCP_DENY_IRREVERSIBLE`
for a headless run where even confirmed actions must be refused.

## The agent

Beyond the raw API tool there is a build-and-test agent that carries the method rather
than the mechanics: how to build a process properly, how to verify it against a live
run, and which smells to look for in someone else's flow.

```bash
python scripts/run-agent.py procesio guidance          # the playbook and best practices
python scripts/run-agent.py procesio checklist         # the self-test discipline
python scripts/run-agent.py procesio verify --process-id <id>
python scripts/run-agent.py procesio audit --process-id <id>
```

`verify` is the one worth wiring into CI: it validates the process, compares what the
designer shows against what the runtime does, launches it and reads the instance
status back.

## Set up in a browser instead

If you would rather not touch a terminal for setup, there is a local console:

```bash
python dashboard/serve.py
```

It binds to loopback only and opens a page that lists every tool, agent and skill
from the live registry. From there you can store credentials straight into your OS
credential store (they never touch a file), edit schema-validated config, see which
tools are ready and which are missing a secret, and run a tool to check it works.
Nothing you enter leaves your machine.

## Test the form you just built

Building a form is half the job. The agent's playbook is blunt about the other half:
a form is not done until every tab, every control and every event has been exercised
live and the runtime diagnostics are clean. Screenshots hide JS errors, failed
launches and flicker.

```bash
python scripts/run-tool.py web save-session --name mine --url https://forms.procesio.app
python scripts/run-tool.py web run --session mine --url <form-url> --steps @steps.json
```

The result carries a `diagnostics` block: console output, page errors, failed
requests and bad responses. Any page error, any console error, or any 4xx or 5xx on
the form's own calls means it is not done.

## What is in here

Seven tools, two agents, two skills, and two components that are neither. The
registry is the authority on all of it: `python scripts/list-tools.py` prints what is
installed, how many actions each one exposes, and which credentials are still
missing. The counts below come from that listing.

### Tools

Run any of them with `python scripts/run-tool.py <tool> <action> [options]`. An
action is required; `--help` lists the actions a tool exposes.

| Tool | Actions | What it does |
|---|--:|---|
| `procesio` | 379 | The platform API: processes, forms, documents, custom actions, environments, credentials, schedules. |
| `connector-builder` | 54 | Turns API documentation into a compiled PROCESIO custom action. Custom actions are the platform's main extension point, so this is the shortest route from a third-party API to something a process can call. |
| `mysql` | 9 | Query the MySQL database a SQL action talks to, to see what a process actually wrote. |
| `sqlserver` | 9 | The same, for SQL Server. |
| `web` | 7 | Drive a real browser: render, click, fill, screenshot, read runtime diagnostics. |
| `xlsx` | 3 | Read a workbook outside a process. PROCESIO's Node allowlist ships no xlsx library. |
| `framework-map` | 2 | Render everything installed as one bilingual page: `python scripts/run-tool.py framework-map build`. |

### Agents

An agent carries method rather than mechanics. Run one with
`python scripts/run-agent.py <agent> <action>`.

| Agent | Actions | What it does |
|---|--:|---|
| `procesio` | 5 | Build and test: the playbook, the self-test checklist, a verify gate against a live process, and a static audit for inefficiency and robustness smells. |
| `connector-builder` | 4 | Drives the connector loop end to end: gather, plan, generate, compile, improve from the feedback. |

### Skills

Knowledge an AI assistant loads on its own from the description; there is nothing to
run. `python scripts/get-skill.py <name> --content` prints one.

| Skill | What it covers |
|---|---|
| `procesio-expert` | Platform knowledge: capabilities, use cases, feasibility evaluation, implementation practice. |
| `sql-server-optimizer` | Reviews the T-SQL a process runs. Inlining flow variables into SQL text is both injection-prone and the wrong action configuration, and this is what catches it. |

### Two components that are not tools

`dashboard/` is the setup console, started with `python dashboard/serve.py`. It is not
in the registry and does not run through `run-tool.py`.

`webplatform/aat_mcp/` is the MCP server, started by your MCP client rather than by
you. See the section above.

## Layout

```
tools/procesio/      the API client, DTOs, flow model, layout engine, handlers
agents/procesio/     the build-and-test agent and its doctrine
tools/_lib/          credentials, JSON I/O contract, manifest loading
skills/              knowledge your assistant loads on its own
dashboard/           the local setup console
scripts/             run-tool, run-agent, list-tools, set-credential, build-router
registry.py          manifest discovery; nothing has a hardcoded tool list
```

A tool is a directory with a `tool.yaml` manifest, an entrypoint, and a README. The
manifest is the contract: the registry reads manifests, and everything else reads the
registry. If you add a tool of your own next to `tools/procesio/`, it shows up in
`list-tools.py` and in the router without registering it anywhere.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: this repo is generated from an
internal monorepo, so a merged change is copied upstream and comes back on the next
publish. That is invisible to you as a contributor, but it explains why commits here
arrive in batches.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
