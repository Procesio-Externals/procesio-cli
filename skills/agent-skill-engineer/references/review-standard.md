# Agent Skill review and release standard

Use this reference for adversarial review, approval, and publication decisions.

## Contents

1. Review order
2. Hard blockers
3. Adversarial questions
4. Performance review
5. Release evidence
6. Maintenance loop

## 1. Review order

Review in this order so polish cannot hide a broken foundation:

1. need and ownership;
2. trigger boundary;
3. safety and permission model;
4. workflow correctness;
5. resource architecture;
6. evaluation validity;
7. direct field proof;
8. context, latency, and maintenance cost;
9. prose quality.

A fluent skill with an ambiguous owner is not nearly ready. A concise skill that routes correctly and proves its output is usually preferable to a sophisticated manual.

## 2. Hard blockers

Do not publish when any of these is true:

- name, folder, frontmatter, links, or resource paths are invalid;
- description does not identify concrete triggers or collides with a neighboring owner;
- the package contains a secret, private data, unsafe download, or path escape;
- a mutation workflow lacks preconditions, approval, retry semantics, or direct verification;
- the skill duplicates authoritative tool schemas or volatile facts without an owner;
- evaluation criteria were invented after seeing results;
- different jurors receive different criteria or control the aggregate verdict;
- a field trial lets the acting agent invent required checks, permit a new gap, or control the aggregate field verdict after seeing results;
- a field budget ignores triggered, child, or nested process instances and therefore understates cost or side effects;
- a claimed improvement lacks the correct baseline;
- A/A exceeds the pre-registered noise limit;
- a high-consequence operational skill has no controlled field proof;
- the completion claim relies on a proxy when direct observation is available;
- a failed required field outcome was relabeled as `passed_with_gap` without a predeclared equivalent fallback;
- generated or translated integration artifacts are stale;
- the package is still marked draft or contains placeholders.

## 3. Adversarial questions

### Scope attack

- What is the nearest prompt that should not trigger this skill?
- Which existing skill would a user reasonably confuse with it?
- Does the description claim a topic or an actionable outcome?
- Can one prompt activate two owners without an explicit handoff?

### Context attack

- What is loaded for every invocation but used by fewer than half of them?
- Could a reference replace a long body section?
- Could a script replace repeated code or fragile prose?
- Is any information duplicated between body, references, and tool schemas?

### Safety attack

- What happens after a timeout during a write?
- What stable ID proves what was changed?
- Can an agent accidentally cross workspace, tenant, repository, or filesystem boundaries?
- Does “dry-run,” “read-only,” or “approved” have observable enforcement?
- Can cleanup delete anything not created by this run?
- Does the execution budget count the full causal tree, including subprocess and trigger-created instances?

### Evaluation attack

- Would a no-skill model pass every criterion anyway?
- Does each criterion measure one requirement?
- Are selection and response quality scored separately?
- Are jurors given identical IDs, order, wording, and required flags?
- Does host code reject missing, extra, renamed, reordered, or non-Boolean results?
- Is the field test observing the user's outcome rather than a convenient proxy?
- Were field check IDs, permitted degraded modes, budgets, cleanup, and promotion rules fixed before the first mutation?
- Does deterministic host code validate the field report and compute pass, rather than trusting the acting agent's label?
- If remediation occurred, is the original failed report archived and the extra mutation/execution cost disclosed?

### Maintenance attack

- Who owns each fact and how does it become stale?
- Will a manifest or API change leave believable but wrong instructions?
- Can generated outputs drift?
- Does a recurring correction have an enforceable structural home?
- Can a future maintainer reproduce the evidence without this conversation?

## 4. Performance review

Measure costs only after correctness and safety clear their gates:

- metadata characters and initial routing budget;
- SKILL.md lines and estimated tokens;
- references loaded per task;
- tool calls and retries;
- response latency and token use;
- success improvement over baseline;
- regression rate on negative and overlap cases;
- maintenance surface: files, duplicate rules, source owners, generated artifacts.

Optimize the bottleneck supported by evidence. Shorter is not better when it removes a critical decision. More detailed is not better when it loads irrelevant context.

## 5. Release evidence

A release record should identify:

- skill version and corpus fingerprint;
- prior baseline or no-skill condition;
- routing corpus results and forbidden collisions;
- static audit and host validator results;
- fixed rubric version and fingerprint;
- A/A verdict when required;
- A/B rounds and minimum effect when required;
- real field task, target isolation, observed output, and cleanup;
- frozen field check IDs, permitted gaps, complete causal execution counts, and remediation lineage;
- target clients and operating systems tested;
- known limitations, manual checks, and rollback or retirement path.

Use artifacts and command outputs, not an author’s summary, as the source of truth.

## 6. Maintenance loop

Route every new signal:

- one-off preference → do not generalize yet;
- repeated user correction → candidate instruction or routing case;
- repeated deterministic mistake → script, schema, or lint;
- tool/API mismatch → executable contract fix;
- stale fact → source refresh and timestamp;
- real field failure → sanitized regression case plus direct-proof improvement;
- failed field gate with repairable scope → preserve the original report, write a separately approved remediation contract, and promote only through host validation;
- portfolio collision → description or ownership redesign;
- jury disagreement → fixed criterion clarification or evaluator repair.

Re-run only the evidence affected by the change, then the full release gates. Never reuse an old passing report after changing the skill, corpus, rubric, evaluator, model contract, or field workflow.
