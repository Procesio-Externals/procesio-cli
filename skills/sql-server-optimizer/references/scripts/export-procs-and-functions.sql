/*Optimized SQL:*/
-- Exports all user stored procedures and user-defined functions (inline/table/scalar)
-- into a single NVARCHAR(MAX) definition blob, then prints it in SSMS-safe chunks.
-- Notes:
--  - Encrypted modules cannot be scripted (definition will be NULL).
--  - Includes CREATE/ALTER text exactly as stored in sys.sql_modules.definition.

SET NOCOUNT ON;

DECLARE @Def NVARCHAR(MAX) = N'';
DECLARE @CRLF NCHAR(2) = NCHAR(13) + NCHAR(10);

-------------------------------------------------------------------------------
-- Header
-------------------------------------------------------------------------------
SET @Def += N'-- Database programmable objects export' + @CRLF
         +  N'-- Database: ' + QUOTENAME(DB_NAME()) + @CRLF
         +  N'-- Generated: ' + CONVERT(NVARCHAR(30), SYSDATETIMEOFFSET(), 126) + @CRLF
         +  N'-- Includes: Stored Procedures + User-Defined Functions' + @CRLF
         +  N'-- ------------------------------------------------------------' + @CRLF + @CRLF;

-------------------------------------------------------------------------------
-- Stored Procedures
-------------------------------------------------------------------------------
;WITH P AS
(
    SELECT
        s.name  AS SchemaName,
        p.name  AS ObjectName,
        p.object_id,
        m.definition
    FROM sys.procedures p
    JOIN sys.schemas s      ON s.schema_id = p.schema_id
    LEFT JOIN sys.sql_modules m ON m.object_id = p.object_id
    WHERE p.is_ms_shipped = 0
)
SELECT @Def +=
       N'-- ============================================================' + @CRLF
     + N'-- STORED PROCEDURE: ' + QUOTENAME(P.SchemaName) + N'.' + QUOTENAME(P.ObjectName) + @CRLF
     + N'-- ============================================================' + @CRLF
     + CASE
           WHEN P.definition IS NULL
                THEN N'-- NOTE: Definition not available (encrypted or no permissions).' + @CRLF
                ELSE P.definition
       END
     + @CRLF + @CRLF
FROM P
ORDER BY P.SchemaName, P.ObjectName;

-------------------------------------------------------------------------------
-- Functions (scalar, inline TVF, multi-statement TVF)
-------------------------------------------------------------------------------
;WITH F AS
(
    SELECT
        s.name  AS SchemaName,
        o.name  AS ObjectName,
        o.object_id,
        o.type,
        o.type_desc,
        m.definition
    FROM sys.objects o
    JOIN sys.schemas s         ON s.schema_id = o.schema_id
    LEFT JOIN sys.sql_modules m   ON m.object_id = o.object_id
    WHERE o.is_ms_shipped = 0
      AND o.type IN (N'FN', N'IF', N'TF') -- scalar, inline table-valued, multi-statement TVF
)
SELECT @Def +=
       N'-- ============================================================' + @CRLF
     + N'-- FUNCTION (' + F.type_desc + N'): ' + QUOTENAME(F.SchemaName) + N'.' + QUOTENAME(F.ObjectName) + @CRLF
     + N'-- ============================================================' + @CRLF
     + CASE
           WHEN F.definition IS NULL
                THEN N'-- NOTE: Definition not available (encrypted or no permissions).' + @CRLF
                ELSE F.definition
       END
     + @CRLF + @CRLF
FROM F
ORDER BY F.SchemaName, F.ObjectName;

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
- Uses sys.procedures + sys.objects (FN/IF/TF) with sys.sql_modules.definition to script module text.
- Encrypted modules (or insufficient permissions) return NULL definition; script inserts a NOTE line instead.
- Output is printed in 3,800-char chunks to avoid SSMS PRINT truncation.
*/