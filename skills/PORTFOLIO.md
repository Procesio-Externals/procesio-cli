# Five-skill portfolio: migration and qualification

## Purpose and loading

This is the actual instruction portfolio for coding agents: five complementary
owners, not five mandatory stages and not a new CLI command. Open the chosen
`skills/<name>/SKILL.md`, then read its conditional references relative to that
package. An Agent Skills-compatible client's native discovery/file reader is
sufficient; additional MCP search/resource features are optional, not required.

- `procesio-cli`: approved platform operations and direct outcome verification.
- `procesio-platform-advisor`: feasibility, architecture and sourced capacity advice.
- `sql-server-optimizer`: measured tuning preserving SQL semantics and isolation.
- `procesio-cli-maintainer`: source/manifests/tests and repository integration.
- `agent-skill-engineer`: skill design, fixed rubrics, auditing and bounded improvement.

The operational and maintainer packages assume a configured checkout of this
repository when invoking `python scripts/...`. Run those commands from that
checkout's root, not from the skill directory or an arbitrary project. Credentials
and target authority are separate from installing a skill. A skill is not a sandbox.

Python helpers need Python 3.11+. The audit additionally imports PyYAML. From this
repository, `uv sync --all-extras` installs the development/test dependencies,
including pytest. SQL helpers require an explicitly scoped SQL Server connection;
they are never executed during installation, discovery or offline tests.

## Proposed export-path migration — maintainer approval required

This PR proposes an exception to CONTRIBUTING's no-move rule; it does not claim
that the exception was accepted. Do not merge until the source/export owner agrees.

- Retire `skills/procesio-expert/`: product advice moves conceptually to
  `procesio-platform-advisor`; operations belong to `procesio-cli`. Do not keep
  the old broad expert trigger active alongside the new bounded owners.
- Retain `skills/sql-server-optimizer/` as the SQL skill, with revised guidance.
- Move each of `export-tables.sql`, `export-indexes.sql`, and
  `export-procs-and-functions.sql` from its `references/scripts/` directory to
  `scripts/`, updating references. The table exporter is UTF-8 rather than the
  old non-UTF-8 file. Publication adds scope warnings and a default-off server
  trigger option, not a newly qualified exporter implementation.
- Add the three remaining owner packages and their local helpers/cases.

This is a standalone proposal against upstream main at
`a731baf738ec5c90fe9ac67265e532907a212a0b`. It does not depend on the optional
CLI/MCP discovery PR. No CLI handler, MCP server, credential store or platform
execution implementation is replaced. Minimal manifest metadata fields support
the offline governance checker; they do not enable runtime integrity admission.

Keep the pre-migration commit until adoption is verified. A maintainer can revert
this portfolio commit to restore old discovery paths; never run both ownership
models accidentally. Clients referring to `procesio-expert` or old SQL paths need
an explicit configuration update after the agreed migration.

## Evidence contract

The checked-in `portfolio-package-fingerprints.json` records the exact packaged
files with SHA-256. It establishes source identity, not correctness, safety,
behavioral uplift or release qualification. Tests recompute every package hash.

Skill versions, `last_verified` dates and `baseline_version` SHAs retain historical
source metadata. They are not current extraction-test timestamps and do not imply
that those commits are in this PR's ancestry or available in an upstream clone.
The packaged catalog/baseline JSON files are frozen historical **description-scorer
fixtures**, not a measurement of improvement over current upstream main. Reproduce
them offline from their embedded data; no fetch or historical private tree is needed.

Per-package fixed-rubric cases and the global behavioral corpus are contracts, not
observed agent responses. Field-boundary and closeout cases are development-only,
not untouched holdouts. `procesio-cli/evals/workflows.json` is a development checklist.
Static phrase-retention assertions and the audit's quality score prove neither
runtime enforcement nor measured behavior. No historical passing runtime reports
or private proof packets are imported as evidence for this extraction.

The extraction-specific `gates.json` remains **release_eligible: false**. Its
`infrastructure-complete` entries identify installed contracts, not passed field
or behavioral gates. This proposal is for code/content review, not production
certification. It carries no permission to run live qualification experiments.

## Included offline validation

From the repository root:

```bash
uv run pytest tools agents dashboard webplatform skills -q
uv run python scripts/validate-skills.py --strict-warnings
uv run python scripts/evaluate-skills.py --catalog skills/evals/baseline-catalog.json --verify-baseline skills/evals/baseline.json
uv run python scripts/evaluate-skill-routing.py --catalog skills/evals/baseline-catalog.json --verify skills/evals/baseline-routing-v2.json
uv run python scripts/evaluate-skill-routing.py --min-accuracy 0.95 --max-collision-rate 0
uv run python scripts/check-skill-governance.py
uv run python scripts/secret_scan.py
uv run python scripts/build-router.py --check
```

`check-skill-governance.py --require-release-eligible` must fail until new matched
proof is accepted. Default governance success only validates the blocked ledger's
structure/metadata. The release-binding helper is tested with synthetic Git repos;
it does not silently substitute current bytes for a missing evaluated commit.

CI includes offline checks only: no model runner, SQL Server connection, PROCESIO
field project or automatic platform run. Actual results belong in the PR/CI, not
in a copied historical pass. Cross-platform and native-agent behavior must be
verified on the intended client before portability claims are made.

## Remaining source-owned limitations

- **Approval and verifier runtime:** instructions do not repair argument-insensitive
  MCP classification, failed/skipped verifier prerequisites or native confidentiality
  enforcement. Obtain approval before calling either execution endpoint; inspect
  actual persisted/output evidence rather than a successful aggregate status.
- **Schedule projection:** check that the installed CLI supports the redacted read
  before acquiring sensitive inputs. If absent, stop and arrange an approved safe
  observation boundary. Raw output is not an equivalent fallback.
- **SQL exporters:** broad metadata inspection only. Module definitions can carry
  secrets; confirm acquisition scope before running. Server trigger collection is
  separately opt-in. Index-family serialization and NULL-definition handling remain
  incomplete; output is not a restoration/replay contract. No live SQL proof is
  supplied and no automatic whole-database export is authorized.
- **Optimizer:** the helper does not enforce one-shot terminal final-test custody
  and can accept later final reports. Preserve independent external custody of the
  untouched test; repeated submission is not new acceptance. Runtime repair needs
  a separately scoped change and regression proof.
- **Scaffold metadata:** the portable scaffold also accepts `stable` and `versioned`,
  which this repository's manifest does not accept. For repository integration, use
  its default `timestamped` or `generated`; run the included governance check before
  adoption. The portable helper's wider vocabulary is not repository policy.
- **Observation summaries:** the optional scorer rejects non-Boolean success values,
  but cannot authenticate results or prove corpus completeness. It is not a release
  acceptance gate; independent fixed-rubric evidence remains necessary.
- **Qualification:** matched behavioral A/A/A/B, transfer, native field proof and
  source-owner approval remain missing for the final packaged bytes.

Private field projects, browser-capture experiments, showcase receipts, installation
profiles, ontology state, machine-local logs and historical governance queues are
intentionally outside this contribution.
