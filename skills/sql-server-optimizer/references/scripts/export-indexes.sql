/*Optimized SQL:*/
-- Exports all user-defined indexes on user tables into a single NVARCHAR(MAX)
-- definition blob, then prints it in SSMS-safe chunks.
-- Notes:
--  - Excludes indexes that back PRIMARY KEY or UNIQUE constraints (already in export-tables.sql).
--  - Includes: NONCLUSTERED, CLUSTERED (non-PK), COLUMNSTORE, XML, SPATIAL indexes.
--  - Includes key columns (with sort direction), included (non-key) columns, and filtered index WHERE clauses.
--  - Disabled indexes are exported with a trailing DISABLE statement.
--  - Hypothetical indexes (used internally by the optimizer) are excluded.

SET NOCOUNT ON;

DECLARE @Def NVARCHAR(MAX) = N'';
DECLARE @CRLF NCHAR(2) = NCHAR(13) + NCHAR(10);

-------------------------------------------------------------------------------
-- Header
-------------------------------------------------------------------------------
SET @Def += N'-- Database indexes export' + @CRLF
         +  N'-- Database: ' + QUOTENAME(DB_NAME()) + @CRLF
         +  N'-- Generated: ' + CONVERT(NVARCHAR(30), SYSDATETIMEOFFSET(), 126) + @CRLF
         +  N'-- Includes: All non-constraint indexes on user tables' + @CRLF
         +  N'-- Excludes: PK and UQ constraint-backed indexes (see export-tables.sql)' + @CRLF
         +  N'-- ------------------------------------------------------------' + @CRLF + @CRLF;

