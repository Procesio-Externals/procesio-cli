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
- Methods handled: `server/discover`, `initialize`, `notifications/*` (swallowed, no
  response), `ping`, `tools/list`, `tools/call`. Unknown request methods → JSON-RPC
  `-32601`. The mechanics live once, in `protocol.py`, shared by both servers; see
  "Protocol eras" below.
- `tools/call` never raises: tool failures (incl. unknown capability, KeyError) come
  back as `{content:[{type:text,text:<json>}], isError:true}` so the model can read
  the error.

## Protocol eras and version negotiation

MCP 2026-07-28 drops the `initialize` handshake. The spec calls that revision *modern*
and everything up to 2025-11-25 *legacy*. In the modern era:

- every request carries its version in `_meta["io.modelcontextprotocol/protocolVersion"]`;
- servers MUST answer `server/discover` (supported versions, capabilities, identity);
- every result carries `resultType: "complete"`, and list results add `ttlMs` and
  `cacheScope`;
- an unsupported version gets error `-32022` with `data: {supported, requested}`.

Both servers are **dual-era over stdio**. A request that names its version in `_meta`
gets the modern shape; anything else gets the legacy shape, unchanged. A modern-only
server would fail every legacy client, and legacy clients cannot fall forward.

**Never echo the requested version.** Both servers used to answer `initialize` with
whatever version the client sent, including dates that do not exist. The client then
believes the server speaks a revision it has never heard of and waits for fields that
never arrive. The answer must come from a list the server implements. `initialize`
always selects the legacy era, so a client asking there for 2026-07-28 gets 2025-11-25.
That case is real: at least one client release proposed the modern version inside
`initialize`.

**How a dual-era client probes** (checked against Claude Code 2.1.284 through a logging
shim). By default it still sends `initialize`. With `MCP_PROTOCOL_NEGOTIATION=auto` it
sends `server/discover` first and falls back to `initialize` on any error that is not a
recognised modern one. So `-32601` on discover means "legacy server", and `-32022` means
"modern server, retry with a listed version". A server that cannot serve modern requests
must never return the second: a public MCP server that did had its client stop seeing
its tools.

**The HTTP transport is legacy-only** (`server.handle(m, modern=False)`). Modern
Streamable HTTP adds `Mcp-Method` / `Mcp-Name` header rules that `http_server.py` does
not implement, so over HTTP discover stays a plain `-32601`. Lift that only together
with the header rules.

**Not used, and deprecated in 2026-07-28 anyway:** roots, sampling, logging and dynamic
client registration. Nothing here should start depending on them.

**The tool-list digest.** `server/discover` reports `_meta["com.procesio/toolsDigest"]`:
sha256 over the canonical JSON of the `tools` array (keys sorted, no whitespace, UTF-8,
non-ASCII unescaped). The procesio-oss exporter writes the same value for the chat
surface into the public `server.json`, which the MCP Registry does not allow to change
after publication. The value a server reports about itself is a label for spotting the
release, not a control - the spec says self-reported server information must not drive
security decisions. The control is a client or gateway hashing the list it actually
received and comparing it with the registry copy. Changing the canonical form in one
place breaks every comparison, so `tests/test_pyoss_pins.py` asserts the exporter and
`protocol.py` agree.

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
| `{search}` | matching ACTIONS; the first three carry their args and whole description, the rest name+description | ~1–8 KB |
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
- **A search answers with what the caller needs next** (`_attach_args`). A lookup runs
  nothing, yet it costs a whole model round trip, and the context is sent again with
  it. A caller that searches then asks for the arguments of a leading match, so a
  compact search answer makes every newly found action cost two round trips before
  the call that does the work. The first `AAT_SEARCH_ARGS` matches (default 3, 0 turns
  it off) therefore carry their args and their whole description, inside one byte
  allowance for the answer (`_SEARCH_ARGS_MAX_BYTES`). Three things keep that from
  growing back into a schema dump: only the leading matches carry them, an action
  whose arguments do not fit stays compact, and a list judged too vague carries none.
  Worked examples stay behind the one-action lookup; a match says `has_examples`.
  Measured on `procesio` over twenty typical searches: the answer grows from about
  2 KB to about 5 KB, and replaces a search plus a lookup that add up to about 6 KB.
