# Challenges Faced & Solutions (Session 2026-10-01)

Consolidated record of bugs hit during Oracle→PostgreSQL migration testing and how each was fixed. Supersedes the separate bugs-fixed / ddl-fixes / kb-embeddings docs.

## 1. FK DDL fails: "relation does not exist"
**Cause:** CrackSQL preserves Oracle's uppercase quoted identifiers (`"DEPARTMENTS"`), but SeaTunnel creates lowercase unquoted Postgres tables (`departments`), so Postgres can't resolve the FK target.
**Fix:** `_sanitize_target_ddl()` in `agents/schema_agent/__init__.py` folds quoted identifiers to lowercase for PostgreSQL targets.

## 2. Connection defaults to `public` schema instead of migrated schema
**Cause:** `psycopg2.connect()` in `dialects/connections.py` never set `search_path`, so unqualified DDL resolved against `public` instead of the target schema.
**Fix:** After connecting, `SET search_path TO "<schema>", public` when a `schema_name` is provided.

## 3. CrackSQL hybrid translation raises `'NoneType' object has no attribute 'name'`
**Cause:** CrackSQL's SQLite config (`tool_adapters/cracksql_adapter/instance/info.db`) had `knowledge_bases.embedding_model_name` pointing at a disabled model (`text-embedding-ada-002`) instead of the active Bedrock model.
**Fix:** Updated `knowledge_bases` rows to `amazon.titan-embed-text-v2:0` for all three KBs (oracle/mysql/postgresql_knowledge).

## 4. Oracle `EDITIONABLE` keyword breaks the ANTLR parser
**Cause:** Oracle's cosmetic packaging keywords (`EDITIONABLE`, `NONEDITIONABLE`, `FORCE`) aren't handled by CrackSQL's Oracle grammar, causing translation to fail with confidence 0.
**Fix:** `_strip_oracle_noise()` strips these keywords from the **source** DDL before it's handed to CrackSQL (previously only stripped from output).

## 5. View DDL keeps source schema name (`SAMPLE_USER` not mapped to `sample`)
**Cause:** `_sanitize_target_ddl()` case-folded identifiers *before* attempting the schema-name regex match, so the uppercase pattern never matched.
**Fix:** Reordered: map source schema → target schema (case-insensitive) **first**, then fold remaining identifiers to lowercase.

## 6. View/procedure DDL has literal `\n`/`\t` instead of real newlines
**Cause:** CrackSQL's translator output contains JSON escape sequences that were never unescaped before executing against Postgres, causing syntax errors.
**Fix:** `cleaned = ddl.encode('utf-8').decode('unicode_escape')` at the top of `_sanitize_target_ddl()`.

## 7. FK constraint apply fails with "already exists" on replay
**Cause:** Re-running a job against a target that already has the FK applied treated `DuplicateObject` as a hard failure.
**Fix:** In `apply_schema_translations()`, `"already exists"` errors for `foreign_key` objects are now treated as idempotent success (marked `APPLIED`).

## 8. Target row counts multiply on every re-run (3x, 4x, ...)
**Cause:** SeaTunnel's JDBC sink used `data_save_mode = "APPEND_DATA"`, so re-running a job against a non-empty target duplicated rows instead of replacing them.
**Fix:** Changed to `data_save_mode = "DROP_DATA"` in `tool_adapters/seatunnel_adapter/__init__.py` — truncates the target table before each load.

## 9. Knowledge base embeddings table was empty
**Cause:** `knowledge_base.ingestion.ingest` was never run, so `knowledge_base_entries` had 0 rows and dialect-aware retrieval returned nothing.
**Fix:** Ran `poetry run python -m knowledge_base.ingestion.ingest` (21 seed documents, Bedrock Titan v2 embeddings). Verified Oracle→PostgreSQL retrieval returns correctly ranked, dialect-filtered results.
**Known limitation (non-blocking):** CrackSQL's `get_document_description()` only retrieves from the target KB, never the source KB — source-dialect-specific patterns are not consulted during translation.

## Lessons learned
- CrackSQL runtime uses `_package_build/cracksql/`, not `backend/` — edits to `backend/` have no effect.
- Embedding model config is split across two SQLite tables (`llm_models`, `knowledge_bases`) that must stay in sync.
- Regex/order-of-operations matters: schema-name substitution must happen **before** case-folding.
- Always unescape JSON escape sequences when passing DDL between systems (CrackSQL → target DB).
- Treat "already exists" as idempotent success for constraints/replay scenarios, not a hard failure.
- Default `APPEND_DATA` sink mode silently duplicates data on re-run; `DROP_DATA` makes migrations idempotent.
