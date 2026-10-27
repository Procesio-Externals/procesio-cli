# Capability map

This map is intentionally stable and high-level. Discover exact current operations through the repository registry rather than copying a volatile action count into prose.

| Area | Typical outcome | How to verify |
|---|---|---|
| Process automation | Design, trigger, branch, transform, and orchestrate work | Inspect process DTO, validate, run representative input, read instance outputs |
| Forms and human tasks | Collect input and involve people in a process | Open the published form, exercise controls, inspect browser diagnostics and resulting instance |
| Documents and files | Generate or transform artifacts | Run the producing process and inspect the downloaded artifact |
| API and connector integration | Call HTTP services or install custom actions | Test credentials/custom action and inspect mapped response/error behavior |
| Data integration | Work with data models, SQL, files, and external stores | Inspect schema and query the persisted/result state |
| Event and time triggers | Webhooks and schedules | Re-fetch trigger configuration and observe the resulting process instance |
| Environment transport | Export/import resources between workspaces | Inventory destination resources and verify dependencies and activation |
| Governance and operations | Credentials, users, workspaces, execution history, auditability | Use current product documentation and live workspace evidence |

A capability discussion should distinguish:

- available platform primitive;
- complete supported solution pattern;
- custom engineering path;
- external system dependency;
- roadmap or unsupported assumption.
