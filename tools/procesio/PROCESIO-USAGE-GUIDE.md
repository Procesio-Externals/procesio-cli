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

**136 rules across 7 notes.**

## The API, and what its answers actually mean

Source: [`PROCESIO-API-NOTES.md`](PROCESIO-API-NOTES.md)

- [DTO casing — live API is camelCase, exports are PascalCase (bites parsers)](PROCESIO-API-NOTES.md#dto-casing-live-api-is-camelcase-exports-are-pascalcase-bites-parsers)
- [Export / Import — the .procesio bundle (Transport)](PROCESIO-API-NOTES.md#export-import-the-procesio-bundle-transport)
- [Validation oracles (use before committing a create/edit)](PROCESIO-API-NOTES.md#validation-oracles-use-before-committing-a-createedit)
- [Auth & client gotchas](PROCESIO-API-NOTES.md#auth-client-gotchas)
- [Endpoints + methods (tag Schedules; permission in parens)](PROCESIO-API-NOTES.md#endpoints-methods-tag-schedules-permission-in-parens)
- [Notification EMAIL — what it carries, and what fires OnFail (measured live)](PROCESIO-API-NOTES.md#notification-email-what-it-carries-and-what-fires-onfail-measured-live)
- [Data Store — what builds today, and the two properties that do not](PROCESIO-API-NOTES.md#data-store-what-builds-today-and-the-two-properties-that-do-not)
- [A Node's <%i%> INLINES THE VALUE AS RAW TEXT](PROCESIO-API-NOTES.md#a-nodes-i-inlines-the-value-as-raw-text)
- [A For Each needs its FULL parameter set, and TWO outgoing edges](PROCESIO-API-NOTES.md#a-for-each-needs-its-full-parameter-set-and-two-outgoing-edges)
- [JS OFFSETS ARE UTF-16 CODE UNITS, SO A PYTHON ORACLE MUST NOT SLICE BY THEM](PROCESIO-API-NOTES.md#js-offsets-are-utf-16-code-units-so-a-python-oracle-must-not-slice-by-them)
- [THE RULE BOTH RECOVERIES TAUGHT, and it is now twice](PROCESIO-API-NOTES.md#the-rule-both-recoveries-taught-and-it-is-now-twice)
- [A Data Store action's sub-fields are GATED ON THE OPERATION VALUE](PROCESIO-API-NOTES.md#a-data-store-actions-sub-fields-are-gated-on-the-operation-value)
- [A CONSTANT column in Set Values needs NO variable binding (F-1381)](PROCESIO-API-NOTES.md#a-constant-column-in-set-values-needs-no-variable-binding-f-1381)
- [UpdateRows updates IN PLACE, matched by a keyed Where — only the matched row moves (F-1382)](PROCESIO-API-NOTES.md#updaterows-updates-in-place-matched-by-a-keyed-where-only-the-matched-row-moves-f-1382)
- [AN ANONYMOUS RESUME MAKES THE CORRELATION ID THE ACCESS CONTROL (F-1384)](PROCESIO-API-NOTES.md#an-anonymous-resume-makes-the-correlation-id-the-access-control-f-1384)
- [INSTRUMENT RULE: A PERMISSIONS FACT COMES FROM THE ASSIGNABLE ROLE MODEL](PROCESIO-API-NOTES.md#instrument-rule-a-permissions-fact-comes-from-the-assignable-role-model)
- [AN API KEY INHERITS ITS OWNER'S AUTHORISATION. IT CARRIES NO SCOPE OF ITS OWN](PROCESIO-API-NOTES.md#an-api-key-inherits-its-owners-authorisation-it-carries-no-scope-of-its-own)
- [✅ POST /api/DataStore/{id}/rows IS WHOLE-BATCH ATOMIC](PROCESIO-API-NOTES.md#post-apidatastoreidrows-is-whole-batch-atomic)
- [InsertRows TAKES ELEMENT 0 OF A LIST. THERE IS NO NATIVE BATCH WRITE](PROCESIO-API-NOTES.md#insertrows-takes-element-0-of-a-list-there-is-no-native-batch-write)
- [A native Set Values mapper writes a COMPUTED value only from a TYPED variable, and CANNOT write a null DateTime](PROCESIO-API-NOTES.md#a-native-set-values-mapper-writes-a-computed-value-only-from-a-typed-variable-and-cannot-write-a-null-datetime)
- [REPORT THE AMBIGUITY RATHER THAN PICKING A WINNER](PROCESIO-API-NOTES.md#report-the-ambiguity-rather-than-picking-a-winner)
- [A GATE THAT CHECKS A CONTAINER HAS NOT CHECKED ITS CONTENTS](PROCESIO-API-NOTES.md#a-gate-that-checks-a-container-has-not-checked-its-contents)
- [VERIFY A FIXTURE CONTAINS WHAT IT CLAIMS BEFORE MEASURING ON IT](PROCESIO-API-NOTES.md#verify-a-fixture-contains-what-it-claims-before-measuring-on-it)
- [BUILD THROUGH THE BUILDER. A RAW PUT IS A DEBUGGING INSTRUMENT](PROCESIO-API-NOTES.md#build-through-the-builder-a-raw-put-is-a-debugging-instrument)
- [A large flow body cannot go through the CLI --body arg (Windows argv ceiling)](PROCESIO-API-NOTES.md#a-large-flow-body-cannot-go-through-the-cli---body-arg-windows-argv-ceiling)
- [A FAIL-CLOSED COMPONENT REPORTS FAILURE IN ITS OUTPUT, NOT AS AN ERROR](PROCESIO-API-NOTES.md#a-fail-closed-component-reports-failure-in-its-output-not-as-an-error)
- [A FAIL-CLOSED GATE MUST REACH NESTED SPEC KINDS](PROCESIO-API-NOTES.md#a-fail-closed-gate-must-reach-nested-spec-kinds)
- [AN API-BUILT ACTION WITH A PARTIAL PARAMETER SET IS UNOPENABLE IN THE DESIGNER](PROCESIO-API-NOTES.md#an-api-built-action-with-a-partial-parameter-set-is-unopenable-in-the-designer)
- [RESOLVED (2026-08-24). The mapper row format](PROCESIO-API-NOTES.md#resolved-2026-08-24-the-mapper-row-format)
- [rowkey uniqueness, and why a presence check is not a landing check](PROCESIO-API-NOTES.md#rowkey-uniqueness-and-why-a-presence-check-is-not-a-landing-check)
- [Cross-workspace triggering: PROCESS ids are workspace-scoped too](PROCESIO-API-NOTES.md#cross-workspace-triggering-process-ids-are-workspace-scoped-too)
- [A Data Store id is WORKSPACE-SCOPED, not a global handle](PROCESIO-API-NOTES.md#a-data-store-id-is-workspace-scoped-not-a-global-handle)
- [An imported process carrying a Data Store mapper CANNOT RUN](PROCESIO-API-NOTES.md#an-imported-process-carrying-a-data-store-mapper-cannot-run)
- [Live-confirmed on a clock build (2026-09-01) — six facts a store-binding card meets](PROCESIO-API-NOTES.md#live-confirmed-on-a-clock-build-2026-09-01-six-facts-a-store-binding-card-meets)
- [Node action injection RAW-INSERTS the value — never inject free-form text](PROCESIO-API-NOTES.md#node-action-injection-raw-inserts-the-value-never-inject-free-form-text)
- [Forms: form-create takes an AUTHORING CONFIG, never a stored DTO](PROCESIO-API-NOTES.md#forms-form-create-takes-an-authoring-config-never-a-stored-dto)
- [DataStore (/api/DataStore) — new module (2026-08)](PROCESIO-API-NOTES.md#datastore-apidatastore-new-module-2026-08)
- [Schema mutation after creation — add a column with PUT, NEVER via the backing model](PROCESIO-API-NOTES.md#schema-mutation-after-creation-add-a-column-with-put-never-via-the-backing-model)
- [Writing a flow definition: three ways the write layer misreports itself](PROCESIO-API-NOTES.md#writing-a-flow-definition-three-ways-the-write-layer-misreports-itself)
- [Data Store is an ACTION, and what it can do](PROCESIO-API-NOTES.md#data-store-is-an-action-and-what-it-can-do)
- [Exports: what can be named, and what a pack section proves](PROCESIO-API-NOTES.md#exports-what-can-be-named-and-what-a-pack-section-proves)
- [Flow control: what blocks, what does not, and what is absent](PROCESIO-API-NOTES.md#flow-control-what-blocks-what-does-not-and-what-is-absent)
- [The Data Store action: what it takes, and four ways it refuses](PROCESIO-API-NOTES.md#the-data-store-action-what-it-takes-and-four-ways-it-refuses)
- [Data Stores in an export pack: measured, after the tool was fixed](PROCESIO-API-NOTES.md#data-stores-in-an-export-pack-measured-after-the-tool-was-fixed)
- [DataStore error surface — read the code and target BEFORE bisecting](PROCESIO-API-NOTES.md#datastore-error-surface-read-the-code-and-target-before-bisecting)
- [The known length cap](PROCESIO-API-NOTES.md#the-known-length-cap)
- [503 / statusCode 100 / target datastore is a PLATFORM row-store outage, not your request](PROCESIO-API-NOTES.md#503-statuscode-100-target-datastore-is-a-platform-row-store-outage-not-your-request)
- [PATCH /api/Projects/{id}/toggle-activation without its state header — CORRECTED](PROCESIO-API-NOTES.md#patch-apiprojectsidtoggle-activation-without-its-state-header-corrected)
- [Node action: <%N%> interpolates a variable RAW into the JavaScript source](PROCESIO-API-NOTES.md#node-action-n-interpolates-a-variable-raw-into-the-javascript-source)
- [Instance status codes](PROCESIO-API-NOTES.md#instance-status-codes)
- [The script engine's capabilities, MEASURED on Internal-PROD 25-08-2026](PROCESIO-API-NOTES.md#the-script-engines-capabilities-measured-on-internal-prod-25-08-2026)
- [What a Data Store SelectRows hands a Node action](PROCESIO-API-NOTES.md#what-a-data-store-selectrows-hands-a-node-action)
- [A pack is a SKELETON: structure travels, bindings do not](PROCESIO-API-NOTES.md#a-pack-is-a-skeleton-structure-travels-bindings-do-not)
- [THE ONE BINDING THAT DOES TRAVEL — AND IT CARRIES A BEARER ID](PROCESIO-API-NOTES.md#the-one-binding-that-does-travel-and-it-carries-a-bearer-id)
- [Binding a webhook to a process: put-projects, never process-edit](PROCESIO-API-NOTES.md#binding-a-webhook-to-a-process-put-projects-never-process-edit)
- [The req/opt column in this API reference does NOT carry information](PROCESIO-API-NOTES.md#the-reqopt-column-in-this-api-reference-does-not-carry-information)
- [The gateway's middleware chain answers before the controller does](PROCESIO-API-NOTES.md#the-gateways-middleware-chain-answers-before-the-controller-does)
- [A working webhook binding, measured from 29 production exports](PROCESIO-API-NOTES.md#a-working-webhook-binding-measured-from-29-production-exports)
- [Read UPSTREAM LATENCY on a refusal — it separates two classes no status code does](PROCESIO-API-NOTES.md#read-upstream-latency-on-a-refusal-it-separates-two-classes-no-status-code-does)
- [A form maps fields to process variables BY NAME; a webhook cannot](PROCESIO-API-NOTES.md#a-form-maps-fields-to-process-variables-by-name-a-webhook-cannot)
- [The anonymous store path's 401 is NOT produced by the application](PROCESIO-API-NOTES.md#the-anonymous-store-paths-401-is-not-produced-by-the-application)
- [A form INSTANCE does not unlock the anonymous store path](PROCESIO-API-NOTES.md#a-form-instance-does-not-unlock-the-anonymous-store-path)
- [A form's DATA-STORE binding is an element EVENT, not an element type](PROCESIO-API-NOTES.md#a-forms-data-store-binding-is-an-element-event-not-an-element-type)
- [The anonymous api/Form/dataStore/{id}/rows path refuses a bound form's own store](PROCESIO-API-NOTES.md#the-anonymous-apiformdatastoreidrows-path-refuses-a-bound-forms-own-store)
- [Creating a Data Store from JSON — two required things the DTO does not shout](PROCESIO-API-NOTES.md#creating-a-data-store-from-json-two-required-things-the-dto-does-not-shout)
- [The FormProcess anonymous route resolves the process WITHIN the form's workspace](PROCESIO-API-NOTES.md#the-formprocess-anonymous-route-resolves-the-process-within-the-forms-workspace)
- [A process built by process-create + put-projects is created INACTIVE](PROCESIO-API-NOTES.md#a-process-built-by-process-create-put-projects-is-created-inactive)
- [Sub-workspace create/delete on a capped Business plan is lossy — reconcile from the ledger](PROCESIO-API-NOTES.md#sub-workspace-createdelete-on-a-capped-business-plan-is-lossy-reconcile-from-the-ledger)
- [A form template is fetchable ANONYMOUSLY — measured](PROCESIO-API-NOTES.md#a-form-template-is-fetchable-anonymously-measured)
- [A native Data Store node is WORKSPACE-SCOPED — cross-workspace store access needs a Call API, not a node](PROCESIO-API-NOTES.md#a-native-data-store-node-is-workspace-scoped-cross-workspace-store-access-needs-a-call-api-not-a-node)
- [THIS REPO SHIPS A FULL API REFERENCE — READ IT BEFORE PROBING](PROCESIO-API-NOTES.md#this-repo-ships-a-full-api-reference-read-it-before-probing)
- [FlowStatus, verbatim](PROCESIO-API-NOTES.md#flowstatus-verbatim)
- [A webhook binding cannot map FIELDS — one variable gets the WHOLE body](PROCESIO-API-NOTES.md#a-webhook-binding-cannot-map-fields-one-variable-gets-the-whole-body)
- [A webhook launch CREATES an instance that does not necessarily RUN](PROCESIO-API-NOTES.md#a-webhook-launch-creates-an-instance-that-does-not-necessarily-run)
- [Revoking a webhook: UNBIND FIRST](PROCESIO-API-NOTES.md#revoking-a-webhook-unbind-first)
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
- [Data Store InsertRows does NOT fan out a list-bound mapper](PROCESIO-API-NOTES.md#data-store-insertrows-does-not-fan-out-a-list-bound-mapper)
- [For Each — containment is ParentId, and identity is never the name](PROCESIO-API-NOTES.md#for-each-containment-is-parentid-and-identity-is-never-the-name)
- [The insert-per-element shape that works](PROCESIO-API-NOTES.md#the-insert-per-element-shape-that-works)
- [The anonymous form/dataStore path is scoped to the WORKSPACE, not the form](PROCESIO-API-NOTES.md#the-anonymous-formdatastore-path-is-scoped-to-the-workspace-not-the-form)
- [The 401 on /rows is a ROUTING failure, not an auth failure](PROCESIO-API-NOTES.md#the-401-on-rows-is-a-routing-failure-not-an-auth-failure)
- [A data-model-typed input variable is not delivered by run-process --payload](PROCESIO-API-NOTES.md#a-data-model-typed-input-variable-is-not-delivered-by-run-process---payload)
- [Extract Text returns ONE page object per page — a no-text page is NOT an empty list (measured)](PROCESIO-API-NOTES.md#extract-text-returns-one-page-object-per-page-a-no-text-page-is-not-an-empty-list-measured)
- [CSV/XLSX read-actions return THREE different empty-shapes — and per-action status 90 = FAILED (measured)](PROCESIO-API-NOTES.md#csvxlsx-read-actions-return-three-different-empty-shapes-and-per-action-status-90-failed-measured)
- [A NULL variable injected at <%N%> is a captured SyntaxError that SILENTLY ADMITS — use [<%N%>][0] (measured)](PROCESIO-API-NOTES.md#a-null-variable-injected-at-n-is-a-captured-syntaxerror-that-silently-admits-use-n0-measured)
- [Reading a finished run's output values: result.variable is keyed BY the variable name (measured)](PROCESIO-API-NOTES.md#reading-a-finished-runs-output-values-resultvariable-is-keyed-by-the-variable-name-measured)
- [isValid is a field the caller sets, not one the platform computes](PROCESIO-API-NOTES.md#isvalid-is-a-field-the-caller-sets-not-one-the-platform-computes)
- [POST /api/Projects/validate answers "valid" for flows the designer refuses to save](PROCESIO-API-NOTES.md#post-apiprojectsvalidate-answers-valid-for-flows-the-designer-refuses-to-save)
- [Every resource read is workspace-scoped, and the designer URL carries the workspace](PROCESIO-API-NOTES.md#every-resource-read-is-workspace-scoped-and-the-designer-url-carries-the-workspace)
- [toggle-activation takes the target state in a REQUEST HEADER, not a body](PROCESIO-API-NOTES.md#toggle-activation-takes-the-target-state-in-a-request-header-not-a-body)
- [Processing-time BILLING is readable per-workspace and per-run — and the meter is not what you'd guess](PROCESIO-API-NOTES.md#processing-time-billing-is-readable-per-workspace-and-per-run-and-the-meter-is-not-what-youd-guess)
- [A Data Store lives in EXACTLY ONE workspace. There is no master → sub inheritance](PROCESIO-API-NOTES.md#a-data-store-lives-in-exactly-one-workspace-there-is-no-master-sub-inheritance)
- [✅ Read AND write are credential-free. The native action has nowhere to put a credential](PROCESIO-API-NOTES.md#read-and-write-are-credential-free-the-native-action-has-nowhere-to-put-a-credential)
- [Export carries SCHEMA ONLY. Rows never travel in a pack](PROCESIO-API-NOTES.md#export-carries-schema-only-rows-never-travel-in-a-pack)
- [Creation, column types, and the duplicate-key contract](PROCESIO-API-NOTES.md#creation-column-types-and-the-duplicate-key-contract)
- [Limits — measured, and the ones that are NOT what the flow-value figure suggests](PROCESIO-API-NOTES.md#limits-measured-and-the-ones-that-are-not-what-the-flow-value-figure-suggests)
- [What an API import carries, and what it leaves behind](PROCESIO-API-NOTES.md#what-an-api-import-carries-and-what-it-leaves-behind)
- [Re-importing an updated pack: what overrideData really does](PROCESIO-API-NOTES.md#re-importing-an-updated-pack-what-overridedata-really-does)
- [Workspace scoping of ids, instances, credentials and files](PROCESIO-API-NOTES.md#workspace-scoping-of-ids-instances-credentials-and-files)
- [Capacity and consumption are pooled at the master](PROCESIO-API-NOTES.md#capacity-and-consumption-are-pooled-at-the-master)
- [Surgical live edits: placeholder quoting, layer counts, decisional retargeting](PROCESIO-API-NOTES.md#surgical-live-edits-placeholder-quoting-layer-counts-decisional-retargeting)
- [Surgical live edits, part 2: single-inbound decisionals, error ports, failure-path defaults](PROCESIO-API-NOTES.md#surgical-live-edits-part-2-single-inbound-decisionals-error-ports-failure-path-defaults)
- [Auditing a workspace: three traps on the read path](PROCESIO-API-NOTES.md#auditing-a-workspace-three-traps-on-the-read-path)
- [Transport import PRESERVES resource ids across workspaces](PROCESIO-API-NOTES.md#transport-import-preserves-resource-ids-across-workspaces)
- [Data-store access control is per WORKSPACE, never per store](PROCESIO-API-NOTES.md#data-store-access-control-is-per-workspace-never-per-store)
- [Importing tools.procesio.main as a library RE-EXECUTES the CLI](PROCESIO-API-NOTES.md#importing-toolsprocesiomain-as-a-library-re-executes-the-cli)
- [A save can be refused by a limit the action's own metadata says is legal](PROCESIO-API-NOTES.md#a-save-can-be-refused-by-a-limit-the-actions-own-metadata-says-is-legal)
- [changed is the intent, put is the outcome](PROCESIO-API-NOTES.md#changed-is-the-intent-put-is-the-outcome)
- [Variable substitution into a script is LITERAL, and a json variable IS the escaping mechanism](PROCESIO-API-NOTES.md#variable-substitution-into-a-script-is-literal-and-a-json-variable-is-the-escaping-mechanism)
- [Consequence: a form field cannot feed a json-typed process input](PROCESIO-API-NOTES.md#consequence-a-form-field-cannot-feed-a-json-typed-process-input)

## Procesio Instance History Notes

Source: [`PROCESIO-INSTANCE-HISTORY-NOTES.md`](PROCESIO-INSTANCE-HISTORY-NOTES.md)

- [Traps (each cost a real diagnosis)](PROCESIO-INSTANCE-HISTORY-NOTES.md#traps-each-cost-a-real-diagnosis)
- [Reading history from INSIDE a flow — binding matters](PROCESIO-INSTANCE-HISTORY-NOTES.md#reading-history-from-inside-a-flow-binding-matters)
- [Get Recent Instances at RUNTIME — measured, and it corrects the action doc](PROCESIO-INSTANCE-HISTORY-NOTES.md#get-recent-instances-at-runtime-measured-and-it-corrects-the-action-doc)
- [Capturing a run's output — capture it LIVE, don't count on reading it back](PROCESIO-INSTANCE-HISTORY-NOTES.md#capturing-a-runs-output-capture-it-live-dont-count-on-reading-it-back)
- [Only FORM-launched instances are LISTED; API-launched ones are only COUNTED](PROCESIO-INSTANCE-HISTORY-NOTES.md#only-form-launched-instances-are-listed-api-launched-ones-are-only-counted)
- [There is no version anywhere on either object](PROCESIO-INSTANCE-HISTORY-NOTES.md#there-is-no-version-anywhere-on-either-object)

## Procesio Foreach Notes

Source: [`PROCESIO-FOREACH-NOTES.md`](PROCESIO-FOREACH-NOTES.md)

- [A programmatically-built For Each is missing two parameters a designer-built one has](PROCESIO-FOREACH-NOTES.md#a-programmatically-built-for-each-is-missing-two-parameters-a-designer-built-one-has)
- [The failure mode: the loop times out without iterating a populated list](PROCESIO-FOREACH-NOTES.md#the-failure-mode-the-loop-times-out-without-iterating-a-populated-list)
- [CONFIRMED (causal test done): the two parameters ARE the cause, and the timeout is NOT](PROCESIO-FOREACH-NOTES.md#confirmed-causal-test-done-the-two-parameters-are-the-cause-and-the-timeout-is-not)

## Procesio Node Code Notes

Source: [`PROCESIO-NODE-CODE-NOTES.md`](PROCESIO-NODE-CODE-NOTES.md)

- [1. <%N%> substitution into a Node's Code is TEXT substitution, and only an OBJECT value is safe](PROCESIO-NODE-CODE-NOTES.md#1-n-substitution-into-a-nodes-code-is-text-substitution-and-only-an-object-value-is-safe)
- [2. A process can read its own workspace's run history in-flow, with NO credential](PROCESIO-NODE-CODE-NOTES.md#2-a-process-can-read-its-own-workspaces-run-history-in-flow-with-no-credential)
- [3. Editing a live Node's Code in place: fix BOTH copies (runtime param AND designer customData)](PROCESIO-NODE-CODE-NOTES.md#3-editing-a-live-nodes-code-in-place-fix-both-copies-runtime-param-and-designer-customdata)

## The Python action

Source: [`PROCESIO-PYTHON-ACTION-NOTES.md`](PROCESIO-PYTHON-ACTION-NOTES.md)

- [I/O mechanics — two traps](PROCESIO-PYTHON-ACTION-NOTES.md#io-mechanics-two-traps)
- [spacy is on the list; a spacy MODEL is not](PROCESIO-PYTHON-ACTION-NOTES.md#spacy-is-on-the-list-a-spacy-model-is-not)
- [Where the compute runs, and why it matters for sizing](PROCESIO-PYTHON-ACTION-NOTES.md#where-the-compute-runs-and-why-it-matters-for-sizing)

## Readings that turned out to be wrong

Source: [`PROCESIO-API-CORRECTIONS.md`](PROCESIO-API-CORRECTIONS.md)

- [5. Transport import refused, and workspace creation lies about failing](PROCESIO-API-CORRECTIONS.md#5-transport-import-refused-and-workspace-creation-lies-about-failing)

## Building a card

Source: [`PROCESIO-CARD-BUILD-NOTES.md`](PROCESIO-CARD-BUILD-NOTES.md)

- [9. Assembling a file-in / file-out card through the builder (the renderer wiring)](PROCESIO-CARD-BUILD-NOTES.md#9-assembling-a-file-in-file-out-card-through-the-builder-the-renderer-wiring)

## Notes not yet indexed here

These carry rules too. They are absent because the `⚠` convention has not
been applied to them yet, not because they hold nothing. Marking a rule in
one of them adds it here on the next build; read them directly meanwhile.

- [`DTO-SUBTOOLS-NOTE.md`](DTO-SUBTOOLS-NOTE.md)
- [`PHASE4-E2E-NOTES.md`](PHASE4-E2E-NOTES.md)
- [`PROCESIO-AUTH-NOTES.md`](PROCESIO-AUTH-NOTES.md)
- [`PROCESIO-CONNECTORS-NOTES.md`](PROCESIO-CONNECTORS-NOTES.md)
- [`PROCESIO-CUSTOM-ACTION-NOTES.md`](PROCESIO-CUSTOM-ACTION-NOTES.md)
- [`PROCESIO-DOCS-FIX-REPORT.md`](PROCESIO-DOCS-FIX-REPORT.md)
- [`PROCESIO-ENVIRONMENTS-NOTES.md`](PROCESIO-ENVIRONMENTS-NOTES.md)
- [`PROCESIO-FE-VALIDATION-NOTES.md`](PROCESIO-FE-VALIDATION-NOTES.md)
- [`PROCESIO-FORM-API-HANG-NOTE.md`](PROCESIO-FORM-API-HANG-NOTE.md)
- [`PROCESIO-FORM-SUBMISSION-NOTES.md`](PROCESIO-FORM-SUBMISSION-NOTES.md)
- [`PROCESIO-METERING-NOTES.md`](PROCESIO-METERING-NOTES.md)
- [`PROCESIO-NODE-MODULE-WHITELIST.md`](PROCESIO-NODE-MODULE-WHITELIST.md)
- [`PROCESIO-QUERY-STORE-NOTES.md`](PROCESIO-QUERY-STORE-NOTES.md)
- [`PROCESIO-RECONCILIATION-PATTERNS.md`](PROCESIO-RECONCILIATION-PATTERNS.md)
- [`PROCESIO-RESOURCE-MODEL-NOTES.md`](PROCESIO-RESOURCE-MODEL-NOTES.md)
- [`PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md`](PROCESIO-SEND-EMAIL-CRED-OPTIONALITY.md)
- [`PROCESIO-SEND-EMAIL-NOTES.md`](PROCESIO-SEND-EMAIL-NOTES.md)
- [`PROCESIO-SQL-ACTIONS-NOTES.md`](PROCESIO-SQL-ACTIONS-NOTES.md)
- [`SCHEDULE-INPUT-SECURITY-NOTES.md`](SCHEDULE-INPUT-SECURITY-NOTES.md)
