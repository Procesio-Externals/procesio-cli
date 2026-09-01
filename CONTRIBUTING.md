# Contributing

Issues and pull requests are welcome. One thing is worth knowing before you open one.

## This repo is generated

`procesio-cli` is published from an internal monorepo where the PROCESIO tool and agent are
developed alongside a larger set of tools. The publication is a filtered copy: the
files you see here are byte-identical to their upstream counterparts, at the same
paths, minus what is internal.

Two consequences:

- **Commits arrive in batches.** A publish carries whatever changed upstream since the
  last one, so the history here is coarser than the work that produced it.
- **A merged PR is copied upstream by hand, once.** Because the paths match, that is a
  mechanical step rather than a rewrite, and your change comes back verbatim on the
  next publish. You will occasionally see your own commit re-land with a different
  hash. Nothing was lost; it took the long way around.

If a PR is merged and then appears to vanish on the next publish, that is a bug in our
process, not in yours. Open an issue and we will fix the port.

## What makes a change easy to accept

- **Keep the contract.** Every tool prints exactly one JSON object on stdout and
  nothing else; errors are `{"error": {"code", "message", "details"}}` with a non-zero
  exit code. Progress goes to stderr.
- **Change the manifest in the same commit as the code.** `tool.yaml` is the source of
  truth for actions, arguments and secrets. A new argument that only exists in the
  handler is a bug, and the tests will say so.
- **Regenerate the generated files.** After a manifest change:
  `python scripts/build-tool-skill.py procesio` and `python scripts/build-router.py`.
- **Never put a secret in a file.** `scripts/secret_scan.py` runs over the tree and
  will refuse anything credential-shaped. Secrets belong in the OS store, reached
  through `tools/_lib/creds.py`.
- **Add a test that fails without your change.** A test that passes both before and
  after is documentation, not a test.

```bash
python -m pytest tools/procesio agents/procesio -q
python scripts/secret_scan.py
```

## Reporting a platform bug

If the problem is PROCESIO itself rather than this client, an issue here is still a
fine place to start; we would rather triage it than have you guess. Include the API
call, the response status, and what you expected. Please redact tokens, workspace ids
and anything from your own data before pasting.
