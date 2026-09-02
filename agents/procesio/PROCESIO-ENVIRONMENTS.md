# Working across PROCESIO environments

PROCESIO runs as separate installations — production, QA, dev, and each client's own
PROD/QA/STAGING. This tool calls each one an **environment**, named `<Client>-<ENV>`
(e.g. `Internal-PROD`, `Internal-QA`, `Internal-DEV`, `Delgaz-PROD`, `Delgaz-DEVQA`).
Each environment has its own host URLs and its own credentials — there is no data path
between them.

## When the user says "work on PROCESIO Internal-QA" (or DEV, or a client env)

That is a **switch the default environment** request. Do:

```
run-tool procesio set-environment --name Internal-QA
```

From then on every process/form/instance action runs against that environment and uses
the credential bound to it — until the user switches again. Confirm what happened by
reading the result's `default_environment`, `web_base`, and `credentials`. If
`credentials` is empty, tell the user no account is bound there yet and how to add one
(below) — do not silently fall back to another environment.

For a **one-off** call against a different environment without moving the default, pass
`--environment <name>` on that single action.

## The built-in environments (zero setup)

`Internal-PROD`, `Internal-QA`, `Internal-DEV` always exist for everyone. Production is
the default until someone switches. Client environments are added at runtime.

## Adding a client environment

```
run-tool procesio add-environment --name Delgaz-PROD \
    --web-base https://webapi.<host> --app-base https://<host> --forms-base https://forms.<host>
```

`client`/`env` are derived from the `<Client>-<ENV>` name. Then bind that client's
account to it:

```
run-tool procesio add-credential --name delgaz-me --type userpass \
    --username <…> --environment Delgaz-PROD
```

(Entering the secret itself is the user's action — never take a password on the command
line for them; the tool prompts without echoing, or the user stores it via the
dashboard / `set-credential`.)

## What you can rely on

- **Nothing to migrate.** An existing credential with no environment binding is treated
  as `Internal-PROD` (production URLs, unchanged). Colleagues keep working with no
  action from them.
- **Credentials are tied to environments.** Switching environment switches the account
  too, as long as exactly one credential is bound there; otherwise pass `--profile`.
- **Read before you switch for someone else.** `list-environments` shows every
  environment, the current default, and which credentials are bound where — use it to
  answer "what environments do I have / which am I on".

Mechanics, the registry-file location, and resolution precedence are documented tool-side
in `tools/procesio/PROCESIO-ENVIRONMENTS-NOTES.md`.
