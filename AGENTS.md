# Agent instructions

This repository's instructions for AI assistants live in **[CLAUDE.md](CLAUDE.md)**,
including a generated capability router that maps a request to the exact command
that serves it.

Read that file first. It is not Claude-specific despite the name; the name is what
several assistants look for by default, and duplicating the content here would give
you two copies to drift apart.

Quick orientation:

```bash
python scripts/list-tools.py                    # what is installed and configured
python scripts/run-tool.py procesio --help      # the PROCESIO tool's actions
python scripts/run-agent.py procesio guidance   # how to build and test properly
```