- **Count the lookups** (`procesio_aat_runtime_capability_lookups_total`, by `mode` and
  `outcome`). Whether a change to discovery helped shows as fewer `mode="action"`
  lookups for the same number of searches; a rising share of `relaxed` or `empty`
  searches says that callers use words the catalog does not.

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
  "start a framework process and normalize its JSON". `flags_from` JSON-encodes
  dict/list arg values into a single argv element; the subprocess is a **list** (no
  shell), which is why structured args don't need escaping.
- **A turn starts the entry point, not the launcher script.** Outside a turn the
  runner starts `scripts/run-tool.py` / `run-agent.py`, as a terminal does. Inside a
  turn (`inherit_env=False`) `runner._run_entry` resolves the tool or agent in the
  server and starts its `main.py` directly, with the same filtered environment and
  per-call user. The launcher only repeated the lookup and added an interpreter, and it
  can hand a call to the warm runner, which a turn must never reach — so
  `runner._run_command` forces `AAT_RUNNER=0` on every process a turn starts.
- **Hiding a tool blocks it only where the hidden names are known.** The process a
  turn starts gets a filtered environment that does not carry `AAT_TOOLS_HIDE`, so a
  check made there never fires. The server does know the names, and in a turn the
  server does the lookup (`_run_entry`), so a hidden tool answers `tool not found`.
  Agents have no hide switch, and a tool an agent runs itself is resolved with
  `respect_hidden=False`. To keep a capability out for certain, leave it out of the
  image.
- **Registry cost:** a scan (`registry.list_tools/agents/skills`) parses every manifest
  and probes credential presence per secret: seconds on a large registry, in the
  thread of whoever asked. Three things keep it off the call path:
  - *One manifest for one name.* `registry.get_tool/get_agent` open the folder the
    name points to (hyphen or underscore form) and walk the folders only when that
    misses. A lookup by name must never cost a scan.
  - *Parse once.* `tools/_lib/manifest` reads YAML with `CSafeLoader` when PyYAML has
    libyaml, and reuses a parsed manifest while the file's modification time and size
    are unchanged. The pure-Python loader is several times slower, and the largest
    manifest is about 500 KB.
  - *Scan again only on change.* After `AAT_REGISTRY_TTL` (default 30 s; 0 scans on
    every call) the bridge compares `_registry_stamp()` — path, modification time and
    size of every manifest, plus the hidden names — and reuses the last scan when the
    stamp is unchanged. That shortcut applies only where readiness cannot change while
    the server runs (`AAT_CREDS_BACKEND` is an `env` kind). Where a credential can be
    stored at any moment, the window still ends in a scan, because readiness is part
    of the scan and is not in the manifest files. Callers that arrive together share
    one scan, and `http_server` warms the registry in a background thread at start.
- **Bytecode in the image.** A tool process in a turn runs as a per-call user that
  cannot write `__pycache__`, so without compiled files every call compiles its imports
  again. The Dockerfile runs `compileall` for that reason; a local run with
  `PYTHONDONTWRITEBYTECODE=1` shows the same cost and is the wrong baseline for a
  timing.
- **Creds backend:** `registry` uses `tools/_lib/creds` (Windows Credential Manager
  today). Running the server on another OS needs the creds backend from spec 06.
