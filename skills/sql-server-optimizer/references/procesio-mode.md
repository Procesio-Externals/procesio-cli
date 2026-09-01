# Mode A — PROCESIO SQL Rules

This file applies when the SQL runs inside a PROCESIO **Execute Query** or **Execute Command** action.

PROCESIO has two ways to pass process variables into SQL. Identify which one is in use.

---

## Sub-mode A1 — Inline Variable Injection (`<%VarName%>` tokens)

The user has written `<%VarName%>` directly inside the SQL text. PROCESIO performs string substitution before the query reaches SQL Server — every token is replaced with the raw value as a string. This is the older/legacy pattern.

**What to do:** Convert every `<%VarName%>` into a proper typed `@p_VarName` SQL parameter with a `DECLARE` + injection point at the top of the query. This is the only way to get correct typing, sargable predicates, and safe NULL handling.

### Rule A1-1 — Variable Conversion

- Replace every unique `<%VarName%>` with `@p_VarName`.
- Each unique variable = one declaration. Never duplicate.
- Place all declarations in a `-- parameters` block at the very top, before any other statements.

Pattern:
```sql
-- parameters
DECLARE @p_VarName <InferredType> = <%VarName%>;
```

The `= <%VarName%>` part is the PROCESIO injection point — the platform substitutes the value here at runtime.

### Rule A1-2 — Type Inference

Infer the SQL type from how the variable is used in the query:

| Usage context | Inferred type |
|---------------|--------------|
| Compared to INT / ID column | `INT` |
| Compared to DATE column | `DATE` |
| Compared to DATETIME column | `DATETIME` |
| Used in LIKE or string filter | `NVARCHAR(MAX)` |
| Compared to BIT column | `BIT` |
| Compared to DECIMAL / MONEY column | `DECIMAL(18,2)` |
| Ambiguous / cannot determine | `NVARCHAR(MAX)` — note assumption |

When the type cannot be determined from context, declare as `NVARCHAR(MAX)` and add an explicit `CAST` in the internal var assignment. Note the assumption in Notes.

### Rule A1-3 — Internal Variables (RHS Only)

After `@p_` declarations, declare internal working variables and assign from the params:

```sql
-- internal vars
DECLARE @VarName <Type>;
SET @VarName = @p_VarName;
-- or with cast:
SET @VarName = CAST(@p_VarName AS <TargetType>);
```

**RHS strictly enforced:**
- ✅ `SET @CustomerId = @p_CustomerId`
- ❌ `SET @p_CustomerId = @CustomerId`
- ❌ `SELECT @p_CustomerId` — never project a `@p_` param in SELECT
- ❌ `SELECT *, @p_CustomerId FROM ...`

Use internal vars everywhere in the query body. `@p_` params appear only in `DECLARE`/`SET` assignments.

### Rule A1-4 — Normalization of String Params

After assignment, normalize optional string params using the PROCESIO-standard pattern:

```sql
SET @VarName = CASE WHEN ISNULL(@p_VarName, '') = '' THEN NULL ELSE @p_VarName END;
```

> This differs from the generic `NULLIF(LTRIM(RTRIM(...)))` pattern. In PROCESIO context, trimming is handled upstream; use `ISNULL(...) = ''` as the standard.

Numeric and flag params do not need normalization unless the column comparison requires it.

---

## Sub-mode A2 — Native Parameter Mapping (Parameters Config Tab)

The user has written SQL with `@paramName` style params (no `<%Var%>` tokens, no `DECLARE` block) and maps them to PROCESIO variables in the action's **Parameters config tab**. This is the recommended modern PROCESIO SQL pattern.

Example of what this looks like in the SQL editor:
```sql
DECLARE @isPartner          BIT
       ,@referintaDeclarant NVARCHAR(MAX)
       ,@UIT                NVARCHAR(50)
       ,@codPartenerComercial NVARCHAR(50)
       ,@FormattedDate      DATE
       ,@cui                NVARCHAR(50)
```
With mappings in the Parameters tab: `isPartner → isPartner`, `UIT → UIT`, etc.

