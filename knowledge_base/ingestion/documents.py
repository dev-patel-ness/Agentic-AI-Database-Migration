"""Seed knowledge-base documents for the Oracle/MySQL/PostgreSQL any-to-any
migration matrix (architecture.md §5 Planner/Schema Agents, §10 Data Stores).

Each entry becomes one row in `knowledge_base_entries` once embedded and
ingested (see `knowledge_base/ingestion/ingest.py`). ``source_dialect``/
``target_dialect`` are ``None`` for pair-agnostic documents, which are
retrieved regardless of the job's dialect pair (see
`knowledge_base/retrievers/similarity.py`).

This is a seed/starting set, not an exhaustive migration reference -- it is
meant to ground the Planner Agent's LLM risk-refinement step and the Phase 4
Schema Agent's translation prompts with real, citable rules rather than
letting the LLM invent them.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class KnowledgeDocument(TypedDict):
    title: str
    category: str
    source_dialect: Optional[str]
    target_dialect: Optional[str]
    content: str


SEED_DOCUMENTS: list[KnowledgeDocument] = [
    # --- Oracle -> PostgreSQL -------------------------------------------------
    {
        "title": "Oracle to PostgreSQL: type mapping",
        "category": "type_mapping",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "content": (
            "Oracle NUMBER without precision/scale maps to PostgreSQL NUMERIC "
            "(unbounded); NUMBER(p,0) maps to NUMERIC(p) or INTEGER/BIGINT if p<=18. "
            "VARCHAR2/NVARCHAR2 map to VARCHAR. CLOB maps to TEXT. BLOB maps to BYTEA. "
            "DATE (which in Oracle always includes a time component) maps to TIMESTAMP, "
            "not DATE, to avoid silently truncating stored time values. RAW/LONG RAW map "
            "to BYTEA. ROWID/UROWID have no PostgreSQL equivalent -- any application code "
            "or DDL referencing them needs a surrogate key (e.g. a UUID or serial column) "
            "instead."
        ),
    },
    {
        "title": "Oracle to PostgreSQL: PL/SQL to PL/pgSQL syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "content": (
            "PL/SQL packages have no direct PostgreSQL equivalent -- package "
            "procedures/functions typically get flattened into individually named "
            "functions in a dedicated schema (used to emulate package namespacing). "
            "Oracle's %TYPE/%ROWTYPE anchored types are supported in PL/pgSQL with the "
            "same syntax, but package-level %TYPE references need the flattened function "
            "signature. Oracle's autonomous transactions (PRAGMA "
            "AUTONOMOUS_TRANSACTION) require rewriting as a separate call via "
            "dblink/postgres_fdw or restructured application logic -- PL/pgSQL has no "
            "autonomous transaction pragma. CONNECT BY hierarchical queries must be "
            "rewritten as PostgreSQL recursive CTEs (WITH RECURSIVE). Oracle's implicit "
            "cursor FOR loops translate directly to PL/pgSQL FOR loops over a query."
        ),
    },
    {
        "title": "Oracle to PostgreSQL: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "content": (
            "Oracle treats an empty string ('') as NULL for VARCHAR2 columns; PostgreSQL "
            "does not -- migrated data with empty-string values needs explicit "
            "reconciliation logic or the empty strings will silently differ from source "
            "semantics after checksum comparison. Oracle sequences and PostgreSQL "
            "sequences behave similarly, but IDENTITY columns (GENERATED ALWAYS AS "
            "IDENTITY) require re-seeding the sequence's current value after bulk load, "
            "or new inserts will collide with migrated primary keys. Oracle's ROWNUM "
            "pseudo-column does not exist in PostgreSQL; queries relying on it for "
            "pagination must be rewritten with LIMIT/OFFSET or window functions, and any "
            "translated view/procedure using ROWNUM should be flagged for manual review."
        ),
    },
    # --- PostgreSQL -> Oracle -------------------------------------------------
    {
        "title": "PostgreSQL to Oracle: type mapping",
        "category": "type_mapping",
        "source_dialect": "postgresql",
        "target_dialect": "oracle",
        "content": (
            "PostgreSQL TEXT/VARCHAR map to Oracle VARCHAR2 (max 4000 bytes for VARCHAR2 "
            "unless MAX_STRING_SIZE=EXTENDED is set on the Oracle target, otherwise use "
            "CLOB for longer values). NUMERIC/DECIMAL map to Oracle NUMBER(p,s). BYTEA "
            "maps to BLOB. TIMESTAMP maps to Oracle DATE (loses sub-second precision) or "
            "TIMESTAMP (preserves it) depending on whether fractional seconds are used in "
            "the source data. JSON/JSONB have no native Oracle equivalent before Oracle "
            "21c JSON type -- for older Oracle targets, store as CLOB with a JSON check "
            "constraint. Arrays (e.g. INTEGER[]) have no direct Oracle equivalent and "
            "must be normalized into a child table or a nested table type."
        ),
    },
    {
        "title": "PostgreSQL to Oracle: PL/pgSQL to PL/SQL syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "postgresql",
        "target_dialect": "oracle",
        "content": (
            "PostgreSQL RETURNS TABLE / SETOF functions translate to Oracle pipelined "
            "table functions or a REF CURSOR OUT parameter -- there is no direct "
            "equivalent syntax, so this always needs a structural rewrite, not a 1:1 "
            "syntax swap. WITH RECURSIVE CTEs translate to Oracle CONNECT BY where the "
            "recursion is tree-shaped, or to the Oracle 11g+ recursive WITH clause "
            "(SELECT ... FROM tbl START WITH ... CONNECT BY, or the ANSI recursive WITH "
            "which Oracle also supports since 11gR2). PostgreSQL's DO blocks (anonymous "
            "PL/pgSQL) map to Oracle anonymous PL/SQL blocks (BEGIN...END;) with matching "
            "syntax. PostgreSQL triggers with a FOR EACH ROW/STATEMENT clause map "
            "directly onto Oracle's identical clause, but PostgreSQL's per-column trigger "
            "targeting (UPDATE OF col) needs to become an IF check inside the trigger "
            "body referencing :OLD/:NEW, since Oracle triggers don't support "
            "column-scoped UPDATE OF outside DML-level granularity the same way."
        ),
    },
    {
        "title": "PostgreSQL to Oracle: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "postgresql",
        "target_dialect": "oracle",
        "content": (
            "PostgreSQL is case-sensitive for unquoted identifiers folded to lowercase; "
            "Oracle folds unquoted identifiers to uppercase. Migrated DDL/procedure code "
            "that mixes quoted and unquoted identifiers needs a consistent case-folding "
            "pass, or object lookups will fail post-migration. PostgreSQL's NULL vs "
            "empty-string distinction is strict; Oracle collapses '' to NULL for "
            "VARCHAR2/CHAR, so string columns containing empty strings need explicit "
            "reconciliation logic during validation (an exact-equality checksum will "
            "flag a false mismatch otherwise). PostgreSQL SERIAL/IDENTITY sequences need "
            "their current value carried over to an Oracle SEQUENCE with a matching "
            "START WITH after bulk load to avoid primary-key collisions on first insert."
        ),
    },
    # --- Oracle -> MySQL -------------------------------------------------------
    {
        "title": "Oracle to MySQL: type mapping",
        "category": "type_mapping",
        "source_dialect": "oracle",
        "target_dialect": "mysql",
        "content": (
            "Oracle VARCHAR2 maps to MySQL VARCHAR (MySQL's row-size limit means very "
            "wide VARCHAR2 columns may need TEXT instead). NUMBER(p,s) with s>0 maps to "
            "DECIMAL(p,s); NUMBER with no scale and p<=18 maps to BIGINT for storage "
            "efficiency. CLOB maps to LONGTEXT. BLOB maps to LONGBLOB. Oracle DATE "
            "(always includes time) maps to MySQL DATETIME, not DATE, to preserve the "
            "time component. Oracle's NUMBER(1) used as a boolean flag convention maps "
            "to MySQL TINYINT(1) (MySQL has no native BOOLEAN; TINYINT(1) is the "
            "idiomatic equivalent)."
        ),
    },
    {
        "title": "Oracle to MySQL: PL/SQL to stored-procedure syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "oracle",
        "target_dialect": "mysql",
        "content": (
            "MySQL stored procedures/functions use a much smaller procedural-SQL surface "
            "than PL/SQL -- Oracle packages must be flattened into individually named "
            "MySQL procedures, and package-level global variables/state have no MySQL "
            "equivalent and need to be re-modeled as session variables or a helper "
            "table. Oracle's exception handling (EXCEPTION WHEN ... THEN) maps to "
            "MySQL's DECLARE ... HANDLER, which is far more limited (no named "
            "user-defined exception types) -- exception blocks with multiple named "
            "handlers usually need to collapse into SQLSTATE- or condition-based "
            "handlers. Oracle's CONNECT BY hierarchical queries have no MySQL "
            "equivalent before MySQL 8.0's recursive CTE support (WITH RECURSIVE); on "
            "MySQL 5.x targets this requires an iterative procedural rewrite."
        ),
    },
    {
        "title": "Oracle to MySQL: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "oracle",
        "target_dialect": "mysql",
        "content": (
            "MySQL has no native sequence object (pre-8.0) -- Oracle SEQUENCE usage "
            "(NEXTVAL/CURRVAL) must be replaced with AUTO_INCREMENT columns, which "
            "changes application code that explicitly selects from a sequence before "
            "insert. MySQL's default case-insensitive collation for VARCHAR comparisons "
            "differs from Oracle's default case-sensitive comparisons -- string-equality "
            "checksums during validation can pass on MySQL for values that would differ "
            "in Oracle unless a binary/case-sensitive collation is chosen for the target "
            "table. MySQL's storage engine (InnoDB) enforces foreign keys by default like "
            "Oracle, but MySQL silently truncates over-length string data by default in "
            "non-strict SQL modes -- STRICT_TRANS_TABLES must be enabled on the target or "
            "data-migration row counts can match while values differ from source."
        ),
    },
    # --- MySQL -> Oracle -------------------------------------------------------
    {
        "title": "MySQL to Oracle: type mapping",
        "category": "type_mapping",
        "source_dialect": "mysql",
        "target_dialect": "oracle",
        "content": (
            "MySQL VARCHAR maps to Oracle VARCHAR2. TEXT/LONGTEXT map to CLOB. "
            "BLOB/LONGBLOB map to BLOB. TINYINT(1) (MySQL's boolean convention) maps to "
            "Oracle NUMBER(1) with an application-level boolean convention (Oracle has no "
            "native BOOLEAN in table columns before 23c). DATETIME maps to Oracle DATE "
            "or TIMESTAMP depending on whether fractional seconds are used. ENUM columns "
            "have no Oracle equivalent and must be replaced with VARCHAR2 plus a CHECK "
            "constraint enumerating the same values, or a lookup table if the enum is "
            "reused across columns. YEAR maps to NUMBER(4). MySQL's AUTO_INCREMENT maps "
            "to an Oracle SEQUENCE plus an identity-column trigger, or Oracle's native "
            "GENERATED ALWAYS AS IDENTITY (12c+)."
        ),
    },
    {
        "title": "MySQL to Oracle: syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "mysql",
        "target_dialect": "oracle",
        "content": (
            "MySQL's DELIMITER directive is a client-side convention only (used so the "
            "client doesn't split a multi-statement procedure body on ';') and has no "
            "meaning in Oracle -- it should simply be dropped, not translated. MySQL "
            "stored procedures declared with DETERMINISTIC/NOT DETERMINISTIC map "
            "conceptually to Oracle's DETERMINISTIC function keyword, but only Oracle "
            "*functions* (not procedures) support it. MySQL trigger bodies are limited to "
            "a single statement unless wrapped in BEGIN...END, same as Oracle -- but "
            "MySQL only supports one trigger per (table, timing, event) combination pre-5.7 "
            "while Oracle allows multiple triggers per combination, so multiple MySQL "
            "workaround triggers chained via helper tables may need consolidating into one "
            "Oracle trigger."
        ),
    },
    {
        "title": "MySQL to Oracle: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "mysql",
        "target_dialect": "oracle",
        "content": (
            "MySQL's default case-insensitive VARCHAR collation means duplicate rows "
            "differing only by case may coexist in the source under a unique "
            "constraint; Oracle's default case-sensitive comparison would treat these as "
            "distinct, so migrated unique constraints won't error, but checksum-based "
            "validation should explicitly account for the collation difference rather "
            "than assume row-for-row equality implies identical comparison semantics. "
            "MySQL's '0000-00-00' zero-date value (allowed in non-strict SQL modes) has "
            "no valid Oracle DATE equivalent and must be remapped to NULL or a sentinel "
            "date during data migration, or the load will fail outright. MySQL's implicit "
            "type coercion (e.g. comparing a string to a number) is far more permissive "
            "than Oracle's -- application/stored-procedure code relying on it needs "
            "explicit CAST/TO_NUMBER after migration."
        ),
    },
    # --- PostgreSQL -> MySQL ---------------------------------------------------
    {
        "title": "PostgreSQL to MySQL: type mapping",
        "category": "type_mapping",
        "source_dialect": "postgresql",
        "target_dialect": "mysql",
        "content": (
            "PostgreSQL TEXT maps to MySQL LONGTEXT (MySQL VARCHAR has a lower practical "
            "limit tied to row size). BYTEA maps to LONGBLOB. NUMERIC/DECIMAL map "
            "directly to MySQL DECIMAL. BOOLEAN maps to TINYINT(1) (MySQL's boolean "
            "convention). JSONB maps to MySQL JSON (5.7.8+) but loses PostgreSQL's binary "
            "storage/indexing advantages -- GIN-indexed JSONB queries need to be "
            "reconsidered against MySQL's JSON functions. Arrays (e.g. INTEGER[]) have no "
            "MySQL equivalent and must be normalized into a child table. PostgreSQL's "
            "native UUID type maps to MySQL CHAR(36) or BINARY(16) (BINARY(16) is more "
            "storage-efficient but requires application-level UUID<->binary conversion)."
        ),
    },
    {
        "title": "PostgreSQL to MySQL: syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "postgresql",
        "target_dialect": "mysql",
        "content": (
            "PostgreSQL's rich window-function and CTE support is mostly matched by "
            "MySQL 8.0+, but MySQL versions before 8.0 have neither -- targeting an older "
            "MySQL means window-function-based views/queries need a full rewrite using "
            "correlated subqueries or session variables. PostgreSQL PL/pgSQL functions "
            "returning SETOF/TABLE map to MySQL stored procedures that populate an OUT "
            "parameter or use a temporary table, since MySQL functions can only return a "
            "single scalar value (only procedures can return result sets). PostgreSQL "
            "triggers can execute a function referencing OLD/NEW freely in any language; "
            "MySQL triggers are restricted to a single SQL/PSM statement body per trigger "
            "and cannot call arbitrary stored procedures with output parameters."
        ),
    },
    {
        "title": "PostgreSQL to MySQL: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "postgresql",
        "target_dialect": "mysql",
        "content": (
            "PostgreSQL enforces referential integrity and constraint checks "
            "consistently regardless of storage engine; MySQL only enforces foreign keys "
            "under InnoDB (not MyISAM) -- the target table's engine must be verified "
            "before assuming FK constraints migrated correctly. PostgreSQL's strict "
            "case-sensitive, NULL-distinct-from-empty-string semantics differ from "
            "MySQL's default case-insensitive collation -- checksum validation should "
            "compare using a matching collation/binary comparison rather than assuming "
            "default MySQL comparison semantics equal PostgreSQL's. PostgreSQL SERIAL/ "
            "IDENTITY sequence values must be carried over to MySQL's AUTO_INCREMENT "
            "counter (ALTER TABLE ... AUTO_INCREMENT = n) after bulk load, or the first "
            "post-migration insert will collide with an existing primary key."
        ),
    },
    # --- MySQL -> PostgreSQL ---------------------------------------------------
    {
        "title": "MySQL to PostgreSQL: type mapping",
        "category": "type_mapping",
        "source_dialect": "mysql",
        "target_dialect": "postgresql",
        "content": (
            "MySQL TINYINT(1) (boolean convention) maps to PostgreSQL BOOLEAN. "
            "ENUM columns have no PostgreSQL equivalent and should become either a "
            "PostgreSQL native ENUM type (if the value set is static) or a VARCHAR plus "
            "CHECK constraint (if the value set changes over time, since altering a "
            "PostgreSQL ENUM type requires ALTER TYPE ... ADD VALUE and cannot remove "
            "values). SET columns have no direct equivalent and should become a "
            "normalized child table or a PostgreSQL array with a CHECK constraint. "
            "MySQL LONGTEXT/LONGBLOB map to PostgreSQL TEXT/BYTEA. MySQL's YEAR type "
            "maps to PostgreSQL SMALLINT. MySQL's AUTO_INCREMENT maps to PostgreSQL "
            "GENERATED ALWAYS AS IDENTITY or a SERIAL column."
        ),
    },
    {
        "title": "MySQL to PostgreSQL: syntax quirks",
        "category": "syntax_quirks",
        "source_dialect": "mysql",
        "target_dialect": "postgresql",
        "content": (
            "MySQL's DELIMITER directive is client-side only and must be dropped when "
            "translating stored routines, not converted. MySQL stored procedures that "
            "return a result set via a bare SELECT map to PostgreSQL functions returning "
            "SETOF/TABLE with an explicit RETURN QUERY. MySQL's ON DUPLICATE KEY UPDATE "
            "upsert syntax maps to PostgreSQL's INSERT ... ON CONFLICT DO UPDATE -- the "
            "column-reference syntax differs (MySQL references VALUES(col), PostgreSQL "
            "references EXCLUDED.col) so a straight text substitution will not work. "
            "MySQL triggers are limited to one per (table, timing, event); PostgreSQL "
            "allows multiple triggers per combination and fires them in name order, so "
            "no consolidation is needed in this direction (unlike MySQL-to-Oracle)."
        ),
    },
    {
        "title": "MySQL to PostgreSQL: known incompatibilities and validation focus",
        "category": "incompatibilities",
        "source_dialect": "mysql",
        "target_dialect": "postgresql",
        "content": (
            "MySQL's default case-insensitive VARCHAR collation can allow "
            "case-differing 'duplicate' values under a unique constraint that "
            "PostgreSQL's default case-sensitive collation would treat as distinct -- "
            "this itself won't break the migration, but naive checksum comparisons "
            "assuming case-insensitive equality will misreport mismatches. MySQL's "
            "permissive '0000-00-00' zero-date and non-strict-mode silent truncation "
            "have no PostgreSQL equivalent (PostgreSQL rejects invalid dates and enforces "
            "column-length constraints strictly) -- either condition will make bulk load "
            "fail outright on rows that MySQL silently accepted, so pre-migration data "
            "profiling for these values is worth doing before scheduling the load."
        ),
    },
    # --- General / pair-agnostic ------------------------------------------------
    {
        "title": "Checksum-based data validation strategy",
        "category": "validation_rules",
        "source_dialect": None,
        "target_dialect": None,
        "content": (
            "Row-level validation should hash a normalized, order-independent "
            "representation of each row (e.g. a per-column string cast, concatenated, "
            "then hashed) rather than comparing raw driver-returned values directly -- "
            "different drivers/dialects format numerics, timestamps, and NULLs "
            "differently even when the underlying data is identical. Compare aggregate "
            "row counts per table first (cheap, catches gross data-loss immediately) "
            "before running the more expensive per-row hash comparison. Batch large "
            "tables by primary-key range rather than loading an entire table into memory "
            "for hashing."
        ),
    },
    {
        "title": "Referential integrity validation after migration",
        "category": "validation_rules",
        "source_dialect": None,
        "target_dialect": None,
        "content": (
            "After bulk load, verify that every foreign-key relationship discovered "
            "during the Assessment phase still holds on the target -- orphaned rows can "
            "appear if child and parent tables were loaded out of dependency order, or "
            "if CDC lag caused a parent delete to apply before its dependent child rows "
            "were migrated. Sequence/AUTO_INCREMENT/IDENTITY counters must be re-seeded "
            "to at least MAX(existing primary key) + 1 after bulk load, in every target "
            "dialect, or the first post-migration insert will collide with a migrated "
            "row."
        ),
    },
    {
        "title": "Risk-scoring guidance for procedural/executable objects",
        "category": "validation_rules",
        "source_dialect": None,
        "target_dialect": None,
        "content": (
            "Procedures, functions, and triggers carry inherently higher migration risk "
            "than tables/views across every dialect pair because their logic (control "
            "flow, exception handling, cursors) rarely has a 1:1 syntactic equivalent in "
            "the target dialect -- flag them for manual review by default even without "
            "inspecting their body text, and only downgrade the risk level when a "
            "specific translation rule for that object's category is known to be "
            "mechanical (e.g. a single-statement trigger with no vendor-specific "
            "pragmas)."
        ),
    },
]
