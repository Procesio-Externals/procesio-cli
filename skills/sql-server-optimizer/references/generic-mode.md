# Mode B — Generic SQL Rules

This file applies when the input is plain T-SQL with no PROCESIO context: raw queries with literals, stored procedures, functions, or multi-statement scripts.

---

## Rule G1 — Respect Existing Params

- Keep existing params (e.g., `@CustomerId`) unless renaming materially improves clarity.
- Never assign into input params. If normalization is needed, copy to an internal var:
  - ✅ `SET @RefNorm = NULLIF(LTRIM(RTRIM(@Ref)), '')`
  - ❌ `SET @Ref = NULLIF(LTRIM(RTRIM(@Ref)), '')` — modifying the input param

---

## Rule G2 — Propose Params for High-Impact Literals

- Parameterize repeated or filter-critical literals (dates, IDs, flags, filter strings) as `@p_<MeaningfulName>`.
- Place in a `-- parameters (proposed)` block at the top.
- Do **not** parameterize:
  - Column names or table names (unless dynamic SQL is explicitly required).
  - One-off semantic constants (e.g., `Status = 1` as a fixed business rule).

---

## Rule G3 — Internal Normalization

- `DECLARE @p_*` only for newly proposed params.
- Declare internal vars only when useful; assign RHS-only:
  - ✅ `SET @FromDate = @p_FromDate`
  - ❌ `SET @p_FromDate = @FromDate`
- Normalize optional string params once:
  ```sql
  SET @RefNorm = NULLIF(LTRIM(RTRIM(@Ref)), '');
  ```
- Precompute flags/scalars once; reuse:
  ```sql
  DECLARE @IsActive BIT = CASE WHEN @Status = 1 THEN 1 ELSE 0 END;
  ```
- Avoid per-row `ISNULL/COALESCE/CASE` in predicates when a precomputed scalar works.

---

## Rule G4 — Object Awareness (Procs & Functions)

For all object definitions (stored procedures and functions):

1. Always add or keep the signature header block.
2. Always add or keep `SET NOCOUNT ON` + `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED`.
3. Follow the appropriate template below.

These are non-negotiable — they apply to every object, every time. See also Universal Object Rules in SKILL.md.

### Stored Procedure Template

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: <Description,,>
-- =============================================
CREATE PROCEDURE <schema_name>.<ProcedureName>
    <@Param1> <DataType> = <Default>
AS
BEGIN
    SET NOCOUNT ON
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED

    -- internal vars and body here
END
GO
```

### Inline TVF Template (preferred over multi-statement)

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: <Description,,>
-- =============================================
CREATE FUNCTION <schema>.<FunctionName>
(
    <@param1> <DataType>
)
RETURNS TABLE
AS
RETURN
(
    SELECT ...
)
GO
```

> Inline TVFs do not have a BEGIN/END block, so SET NOCOUNT and SET TRANSACTION ISOLATION LEVEL cannot be placed inside them. Note this in Notes if relevant.

### Multi-statement TVF Template (flag perf risk in Notes)

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: <Description,,>
-- =============================================
CREATE FUNCTION <schema>.<FunctionName>
(
    <@param1> <DataType>
)
RETURNS @Result TABLE
(
    <Col1> <DataType>,
    <Col2> <DataType>
)
AS
BEGIN
    SET NOCOUNT ON
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED

    -- fill @Result
    RETURN
END
GO
```

### Scalar Function Template

```sql
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: <Description,,>
-- =============================================
CREATE FUNCTION <schema>.<FunctionName>
(
    <@Param1> <DataType>
)
RETURNS <ReturnType>
AS
BEGIN
    SET NOCOUNT ON
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED

    DECLARE @Result <ReturnType>
    SELECT @Result = <@Param1>
    RETURN @Result
