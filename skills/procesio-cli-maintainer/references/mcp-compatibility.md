# MCP compatibility contract

This is guidance for MCP source changes, not a dependency of the standalone skill portfolio. Coding agents may read skill-relative files natively. Query filtering and resource retrieval are optional: inspect the installed schema before using them. Native file loading does not require these extensions.

- Prefer extending optional fields on an existing generic operation over multiplying tools when the old meaning remains intact.
- Keep existing tool names and required arguments unless a versioned migration is intentional.
- Return structured readable errors; do not leak exceptions, paths, or secrets.
- Keep argument objects shell-free and encode nested values as one argv element.
- Classify irreversible actions in code before dispatch; the model cannot self-approve.
- Retained qualification blocker: inherited argument-insensitive gating can execute a mutation through an unconfirmed endpoint. Require local exact-effect preview and explicit operator approval before either execution endpoint; skill instructions do not repair runtime classification or qualify it as a complete approval gate.
- Bound discovery results and use progressive resource retrieval instead of returning the entire registry or corpus.
- Confine file/resource access to an established root and reject absolute paths, traversal, and symlink escape.
- Test protocol listing, old calls, new calls, error paths, and safety gates with no live credentials.
