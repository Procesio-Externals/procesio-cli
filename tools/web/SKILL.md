---
name: web
description: Drive web apps that have NO API via Playwright, reusing SAVED login sessions so we authenticate once and reuse. Sessions are Playwright storageState (cookies + localStorage) per named site, stored gitignored under tools/web/sessions/<name>.json - they hold live auth and are SENSITIVE (never committed, never printed). Other tools and the outreach agent call this whenever they need to connect to a…
---

# web

Drive web apps that have NO API via Playwright, reusing SAVED login sessions so we authenticate once and reuse. Sessions are Playwright storageState (cookies + localStorage) per named site, stored gitignored under tools/web/sessions/<name>.json - they hold live auth and are SENSITIVE (never committed, never printed). Other tools and the outreach agent call this whenever they need to connect to a site or do deeper web research. Action-dispatched. No HTTP API; a BrowserDriver abstraction wraps Playwright (imported lazily) so the tool loads even before browsers are installed. BROKER-OWNED SESSIONS: run/get-text/screenshot against a session owned by a serializing broker (whatsapp/ryver/fgo/mirro - tools/_lib/webserialize) are executed INSIDE that broker, serialized with the owning tool's commands, so ad-hoc web commands can't race the profile. --direct bypasses (backup). save-session/delete-session auto-stop the owning broker first.

## How to call it

```bash
python scripts/run-tool.py web <action> [--args]
# e.g. web run --session <name> ...   (read text: web get-text; one-time login: web save-session)
```

One JSON object on stdout for success; `{"error": {"code", "message", "details"}}` and a non-zero exit on failure. Progress and logs go to stderr only.

**Start with `run`.**

## Actions

| action | required args | what it does |
|---|---|---|
| `delete-session` | `--name` | Delete ALL of a saved session's artifacts - the storageState file, the persistent <name>.profile/ directory, and the <name>.cookies.json sidecar. Deleting a… |
| `get-text` | `--session`, `--url` | Convenience: load a session, open --url, return visible text (whole page or --selector). For lead/topic research. |
| `list-sessions` | — | List saved sessions (names + metadata only, never contents). |
| `render-pdf` | `--out` | Render an HTML string/file to a PDF (session-less, headless Chromium page.pdf). |
| `run` | `--session` | Load a saved session, optionally navigate to --url, then execute a declarative step list (--actions JSON array or --actions-file). Returns collected outputs.… |
| `save-session` | `--name`, `--url` | Interactively capture a login session. Launches a HEADED browser at --url, lets the human log in, then captures storageState to tools/web/sessions/<name>.json.… |
| `screenshot` | `--session`, `--url`, `--out` | Load a session, open --url, save a screenshot to --out. |

---

Generated from `tools/web/tool.yaml` by `scripts/build-tool-skill.py`. Do not edit by hand — change the manifest and regenerate.
