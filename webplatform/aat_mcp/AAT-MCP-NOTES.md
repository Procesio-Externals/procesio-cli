# aat-mcp — connection & mechanics notes

Durable notes on how the bridge connects and non-obvious mechanics (Hard rules 6, 7).

## How opencode connects to it

opencode is an MCP **client**; aat-mcp is a **local (stdio)** MCP server. Wiring lives
in `webplatform/spike/opencode.json`:

```json
"mcp": {
  "aat": {
    "type": "local",
    "command": ["<abs>/.venv/Scripts/python.exe", "<abs>/webplatform/aat_mcp/server.py"],
    "enabled": true
  }
}
```

- **Absolute paths** in the command: robust to opencode's spawn cwd, and space-safe
  because each element is a separate argv entry. Machine-local for the spike; the
  container image (spec 05) will use image paths + HTTP transport.
- opencode spawns the server as a child of its own process (started by
  `run-spike.cmd`, which put `.venv\Scripts` on PATH), so the server runs on the
  framework venv. `server.py` and `bridge.py` resolve paths from `__file__`
  (absolute), so cwd does not matter.
- The model is nudged to prefer these tools over bash via
  `webplatform/spike/MCP-HINT.md` (added to opencode `instructions`).

## Protocol

- Transport: newline-delimited JSON-RPC 2.0 over stdio. One JSON object per line;
  responses flushed immediately. stdout is reconfigured to `newline="\n"` so Windows
  does not inject `\r\n` into the protocol stream. **stdout is the protocol channel —
  all logs go to stderr** (`_log`).
- Methods handled: `initialize` (echoes the client's protocolVersion, default
  `2024-11-05`), `notifications/*` (swallowed, no response), `ping`, `tools/list`,
  `tools/call`. Unknown request methods → JSON-RPC `-32601`.
- `tools/call` never raises: tool failures (incl. unknown capability, KeyError) come
  back as `{content:[{type:text,text:<json>}], isError:true}` so the model can read
  the error.

## Capability discovery — why it is narrow

A big tool's full schema is not a large answer, it is NO answer. `procesio` alone is
~369 KB / 379 actions; an MCP client truncates that to a single-line JSON file, and
then `read` (offset/limit sees one line), `grep` (ripgrep refuses a record over 64 KB)
and `bash` (permission-gated) all fail on it. The turn is spent and the model has
nothing. Measured on real autonomous runs: **27% of all tool calls were the model
guessing argument names**, e.g. the same action retried with four different spellings
(`--name`, `--title`, `--datastore_name`, `--workspace_id`) when the manifest said
`--payload`.

So `capabilities` answers narrowest-first:

| call | returns | size (procesio) |
|---|---|---|
| `{}` | compact tool/agent/skill list | small |
| `{search}` | matching ACTIONS, name+description only | ~0.3 KB |
| `{name, action}` | that action's args + the literal call shape | ~1–2 KB |
| `{name}` | full schema, **or** the action-name index if oversized | 11 KB (was 369 KB) |

Three rules that matter when touching this:

- **The degrade is a mechanism, not advice.** The prompt used to carry "NEVER call
  `aat_capabilities` with a name"; transcripts show the model ignoring it and burning
  the turn exactly as described above. Over `AAT_CAPABILITIES_MAX_BYTES` (default
  40 000) the payload becomes the action index plus a pointer to `action=`/`search=`.
  It keys off SIZE, not a tool list, so it covers every tool that grows.
- **Usage errors answer themselves** (`server._usage_help`). On `unknown action` /
  `unrecognized arguments` / `arguments are required`, the failure carries a `schema`
  field with the valid arg names, or `did_you_mean` for the action. The framework
  already held the answer at that moment; it just never said it. One choke point,
  every tool, no per-tool change. Remote errors (HTTP 4xx/5xx) are NOT enriched —
  those are real feedback, not naming problems.
- **Suggestions must survive word order and plurals.** A model writes
  `credential-list` for `list-credentials`; edit distance alone ranks those far apart,
  so `_suggest` compares singularized WORD SETS first and only then falls back to
  `difflib`.

Argument names are returned verbatim from the manifest (`workspace-id`, hyphenated).
Returning the literal spelling is what stops the snake_case guessing — do not
normalize or prettify them.

## Mechanics / gotchas

- **Naming:** the parent dir is `webplatform/`, NOT `platform/` — a top-level
  `platform/` package shadows Python's stdlib `platform` module whenever repo root is
  on `sys.path` (every framework subprocess), breaking keyring/pydantic. Do not rename
  it back.
- **Execution reuse:** `bridge.run_tool/run_agent` delegate to
  `dashboard.server.runner` (`flags_from` + `run_tool`/`run_agent`) — ONE definition of
  "shell a framework script and normalize its JSON". `flags_from` JSON-encodes
  dict/list arg values into a single argv element; the subprocess is a **list** (no
  shell), which is why structured args don't need escaping.
- **Registry cost:** `aat_capabilities` (no name) calls `registry.list_tools/agents`,
  which probes credential presence per secret — a few hundred ms. Fine for the low
  call volume; cache if it ever matters.
- **Creds backend:** `registry` uses `tools/_lib/creds` (Windows Credential Manager
  today). Running the server on another OS needs the creds backend from spec 06.

## Safety gate (spec 03)

- **Code-authoritative, pre-execution** (`gate.py` → `agents/_lib/reversibility`). The
  plain `run_tool`/`run_agent` refuse an irreversible action (verb in the tool/agent
  name or the ACTION name — send-message, delete-messages, issue-invoice) and return
  `approval_required`; the `*_confirmed` tools execute it. Classification is on
  name+action only, NOT arg values (a subject line "please send..." must not trip it).
- **opencode permission keys (namespaced `aat_*`):** `aat_run_tool`/`aat_run_agent` →
  `allow` (the server code-gate refuses irreversible on them), `aat_run_tool_confirmed`
  /`aat_run_agent_confirmed` → `ask` (the human approval), `aat_capabilities`/
  `aat_get_skill` → `allow`. This is why the human gate is unforgeable: the model
  can't self-approve the `ask`, and can't route an irreversible action through an
  `allow` tool (it refuses).
- **Headless fail-safe:** `AAT_MCP_DENY_IRREVERSIBLE=1` makes even the confirmed tools
  refuse — matches `orchestrator drive`'s default when no human is in the seat.

## Status

Spec 02 (B1) transport + surface AND spec 03 (B2) reversibility gate: built +
unit-tested (19 tests) + wire-tested (send refused on plain tool, executes on
confirmed). Tool names dropped the `aat_` prefix (opencode re-adds it → clean
`aat_run_tool`). Pending: live opencode action-count/gate check in the browser, and
HTTP transport (spec 05).