END
GO
```

---

## Rule G5 — Semantics Preservation

- Never change result set meaning unless explicitly told.
- Don't convert LEFT↔INNER unless equivalence is provable; otherwise keep and note assumption.
- Preserve NULL/three-valued logic; be careful when moving predicates between ON and WHERE.
- If ambiguity exists: keep original semantics, state assumption in Notes.

---

## Rule G6 — Proc-Specific Hygiene

- Mention parameter sniffing risk in Notes only when relevant (large tables, highly skewed distributions, wide date range params).
- Avoid dynamic SQL unless required. If used: always `sp_executesql` with params — never raw string concatenation.
- Inline TVFs preferred over multi-statement TVFs. Multi-statement TVFs lose cardinality estimates — note this risk.
- Avoid scalar UDFs in WHERE/JOIN on large sets — they execute per-row, prevent parallelism. Inline when possible.

---

## Generic Mode Procedure

1. Classify input: query / proc / function / script.
2. Identify existing params and candidate literals.
3. Propose `@p_` params where beneficial.
4. Declare internal vars; assign RHS only; normalize once.
5. If input is an object: apply template + signature + isolation level.
6. Apply shared SQL rules from `sql-rules.md`.
7. Verify checklist below.
8. Output in `/*Optimized SQL:*/` comment format.

---

## Generic Checklist

- [ ] Existing params respected; new `@p_` params proposed only when helpful.
- [ ] No assignment into input params.
- [ ] Internal vars declared when needed; RHS assignment; normalized once.
- [ ] Semantics preserved (JOIN type, NULL logic, predicate movement).
- [ ] For procs/functions: signature header present, `SET NOCOUNT ON`, `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED` present.
- [ ] Correct template used (inline TVF vs multi-statement TVF vs scalar vs proc).
- [ ] Shared SQL rules applied (see `sql-rules.md`).
- [ ] Output in `/*Optimized SQL:*/` comment format.

---

## Examples

### Example 1 — Raw query with literals

**Input:**
```sql
SELECT *
FROM dbo.InvoiceArticles IA
INNER JOIN dbo.Invoices I ON IA.Status=1 AND IA.InvoiceId=I.InvoiceId
LEFT JOIN dbo.StockHolders SH ON SH.InvoiceId=I.InvoiceId
WHERE I.IssueDate>='2024-01-01' AND I.CustomerId=200;
```

**Output:**
```sql
/*Optimized SQL:*/
-- parameters (proposed)
DECLARE @FromDate   DATE = '2024-01-01';
DECLARE @CustomerId INT  = 200;

SELECT I.InvoiceId, IA.ArticleId, I.IssueDate
FROM dbo.Invoices I
    INNER JOIN dbo.InvoiceArticles IA ON IA.InvoiceId = I.InvoiceId AND IA.Status = 1
    LEFT JOIN dbo.StockHolders SH ON SH.InvoiceId = I.InvoiceId
WHERE I.CustomerId = @CustomerId
    AND I.IssueDate >= @FromDate;

/* Parameter Mapping:
@FromDate (DATE)   -> literal '2024-01-01'
@CustomerId (INT)  -> literal 200

Notes:
- Proposed params for key filter literals.
- Reordered FROM: Invoices (parent, selective) first; IA.Status=1 moved to ON clause.
- WHERE reordered: equality filter (CustomerId) before range (IssueDate).
- SELECT * replaced with explicit projection; expand as needed.
*/
```

### Example 2 — Stored procedure with optional filter

**Input:**
```sql
CREATE PROCEDURE dbo.GetInvoices
    @CustomerId INT,
    @Ref NVARCHAR(100) = NULL
AS
BEGIN
    SELECT *
    FROM dbo.Invoices I
        LEFT JOIN dbo.InvoiceRefs R ON R.InvoiceId = I.InvoiceId
    WHERE I.CustomerId = @CustomerId
        AND (ISNULL(@Ref,'')='' OR R.Ref LIKE '%' + @Ref + '%');
END
```

**Output:**
```sql
/*Optimized SQL:*/
SET ANSI_NULLS ON
GO
SET QUOTED_IDENTIFIER ON
GO
-- =============================================
-- Author:      <Author,,Name>
-- Create date: <Create Date,,>
-- Description: Returns invoices for a customer with optional ref filter.
-- =============================================
CREATE PROCEDURE dbo.GetInvoices
    @CustomerId INT,
    @Ref        NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON
    SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED

    -- internal vars
    DECLARE @RefNorm NVARCHAR(100);
    SET @RefNorm = NULLIF(LTRIM(RTRIM(@Ref)), '');

    SELECT I.InvoiceId, I.CustomerId, I.IssueDate, R.Ref
    FROM dbo.Invoices I
        LEFT JOIN dbo.InvoiceRefs R ON R.InvoiceId = I.InvoiceId
    WHERE I.CustomerId = @CustomerId
        AND (@RefNorm IS NULL OR R.Ref LIKE '%' + @RefNorm + '%');
END
GO

/* Parameter Mapping:
- None (no new parameters proposed; existing params kept)

Notes:
- Added SET ANSI_NULLS/QUOTED_IDENTIFIER, signature header, NOCOUNT, and READ UNCOMMITTED.
- @Ref normalized once into @RefNorm; optional filter rewritten to canonical (@RefNorm IS NULL OR ...) pattern.
- SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED: allows dirty reads — acceptable for read-only reporting procs. If this proc is used in a transactional context, evaluate whether stricter isolation is needed.
- SELECT * replaced with explicit projection; expand column list as needed.
- LIKE '%x%' on InvoiceRefs.Ref causes full scan — consider full-text index if this table is large.
*/
```