- **A secret that belongs to the installation, not to a user.** A tool of a turn gets
  only what the turn's user can see: the bridge builds its secrets from that user's
  credentials, and the process inherits nothing from the container. So a value that no
  user credential carries reaches a tool only when the bridge hands it over on purpose.
  The passphrase of a form's code is one. The installation's web app encrypts
  `Data.code` (a form's CSS and JavaScript) with it. The deployment sets
  `AAT_PROCESIO_FORM_CODE_KEY`, and `_procesio_profile` adds it as `form-code-key` to
  the secrets of the procesio tool, and of no other tool. The bare name is the right
  one, because a turn runs on the tool's default environment. Without the setting, the
  actions that read or write form code answer `no form-code-key stored`. A wrong value
  is worse than none: the tool writes a blob that the web app cannot open, and the form
  shows blank with no error. Add another such value the same way: one named setting,
  one tool, never the container's whole environment.

## Log lines

- **One writer, two formats.** Every line goes through `runtime_log.write`. `AAT_LOG_FORMAT=json`
  (set in the k8s configmap) writes one JSON object per line; unset or `text` writes
  `[source] sentence`, which is what a local run and the stdio servers show. Never write to
  stderr directly in `bridge`, `http_server`, `metrics` or `server`: one plain line among JSON
  lines is a line the log store cannot parse. A test holds that.
- **The JSON keys are the ones the .NET services write** - `Timestamp`, `Level`,
  `RenderedMessage`, `Properties` - so one query reads the three services. `RenderedMessage` is
  the sentence of the text line, unchanged. `Properties` holds its values one by one.
- **A turn is found by `Properties.MessageId`**, the same key the other services use. The lines
  about a call and a refusal carry `SourceContext: Procesio.Aat.Turn`, the category the other
  services give their lines about a turn. The other sources are `aat-mcp-http`, `aat-metrics`,
  `aat-mcp` and `entrypoint`. A line of a request without an id has no `MessageId` key.
- **The access line says what the request was for**: the MCP method, the MCP tool, and the tool
  or agent and action the call names, with the time the request took. Names only. `args`, a
  search text and a payload can hold what the user wrote and are never logged.
- **An exception is one line.** The HTTP server class and the uncaught-exception hooks put the
  traceback in the `Exception` key. The standard handlers print it over many lines, each of
  which a log store reads as an entry of its own.

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

## The platform's typed surface

`platform_server.py` is what `http_server.py` serves. `AAT_MCP_SURFACE` chooses the tool
list: `generic` (the default: `server.py`'s tools, exactly as before), `typed` (the named
tools of `platform_surface.yaml`), or `both` (the named tools first, then the generic ones).

**Why named tools.** With the generic tools a model does three things for each action it
has not used yet: it searches, it asks for the arguments, and it runs the action. The first
two run nothing, each is a model round trip, and the context is sent again with each. A
named tool has its name, its description and its schema in the tool list, so the model
calls it in one step and the client checks the arguments first. The generic tools stay for
the long tail: hundreds of actions do not fit in a tool list.

Rules that matter when touching it:

- **A tool earns its place by being called.** Every definition is sent with every model
  request. Choose the list from the per-action call counts
  (`procesio_aat_runtime_action_duration_seconds_count`), not from what looks useful.
- **One tool is one action.** A tool that needs several steps gets an ACTION that does
  them (`node-edit-batch`), and the tool maps to it. The declaration then carries no
  behaviour, and the conformance tests can check every entry against the registry.
- **Shape the tool for the caller, in the declaration.** No workspace, environment or
  profile argument (a turn has one of each). No argument that names a file (the model's
  files are on another machine). A JSON argument is an `object` or an `array`, so the
  client checks its shape. `fixed` sends a flag that the caller cannot change.
- **A structured argument's schema has one home.** `schema_from_manifest: true` takes it
  from the action's manifest, which takes it from the code that validates. A copy in the
  declaration would drift.
- **Every answer says `read_only` and `dry_run`.** A caller that must know whether a call
  changed anything reads those. Inferring it from a tool's name and the layout of its
  arguments stops working the moment the names are typed.
- **An argument the tool does not declare is an error**, with the valid ones beside it.
  The public surface drops such an argument; there the caller is a stranger. Here the
  caller has the schema, and a dropped argument hides a mistake it should correct.
- **Unknown setting, generic surface.** A typo in `AAT_MCP_SURFACE` must leave the
  assistant with the tools it had.
- **The Worker must agree.** Its instructions and its tool permissions depend on which
  surface is served, so the Worker has the same setting. A named tool that the Worker does
  not permit is refused by the client before it reaches this server.

The snapshot (`platform_surface.snapshot.json`) makes a change to the list a reviewable
diff. A turn starts a new client each time, so there is no client-side cache to mislead;
the snapshot is for the reviewer.

## Three surfaces over one substrate

There are three tool surfaces here, on purpose. `server.py` offers six freeform tools that
dispatch whatever the registry holds - right for an operator driving the framework.
`chat_server.py` offers one named tool per operation, built from `chat_surface.yaml` -
what a general chat client and a directory review both need. `platform_server.py` offers
the named tools of `platform_surface.yaml` to the platform's assistant, beside the freeform
ones (previous section). The two declared surfaces share `surface.py`, which turns a
declaration into a tool list, and nothing else: neither imports the other.

**A published tool list is a different kind of artefact from a registry.** The registry
is the source of truth for what a tool IS, and a surface that derives from it tracks it
automatically, which is correct for the freeform one. A published list is a contract
with people who did not write the manifests, and deriving it from them means a rename
silently removes a published tool, a new argument silently reshapes a published schema,
and a new tool silently appears in a surface someone reviewed. **MCP clients cache tool
definitions at initialisation and do not refresh them**, so none of those three errors
even produce an error - the client keeps calling the old shape and the model
misunderstands the result. That is why the declaration is a separate file and why the
disagreement is resolved at CI rather than at a user's call.

**`read_only` and `reversible` answer different questions.** Reversible asks whether a
change can be undone; read-only asks whether anything changes at all. A create action is
reversible and is not read-only. Mapping one onto the other would mark every write
safe to run unattended. The implication only runs one way, and that is what is asserted:
read_only ⟹ reversible.

**Annotations are not a control.** The spec tells clients to treat tool annotations as
untrusted. They drive a client's auto-run behaviour, so a wrong one is a write that
fires unprompted - worth getting right - but the enforcement is `gate.py`. The curated
surface carries no `*_confirmed` twin and instead refuses irreversible actions outright,
with a test asserting nothing declared is irreversible; adding a destructive operation
fails the build rather than growing a second, softer approval path.

**Shared protocol, separate surfaces.** The two servers differ in what they publish and
to whom, so their tools, dispatchers and identities stay apart. The protocol is a
different matter: it has one correct behaviour. It used to be duplicated, about 50 lines
in each server, and the two copies made the same mistake - agreeing to any version a
client named. It now lives once in `protocol.py`: negotiation, the modern and legacy
result shapes, `server/discover` and the stdio loop. That module is standard library
only and imports neither surface, so a change to one surface cannot reach the other
through it. Both servers import `bridge`, `gate` and `protocol`; neither imports the
other. `test_chat_surface.py` asserts all of this by parsing the AST.

### Design rules taken from published guidance

- **Namespace tool names by domain** (`procesio_list_processes`, not `list_processes`).
  A directory client merges several servers into one list. Anthropic's tool-writing
  guidance reports that naming scheme alone has non-trivial effects on tool-use
  evaluations.
- **Curate for workflows, not endpoints.** Prefer `search_*` over `list_*` because agent
  context is limited. The generated REST passthroughs are exactly what does not belong
  in a published surface.
- **Cap tool results.** A result lands directly in a model's context, so an unbounded
  one is a context leak rather than a large answer. Truncation carries a hint naming the
  arguments that narrow *that* tool, because a generic "too large" is not actionable.
  (Claude Code caps tool responses at 25,000 tokens by default; MCP metadata has been
  measured at ~40% of token usage in some environments, which is the argument for a
  small surface.)
- **Version the surface separately from the package.** The MCP registry requires a
  unique version string per publication and recommends semver; `server.json` aligns with
  the release, while `surface_version` describes the published tool contract. A client
  pins to a surface, and a release can ship with the surface unchanged.
- **Known gap:** the declaration is a 1:1 mapping (one MCP tool = one action), which
  keeps it free of behaviour and fully verifiable against the registry, but forecloses
  the consolidation that guidance recommends (one `schedule_event` rather than find-slot
  + book). Consolidation needs composition logic in the surface layer and its own tests.

## Status

Spec 02 (B1) transport + surface AND spec 03 (B2) reversibility gate: built +
unit-tested (19 tests) + wire-tested (send refused on plain tool, executes on
confirmed). Tool names dropped the `aat_` prefix (opencode re-adds it → clean
`aat_run_tool`). Pending: live opencode action-count/gate check in the browser, and
HTTP transport (spec 05).

Dual-era negotiation for MCP 2026-07-28 (`protocol.py`): built, unit-tested
(`tests/test_protocol.py`), and checked live with Claude Code in both negotiation modes
(default `initialize`, and `MCP_PROTOCOL_NEGOTIATION=auto` via `server/discover`).
