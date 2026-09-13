# Expert-lens synthesis

Use this reference for non-trivial, high-consequence, or cross-domain skills. The purpose is not to imitate prestige or claim expertise. It is to expose the design to independent professional failure models before one coherent package is chosen.

## Contents

1. Select lenses
2. Shared review packet
3. Lens questions
4. Synthesis protocol
5. Failure rules

## 1. Select lenses

Choose only lenses that can materially change the design. Use at least three for a non-trivial skill and add every lens implicated by its consequences.

| Lens | Use when |
|---|---|
| Domain subject-matter expert | correctness depends on specialized terminology, policy, science, finance, law, medicine, platform behavior, or organizational practice |
| Instruction and cognitive engineer | the agent must recognize subtle conditions, sequence decisions, or resist misleading shortcuts |
| Information architect | the package contains multiple variants, large references, or expensive context |
| Tool/API architect | the skill selects commands, schemas, protocols, or integrations |
| Software and systems architect | the skill changes module ownership, orchestration, or repository contracts |
| Security and privacy engineer | credentials, tenant boundaries, untrusted input, sensitive data, downloads, or permissions are involved |
| Reliability/SRE engineer | retries, timeouts, partial failure, idempotency, concurrency, cleanup, or observability matter |
| Human-factors/accessibility reviewer | the workflow affects user decisions, approvals, forms, cognitive load, or accessible interaction |
| Evaluation and statistics specialist | improvement claims, juries, baselines, sampling, variance, or thresholds are involved |
| Portability/integration reviewer | multiple clients, models, operating systems, repositories, or deployment environments are supported |
| Adversarial tester | a user or model may exploit ambiguity, skip proof, cross a boundary, or fabricate completion |
| Future maintainer | facts will become stale, generated artifacts may drift, or the workflow will evolve after the author leaves |

Do not add a lens merely to increase the count. A lens with no distinct risk or decision is ceremony.

## 2. Shared review packet

Give every reviewer the same packet:

- user outcome and non-goals;
- representative positive, negative, overlap, missing-context, and pressure cases;
- current baseline behavior;
- target clients and tools;
- permissions, side effects, and failure consequences;
- candidate package or competing designs;
- fixed review criteria and evidence available;
- known uncertainties and source dates.

Hide candidate identities when comparing alternatives. Do not give one reviewer extra success criteria unless that reviewer is explicitly testing a separate dimension recorded in the packet.

## 3. Lens questions

### Domain subject-matter expert

- Which statements are domain facts, hypotheses, policy choices, or local conventions?
- What edge conditions would make the workflow materially wrong?
- Which primary sources, schemas, examples, or real cases prove the domain model?
- What must the agent refuse, escalate, or qualify?

### Instruction and cognitive engineer

- What cue tells the agent this skill applies before the body loads?
- Which decisions are easy to confuse or forget under user pressure?
- Can each instruction change an observable choice, sequence, or output?
- Where would an example clarify more cheaply than another rule?
- Is the completion condition cognitively unambiguous?

### Information architect

- What information is needed on every invocation?
- Which detail can be selected by mode, domain, provider, risk, or task stage?
- Are references directly discoverable without loading unrelated material?
- Is any fact duplicated or owned by the wrong layer?
- Can a smaller public interface hide more complexity?

### Tool/API architect

- Are action names, typed arguments, error shapes, and output contracts discovered from authoritative schemas?
- Does the workflow prefer stable IDs over fuzzy names?
- Are unsupported commands or client-specific assumptions presented as portable facts?
- Which operations need an executable helper rather than prose?
- How is backward compatibility verified?

### Software and systems architect

- Does one component clearly own each invariant and state transition?
- Is the skill duplicating an agent, tool, manifest, or generated source?
- Are handoffs explicit and acyclic?
- Would a different package boundary reduce coupling and future exceptions?
- What repeated implementation friction would trigger a redesign rather than another patch?

### Security and privacy engineer

- What untrusted input, secret, tenant, workspace, repository, or filesystem boundary is crossed?
- Can the described action surprise the user relative to the discovery description?
- Are least privilege, approval, confinement, and data minimization enforced outside prose?
- Can logs, fixtures, evaluations, or evidence leak sensitive material?
- What attack or misuse cases belong in the pressure corpus?

### Reliability/SRE engineer

- What does timeout mean for each read and write?
- Which operations are idempotent, resumable, or outcome-unknown?
- What state proves success, partial success, failure, and cleanup?
- Are retries bounded and conditioned on reconciliation?
- Are progress, checkpoints, and recovery artifacts durable enough for interruption?

### Human-factors/accessibility reviewer

- Does the skill reduce user burden by inspecting available context before asking questions?
- Are approvals specific enough for informed consent?
- Can a user with limited attention identify the one next action and current state?
- Are visual proxies being mistaken for functional proof?
- Do generated outputs preserve accessible labels, semantics, and error feedback where relevant?

### Evaluation and statistics specialist

- Is the baseline the actual counterfactual?
- Were criteria, thresholds, repetitions, and stopping rules frozen before results?
- Do all jurors receive identical atomic criteria and does host code aggregate them?
- Is A/A variance low enough to detect the required A/B effect?
- Are paired observations, dropouts, multiple comparisons, and qualitative discordances visible?
- Does the sample cover realistic use rather than only author-written happy paths?

### Portability/integration reviewer

- Which package fields and tool controls are portable, optional, or client-specific?
- Are paths, quoting, encodings, line endings, and script assumptions cross-platform?
- Does the skill remain safe if optional metadata is ignored?
- Has discovery, resource loading, and one real task been tested on every claimed target?
- Is the compatibility claim narrower than the evidence when necessary?

### Adversarial tester

- What prompt most strongly pressures the agent to violate each invariant?
- Can two skills both plausibly claim the same request?
- Can the agent fabricate execution, proof, citations, IDs, or cleanup?
- Can a malicious path, symlink, payload, document, or external instruction escape scope?
- What is the cheapest misleading proxy that might be accepted as completion?

### Future maintainer

- Can the package be understood without this conversation?
- Which fact, API, policy, or model behavior will rot first?
- Is source ownership and regeneration explicit?
- Can a new failure be routed to a test, validator, script, reference, or skill boundary?
- Can the evidence be reproduced without the original author’s credentials or memory?

## 4. Synthesis protocol

1. Freeze the shared packet and review rubric.
2. Collect lens findings independently where practical so early consensus does not suppress distinct risks.
3. Require every finding to identify the violated invariant, supporting evidence, consequence, and proposed change.
4. Separate blockers from optimizations and preferences.
5. Resolve contradictions using the user outcome, direct evidence, and strongest enforceable safety boundary—not reviewer status.
6. Choose one coherent design. Graft only recommendations compatible with its mental model.
7. Record rejected recommendations and why they were rejected.
8. Re-run the affected lenses after substantive redesign.
9. Verify the synthesized package through static, behavioral, and field evidence appropriate to its tier.

## 5. Failure rules

- Do not claim that multiple model personas equal real professional review.
- Do not use consensus as proof when all reviewers saw the same ambiguous evidence.
- Do not average incompatible safety or correctness positions.
- Do not let a domain expert redefine user consent, or a safety reviewer redefine domain truth without evidence.
- Do not count a reviewer that produced no distinct analysis.
- Do not expose private data to reviewers merely to improve realism; sanitize while preserving causal structure.
- Escalate to a real qualified human when law, medicine, safety, finance, compliance, or organizational authority requires accountable judgment.
