# Documents and files

## Goal

Create or change a document/file workflow and prove the generated artifact's bytes and meaningful content, not only the template or successful process status.

## Preconditions

- Identify workspace, document/process IDs, template variables, sample data, expected format/name, size limits, retention/privacy policy, and output destination.
- Use sanitized fixtures for documents containing personal, financial, or regulated data.

## Inspect

1. Fetch the document template, variable schema, producing process, file mappings, and any conversion/storage actions.
2. Check fonts/assets, dynamic tables/images, encoding/diacritics, file names, MIME types, and downstream consumers.
3. Record a known-good sample artifact when parity matters.

## Preview and approval

- Preview the document DTO/template and process mappings before save.
- Show any overwrite, external upload, email/send, or retention side effect separately.
- Generating a local/test artifact may be safe; sending or publishing it is a distinct mutation.

## Execute

1. Save/re-fetch the template or process change.
2. Run the producing process once with representative sample data.
3. Read the instance output and download the exact file by returned ID/path.
4. Keep artifact generation separate from distribution so each boundary can be verified.

## Verify

- File exists, is non-empty, has expected name/MIME/size, and opens with the intended parser/viewer.
- Inspect meaningful content: expected text/fields, page/sheet count, tables/images, encoding, and absence of unresolved template tokens.
- Compare digest or selected semantic fields with a baseline when parity is required.
- Verify downstream storage or attachment only if authorized, and check the destination directly.

## Recovery and cleanup

Do not delete a failed artifact before capturing diagnostics. Remove sanitized test outputs from shared storage after acceptance according to policy. If distribution occurred incorrectly, stop further sends, preserve IDs, and follow the destination's recall/delete process with explicit approval.

## Evidence

Return document/process/instance/file IDs, artifact path or destination, digest and key metadata, semantic checks performed, unresolved differences, and whether distribution was intentionally skipped.
