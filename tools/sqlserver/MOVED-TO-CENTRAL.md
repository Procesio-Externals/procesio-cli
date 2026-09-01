# profiles.json moved to the central user-data folder

`tools/sqlserver/profiles.json` is no longer here. User-specific connection
profiles now live in the central, git-ignored user-data folder so the framework
stays free of user data (hand the repo to someone else, wipe that folder, done).

New location (resolved by `tools/_lib/userdata.py`):

```
context-state-knowledge/config/sqlserver/profiles.json
```

Override the root with the `AAT_USERDATA_DIR` environment variable. Passwords were
never in this file - they remain in Windows Credential Manager under
`agents-and-tools:sqlserver:<profile>`.

The tool resolves the path via `userdata.config_dir("sqlserver")`; nothing else
changes. Add/list profiles exactly as before (`run-tool.py sqlserver add-profile ...`).

**Fresh install / wiped user data?** `profiles.template.json` here seeds an EMPTY
`{}` on purpose: in this format every top-level key is a live profile, so a
placeholder entry would show up in `profiles`, get suggested by error hints, and
invite credentials for a fake host. Use `add-profile`, which builds the file:

```bash
python scripts/run-tool.py sqlserver add-profile --name myprofile \
  --server sql.example.com --database mydb --username user --encrypt
python scripts/set-credential.py sqlserver myprofile   # password -> CredMan
```
