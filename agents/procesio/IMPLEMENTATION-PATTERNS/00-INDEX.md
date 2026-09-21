# Implementation patterns: how this team builds in PROCESIO

These patterns were distilled from a full audit of a production workspace: 9 forms, 91 processes and a
SQL Server database with 51 tables and 23 stored procedures. That workspace covers form-driven request
intake, agent review, LLM document extraction, ERP integration, SFTP archiving and multi-party
e-signing. Every client-specific value has been removed. What remains is the **house style**: the
techniques this team actually uses, stated so a builder in any workspace can apply them.

The best-practices and playbook docs say what good looks like. These docs show how we build it here.
Where the two disagree, trust the docs and treat the entry as a proposal to reconcile. Each entry
marks whether it is **NEW**, **REFINES** an existing rule, or **CONFIRMS** one.

| topic | file | covers |
|---|---|---|
| `patterns-processes` | 01-PROCESSES.md | result flags for forms, HTML rendered server-side, Node idioms, subprocess utilities, versioned scripts, status machines |
| `patterns-forms` | 02-FORMS.md | step and confirm structure, visibility driven by process flags, JS bridges into no-code conditions, validator and collector runtimes, the async-output caveat |
| `patterns-integrations` | 03-INTEGRATIONS.md | inbound webhooks with API keys, ERP step orchestration with a run log, SFTP layout, LLM extraction with strict schemas, document generation |
| `patterns-database` | 04-DATABASE.md | a JSON-in orchestrator SP, errors collected before writes, one fixed result shape, deploy conventions, how a process reads a result |

## Every pattern file also lists the anti-patterns the audit found

Treat these as the house rules going forward:

- **Never paste a process variable into SQL text** (`N'{{v}}'`). Bind parameters instead (`sql-parameterize`).
  In the audited workspace almost every SQL node pasted values. A single apostrophe broke the save, and a
  token from a public URL reached the database unfiltered.
- **Hiding a section is not access control.** A public form that loads data on FORM_LOAD has already sent
  that data to the browser.
- **Wire error ports on every integration node** (HTTP, SFTP, SQL, LLM). An integration with no error port
  fails silently.
- **Keep secrets in credentials, never in application tables.**
- **When a later event in the same click chain needs a process's outputs, run that process with `syncRun`.**
- **Fix a JS runtime at one version on every element that installs it.** If each element carries a
  different version, every one of them installs a fresh copy and the listeners pile up.

## Workspace-specific knowledge (user data, not here)

An audit also produces knowledge that names the workspace's own processes, tables and findings. That goes
in the user-data folder, never in this framework folder:

```
context-state-knowledge/resources/procesio-workspaces/<workspace-slug>/
  raw/                  API dumps (processes/, forms/) - input to the digests
  processes/            flow-digest output (one .md per process + INDEX.md)
  forms/                form-digest output (+ FORM-PROCESS-MAP.md, scripts, global code)
  db-schema/            sqlserver schema-extract mirror
  knowledge/            the curated knowledge + audit findings (README.md = entry point)
```

Before building in a workspace, check whether it has such a folder: run `curator recall --query
"<workspace name> procesio knowledge"` or look in the folder directly. Build the same way its
knowledge describes.

To audit a new workspace, reproduce the folder with these steps:
1. `request GET /api/Projects/<id>` for each process, and `form-get` plus `form-get-code` for each form,
   into `raw/`.
2. `flow-digest --in raw/processes --out processes --names names.json`.
3. `form-digest --in raw/forms --processes raw/processes --out forms`.
4. `sqlserver schema-extract --profile <p> --out db-schema`.
5. Read and curate the results into `knowledge/`.
