# Agent Skill portability standard

Use this reference when a skill must work across clients, repositories, operating systems, or execution environments.

## Contents

1. Portable core
2. Metadata compatibility
3. Resource paths
4. Scripts and operating systems
5. Tool and security assumptions
6. Client test matrix
7. Standards anchors

## 1. Portable core

Treat `SKILL.md` with `name` and `description` as the minimum portable contract. Keep essential behavior in Markdown and optional resources under `references/`, `scripts/`, and `assets/`. Put host-specific metadata and evaluation wiring behind documented compatibility assumptions.

Do not make the skill's core behavior depend on a UI chip, marketplace field, proprietary slash-command syntax, or one client’s hidden system prompt.

## 2. Metadata compatibility

Clients differ in which frontmatter keys they preserve or use. Follow these rules:

- keep `name` and `description` valid everywhere;
- use lowercase hyphenated names under 64 characters;
- keep descriptions under 1024 characters and front-load decisive triggers;
- treat keys such as tool allowlists, invocation controls, UI metadata, ownership, and evaluation paths as host extensions;
- do not rely on an extension key as the only safety boundary;
- validate the final package with every target client's native checker when available.

If a client strips unsupported fields, the skill should remain understandable and safe, or its compatibility field should explicitly exclude that client.

## 3. Resource paths

- Use relative paths rooted in the skill directory.
- Keep `references/`, `scripts/`, and `assets/` one level deep unless every target client supports deeper discovery.
- Link each optional resource from SKILL.md with a load condition.
- Reject absolute paths, `..` traversal, and symlink escape.
- Avoid case-only filename distinctions and characters that are invalid on Windows.
- Use UTF-8 and normalized line endings where repository policy permits.
- Do not assume the current working directory; scripts should resolve paths from `__file__` or receive an explicit root.

## 4. Scripts and operating systems

Prefer the standard library for small helpers. When dependencies are necessary, declare them and fail with an actionable message.

Portable scripts should:

- use `pathlib` or equivalent path APIs;
- avoid shell-dependent quoting when direct argv execution is possible;
- separate stdout machine output from stderr diagnostics;
- return non-zero on failure;
- use atomic or no-overwrite writes for important artifacts;
- clean only resources created by the current run;
- test Windows, macOS, and Linux path behavior when those clients are supported;
- avoid assuming executable bits, `/tmp`, `/bin/bash`, GNU-only flags, or a desktop keyring.

Provide platform-specific wrappers only when a portable implementation would be less reliable.

## 5. Tool and security assumptions

A skill is instructions, not a sandbox. A client may ignore tool allowlists, expose additional tools, or run with the user's full filesystem permissions.

Therefore:

- require approvals and scopes in the executable layer as well as prose;
- keep credentials in host secret stores, never in the package;
- use least-privilege profiles and explicit target IDs;
- make destructive actions reject broad or ambiguous targets;
- verify network, repository, workspace, and tenant boundaries at runtime;
- state which operations are safe without credentials or external access;
- treat downloaded skills and scripts as code requiring review.

## 6. Client test matrix

For each supported client, record:

- discovery path and metadata fields used;
- explicit invocation syntax, if any;
- whether full SKILL.md and referenced resources load correctly;
- tool availability and permission behavior;
- script interpreter and dependency availability;
- path and line-ending behavior;
- output parsing expectations;
- one positive trigger, one abstention, and one resource-loading smoke test.

Run the same semantic cases across clients, but do not require identical wording. Compare decisions, outputs, and side effects.

## 7. Standards anchors

Re-check these primary sources when changing portability assumptions:

- Agent Skills specification: https://agentskills.io/specification
- OpenAI skill creator: https://github.com/openai/skills/tree/main/skills/.system/skill-creator
- Anthropic skill creator: https://github.com/anthropics/skills/tree/main/skills/skill-creator
- Cursor pstack source: https://github.com/cursor/plugins/tree/main/pstack

These sources inform package conventions and authoring methods. The target client's current validator remains authoritative for what that client accepts.
