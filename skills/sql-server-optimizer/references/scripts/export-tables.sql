
/*Optimized SQL:*/
-- Exports a database “definition file” containing:
--  - Tables, columns, computed/identity, and full data types
--  - Constraints (PK, UQ, FK, CHECK, DEFAULT)
--  - Triggers (DML + DDL)
-- Output: one NVARCHAR(MAX) text file written by sqlcmd (recommended).
-- If you cannot use sqlcmd, see the “PRINT/SELECT” note at the bottom.

SET NOCOUNT ON;

DECLARE @p_Database   SYSNAME        = DB_NAME();                   -- or set to a specific DB name

/* build definition text */
DECLARE @Def NVARCHAR(MAX) = N'';
DECLARE @CRLF NCHAR(2) = NCHAR(13) + NCHAR(10);

-- header
SET @Def += N'-- Database definition export' + @CRLF
         +  N'-- Database: ' + QUOTENAME(@p_Database) + @CRLF
         +  N'-- Generated: ' + CONVERT(NVARCHAR(30), SYSDATETIMEOFFSET(), 126) + @CRLF
         +  N'-- ------------------------------------------------------------' + @CRLF + @CRLF;

--------------------------------------------------------------------------------
-- TABLES + COLUMNS
--------------------------------------------------------------------------------
;WITH T AS
(
    SELECT
        s.name  AS SchemaName,
        t.name  AS TableName,
        t.object_id
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.is_ms_shipped = 0
)
, C AS
(
    SELECT
        s.name AS SchemaName,
        t.name AS TableName,
        c.column_id,
        c.name AS ColumnName,

        -- full type (handles (n)varchar/(n)char/varbinary, decimal/numeric, datetime2/time/datetimeoffset, xml, udt/alias)
        CASE
            WHEN ty.is_user_defined = 1 THEN QUOTENAME(SCHEMA_NAME(ty.schema_id)) + N'.' + QUOTENAME(ty.name)
            WHEN ty.name IN (N'varchar', N'char', N'varbinary', N'binary') THEN
                ty.name + N'(' + CASE WHEN c.max_length = -1 THEN N'MAX' ELSE CONVERT(NVARCHAR(10), c.max_length) END + N')'
            WHEN ty.name IN (N'nvarchar', N'nchar') THEN
                ty.name + N'(' + CASE WHEN c.max_length = -1 THEN N'MAX' ELSE CONVERT(NVARCHAR(10), c.max_length / 2) END + N')'
            WHEN ty.name IN (N'decimal', N'numeric') THEN
                ty.name + N'(' + CONVERT(NVARCHAR(10), c.precision) + N',' + CONVERT(NVARCHAR(10), c.scale) + N')'
            WHEN ty.name IN (N'datetime2', N'time', N'datetimeoffset') THEN
                ty.name + N'(' + CONVERT(NVARCHAR(10), c.scale) + N')'
            ELSE
                ty.name
        END
        + CASE
            WHEN ty.name COLLATE Latin1_General_100_CI_AS IN (N'varchar', N'char', N'nvarchar', N'nchar', N'text', N'ntext')
                 AND c.collation_name IS NOT NULL
            THEN N' COLLATE ' + c.collation_name
            ELSE N''
          END
        AS DataType,

        c.is_nullable,
        c.is_identity,
        ic.seed_value,
        ic.increment_value,
        cc.is_computed,
        cc.definition AS ComputedDefinition,

        dc.definition AS DefaultDefinition
    FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    JOIN sys.columns c ON c.object_id = t.object_id
    JOIN sys.types ty ON ty.user_type_id = c.user_type_id
    LEFT JOIN sys.identity_columns ic ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    LEFT JOIN sys.computed_columns cc ON cc.object_id = c.object_id AND cc.column_id = c.column_id
    LEFT JOIN sys.default_constraints dc ON dc.parent_object_id = c.object_id AND dc.parent_column_id = c.column_id
    WHERE t.is_ms_shipped = 0
)
SELECT @Def +=
    N'-- ============================================================' + @CRLF +
    N'-- TABLE: ' + QUOTENAME(T.SchemaName) + N'.' + QUOTENAME(T.TableName) + @CRLF +
    N'-- ============================================================' + @CRLF +
    N'CREATE TABLE ' + QUOTENAME(T.SchemaName) + N'.' + QUOTENAME(T.TableName) + N' (' + @CRLF +
    STUFF((
        SELECT
            @CRLF + N'    , ' +
            QUOTENAME(C.ColumnName) + N' ' +
            CASE
                WHEN C.is_computed = 1 THEN N'AS ' + C.ComputedDefinition
                ELSE
                    C.DataType +
                    CASE
                        WHEN C.is_identity = 1 THEN
                            N' IDENTITY(' + CONVERT(NVARCHAR(40), C.seed_value) + N',' + CONVERT(NVARCHAR(40), C.increment_value) + N')'
                        ELSE N''
                    END +
                    CASE
                        WHEN C.is_nullable = 1 THEN N' NULL' ELSE N' NOT NULL' END +
                    CASE
                        WHEN C.DefaultDefinition IS NOT NULL THEN N' DEFAULT ' + C.DefaultDefinition ELSE N'' END
            END
        FROM C
        WHERE C.SchemaName = T.SchemaName AND C.TableName = T.TableName
        ORDER BY C.column_id
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, (LEN(@CRLF) + 6), N'    ') + @CRLF +
    N');' + @CRLF + @CRLF
FROM T
ORDER BY T.SchemaName, T.TableName;

--------------------------------------------------------------------------------
-- CONSTRAINTS: PK / UQ / CHECK
--------------------------------------------------------------------------------
;WITH K AS
(
    SELECT
        s.name AS SchemaName,
        t.name AS TableName,
        kc.name AS ConstraintName,
        kc.type AS ConstraintType,
        i.index_id,
		i.type AS is_clustered,          -- 1 = CLUSTERED, 2 = NONCLUSTERED
        i.is_unique
    FROM sys.key_constraints kc
    JOIN sys.tables t ON t.object_id = kc.parent_object_id
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    JOIN sys.indexes i ON i.object_id = kc.parent_object_id AND i.index_id = kc.unique_index_id
    WHERE t.is_ms_shipped = 0
)
SELECT @Def +=
    N'-- Keys: ' + QUOTENAME(K.SchemaName) + N'.' + QUOTENAME(K.TableName) + @CRLF +
    N'ALTER TABLE ' + QUOTENAME(K.SchemaName) + N'.' + QUOTENAME(K.TableName) + N' ADD CONSTRAINT ' + QUOTENAME(K.ConstraintName) + N' ' +
    CASE WHEN K.ConstraintType = 'PK' THEN N'PRIMARY KEY ' ELSE N'UNIQUE ' END +
    CASE WHEN K.is_clustered = 1 THEN N'CLUSTERED ' ELSE N'NONCLUSTERED ' END +
    N'(' +
    STUFF((
        SELECT N', ' + QUOTENAME(c.name) +
               CASE WHEN ic.is_descending_key = 1 THEN N' DESC' ELSE N' ASC' END
        FROM sys.index_columns ic
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE ic.object_id = OBJECT_ID(QUOTENAME(K.SchemaName) + N'.' + QUOTENAME(K.TableName))
          AND ic.index_id = K.index_id
          AND ic.key_ordinal > 0
        ORDER BY ic.key_ordinal
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 2, N'') +
    N');' + @CRLF + @CRLF
FROM K
ORDER BY K.SchemaName, K.TableName, K.ConstraintName;

;WITH CK AS
(
    SELECT
        s.name AS SchemaName,
        t.name AS TableName,
        cc.name AS ConstraintName,
        cc.definition,
        cc.is_disabled,
        cc.is_not_trusted
    FROM sys.check_constraints cc
    JOIN sys.tables t ON t.object_id = cc.parent_object_id
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE t.is_ms_shipped = 0
)
SELECT @Def +=
    N'-- Check constraints: ' + QUOTENAME(CK.SchemaName) + N'.' + QUOTENAME(CK.TableName) + @CRLF +
    N'ALTER TABLE ' + QUOTENAME(CK.SchemaName) + N'.' + QUOTENAME(CK.TableName) + N' WITH ' +
    CASE WHEN CK.is_not_trusted = 1 THEN N'NOCHECK' ELSE N'CHECK' END +
    N' ADD CONSTRAINT ' + QUOTENAME(CK.ConstraintName) + N' CHECK ' + CK.definition + N';' + @CRLF +
    CASE WHEN CK.is_disabled = 1 THEN
        N'ALTER TABLE ' + QUOTENAME(CK.SchemaName) + N'.' + QUOTENAME(CK.TableName) + N' NOCHECK CONSTRAINT ' + QUOTENAME(CK.ConstraintName) + N';' + @CRLF
    ELSE N'' END + @CRLF
FROM CK
ORDER BY CK.SchemaName, CK.TableName, CK.ConstraintName;

--------------------------------------------------------------------------------
-- FOREIGN KEYS
--------------------------------------------------------------------------------
;WITH FK AS
(
    SELECT
        fs.name AS FkSchemaName,
        ft.name AS FkTableName,
        fk.name AS FkName,
        rs.name AS RefSchemaName,
        rt.name AS RefTableName,
        fk.delete_referential_action_desc AS OnDelete,
        fk.update_referential_action_desc AS OnUpdate,
        fk.is_disabled,
        fk.is_not_trusted,
        fk.object_id
    FROM sys.foreign_keys fk
    JOIN sys.tables ft ON ft.object_id = fk.parent_object_id
    JOIN sys.schemas fs ON fs.schema_id = ft.schema_id
    JOIN sys.tables rt ON rt.object_id = fk.referenced_object_id
    JOIN sys.schemas rs ON rs.schema_id = rt.schema_id
    WHERE ft.is_ms_shipped = 0
)
SELECT @Def +=
    N'-- Foreign keys: ' + QUOTENAME(FK.FkSchemaName) + N'.' + QUOTENAME(FK.FkTableName) + @CRLF +
    N'ALTER TABLE ' + QUOTENAME(FK.FkSchemaName) + N'.' + QUOTENAME(FK.FkTableName) + N' WITH ' +
    CASE WHEN FK.is_not_trusted = 1 THEN N'NOCHECK' ELSE N'CHECK' END +
    N' ADD CONSTRAINT ' + QUOTENAME(FK.FkName) + N' FOREIGN KEY (' +
    STUFF((
        SELECT N', ' + QUOTENAME(pc.name)
        FROM sys.foreign_key_columns fkc
        JOIN sys.columns pc ON pc.object_id = fkc.parent_object_id AND pc.column_id = fkc.parent_column_id
        WHERE fkc.constraint_object_id = FK.object_id
        ORDER BY fkc.constraint_column_id
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 2, N'') +
    N') REFERENCES ' + QUOTENAME(FK.RefSchemaName) + N'.' + QUOTENAME(FK.RefTableName) + N' (' +
    STUFF((
        SELECT N', ' + QUOTENAME(rc.name)
        FROM sys.foreign_key_columns fkc
        JOIN sys.columns rc ON rc.object_id = fkc.referenced_object_id AND rc.column_id = fkc.referenced_column_id
        WHERE fkc.constraint_object_id = FK.object_id
        ORDER BY fkc.constraint_column_id
        FOR XML PATH(N''), TYPE
    ).value(N'.', N'nvarchar(max)'), 1, 2, N'') +
    N')' +
    CASE WHEN FK.OnDelete <> N'NO_ACTION' THEN N' ON DELETE ' + REPLACE(FK.OnDelete, N'_', N' ') ELSE N'' END +
    CASE WHEN FK.OnUpdate <> N'NO_ACTION' THEN N' ON UPDATE ' + REPLACE(FK.OnUpdate, N'_', N' ') ELSE N'' END +
    N';' + @CRLF +
    CASE WHEN FK.is_disabled = 1 THEN
        N'ALTER TABLE ' + QUOTENAME(FK.FkSchemaName) + N'.' + QUOTENAME(FK.FkTableName) + N' NOCHECK CONSTRAINT ' + QUOTENAME(FK.FkName) + N';' + @CRLF
    ELSE N'' END + @CRLF
FROM FK
ORDER BY FK.FkSchemaName, FK.FkTableName, FK.FkName;

--------------------------------------------------------------------------------
-- TRIGGERS (DML)
--------------------------------------------------------------------------------
;WITH TR AS
(
    SELECT
        ss.name AS SchemaName,
        t.name  AS TableName,
        tr.name AS TriggerName,
        tr.is_disabled,
        m.definition
    FROM sys.triggers tr
    JOIN sys.tables t ON t.object_id = tr.parent_id
    JOIN sys.schemas ss ON ss.schema_id = t.schema_id
    JOIN sys.sql_modules m ON m.object_id = tr.object_id
    WHERE t.is_ms_shipped = 0
      AND tr.parent_class = 1
)
SELECT @Def +=
    N'-- Trigger: ' + QUOTENAME(TR.SchemaName) + N'.' + QUOTENAME(TR.TableName) + N' -> ' + QUOTENAME(TR.TriggerName) + @CRLF +
    TR.definition + @CRLF +
    CASE WHEN TR.is_disabled = 1 THEN
        N'DISABLE TRIGGER ' + QUOTENAME(TR.TriggerName) + N' ON ' + QUOTENAME(TR.SchemaName) + N'.' + QUOTENAME(TR.TableName) + N';' + @CRLF
    ELSE N'' END + @CRLF
FROM TR
ORDER BY TR.SchemaName, TR.TableName, TR.TriggerName;

--------------------------------------------------------------------------------
-- DDL TRIGGERS (database-level) + SERVER TRIGGERS (if permitted)
--------------------------------------------------------------------------------
;WITH DDLT AS
(
    SELECT
        tr.name AS TriggerName,
        tr.is_disabled,
        m.definition
    FROM sys.triggers tr
    JOIN sys.sql_modules m ON m.object_id = tr.object_id
    WHERE tr.parent_class = 0  -- database DDL triggers
)
SELECT @Def +=
    N'-- Database DDL Trigger: ' + QUOTENAME(DDLT.TriggerName) + @CRLF +
    DDLT.definition + @CRLF +
    CASE WHEN DDLT.is_disabled = 1 THEN
        N'DISABLE TRIGGER ' + QUOTENAME(DDLT.TriggerName) + N' ON DATABASE;' + @CRLF
    ELSE N'' END + @CRLF
FROM DDLT
ORDER BY DDLT.TriggerName;

-- Server triggers require VIEW SERVER STATE / CONTROL SERVER; attempt if available
IF HAS_PERMS_BY_NAME(NULL, NULL, 'CONTROL SERVER') = 1
BEGIN
    ;WITH ST AS
    (
        SELECT
            tr.name AS TriggerName,
            tr.is_disabled,
            m.definition
        FROM sys.server_triggers tr
        JOIN sys.server_sql_modules m ON m.object_id = tr.object_id
    )
    SELECT @Def +=
        N'-- Server Trigger: ' + QUOTENAME(ST.TriggerName) + @CRLF +
        ST.definition + @CRLF +
        CASE WHEN ST.is_disabled = 1 THEN
            N'DISABLE TRIGGER ' + QUOTENAME(ST.TriggerName) + N' ON ALL SERVER;' + @CRLF
        ELSE N'' END + @CRLF
    FROM ST
    ORDER BY ST.TriggerName;
END
ELSE
BEGIN
    SET @Def += N'-- NOTE: Skipped server-level triggers (no CONTROL SERVER permission).' + @CRLF + @CRLF;
END;

--------------------------------------------------------------------------------
-- WRITE FILE (sqlcmd)
--------------------------------------------------------------------------------
-- This prints/returns the text; use sqlcmd to spool it to a file.
-- Recommended command:
-- sqlcmd -S <server> -d <db> -E -h -1 -W -w 65535 -Q "SET NOCOUNT ON; <paste this script>" -o "C:\temp\DbDefinition.sql"

-- If running inside SSMS and you just want the text:
SELECT @Def AS DefinitionFileText;


/*Optimized SQL:*/
-- Prints an NVARCHAR(MAX) variable in SSMS-friendly chunks (avoids PRINT truncation).
-- Usage:
--   1) Build @Def in your main script.
--   2) Run this block (or wrap it in a helper proc) to output @Def in chunks.
-- Notes:
--   - PRINT is limited (~4,000 NVARCHAR chars / ~8,000 VARCHAR chars).
--   - RAISERROR ... WITH NOWAIT shows output immediately in the Messages tab.
--   - Also bumps SSMS output limits: Tools > Options > Query Results > (Text) "Maximum number of characters displayed..."

/*Optimized SQL:*/
-- Pattern A (recommended): RAISERROR with a variable
SET NOCOUNT ON;

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
@p_ChunkSize (INT) -> chunk size for printing @Def (default 3800)
Notes:
- RAISERROR substitution parameters must be variables/constants; SUBSTRING(@Def,...) inline can throw a syntax error.
- Using severity 0 + WITH NOWAIT prints progressively to the Messages tab without PRINT’s 4k truncation.
*/
