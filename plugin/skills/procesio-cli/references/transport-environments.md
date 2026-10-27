# Transport and environments

## Goal

Move selected PROCESIO resources between workspaces or installations without leaking secrets, overwriting the wrong target, or declaring success before dependency verification.

## Preconditions

- Identify source/destination installations, workspace IDs, credential profiles, selected resources, overwrite policy, activation policy, and rollback owner.
- Confirm source read/export rights and destination import/admin rights.
- Inventory dependencies: data models, processes, forms, documents, webhooks, schedules, credentials, custom actions, and child-process references.

## Inspect

1. Resolve both environments and workspaces by stable ID; print a compact source/destination banner.
2. Fetch source resource inventory and destination collisions.
3. Determine which references are portable and which must be rebound after import.
4. Ensure credential secret export is disabled unless the user explicitly authorizes a secure exceptional path.

Apply the pre-acquisition confidentiality gate in `references/process-lifecycle.md`
before reading/exporting configurations. Disabling credential export does not exclude
inline secrets in process/form/schedule fields, response variables or logs. Establish
source-side exclusion or approved secure handling before acquisition; checking the
artifact afterward is an additional check, not prevention of an earlier exposure.

## Preview and approval

- Run export/import dry-run or selection preview where available.
- Show selected resource names/IDs, excluded sensitive data, overwrite flags, destination collisions, and expected post-import inactive state.
- Obtain approval for the exact destination and overwrite set.

## Execute

1. Export to a named artifact and record its digest.
2. Import once with explicit per-resource include/overwrite choices.
3. Treat timeout/lost response as unknown outcome and inventory destination before retry.
4. Rebind environment-specific credentials, URLs, workspace IDs, schedules, webhooks, and custom-action dependencies without copying secrets into files.

## Verify

- Destination inventory contains the intended resources once, with expected names and relationships.
- Imported processes/forms/documents validate.
- Triggers remain in the agreed safe state until verification completes.
- Run representative smoke tests in the destination and inspect instances/outputs/side effects.
- Confirm no credential secrets entered the export artifact or logs.

## Recovery and cleanup

Prefer a pre-import destination export or isolated destination workspace as rollback. If import partially succeeds, inventory and reconcile; do not blindly re-import. Remove only resources proven to have been created by this transport and preserve the artifact/evidence until acceptance.

## Evidence

Return source/destination IDs, artifact path/digest, exact selection/overwrite policy, import result, dependency rebindings, validation/smoke-test IDs, activation state, and rollback artifact.
