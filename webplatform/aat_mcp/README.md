# aat-mcp — the AAT → MCP bridge

A stdio MCP server that exposes the live AAT registry to any MCP client (opencode
now, others later) as a **small generic surface**. It replaces bash passthrough:
capabilities are called as typed tools with **structured JSON args** (no shell
quote-escaping), and capability schemas replace `--help` spelunking.

Part of the "local web platform" initiative — specs `todo/local web platform Claude replacer/02-aat-mcp-bridge.md` (transport) and `03-safety-approval-parity.md` (gate).

## Tools exposed

Server tool names below; opencode shows them prefixed with the server name (e.g.
`run_tool` → `aat_run_tool`).

| MCP tool | Args | Purpose |
|---|---|---|
| `capabilities` | `{kind?, name?}` | no `name`: compact list of every ready tool/agent/skill. With `name`: that capability's full action+arg schema (the `--help` replacement) |
| `run_tool` | `{tool, action?, args?}` | run a **reversible** tool action; refuses irreversible ones with `approval_required` |
| `run_agent` | `{agent, action?, args?}` | run a **reversible** agent action |
| `run_tool_confirmed` | `{tool, action?, args?}` | run a tool **including irreversible** actions — opencode asks the operator to approve |
| `run_agent_confirmed` | `{agent, action?, args?}` | run an agent including irreversible actions — operator-approved |
| `get_skill` | `{name}` | the skill's full markdown (model-decided loading; spec 04) |

`args` is a JSON object of flag name → value. dict/array values are JSON-encoded into
a single argv element and passed via a subprocess **list** (no shell) — the fix for
the B0 spike's quote-escaping thrash.

## Safety gate (code-authoritative)

The reversibility gate is **code, evaluated before execution** (`gate.py` →
`agents/_lib/reversibility`, the same policy as `orchestrator drive` and `deputy`):

- `run_tool`/`run_agent` **refuse** an irreversible action (send/delete/pay/post/
  issue-invoice/...) and return `approval_required`, naming the `*_confirmed` path.
- Only the `*_confirmed` tools are marked `ask` in opencode, so a **human** approves
  each side effect. A model cannot forge the approval, and cannot bypass by picking
  the plain tool (it refuses). Reversible/read actions run freely on the plain tools.
- `AAT_MCP_DENY_IRREVERSIBLE=1` makes even the confirmed tools refuse — a fail-safe
  for a headless run with no human in the seat.

## Run

```
python webplatform/aat_mcp/server.py      # opencode spawns this over stdio
```

Quick manual check (newline-delimited JSON-RPC on stdin):
```
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"run_tool","arguments":{"tool":"hello-world","args":{"name":"MCP"}}}}' \
| .venv/Scripts/python.exe webplatform/aat_mcp/server.py
```

## Design

- **Placement:** a platform component (`webplatform/aat_mcp/`), not a registered tool
  — a long-running server does not fit the JSON-in/out-and-exit tool contract, and
  this avoids a tools→agents import inversion (execution reuses `dashboard.server.runner`).
- **Generic, not exploded:** a handful of tools, not one-per-capability — avoids MCP
  tool-count limits and manifest drift. The model discovers capabilities via
  `capabilities` (the router map), exactly as a session does today.
- **Source of truth:** capability + arg schemas are read live from the registry
  (manifests); the reversibility policy is the shared `agents/_lib/reversibility`.
- **No new dependency:** the MCP protocol is hand-rolled JSON-RPC over stdio (stdlib
  only), robust to environment quirks.

## Not yet (downstream specs)

- **HTTP/SSE transport** (spec 05): for containers/k8s, where opencode connects as a
  remote MCP client. stdio is the local transport.

## Tests

`python -m pytest webplatform/aat_mcp/tests/ -q` — protocol dispatch, the
reversibility gate (refuse/confirm/headless-deny), and the anti-thrash argv
guarantee, all with fakes (no real subprocess or credentials).