**What to do:** Treat the existing `@params` as the injection points. Do NOT rename them (the parameter names must match what's configured in the Parameters tab). Optimize the SQL body normally. Add internal vars for normalization/cleaning if needed, but never reassign into the mapped params.

### Rule A2-1 — Respect Parameter Names

- Keep all existing `@paramName` declarations exactly as-is — name, type, and position.
- Never rename; the Parameters config tab maps by exact name.
- Never add `@p_` prefix to existing params (that would break the mapping).
- Only propose new `@p_` params if you are adding parameters that don't yet exist in the mapping.

### Rule A2-2 — Internal Variables for Normalization

If a param needs cleaning (optional string filter, type normalization), copy to an internal var:

```sql
-- internal vars
DECLARE @ReferintaDeclarantNorm NVARCHAR(MAX);
SET @ReferintaDeclarantNorm = CASE WHEN ISNULL(@referintaDeclarant, '') = '' THEN NULL ELSE @referintaDeclarant END;
```

Never modify the mapped param itself.

### Rule A2-3 — No Projection of Mapped Params

Same rule as A1 — `@params` that are mapped via the Parameters tab must never appear in SELECT column lists. Use an internal var or alias if the value needs to be projected.

---

## Shared PROCESIO Rules (Both A1 and A2)

### Rule AP-1 — Optional Filters

After normalization, always use the canonical optional filter pattern:

```sql
WHERE (@VarName IS NULL OR Table.Column LIKE '%' + @VarName + '%')
```

Never simulate optional filters with row-level CASE:
- ❌ `WHERE Col LIKE CASE WHEN @Var IS NULL THEN '%' ELSE '%' + @Var + '%' END`
- ❌ `WHERE (ISNULL(@Var,'') = '' OR Col = @Var)` — the ISNULL check belongs in the normalization step, not the predicate

`LIKE '%x%'` always causes a full table scan. If the target table is large, warn in Notes and suggest a filtered index or full-text search (FTS).

### Rule AP-2 — NULL Handling

If a mapped parameter value is NULL, PROCESIO automatically sends SQL NULL to the database. This is correct behavior — do not add workarounds for NULL. The normalization pattern converts empty string to NULL so the optional filter pattern works correctly.

### Rule AP-3 — No Stored Procedure / Function Templates in PROCESIO SQL Actions

SQL inside Execute Query / Execute Command actions is a **bare query or script**, not a stored procedure or function. Do not wrap it in `CREATE PROCEDURE` or `CREATE FUNCTION` templates. The Universal Object Rules (signatures, NOCOUNT, READ UNCOMMITTED) apply only when the SQL input is an actual object definition.

---

## PROCESIO Mode Procedure

1. Identify sub-mode: scan for `<%Var%>` tokens (A1) or check user context (A2).
2. **A1**: List all unique `<%VarName%>` → declare `@p_` with inferred types + injection point.
   **A2**: List all existing `@params` → keep as-is; note them in Parameter Mapping.
3. Declare internal vars; normalize string params (ISNULL pattern); assign RHS only.
4. Replace all `<%VarName%>` in query body with internal var names (A1 only).
5. Apply shared SQL rules from `sql-rules.md`.
6. Verify checklist below.
7. Output in unified comment-wrapper format.

---

## PROCESIO Checklist

- [ ] Sub-mode identified: A1 (percent-bracket tokens) or A2 (Parameters tab / native params).
- [ ] **A1**: All `<%Var%>` tokens found and declared as `@p_Var` with inferred types.
- [ ] **A2**: All existing `@params` preserved with exact names and types.
- [ ] Each parameter declared exactly once; no duplicates.
- [ ] Internal vars declared; assigned RHS only; string params normalized via ISNULL pattern.
- [ ] No `@p_` param or mapped `@param` appears in SELECT, ORDER BY, or GROUP BY positions.
- [ ] Optional filters use `(@Var IS NULL OR ...)` — no row-level CASE.
- [ ] If SQL is a bare query/script (not object definition): no proc/function wrappers added.
- [ ] Shared SQL rules applied (see `sql-rules.md`).
- [ ] Output in unified `/*Optimized SQL:*/` comment format.

---

## Examples

### Example A1 — Inline variable injection

**Input:**
```sql
SELECT * FROM dbo.InvoiceArticles IA
INNER JOIN dbo.Invoices I ON IA.Status=1 AND IA.InvoiceId=I.InvoiceId
LEFT JOIN dbo.StockHolders SH ON SH.InvoiceId=I.InvoiceId
WHERE I.IssueDate>='<%FromDate%>' AND I.CustomerId='<%CustomerId%>'
```

**Output:**
```sql
/*Optimized SQL:*/
-- parameters
DECLARE @p_FromDate    NVARCHAR(MAX) = <%FromDate%>;
DECLARE @p_CustomerId  NVARCHAR(MAX) = <%CustomerId%>;

-- internal vars
DECLARE @FromDate    DATE;
DECLARE @CustomerId  INT;
SET @FromDate    = CAST(@p_FromDate AS DATE);
SET @CustomerId  = CAST(@p_CustomerId AS INT);

SELECT I.InvoiceId, IA.ArticleId, I.IssueDate
FROM dbo.Invoices I
    INNER JOIN dbo.InvoiceArticles IA ON IA.InvoiceId = I.InvoiceId AND IA.Status = 1
    LEFT JOIN dbo.StockHolders SH ON SH.InvoiceId = I.InvoiceId
WHERE I.CustomerId = @CustomerId
    AND I.IssueDate >= @FromDate;

/* Parameter Mapping:
@p_FromDate (NVARCHAR(MAX))   -> <%FromDate%> — injected as string, cast to DATE
@p_CustomerId (NVARCHAR(MAX)) -> <%CustomerId%> — injected as string, cast to INT

Notes:
- Converted PROCESIO inline variables to typed SQL parameters via DECLARE/CAST pattern.
- Types inferred from column usage — verify DATE and INT against actual schema.
- Reordered FROM: Invoices (parent, selective) drives the join; IA.Status=1 moved to ON.
- WHERE reordered: equality filter (CustomerId) before range (IssueDate).
- SELECT * replaced with explicit projection; expand column list as needed.
*/
```

### Example A1 — Optional string filter with bad pattern

**Input:**
```sql
SELECT * FROM dbo.UITCodes UC
LEFT JOIN dbo.VehiclePlates VP ON UC.UIT=VP.UIT
WHERE UC.UIT LIKE CASE WHEN '<%RefDec%>'='' THEN '%' ELSE '%<%RefDec%>%' END
```

**Output:**
```sql
/*Optimized SQL:*/
-- parameters
DECLARE @p_RefDec NVARCHAR(MAX) = <%RefDec%>;

-- internal vars
DECLARE @RefDec NVARCHAR(MAX);
SET @RefDec = CASE WHEN ISNULL(@p_RefDec, '') = '' THEN NULL ELSE @p_RefDec END;

SELECT UC.UIT, VP.Ref
FROM dbo.UITCodes UC
    LEFT JOIN dbo.VehiclePlates VP ON VP.UIT = UC.UIT
WHERE (@RefDec IS NULL OR VP.Ref LIKE '%' + @RefDec + '%');

/* Parameter Mapping:
@p_RefDec (NVARCHAR(MAX)) -> <%RefDec%>

Notes:
- Replaced row-level CASE LIKE pattern with canonical optional filter: (@RefDec IS NULL OR ...).
- @RefDec normalized once before query — NULL when empty, value when present.
- SELECT * replaced with explicit projection; expand as needed.
- LIKE '%x%' causes a full scan on VehiclePlates — consider a filtered index or full-text search if this table is large.
*/
```

### Example A2 — Native parameter mapping (Parameters config tab)

**Input** (user says: "this runs in PROCESIO Execute Query, params are mapped in the config tab"):
```sql
DECLARE @isPartner           BIT
       ,@referintaDeclarant  NVARCHAR(MAX)
       ,@UIT                 NVARCHAR(50)
       ,@codPartenerComercial NVARCHAR(50)
       ,@partenerComercial   NVARCHAR(500)
       ,@numarVehicul        NVARCHAR(50)
       ,@FormattedDate       DATE
       ,@cui                 NVARCHAR(50)

SELECT * FROM dbo.VehiclePlates VP
LEFT JOIN dbo.Partners P ON P.UIT=VP.UIT
WHERE VP.UIT=@UIT
    AND (ISNULL(@referintaDeclarant,'')='' OR VP.Ref LIKE '%'+@referintaDeclarant+'%')
    AND (@isPartner IS NULL OR P.IsPartner=@isPartner)
    AND (@FormattedDate IS NULL OR VP.ActiveDate<=@FormattedDate)
```

**Output:**
```sql
/*Optimized SQL:*/
-- parameters (mapped via PROCESIO Parameters config tab — do not rename)
DECLARE @isPartner            BIT
       ,@referintaDeclarant   NVARCHAR(MAX)
       ,@UIT                  NVARCHAR(50)
       ,@codPartenerComercial  NVARCHAR(50)
       ,@partenerComercial    NVARCHAR(500)
       ,@numarVehicul         NVARCHAR(50)
       ,@FormattedDate        DATE
       ,@cui                  NVARCHAR(50)

--Prepare variables
DECLARE @ReferintaNorm NVARCHAR(MAX);
SET @ReferintaNorm = CASE WHEN ISNULL(@referintaDeclarant, '') = '' THEN NULL ELSE @referintaDeclarant END;

SELECT VP.UIT, VP.Ref, VP.ActiveDate, P.IsPartner
FROM dbo.VehiclePlates VP
    LEFT JOIN dbo.Partners P ON P.UIT = VP.UIT
WHERE VP.UIT = @UIT
    AND (@ReferintaNorm IS NULL OR VP.Ref LIKE '%' + @ReferintaNorm + '%')
    AND (@isPartner IS NULL OR P.IsPartner = @isPartner)
    AND (@FormattedDate IS NULL OR VP.ActiveDate <= @FormattedDate);

/* Parameter Mapping:
@isPartner            -> mapped via Parameters config tab
@referintaDeclarant   -> mapped via Parameters config tab
@UIT                  -> mapped via Parameters config tab
@codPartenerComercial -> mapped via Parameters config tab (not used in query — verify if needed)
@partenerComercial    -> mapped via Parameters config tab (not used in query — verify if needed)
@numarVehicul         -> mapped via Parameters config tab (not used in query — verify if needed)
@FormattedDate        -> mapped via Parameters config tab
@cui                  -> mapped via Parameters config tab (not used in query — verify if needed)

Notes:
- Preserved all parameter names exactly — renaming would break the PROCESIO Parameters config tab mapping.
- @referintaDeclarant normalized into @ReferintaNorm; optional filter rewritten to canonical (@Var IS NULL OR ...) pattern.
- Removed row-level ISNULL check from WHERE — normalization now handles it before the query.
- Parameters declared but not used in query (@codPartenerComercial, @partenerComercial, @numarVehicul, @cui) — retained for config tab completeness; verify whether they are intentionally unused or missing from WHERE.
- SELECT * replaced with explicit projection; expand column list as needed.
- LIKE '%x%' on VP.Ref causes full scan — consider full-text index if VehiclePlates is large.
*/
```

### Example A1 — Illegal param projection (common PROCESIO mistake)

**Input:**
```sql
SELECT '<%CustomerId%>', I.InvoiceId FROM dbo.Invoices I WHERE I.CustomerId='<%CustomerId%>'
```

**Output:**
```sql
/*Optimized SQL:*/
-- parameters
DECLARE @p_CustomerId NVARCHAR(MAX) = <%CustomerId%>;

-- internal vars
DECLARE @CustomerId INT;
SET @CustomerId = CAST(@p_CustomerId AS INT);

SELECT @CustomerId AS CustomerId, I.InvoiceId
FROM dbo.Invoices I
WHERE I.CustomerId = @CustomerId;

/* Parameter Mapping:
@p_CustomerId (NVARCHAR(MAX)) -> <%CustomerId%> — injected as string, cast to INT

Notes:
- <%CustomerId%> was projected in SELECT — converted to internal var @CustomerId and projected instead. @p_ parameters must never appear in SELECT or any non-SET position.
- Explicit CAST applied; INT inferred from column usage — verify against schema.
*/
```
