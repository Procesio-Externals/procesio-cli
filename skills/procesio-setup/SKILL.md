---
name: procesio-setup
description: >-
  Connect this installation to a PROCESIO workspace, so the MCP server and the CLI can
  reach it. Use on first run, after installing the plugin, when a call fails with
  auth_required, missing_secrets or no stored credential, when someone asks how to add
  an API key or a second environment, when switching between PROCESIO environments, or
  when a tool reports a missing machine prerequisite.
version: 1.0.0
owner: procesio-cli maintainers
last_verified: 2026-09-23
---

# Connecting to PROCESIO

Nothing here reaches a PROCESIO workspace until one credential profile exists on this
machine. This walks through that, verifies it, and covers the optional extras that
individual tools need.

## Read this first: never handle the secret yourself

**Never ask the person to paste an API key, password or token into the conversation, and
never read one back.** Anything typed into chat is in the transcript.

Every command that needs a secret prompts for it directly, without echoing, when you omit
the value. That prompt belongs to the person, not to you: **you print the command, they
run it in their own terminal.** Do not run it for them, because a prompt you drive is a
prompt whose answer passes through you.

The values land in the OS credential store (Windows Credential Manager, macOS Keychain,
Linux keyring) under `agents-and-tools:<tool>:<secret>`. They are never written to a file
in this repository, and nothing here should ever print one.

If someone pastes a credential into the conversation anyway, say plainly that it is now in
the transcript and should be rotated, then carry on with the prompted flow.

## The one thing that is required

A PROCESIO credential profile. Without it every `procesio_*` tool fails; with it, 17 of
the 21 work. Everything below this section is optional and serves a specific feature.

Two kinds, and which one to use is decided by what the person already has:

- **API key** — the normal choice. A key minted in the PROCESIO UI, sent as a header.
- **Username and password** — for an account without a key, or where a key cannot be
  minted.

### API key

Give them this to run, with a profile name of their choosing:

```bash
python scripts/run-tool.py procesio add-credential --name personal --type apikey --make-default
```

Omitting `--key` and `--value` is deliberate: the command prompts for both without
echoing. If they want a specific workspace rather than the account default, add
`--workspace-id <guid>`.

### Username and password

```bash
python scripts/run-tool.py procesio add-credential --name personal --type userpass --username someone@example.com --make-default
```

Same rule: `--password` is omitted, so it is prompted without echoing.

### Installed from the plugin rather than cloned

The console scripts replace `python scripts/run-tool.py`:

```bash
procesio add-credential --name personal --type apikey --make-default
```

Everything else on this page works the same way, with `procesio` in place of
`python scripts/run-tool.py procesio`.

## Verify before declaring it done

A stored credential is not a working credential. This hits a live read endpoint:

```bash
python scripts/run-tool.py procesio check-auth
```

Then confirm it can actually see the workspace:

```bash
python scripts/run-tool.py procesio list-processes
```

`check-auth` passing while `list-processes` returns nothing usually means the credential
authenticates against the right account but the wrong workspace. Check `--workspace-id`.

To see what is stored without revealing anything, `list-credentials` shows names, types
and workspaces only, and `show-credential --name <name>` shows one profile's non-secret
fields, with secrets reported only as present or absent.

## Environments

Calls go to `Internal-PROD` unless told otherwise. For a client installation or a QA
environment, register it once and bind the credential to it:

```bash
python scripts/run-tool.py procesio add-environment --name Acme-QA --web-base https://... --auth-base https://...
python scripts/run-tool.py procesio add-credential --name acme-qa --type apikey --environment Acme-QA
```

`list-environments` shows what is registered, which is the default, and which credential
each one is bound to. Individual tool calls can also override per call with
`--environment`, which is worth reaching for before changing the default.

## Optional, per feature

Add these only when the person needs the feature. Each is inert until then, so a
first-run setup should not collect them.

| feature | what it needs |
|---|---|
| Building connectors from API docs | a Connector Builder credential |
| Tidying a process canvas | Node.js, plus `elkjs` |
| Reading or writing a form's code blob | the form-code encryption passphrase |

**Connector Builder** takes either an API key, or an account login:

```bash
python scripts/set-credential.py connector-builder api-key
```

That command prompts for the value without echoing. For the login route, store `username`
and `password` the same way.

**Node and elkjs** are machine prerequisites rather than credentials. `check-requirements.py`
reports what is missing and the install line for each:

```bash
python scripts/check-requirements.py
```

Worth knowing why this is a separate check: these dependencies are imported lazily, so a
machine without them still reports the tool ready and still passes the test suite. The
failure surfaces at the first real call instead.

**The form-code passphrase** encrypts a form's `Data.code` blob:

```bash
python scripts/set-credential.py procesio form-code-key
```

This one has a sharp edge worth stating before they set it. The passphrase is what decrypts
existing blobs, so **changing it makes every form already saved under the old one
undecryptable**, and the editing path fails before any write can happen. If that has already
happened, `form-set-code --clear` is the way back in.

## When something still fails

Read the error rather than re-running the setup.

| what comes back | what it means |
|---|---|
| `missing_secrets` | nothing is stored for that tool yet. Store it, above. |
| `auth_required` | a secret is stored but the tool could not use it. |
| `check-auth` fails while a secret is present | the value is present and wrong, or expired, or minted for a different environment. |
| calls succeed but return nothing | authenticated against the right account, wrong workspace. |

A stored secret being **present** is not the same as it being **valid** — presence is all an
inventory can see. Probe with `check-auth`, never by inspecting the store.

If a key was minted on one workspace and used against another, it will not work even though
both belong to the same account: a key inherits the permissions of whoever created it, in
the place it was created.

## What good looks like

Setup is finished when `check-auth` passes and `list-processes` returns the workspace the
person expected. Say which profile and which environment that was, so the next session
starts from a known place rather than rediscovering it.
