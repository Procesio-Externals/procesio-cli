# tools/_lib

Shared helpers for every tool. Import these — don't duplicate logic.

## creds.py — the OS credential store (Windows / macOS / Linux)

```python
from tools._lib import creds

token = creds.get("ryver", "api-token")              # raises KeyError if missing
maybe = creds.get_optional("ryver", "api-token")     # None if missing
creds.has("ryver", "api-token")                      # bool
```

Storing is done through `scripts/set-credential.py`, not from inside tool code.

`creds.py` is a thin facade; the store itself is a pluggable backend in
`creds_backends.py`, selected once by `AAT_CREDS_BACKEND`. **Leave it unset** and each
OS gets its own native store, with the same `agents-and-tools:<tool>:<secret>` identity
everywhere:

| platform | store | writable |
|---|---|---|
| Windows | Credential Manager | yes |
| macOS | login Keychain | yes |
| Linux (desktop) | GNOME Keyring / KWallet over D-Bus | yes |

A **headless** machine has no OS keyring at all — no session bus, so there is nothing
to talk to. That is not a bug to work around with a fallback that silently reads as
empty; pick a backend explicitly:

- `AAT_CREDS_BACKEND=encrypted-file` — one passphrase-encrypted file
  (`AAT_SECRETS_FILE`, default `~/.config/agents-and-tools/secrets.enc`; passphrase in
  `AAT_SECRETS_PASSPHRASE`). Read/write, so `set-credential.py` works. This is the
  right choice for a server or a stateful container.
- `AAT_CREDS_BACKEND=file` / `env` — read-only views of secrets a host or cluster
  already manages (mounted k8s Secret, or one JSON blob).
- `bridge` / `procesio` — read-only HTTP resolvers (host bridge, platform store).

The distinction that matters: the four **owned** stores (windows / macos / linux /
encrypted-file) are read/write; the four **borrowed** ones are read-only, so a
container can never pretend to own the secret store it is reading from.

A wrong passphrase on `encrypted-file` **raises** rather than returning an empty store.
Reading as empty would be reported upstream as "credential missing", and the caller
would helpfully store the secret again under the wrong key.

## io.py — JSON I/O contract

```python
from tools._lib.io import emit, fail, log

log("starting")                                       # stderr
emit({"result": "ok"})                                # stdout JSON + exit 0
fail("invalid_input", "name is required", {"arg": "name"})  # stdout error + exit 1
```

`emit` and `fail` both call `sys.exit` — they never return.

## manifest.py — tool.yaml loading

Used by `registry.py`. Tool authors don't usually touch this directly.

## google_auth.py — shared Google OAuth (multi-account)

All Google tools (calendar, contacts, mail, drive, sheets, docs, slides) share
**one OAuth client** (`agents-and-tools:google:oauth-client`) and authenticate
with **per-account refresh tokens**:

| account | token secret |
|---------|--------------|
| `default` | `agents-and-tools:google:oauth-token` (backward compatible) |
| `<label>` | `agents-and-tools:google:oauth-token@<label>` |

`agents-and-tools:google:oauth-accounts` is a JSON index of known labels,
maintained automatically by login/logout.

**Selecting the active account** (highest priority first):
1. `google_auth.set_account("<label>")` — called from the `--account` CLI flag
2. `GOOGLE_ACCOUNT` env var
3. `default`

A `--account <label>` flag is parsed globally in `google_contacts/main.py`
(stripped before argparse) so it applies to **every** action — auth *and* data.
To add the flag to the other Google tools, copy the `_pop_account` helper +
`set_account` call from `google_contacts/main.py`. Even without the flag, the
other tools already honor the `GOOGLE_ACCOUNT` env var and the shared backend.

One Google Cloud OAuth client can authorize many Google accounts. If the
consent screen is in **Testing** mode, each extra account's email must be added
as a **Test user** in Google Cloud Console before its `auth-login` will succeed.


## webserialize/ — serializing brokers for web-profile tools

One broker process per tool owns its browser session/profile and executes
commands strictly one at a time; parallel chat sessions queue instead of
racing the profile (SingletonLock -> session invalidation). Registry of
brokers/ports/owned sessions: `webserialize/registry.py` (whatsapp-personal
47611, ryver-web 47612, fgo-web 47613, mirro 47614). Each tool routes its
browser actions in `main.dispatch` and exposes `service-status/-start/-stop`;
`--direct` / `<PREFIX>_DIRECT=1` is the in-process backup. The generic `web`
tool routes run/get-text/screenshot on OWNED sessions through the owning
broker (`web-steps` op) and stops the broker before save/delete-session.
Reference integration + full design rationale: tools/whatsapp-personal
(WHATSAPP-NOTES.md) and webserialize/server.py docstrings.
