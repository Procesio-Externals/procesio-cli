# Setup & Health Dashboard

A local web console for setting up and monitoring the framework. Built for
onboarding: a colleague who has just cloned the repo can see every tool, agent,
and skill, see exactly what each one is missing, and perform every setup action
from the browser instead of the terminal or a chat with Claude.

It is a framework component (like `scripts/`), not a registered tool - it is a
long-running local server, not a JSON-in/JSON-out command. It carries **zero
user data**: all state stays under `context-state-knowledge/` via
`tools/_lib/userdata.py`, so the wipe-safe boundary is intact.

## Launch

```powershell
python dashboard/serve.py
```

It binds to `127.0.0.1` only, prints a URL containing a one-time token, and opens
your browser. Options: `--port <n>`, `--no-browser`, `--host` (loopback only).

> Run it from a terminal (it needs an interactive console for the credential
> store). If you launch it from a detached/service context, force the backend
> with `PYTHON_KEYRING_BACKEND=keyring.backends.Windows.WinVaultKeyring`
> (serve.py already sets this).

## What you get

- **Inventory** - every tool, agent, and skill from the live registry, grouped
  into tabs, each with a readiness dot, its description, and its actions.
- **Credential status** - per secret: present or missing, with a one-click
  **Store** / **update** / **delete**. Values go straight to Windows Credential
  Manager and are never written to disk or logged.
- **Live validation** - beyond "present", each capability with a probe is
  actively checked: **connected**, **invalid** (with the error), or **no live
  probe**. Streams in as results land; **Re-check all** re-runs it.
- **Config editor** - the LLM Providers tab and each config template open a
  validated JSON editor. `llm/providers.json` is schema-checked; every config
  is scanned for leftover template placeholders.
- **Web login** - tools that log in via a browser declare a `web_session:` block
  (ryver-web, whatsapp, quickmail-web, fgo-web, linkedin-web, the *-invoices tools).
  Their card shows a **Connect** button prefilled with the right session name and
  URL - no guessing - and a missing login counts as needs-setup.
- **OAuth** - tools with an `auth-login` action (google-*, linkedin) show a
  **Connect** button on the card; the oauth token/accounts secrets (produced by
  the flow, not typed) are hidden so only the client key is settable.
- **Bootstrap** - on a fresh install a banner offers one-click
  `orchestrator bootstrap --with-templates`.
- **Plain-language status** - each card leads with one line - "Ready to use",
  "Needs a credential", "Needs a browser login", "Needs Google/LinkedIn sign-in",
  or "Not working" - and only shows a live-check row where a probe exists. When a
  check fails, an **Explain** button asks the LLM why.
- **LLM-backed verification & copilot** - once an LLM provider is configured, the
  Context tab summarizes what the store knows, **Explain** judges a failing probe,
  and **Copilot** answers setup questions with one-click suggested actions. All of
  this goes through the provider-agnostic `llm` tool - the dashboard never calls
  Claude or any hardcoded provider.

## The live-validation convention

"Is the credential actually connected?" is answered by a probe resolved in this
order per capability:

1. an explicit `healthcheck:` block in the manifest (a cheap, read-only action),
2. else a conventional `auth-status` action,
3. else **no live probe** (presence only).

A capability with a missing secret is not probed - it is already known
unconfigured. To make a tool live-validatable, add to its `tool.yaml`:

```yaml
healthcheck:
  action: list-users      # a cheap, read-only, side-effect-free action
  args: { limit: 1 }      # forwarded as --limit 1
  label: "list one user"
```

Probes run concurrently, cache briefly, and are single-flighted so a client can
never storm the machine.

## Security model

Single user, own laptop. The server binds loopback only and gates every `/api/*`
call with a one-time token (in the launch URL, then stripped from the address
bar). It is **not** multi-user auth - that is out of scope until a shared/remote
mode is built. No GET ever returns a stored secret value.

## Architecture

```
dashboard/
  serve.py              launcher (venv re-exec, loopback bind, token)
  server/
    handler.py          routing, token gate, JSON + SSE + static
    routes.py           URL -> handler wiring
    inventory.py        read model (in-process: registry + store + providers)
    validate.py         live probes (concurrent, cached, single-flight)
    setup.py            credentials, config, bootstrap, sessions, OAuth
    jobs.py             background jobs for interactive logins
    config_schemas.py   per-config validation (jsonschema + placeholder scan)
    llmtest.py          provider-agnostic tests, context inspect, copilot
    runner.py           subprocess bridge to the framework scripts
    security.py         loopback token
  web/                  vanilla JS + CSS SPA (no build step, no npm)
  tests/
```

Reads are in-process (fast, always current). Anything that runs a tool/agent or
writes a credential goes through the existing scripts as a subprocess, so each
runs exactly as it does from the terminal - the dashboard never reimplements a
tool's logic or credential handling.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest dashboard/tests -q
```
