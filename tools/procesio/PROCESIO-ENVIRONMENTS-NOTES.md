# PROCESIO environments — model & mechanics

PROCESIO ships as independent installations with no data path between them (each has
its own hosts, its own accounts). This tool models each installation as a named
**environment** `<Client>-<ENV>` carrying the four hosts it lives on, and binds each
credential to one environment.

## The four hosts

| field        | what it is                              | prod value                 |
|--------------|------------------------------------------|----------------------------|
| `web_base`   | Web API — every REST call                | `https://webapi.procesio.app` |
| `app_base`   | designer / front-end — designer URLs + the login CORS `Origin`/`Referer` | `https://procesio.app` |
| `forms_base` | public forms host — rendered-form URLs   | `https://forms.procesio.app` |
| `auth_base`  | legacy Proxy/Authentication host (login actually goes to `web_base`; rarely used) | `https://auth.procesio.app` |

The `-qa` / `-dev` installations follow a host family: `webapi-qa.` / `qa.` /
`forms-qa.` and `webapi-dev.` / `dev.` / `forms-dev.`.

## Two layers, merged at read time

- **Built-in presets** in `environments.py::BUILTIN` (`Internal-PROD/QA/DEV`) — PROCESIO's
  own infra, framework-shared, available with zero setup. These are *framework* data
  (public app hostnames), like the historical hard-coded defaults were.
- **User registry** at `context-state-knowledge/config/procesio/environments.json`
  (per-user, wipeable) — client-specific environments (`Delgaz-*`, …) and the
  `default` pointer. A user entry with a built-in's name **overrides** it (correct a
  moved Internal host without a code change). Client installation URLs are
  customer-specific, so they are **user data** and live here, never in shared code.

## Resolution precedence (both credential + URL)

Active **environment** for a call, highest first:
1. `--environment <name>` flag,
2. the credential's own `environment` binding,
3. the stored `default` environment,
4. `Internal-PROD`.

The resolved environment's URLs are folded into the profile the client holds, so
`config.web_base/app_base/forms_base/auth_base` pick them up. An explicit per-profile
URL override (a rare `web_base` on the credential blob itself) still wins — injection
uses `setdefault`.

Active **credential** for a call: `--profile` → the credential bound to the active
environment → the stored default profile. So switching environment also switches which
account/key is used, provided exactly one credential is bound there.

## Backward compatibility (why nothing breaks on upgrade)

A pre-existing single-credential setup keeps working as production with **nothing to
re-enter**: no registry file + an **unbound** credential ⇒ `Internal-PROD` ⇒ the exact
historical hard-coded URLs. Existing credentials carry no `environment` field, so they
resolve to `Internal-PROD` automatically.

## Operating it

```
list-environments                       # what exists, which is default, bound creds
add-environment --name Delgaz-PROD \     # register a client installation
    --web-base https://webapi.delgaz… --app-base https://delgaz… --forms-base https://forms.delgaz…
set-environment --name Internal-QA       # move the default pointer (persists)
add-credential --name qa-me --type userpass --username … --environment Internal-QA
<any action> --environment Internal-DEV  # one call against another env, default unchanged
```

`add-environment` needs all three of `--web-base/--app-base/--forms-base`; `client`/`env`
are derived from the `<Client>-<ENV>` name when omitted. Built-in `Internal-*` cannot be
removed. Names are matched case-insensitively.

## Tests / isolation

The suite's autouse `_isolate_userdata` fixture (conftest) pins `AAT_USERDATA_DIR` to a
temp dir, so every test starts from the built-ins with `default = Internal-PROD` and no
test reads or writes the developer's real registry. Userpass login tests must also take
the `store` fixture (in-memory creds) or a persistent cached token skips the login.
