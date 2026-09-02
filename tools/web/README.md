# web

Drive web apps that have **no API** using [Playwright](https://playwright.dev/python/),
reusing **saved login sessions** so you authenticate once per site and reuse it
headlessly forever after. This is the framework's bridge to anything that only
lives behind a browser: tools like `whatsapp-personal` and the outreach agent
call `web` whenever they need to connect to a site or do deeper web research.

There is **no HTTP API** here. A small `BrowserDriver` abstraction wraps
Playwright (imported lazily) so the tool — and its test suite — load even before
the browser binaries are installed.

## Why saved sessions

A *session* is a Playwright **storageState**: the cookies + localStorage of a
browser after a human logged in. Capture it once (`save-session`, headed) and
every later headless run reuses that authentication.

> **Sessions are SENSITIVE.** Each `tools/web/sessions/<name>.json` contains live
> auth material — anyone with the file can act as you on that site until it
> expires. They are **gitignored** (`tools/web/sessions/*.json`), never printed,
> and never logged. `list-sessions` reports names + size + mtime only. Treat them
> like passwords.

## Setup (one-time)

```powershell
uv sync
uv run playwright install chromium    # download the browser binary (~120 MB)
```

If `playwright install chromium` is skipped, the tool still loads and the test
suite still passes (Playwright is imported lazily) — but any action that opens a
real browser will fail with a `browser_error` telling you to install it.

> **`browser_error: Executable doesn't exist` even after installing?** A prior
> install can be marked-present-but-incomplete, so a plain `playwright install`
> no-ops instead of repairing it. Force a clean re-download:
> `uv run playwright install chromium --force` (or
> `.\.venv\Scripts\python.exe -m playwright install chromium --force`).

## Actions

| Action | Purpose |
|--------|---------|
| `save-session`   | Interactively capture a login session (headed browser + ENTER). |
| `list-sessions`  | List saved sessions (metadata only). |
| `delete-session` | Remove a saved session file. |
| `run`            | Run a declarative step list against a saved session. |
| `get-text`       | Load a session, open a URL, return visible text. |
| `screenshot`     | Load a session, open a URL, save a screenshot. |

### save-session (run once per site)

```powershell
python scripts/run-tool.py web save-session --name linkedin --url https://www.linkedin.com/login
```

A **headed** browser opens at the URL. Log in fully (including any 2FA), return
to the terminal, and press **ENTER**. The storageState is captured and written
to `tools/web/sessions/linkedin.json`.

Args: `--name` (required), `--url` (required), `--channel` (optional: `chrome`
or `msedge` to drive a real installed browser instead of the bundled Chromium —
useful when a site fingerprints the bundled build).

### list-sessions / delete-session

```powershell
python scripts/run-tool.py web list-sessions
python scripts/run-tool.py web delete-session --name linkedin
```

### run — declarative step list

```powershell
python scripts/run-tool.py web run --session linkedin --actions-file steps.json
```

Inline `--actions` also works but mind your shell's JSON quoting; a file is more
robust. Optional `--url` visits a page first; `--headed` shows the window;
`--channel` picks a browser channel.

Returns:

```json
{ "session": "linkedin",
  "results": { "name": "value" },
  "screenshots": ["path"],
  "final_url": "https://..." }
```

#### Step schema (the mini-language)

Each step is a JSON object with a `do` key; the rest are its parameters.
Unknown `do` values or keys, or missing required keys, fail fast with
`invalid_argument` **before** any browser opens.

| `do` | Required keys | Optional keys | Effect |
|------|---------------|---------------|--------|
| `goto`         | `url` | `timeout` | Navigate to a URL. |
| `click`        | `selector` | `timeout`, `force` | Click the first match. `force: true` skips the actionability wait - for a framework that paints a container over its own controls, where the hit test at the control's centre returns that container and the click is refused although a person can press it. It also skips the visibility check, so a truly hidden element is "clicked" with no effect and no error. |
| `fill`         | `selector`, `text` | `timeout` | Type text into an input. |
| `press`        | `key` | `selector` | Press a key (globally, or focused on a selector). |
| `wait_for`     | `selector` | `timeout` | Wait until a selector appears. |
| `extract_text` | (none) | `selector`, `name`, `timeout` | Read text (a selector, or whole page body) into `results[name]`. |
| `extract_attr` | `selector`, `attr` | `name`, `timeout` | Read an attribute into `results[name]`. |
| `screenshot`   | `path` | `full_page` | Save a screenshot; path collected into `screenshots`. |
| `upload`       | `selector`, `path` | `timeout` | Set files on an `<input type=file>` (often hidden). `path` is a path or list of paths. |
| `upload_via_chooser` | `selector`, `path` | `timeout` | Attach files behind a NATIVE chooser: clicks `selector` while expecting the chooser, then hands it the files. |

`timeout` is in **milliseconds**. For `extract_text`/`extract_attr`, `name` is
the key in `results`; it defaults to the selector (or `text` / `selector@attr`).

Example `steps.json`:

```json
[
  {"do": "goto", "url": "https://www.linkedin.com/in/someone"},
  {"do": "wait_for", "selector": "main"},
  {"do": "extract_text", "selector": "h1", "name": "name"},
  {"do": "extract_text", "selector": ".text-body-medium", "name": "headline"},
  {"do": "screenshot", "path": "outputs/profile.png"}
]
```

#### Human handoff — the agent stages, you submit

For anything outward-facing (Submit, Confirm, Send), the agent fills the form
and **you** click the control. `--hold-seconds` keeps the headed browser open
after the last step so you can review and act:

```powershell
python scripts/run-tool.py web run --session dca --headed --hold-seconds 900 --hold-until-selector "text=Thank" --actions-file steps.json
```

`--hold-until-selector` / `--hold-until-url-excludes <host>` end the hold as soon
as you act. The result gains a `hold` block:

```json
"hold": { "held_seconds": 412.0, "completed": true, "reason": "selector" }
```

`reason` is `selector` | `url` | `timeout`. **An expired hold is still a
successful run** (exit 0, `completed: false`) — the steps ran, you were just not
at the desk. `--hold-seconds` requires `--headed` (usage error otherwise), and
`completed` is advisory: confirm the outcome from `final_url` + `diagnostics`,
never from a screenshot taken before you clicked.

### get-text — convenience for research

```powershell
python scripts/run-tool.py web get-text --session linkedin --url https://example.com --selector main --wait main
```

`--selector` (optional) reads one element; without it, the whole page body.
`--wait` (optional selector) is awaited first — handy for single-page apps.

### screenshot

```powershell
python scripts/run-tool.py web screenshot --session linkedin --url https://example.com --out outputs/page.png
```

`--viewport-only` captures just the viewport (default is full page); `--wait`
awaits a selector first.

## Runtime diagnostics (verification)

`run`, `get-text`, and `screenshot` results include a `diagnostics` object collected over
the session — the observability for "verify before declaring done" (don't trust a
screenshot alone; it hides JS errors and failed requests):

```json
"diagnostics": {
  "console": [{"type": "error", "text": "..."}],   // console error/warning messages
  "page_errors": ["..."],                            // uncaught JS exceptions
  "failed_requests": [{"url": "...", "method": "GET", "failure": "..."}],
  "bad_responses": [{"url": "...", "status": 400}]   // HTTP >= 400
}
```

Empty lists = a clean run. Any `page_errors`, `console` errors, or a 4xx/5xx on the page's
OWN endpoints means the page is broken even if it looks fine in a screenshot. (Used to
verify PROCESIO forms end-to-end — see `agents/procesio/PROCESIO-BUILD-AND-TEST-PLAYBOOK.md`.)

## Output contract

Like every tool here: exactly one JSON object on stdout, progress/debug on
stderr, non-zero exit on error. Error envelope:

```json
{ "error": { "code": "...", "message": "...", "details": { } } }
```

Codes: `invalid_argument` (bad args/step schema, exit 2),
`session_not_found` (missing/corrupt session, exit 1),
`browser_error` (navigation/selector/timeout/missing-binary, exit 1),
`error` (anything else, exit 1).

## Python API (for other tools and agents)

Import `web` directly instead of shelling out. The driver is always torn down
for you. All functions accept `driver_factory=` so callers/tests can inject a
fake driver and run with no real browser.

```python
from tools.web import (
    open_session,   # -> a STARTED BrowserDriver (use as a context manager)
    run_steps,      # run a declarative step list against a saved session
    get_text,       # load session, open url, return visible text
    screenshot,     # load session, open url, save an image
    save_session,   # interactive capture (headed + human signal callback)
    list_sessions,  # metadata of saved sessions
    delete_session, # remove a saved session
    session_path,   # absolute Path to a session file
    BrowserDriver,  # the Protocol other code programs against
)
```

### Signatures

```python
open_session(name: str, *, headless: bool = True, channel: str | None = None,
             url: str | None = None, driver_factory=PlaywrightDriver) -> BrowserDriver

run_steps(name: str, steps: list[dict], *, url: str | None = None,
          headless: bool = True, channel: str | None = None,
          driver_factory=...) -> dict   # {"session","results","screenshots","final_url"}

get_text(name: str, url: str, *, selector: str | None = None, wait: str | None = None,
         headless: bool = True, channel: str | None = None, driver_factory=...) -> dict

screenshot(name: str, url: str, out: str, *, full_page: bool = True,
           wait: str | None = None, headless: bool = True,
           channel: str | None = None, driver_factory=...) -> dict

save_session(name: str, url: str, *, wait_for_signal: Callable[[], Any] | None = None,
             channel: str | None = None, driver_factory=...) -> dict

list_sessions() -> list[dict]      # [{name, bytes, modified}]
delete_session(name: str) -> bool
session_path(name: str) -> pathlib.Path
```

### Programmatic example — drive a saved session step by step

```python
from tools.web import open_session

# open_session returns a started driver; use it as a context manager so the
# browser is always closed.
with open_session("whatsapp", url="https://web.whatsapp.com") as d:
    d.wait_for("div[role='textbox']")
    d.fill("div[role='textbox']", "Hi there")
    d.press("Enter")
    last = d.extract_text("div.message-in:last-child")
```

### One-shot scripted interaction

```python
from tools.web import run_steps

out = run_steps("linkedin", [
    {"do": "goto", "url": "https://www.linkedin.com/in/someone"},
    {"do": "extract_text", "selector": "h1", "name": "name"},
])
print(out["results"]["name"])
```

### The BrowserDriver surface

`open_session` returns an object implementing `BrowserDriver`:

```
goto(url, *, timeout=None)            click(selector, *, timeout=None, force=False)
fill(selector, text, *, timeout=None) press(key, *, selector=None)
wait_for(selector, *, timeout=None)   extract_text(selector=None, *, timeout=None) -> str
extract_attr(selector, attr, *, timeout=None) -> str | None
screenshot(path, *, full_page=True) -> str    current_url() -> str
storage_state() -> dict   # capture cookies+localStorage (used by save_session)
close()                   # idempotent teardown
```

## Testing

```powershell
uv run pytest tools/web -q
```

The suite is **fully hermetic**: every test injects a `FakeDriver` and an
isolated temp sessions dir, so it runs with **zero real browser** and passes even
when Playwright's binaries are not installed. It covers the step interpreter,
session path/name validation (no traversal) and lifecycle, the public API,
dispatch/arg-parsing, error mapping, and the manifest-runtime sync guard.

A real-browser test is intentionally *not* in the suite (it would break hermetic
guarantees and CI without binaries). To smoke-test a real browser manually,
create an anonymous session file `tools/web/sessions/smoke.json` containing
`{"cookies":[],"origins":[]}` and run:

```powershell
python scripts/run-tool.py web get-text --session smoke --url https://example.com --selector h1
```