-------------------------------------------------------------------------------
-- Indexes
-------------------------------------------------------------------------------
;WITH IX AS
(
    SELECT
        s.name          AS SchemaName,
        t.name          AS TableName,
        i.name          AS IndexName,
        i.index_id,
        i.type_desc     AS IndexType,       -- CLUSTERED, NONCLUSTERED, XML, SPATIAL, CLUSTERED COLUMNSTORE, NONCLUSTERED COLUMNSTORE
        i.is_unique,
        i.is_disabled,
        i.is_padded,
        i.fill_factor,
        i.filter_definition,                -- non-NULL for filtered indexes
        t.object_id
    FROM sys.indexes i
    JOIN sys.tables t  ON t.object_id  = i.object_id
    JOIN sys.schemas s ON s.schema_id  = t.schema_id
    WHERE t.is_ms_shipped   = 0
      AND i.is_hypothetical = 0             -- exclude hypothetical (optimizer internal)
      AND i.index_id       > 0             -- exclude heap (index_id = 0)
      AND i.is_primary_key = 0             -- exclude PK-backed indexes (in export-tables.sql)
      AND i.is_unique_constraint = 0       -- exclude UQ-backed indexes (in export-tables.sql)
)
SELECT @Def +=
    N'-- ============================================================' + @CRLF
  + N'-- INDEX: ' + QUOTENAME(IX.SchemaName) + N'.' + QUOTENAME(IX.TableName)
                  + N' -> ' + QUOTENAME(IX.IndexName) + @CRLF
  + N'-- Type: ' + IX.IndexType
                + CASE WHEN IX.is_unique  = 1 THEN N' UNIQUE'     ELSE N'' END
                + CASE WHEN IX.is_disabled = 1 THEN N' [DISABLED]' ELSE N'' END + @CRLF
  + N'-- ============================================================' + @CRLF
  + N'CREATE '
  + CASE WHEN IX.is_unique = 1 THEN N'UNIQUE ' ELSE N'' END
  + IX.IndexType + N' INDEX '
  + QUOTENAME(IX.IndexName) + N' ON '
  + QUOTENAME(IX.SchemaName) + N'.' + QUOTENAME(IX.TableName)

  -- Key columns
  + N' (' + @CRLF
  + STUFF((
        SELECT N'    , ' + QUOTENAME(c.name)
                         + CASE WHEN ic.is_descending_key = 1 THEN N' DESC' ELSE N' ASC' END + @CRLF
        FROM sys.index_columns ic
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id  = IX.object_id
          AND ic.index_id   = IX.index_id
          AND ic.is_included_column = 0
          AND ic.key_ordinal > 0
        ORDER BY ic.key_ordinal
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 6, N'    ')
  + N')'

  -- Included (non-key) columns — omit INCLUDE clause if none exist
  + ISNULL(
        N' INCLUDE (' + @CRLF
      + STUFF((
            SELECT N'    , ' + QUOTENAME(c.name) + @CRLF
            FROM sys.index_columns ic
            JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
            WHERE ic.object_id         = IX.object_id
              AND ic.index_id          = IX.index_id
              AND ic.is_included_column = 1
            ORDER BY ic.index_column_id
            FOR XML PATH(N''), TYPE
        ).value(N'.', N'nvarchar(max)'), 1, 6, N'    ')
      + N')',
        N''
    )

  -- Filtered index WHERE clause
  + CASE WHEN IX.filter_definition IS NOT NULL
         THEN N' WHERE ' + IX.filter_definition
         ELSE N''
    END

  -- WITH options: fill factor (only emit when non-default), pad index
  + CASE
        WHEN IX.fill_factor <> 0 OR IX.is_padded = 1
        THEN N' WITH ('
           + CASE WHEN IX.fill_factor <> 0 THEN N'FILLFACTOR = ' + CONVERT(NVARCHAR(3), IX.fill_factor) ELSE N'' END
           + CASE WHEN IX.fill_factor <> 0 AND IX.is_padded = 1 THEN N', ' ELSE N'' END
           + CASE WHEN IX.is_padded  = 1 THEN N'PAD_INDEX = ON' ELSE N'' END
           + N')'
        ELSE N''
    END

  + N';' + @CRLF

  -- Emit DISABLE statement for disabled indexes
  + CASE WHEN IX.is_disabled = 1
         THEN N'ALTER INDEX ' + QUOTENAME(IX.IndexName)
            + N' ON ' + QUOTENAME(IX.SchemaName) + N'.' + QUOTENAME(IX.TableName)
            + N' DISABLE;' + @CRLF
         ELSE N''
    END

  + @CRLF

FROM IX
ORDER BY IX.SchemaName, IX.TableName, IX.IndexName;

-- If running inside SSMS and you just want the text:
SELECT @Def AS DefinitionFileText;

-------------------------------------------------------------------------------
-- PRINT IN CHUNKS (leave as-is per your preferred pattern)
-------------------------------------------------------------------------------
DECLARE @p_ChunkSize INT = 3800;
DECLARE @Offset INT = 1;
DECLARE @Len INT;
DECLARE @Chunk NVARCHAR(4000);

SELECT @Len = CASE WHEN @Def IS NULL THEN 0 ELSE LEN(@Def) END;

IF @Len = 0
BEGIN
    RAISERROR(N'@Def is NULL or empty.', 0, 1) WITH NOWAIT;
    RETURN;
END;

WHILE @Offset <= @Len
BEGIN
    SET @Chunk = SUBSTRING(@Def, @Offset, @p_ChunkSize);
    PRINT(@Chunk);
    SET @Offset += @p_ChunkSize;
END;

/* Parameter Mapping:
- None (no changes)

Notes:
- PK and UQ constraint-backed indexes are excluded — they are already scripted in export-tables.sql.
  Cross-reference the two outputs to get the complete index picture for a table.
- Included (non-key) columns are emitted only when present; omitted otherwise to keep output clean.
- Filtered index WHERE clauses are preserved verbatim from sys.indexes.filter_definition.
- fill_factor = 0 means SQL Server uses its default (usually 80%); omitted from WITH clause.
- Disabled indexes are exported as CREATE INDEX + ALTER INDEX ... DISABLE so they can be
  recreated and re-disabled identically on another instance.
- Hypothetical indexes (used internally by the Database Engine Tuning Advisor) are excluded.
- Output is printed in 3,800-char chunks to avoid SSMS PRINT truncation.
- Read output from the Messages tab in SSMS, not the Results tab.
*/
