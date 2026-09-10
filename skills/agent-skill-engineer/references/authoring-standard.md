# Agent Skill authoring standard

Use this reference while drafting or restructuring a skill package.

## Contents

1. Package contract
2. Frontmatter and description
3. SKILL.md body
4. Progressive resources
5. Instruction design
6. Sources and freshness
7. Safety and trust
8. Authoring review

## 1. Package contract

The portable core is:

```text
skill-name/
├── SKILL.md
├── references/   # optional, read on demand
├── scripts/      # optional, execute or inspect on demand
├── assets/       # optional, copied or transformed into outputs
└── evals/        # optional host-specific evaluation data
```

Keep resources shallow and path-confined. Use UTF-8 text, relative links, and stable filenames. Do not add README, quick-reference, changelog, installation guide, or design diary files unless a target client explicitly requires them.

## 2. Frontmatter and description

### Name

- Use lowercase letters, digits, and hyphens only.
- Keep it under 64 characters.
- Prefer a short verb-led or role-plus-outcome name.
- Match the folder name exactly.
- Namespace by tool or platform only when that improves routing clarity.

### Description

The description is the discovery interface. Put all trigger information there because the body is normally unavailable until after selection.

Use this shape:

```text
<Capability and primary output>. Use when <concrete user intents, artifacts, or failure states>. Do not use for <nearest competing intents>; use <owner> instead.
```

Good descriptions:

- begin with the capability, not marketing language;
- include phrases a user is likely to say;
- name relevant artifacts and outcomes;
- include the nearest high-risk exclusion when overlap exists;
- front-load decisive words because clients may truncate metadata;
- avoid implementation detail and full workflow summaries;
- stay below 1024 characters.

Avoid generic triggers such as “help,” “best practices,” “complex tasks,” or “when quality matters.” Avoid self-praise such as “ultimate,” “world-class,” or “expert.” Such language consumes routing budget without separating the skill from its neighbors.

## 3. SKILL.md body

Target fewer than 250 body lines; never exceed the host specification or validator limit. The body should contain only what must be present whenever the skill activates:

1. outcome;
2. boundary and handoffs;
3. non-negotiable decisions or invariants;
4. core workflow;
5. resource-selection guidance;
6. proof and completion contract;
7. failure or stop conditions.

Use imperative sentences. Prefer one statement per sentence. State why a surprising constraint exists when that reason changes compliance. Remove background theory the model already knows.

Do not repeat the description verbatim in the body. Do not repeat a reference in the body. Do not embed an entire tool catalog that a manifest or schema already owns.

## 4. Progressive resources

### References

Use references for stable detail that is needed only in some modes, domains, providers, or risk tiers. Link every reference directly from SKILL.md and say exactly when to read it. For long references, begin with a contents list and use searchable headings.

Use separate references when variants have substantially different mechanics. Do not create chains where one reference is discoverable only from another.

### Scripts

Create a script when:

- the same code or validation is repeatedly reconstructed;
- exact formatting or ordering matters;
- safety depends on path confinement, idempotency, or bounded inputs;
- a deterministic check can replace model judgment;
- an operation is narrow enough to expose a small stable interface.

Scripts should:

- refuse surprising overwrite or destructive behavior by default;
- validate inputs before side effects;
- return stable exit codes and machine-readable output where practical;
- keep diagnostics separate from parseable output;
- avoid secrets in arguments, logs, fixtures, and repository files;
- document dependencies and supported platforms;
- include tests for success, malformed input, boundaries, and failure cleanup.

### Assets

Assets are output materials, not instructions. Use them for templates, media, or boilerplate copied into an artifact. If an agent must read a file to decide what to do, it belongs in references instead.

### Evaluations

Keep evaluation cases beside the skill only when the host supports them. Treat their schema as a versioned contract. Use fixed criterion IDs and exact binary pass descriptions; do not store only a paragraph that each juror must reinterpret.

## 5. Instruction design

### Decision before procedure

Tell the agent how to recognize the situation before prescribing steps. A procedure without a selection rule is applied in the wrong places.

### Observable state transitions

Express fragile workflows as:

```text
preconditions → inspect → preview → approve → execute once → observe → recover/clean up → report evidence
```

Omit stages that truly do not apply, but never hide a mutation or substitute a proxy for outcome verification.

### Stable identifiers

Prefer IDs, paths, hashes, schema keys, and explicit target names over fuzzy search or “the latest one.” Capture IDs from write responses and use them for verification and cleanup.

### Failure semantics

Define unknown outcomes, retry rules, idempotency, and cleanup ownership. A timeout after a write is not proof that nothing happened. A failed test is evidence, not permission to try unrelated mutations.

### Examples

Use examples to disambiguate format or a subtle decision. Keep them realistic and diverse. Do not let one example become an accidental universal rule.

## 6. Sources and freshness

Assign each fact to a source class:

- **generated:** derived reproducibly from code, manifests, or schemas;
- **versioned:** tied to a release, commit, or protocol version;
- **timestamped:** current external facts requiring periodic re-verification;
- **stable:** domain principles unlikely to change.

Record an owner and last verification date when the host supports governance metadata. Prefer authoritative primary sources. Move volatile details into references so refreshing facts does not destabilize the core workflow.

## 7. Safety and trust

- A skill must not conceal behavior that would surprise a user who read its description.
- Never place credentials, tokens, private conversations, customer data, or environment-specific secrets in the package.
- Treat client allowlists such as `allowed-tools` as convenience controls, not the sole security boundary.
- Reject traversal and symlink escape in resource readers and scaffolders.
- Require explicit approval for irreversible or externally visible mutations.
- Distinguish observed facts, inferences, proposals, executions, and verified proof.
- Preserve compatibility or state the breaking change and migration explicitly.

## 8. Authoring review

Before evaluation, answer yes to each question:

- Can a new reader state the skill’s single primary outcome?
- Can a router distinguish it from every neighboring skill using only metadata?
- Does every body section change a decision, sequence, output, or failure response?
- Are volatile mechanics owned by a source rather than copied into prose?
- Is every optional resource linked with a clear load condition?
- Could a deterministic check replace any remaining instruction?
- Are mutation, retry, verification, and cleanup semantics explicit where relevant?
- Does the package avoid secret material, opaque downloads, and unexpected behavior?
- Is missing evidence labeled rather than disguised by confident prose?

If the answer is no, fix the package before spending model calls.
