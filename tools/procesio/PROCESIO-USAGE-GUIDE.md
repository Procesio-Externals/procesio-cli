# Using PROCESIO: the rules that are not obvious

**Generated from the notes in this folder. Do not edit by hand.**
Regenerate with `python scripts/run-tool.py procesio usage-guide`.

Every rule below was learned by losing time to it against the live platform,
and they share a shape: the call succeeds, the status says finished, nothing
is logged, and the thing you asked for did not happen. That is what makes
them expensive. There is no error to search for, so you look in the wrong
place.

None of these is a defect report. Each is the platform doing something
defensible that reads as a failure until you know the rule.

This page carries the rule and a pointer. The reasoning, the measurement and
the worked example stay in the note it points at, one copy, so a correction
lands in exactly one place and this page follows on the next build.

**58 rules across 3 notes.**

## The API, and what its answers actually mean

Source: [`PROCESIO-API-NOTES.md`](PROCESIO-API-NOTES.md)

- [DTO casing — live API is camelCase, exports are PascalCase (bites parsers)](PROCESIO-API-NOTES.md#dto-casing-live-api-is-camelcase-exports-are-pascalcase-bites-parsers)
- [Auth & client gotchas](PROCESIO-API-NOTES.md#auth-client-gotchas)
- [Endpoints + methods (tag Schedules; permission in parens)](PROCESIO-API-NOTES.md#endpoints-methods-tag-schedules-permission-in-parens)
- [Data Store — what builds today, and the two properties that do not](PROCESIO-API-NOTES.md#data-store-what-builds-today-and-the-two-properties-that-do-not)
- [A Node's <%i%> INLINES THE VALUE AS RAW TEXT](PROCESIO-API-NOTES.md#a-nodes-i-inlines-the-value-as-raw-text)
- [A For Each needs its FULL parameter set, and TWO outgoing edges](PROCESIO-API-NOTES.md#a-for-each-needs-its-full-parameter-set-and-two-outgoing-edges)
- [JS OFFSETS ARE UTF-16 CODE UNITS, SO A PYTHON ORACLE MUST NOT SLICE BY THEM](PROCESIO-API-NOTES.md#js-offsets-are-utf-16-code-units-so-a-python-oracle-must-not-slice-by-them)
- [THE RULE BOTH RECOVERIES TAUGHT, and it is now twice](PROCESIO-API-NOTES.md#the-rule-both-recoveries-taught-and-it-is-now-twice)
- [A Data Store action's sub-fields are GATED ON THE OPERATION VALUE](PROCESIO-API-NOTES.md#a-data-store-actions-sub-fields-are-gated-on-the-operation-value)
- [INSTRUMENT RULE: A PERMISSIONS FACT COMES FROM THE ASSIGNABLE ROLE MODEL](PROCESIO-API-NOTES.md#instrument-rule-a-permissions-fact-comes-from-the-assignable-role-model)
- [AN API KEY INHERITS ITS OWNER'S AUTHORISATION. IT CARRIES NO SCOPE OF ITS OWN](PROCESIO-API-NOTES.md#an-api-key-inherits-its-owners-authorisation-it-carries-no-scope-of-its-own)
- [✅ POST /api/DataStore/{id}/rows IS WHOLE-BATCH ATOMIC](PROCESIO-API-NOTES.md#post-apidatastoreidrows-is-whole-batch-atomic)
- [InsertRows TAKES ELEMENT 0 OF A LIST. THERE IS NO NATIVE BATCH WRITE](PROCESIO-API-NOTES.md#insertrows-takes-element-0-of-a-list-there-is-no-native-batch-write)
- [REPORT THE AMBIGUITY RATHER THAN PICKING A WINNER](PROCESIO-API-NOTES.md#report-the-ambiguity-rather-than-picking-a-winner)
- [A GATE THAT CHECKS A CONTAINER HAS NOT CHECKED ITS CONTENTS](PROCESIO-API-NOTES.md#a-gate-that-checks-a-container-has-not-checked-its-contents)
- [VERIFY A FIXTURE CONTAINS WHAT IT CLAIMS BEFORE MEASURING ON IT](PROCESIO-API-NOTES.md#verify-a-fixture-contains-what-it-claims-before-measuring-on-it)
- [BUILD THROUGH THE BUILDER. A RAW PUT IS A DEBUGGING INSTRUMENT](PROCESIO-API-NOTES.md#build-through-the-builder-a-raw-put-is-a-debugging-instrument)
- [A FAIL-CLOSED COMPONENT REPORTS FAILURE IN ITS OUTPUT, NOT AS AN ERROR](PROCESIO-API-NOTES.md#a-fail-closed-component-reports-failure-in-its-output-not-as-an-error)
- [A FAIL-CLOSED GATE MUST REACH NESTED SPEC KINDS](PROCESIO-API-NOTES.md#a-fail-closed-gate-must-reach-nested-spec-kinds)
- [AN API-BUILT ACTION WITH A PARTIAL PARAMETER SET IS UNOPENABLE IN THE DESIGNER](PROCESIO-API-NOTES.md#an-api-built-action-with-a-partial-parameter-set-is-unopenable-in-the-designer)
- [RESOLVED (2026-08-24). The mapper row format](PROCESIO-API-NOTES.md#resolved-2026-08-24-the-mapper-row-format)
- [rowkey uniqueness, and why a presence check is not a landing check](PROCESIO-API-NOTES.md#rowkey-uniqueness-and-why-a-presence-check-is-not-a-landing-check)
- [Cross-workspace triggering: PROCESS ids are workspace-scoped too](PROCESIO-API-NOTES.md#cross-workspace-triggering-process-ids-are-workspace-scoped-too)
- [A Data Store id is WORKSPACE-SCOPED, not a global handle](PROCESIO-API-NOTES.md#a-data-store-id-is-workspace-scoped-not-a-global-handle)
- [An imported process carrying a Data Store mapper CANNOT RUN](PROCESIO-API-NOTES.md#an-imported-process-carrying-a-data-store-mapper-cannot-run)
- [DataStore (/api/DataStore) — new module (2026-08)](PROCESIO-API-NOTES.md#datastore-apidatastore-new-module-2026-08)
- [Writing a flow definition: three ways the write layer misreports itself](PROCESIO-API-NOTES.md#writing-a-flow-definition-three-ways-the-write-layer-misreports-itself)
- [Data Store is an ACTION, and what it can do](PROCESIO-API-NOTES.md#data-store-is-an-action-and-what-it-can-do)
- [Exports: what can be named, and what a pack section proves](PROCESIO-API-NOTES.md#exports-what-can-be-named-and-what-a-pack-section-proves)
- [Flow control: what blocks, what does not, and what is absent](PROCESIO-API-NOTES.md#flow-control-what-blocks-what-does-not-and-what-is-absent)
- [The Data Store action: what it takes, and four ways it refuses](PROCESIO-API-NOTES.md#the-data-store-action-what-it-takes-and-four-ways-it-refuses)
- [Data Stores in an export pack: measured, after the tool was fixed](PROCESIO-API-NOTES.md#data-stores-in-an-export-pack-measured-after-the-tool-was-fixed)
- [DataStore error surface — read the code and target BEFORE bisecting](PROCESIO-API-NOTES.md#datastore-error-surface-read-the-code-and-target-before-bisecting)
- [The known length cap](PROCESIO-API-NOTES.md#the-known-length-cap)
- [PATCH /api/Projects/{id}/toggle-activation reports success and does not activate](PROCESIO-API-NOTES.md#patch-apiprojectsidtoggle-activation-reports-success-and-does-not-activate)
- [Node action: <%N%> interpolates a variable RAW into the JavaScript source](PROCESIO-API-NOTES.md#node-action-n-interpolates-a-variable-raw-into-the-javascript-source)
- [Instance status codes](PROCESIO-API-NOTES.md#instance-status-codes)
- [The script engine's capabilities, MEASURED on Internal-PROD 25-08-2026](PROCESIO-API-NOTES.md#the-script-engines-capabilities-measured-on-internal-prod-25-08-2026)
- [What a Data Store SelectRows hands a Node action](PROCESIO-API-NOTES.md#what-a-data-store-selectrows-hands-a-node-action)
- [A pack is a SKELETON: structure travels, bindings do not](PROCESIO-API-NOTES.md#a-pack-is-a-skeleton-structure-travels-bindings-do-not)
- [PROCESIO's outbound calls identify themselves](PROCESIO-API-NOTES.md#procesios-outbound-calls-identify-themselves)
- [A REST credential's connection test proves only what its Test endpoint requires](PROCESIO-API-NOTES.md#a-rest-credentials-connection-test-proves-only-what-its-test-endpoint-requires)
- [Create a process with process-create. NEVER provision one by duplicating](PROCESIO-API-NOTES.md#create-a-process-with-process-create-never-provision-one-by-duplicating)
- [And the launch refusal names the wrong cause](PROCESIO-API-NOTES.md#and-the-launch-refusal-names-the-wrong-cause)
- [Building a process through process-create — the parameter names](PROCESIO-API-NOTES.md#building-a-process-through-process-create-the-parameter-names)
- [What to do about it, as a rule](PROCESIO-API-NOTES.md#what-to-do-about-it-as-a-rule)
- [The Python action returns what the script PRINTS — assignment is silently useless](PROCESIO-API-NOTES.md#the-python-action-returns-what-the-script-prints-assignment-is-silently-useless)
- [There is NO crypto module in the Node action. Hashing must be implemented in full](PROCESIO-API-NOTES.md#there-is-no-crypto-module-in-the-node-action-hashing-must-be-implemented-in-full)
- [process-create's config CANNOT express a Data Store mapper. Create, then patch](PROCESIO-API-NOTES.md#process-creates-config-cannot-express-a-data-store-mapper-create-then-patch)
- [The Data Store side panel, in full (its properties are addressed at TOP level)](PROCESIO-API-NOTES.md#the-data-store-side-panel-in-full-its-properties-are-addressed-at-top-level)
- [isValid is a field the caller sets, not one the platform computes](PROCESIO-API-NOTES.md#isvalid-is-a-field-the-caller-sets-not-one-the-platform-computes)
- [POST /api/Projects/validate answers "valid" for flows the designer refuses to save](PROCESIO-API-NOTES.md#post-apiprojectsvalidate-answers-valid-for-flows-the-designer-refuses-to-save)
- [A cross-workspace GET is refused as 400, not 404](PROCESIO-API-NOTES.md#a-cross-workspace-get-is-refused-as-400-not-404)
- [toggle-activation only ever deactivates — it never activates](PROCESIO-API-NOTES.md#toggle-activation-only-ever-deactivates-it-never-activates)

## The Python action

Source: [`PROCESIO-PYTHON-ACTION-NOTES.md`](PROCESIO-PYTHON-ACTION-NOTES.md)

- [I/O mechanics — two traps](PROCESIO-PYTHON-ACTION-NOTES.md#io-mechanics-two-traps)
- [spacy is on the list; a spacy MODEL is not](PROCESIO-PYTHON-ACTION-NOTES.md#spacy-is-on-the-list-a-spacy-model-is-not)
- [Where the compute runs, and why it matters for sizing](PROCESIO-PYTHON-ACTION-NOTES.md#where-the-compute-runs-and-why-it-matters-for-sizing)

## Readings that turned out to be wrong

Source: [`PROCESIO-API-CORRECTIONS.md`](PROCESIO-API-CORRECTIONS.md)

- [5. Transport import refused, and workspace creation lies about failing](PROCESIO-API-CORRECTIONS.md#5-transport-import-refused-and-workspace-creation-lies-about-failing)

## Notes not yet indexed here

These carry rules too. They are absent because the `⚠` convention has not
been applied to them yet, not because they hold nothing. Marking a rule in
one of them adds it here on the next build; read them directly meanwhile.

- [`DTO-SUBTOOLS-NOTE.md`](DTO-SUBTOOLS-NOTE.md)
- [`PHASE4-E2E-NOTES.md`](PHASE4-E2E-NOTES.md)
- [`PROCESIO-AUTH-NOTES.md`](PROCESIO-AUTH-NOTES.md)
- [`PROCESIO-CARD-BUILD-NOTES.md`](PROCESIO-CARD-BUILD-NOTES.md)
- [`PROCESIO-CUSTOM-ACTION-NOTES.md`](PROCESIO-CUSTOM-ACTION-NOTES.md)
- [`PROCESIO-DOCS-FIX-REPORT.md`](PROCESIO-DOCS-FIX-REPORT.md)
- [`PROCESIO-ENVIRONMENTS-NOTES.md`](PROCESIO-ENVIRONMENTS-NOTES.md)
- [`PROCESIO-FE-VALIDATION-NOTES.md`](PROCESIO-FE-VALIDATION-NOTES.md)
- [`PROCESIO-FORM-API-HANG-NOTE.md`](PROCESIO-FORM-API-HANG-NOTE.md)
- [`PROCESIO-FORM-SUBMISSION-NOTES.md`](PROCESIO-FORM-SUBMISSION-NOTES.md)
- [`PROCESIO-METERING-NOTES.md`](PROCESIO-METERING-NOTES.md)
- [`PROCESIO-NODE-MODULE-WHITELIST.md`](PROCESIO-NODE-MODULE-WHITELIST.md)
- [`PROCESIO-RECONCILIATION-PATTERNS.md`](PROCESIO-RECONCILIATION-PATTERNS.md)
- [`PROCESIO-RESOURCE-MODEL-NOTES.md`](PROCESIO-RESOURCE-MODEL-NOTES.md)
- [`PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md`](PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md)
- [`PROCESIO-SEND-EMAIL-NOTES.md`](PROCESIO-SEND-EMAIL-NOTES.md)
- [`PROCESIO-SQL-ACTIONS-NOTES.md`](PROCESIO-SQL-ACTIONS-NOTES.md)
