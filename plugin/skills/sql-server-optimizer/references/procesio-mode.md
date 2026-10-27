# PROCESIO SQL action mode

Use this mode for T-SQL executed by PROCESIO Execute Query or Execute Command actions.

## Identify the boundary

- **Native mapping:** SQL uses `@parameter` placeholders and the action maps each parameter to a typed process variable. Preserve exact names and types unless the action configuration changes with the SQL.
- **Inline substitution:** SQL contains `<%Variable%>` tokens. The platform generates SQL text before SQL Server compiles it. This is not database parameterization.

## Migrate inline substitution

Prefer this sequence:

1. Replace each inline token in SQL with an ordinary `@ParameterName` placeholder.
2. Infer no type from spelling alone; verify the target column/process-variable types.
3. Configure the action's native parameter mapping for every placeholder.
4. Define null and empty-string behavior explicitly.
5. Test normal, null, empty, quote-containing, boundary, and invalid values.
6. Inspect the real process instance and database/result side effect.

Do not leave `<%Variable%>` inside a `DECLARE` assignment and call it safe. The value still entered as generated SQL text.

## Query versus command

- A read path must not acquire write behavior through a hidden stored procedure or dynamic statement.
- A command path needs transaction, idempotency, retry, and affected-row expectations.
- A process retry after an unknown database outcome can duplicate effects. Reconcile by business key or idempotency key before rerunning.

## Parameter mapping output

For every parameter, state:

| SQL parameter | SQL type | PROCESIO variable | Null/empty rule | Used in |
|---|---|---|---|---|

Flag mapped-but-unused and referenced-but-unmapped parameters. Do not rename a mapped parameter without updating the action configuration in the same change.

## Verification

SQL correctness is only half the proof. Return to `procesio-cli` to validate and run the surrounding process, inspect the instance, and query the actual database/result when safe.
