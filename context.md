## Session Summary: Phase 5 (Data Agent + SeaTunnel Adapter) — Complete, live-verified

### Goal
Implement Phase 5: the Data Agent bulk-loads every discovered table via Apache SeaTunnel (Zeta engine, JDBC->JDBC, `schema_save_mode=CREATE_SCHEMA_WHEN_NOT_EXIST` auto-creates target tables -- "whatever SeaTunnel can do"), then applies the Phase 4 Schema Agent's translated DDL (views/procedures/functions/triggers/foreign_keys) to the target DB now that tables exist -- "CrackSQL does the rest".

### Key decisions (confirmed with user up front)
1. SeaTunnel runs in a **new Docker container** (custom image FROM `apache/seatunnel:2.3.9`), not built from the cloned `seatunnel/` source repo.
2. **Bulk load only** for now -- no streaming CDC yet (future phase).
3. Phase 5 **does** apply CrackSQL's translated DDL to the target DB (previously only stored with a confidence score, never executed) -- ordered by a fixed priority (procedure/function -> view -> trigger -> foreign_key) since only table-table FK edges are tracked in the discovery dependency graph.
4. JDBC driver jars weren't available locally -- fetched from Maven Central (`infra/docker/seatunnel/fetch_jdbc_drivers.ps1`).

### Files created
- `dialects/connections.py` -- shared `connect()`/`default_namespace()`, extracted from `schema_extractor_adapter` (now reused by `agents/schema_agent`'s new DDL-apply step and `agents/data_agent`).
- `infra/docker/seatunnel/{Dockerfile,fetch_jdbc_drivers.ps1,jars/*.jar,connectors/*.jar}` -- custom SeaTunnel image (connector-jdbc jar + 3 vendor driver jars, all fetched directly from Maven Central rather than via the image's broken `install-plugin.sh`).
- `agents/data_agent/metadata_store.py` -- `save_data_migration_result` (writes into the pre-existing but previously-unused `data_migration_results` table).
- `tests/unit/test_data_agent.py`, `tests/unit/test_seatunnel_adapter.py`.

### Files modified
- `tool_adapters/seatunnel_adapter/__init__.py`: real implementation -- generates a per-table HOCON job config (`query`-mode source, `generate_sink_sql`+`schema_save_mode` sink), runs it via `docker exec seatunnel ./bin/seatunnel.sh -m local -c /jobs/<file>.conf`, parses `Total Read/Write Count` from stdout. Emits both `username` and `user` keys (see gotcha below).
- `agents/data_agent/__init__.py`: `migrate_data()` loops discovered tables, calls the adapter, aggregates rows moved, then calls `apply_schema_translations`.
- `agents/schema_agent/__init__.py`: new `apply_schema_translations(job_id, target_dialect, target_connection)` -- executes pending translated DDL against the target DB, one object at a time (failures don't block the batch).
- `agents/schema_agent/metadata_store.py`: `fetch_applicable_translations`/`mark_translation_applied`.
- `orchestrator/state.py`: `DataMigrationResult` gained `tables`/`ddl_applications` fields.
- `orchestrator/graph.py`: `_data_migrate` node now calls the real Data Agent (was a TODO stub).
- `docker-compose.yml`: new `seatunnel` service (kept alive via `tail -f /dev/null`, `extra_hosts: host.docker.internal:host-gateway`).
- `infra/docker/postgres-init.sql`: `translation_results` gained `applied_status`/`applied_error` columns (also applied live via `docker exec`).
- `tool_adapters/schema_extractor_adapter/__init__.py`: refactored to use the new shared `dialects/connections.py` helpers.

### Critical bugs found & fixed during live verification (see repo memory for full detail)
1. **`install-plugin.sh` is broken in the published `apache/seatunnel:2.3.9` Docker image** (shells out to a `mvnw` wrapper that only exists in the source tarball, not the image) -- silently installed zero connectors. Fixed by fetching `connector-jdbc-2.3.9.jar` directly from Maven Central instead.
2. **The real killer bug**: connector-jdbc 2.3.9's catalog/auto-schema code (`schema_save_mode`) reads the HOCON key **`user`**, not `username` -- despite `username` being what the (newer) docs in the sibling `seatunnel/` source tree describe. Every job failed with a confusing `IllegalArgumentException` deep in `AbstractJdbcCatalog.<init>` even though `username` was set correctly. Root-caused by extracting the actual class from the running container's jar and decompiling with `javap` (source-tree docs didn't match the actual shipped jar version). Fixed by emitting both `username` and `user` keys.
3. Networking: SeaTunnel job configs run *inside* the container, so `localhost` there ≠ the sample DB containers -- fixed by rewriting to `host.docker.internal`.

### Status at end of session: LIVE-VERIFIED
Real end-to-end test: `postgres-sample.sample.departments` (3 rows) bulk-loaded into `mysql-sample` via a real `docker exec seatunnel ./bin/seatunnel.sh` run -- target table auto-created, all 3 rows landed and confirmed via direct `SELECT`. All 70 unit tests pass. Next session: run the full Data Agent (not just the raw adapter) against a complete discovery result across all 6 directed dialect pairs, per `scripts/_phase4_e2e.py`'s pattern, and validate `apply_schema_translations` against real FK/view/trigger DDL post-data-load.

---

## Session Summary: Phase 4 (Schema Agent + CrackSQL Adapter) — Complete

### Goal
Implement Phase 4 of the Agentic AI Data Migration platform (`Agentic-AI-Data-Migration`): the Schema Agent that translates DDL between Oracle/MySQL/PostgreSQL using CrackSQL (`CrackSQL`, a separate sibling repo).

### Key architecture decisions made
1. **CrackSQL integration**: patched `backend` source directly to replace its OpenAI-only backend with **AWS Bedrock** (Nova Pro via Converse API for translation, Titan Embed v2 for its knowledge base). Packaged as an editable `cracksql` poetry dependency via a new `build_editable.py` script → installs into `_package_build` (gitignored, regenerate after any `backend/` edit).
2. **Dropped ChromaDB entirely** — `chroma-hnswlib` has zero prebuilt Windows wheels at any version (needs MSVC Build Tools). Rewrote `chroma_store.py`'s `ChromaStore` class (same name/path, so no call sites changed) to be Postgres+pgvector-backed instead, reusing the existing `postgres-metadata` docker service.
3. **Scope correction (important, from user feedback)**: Schema Agent does **NOT** translate `CREATE TABLE` DDL — table creation is delegated to the Data Agent/SeaTunnel (its JDBC sink auto-generates basic target schema via `schema_save_mode`). This was verified by reading SeaTunnel's actual Java source, not just docs: `MysqlCreateTableSqlBuilder.java`/`PostgresCreateTableSqlBuilder.java` explicitly skip `FOREIGN_KEY` generation, and Oracle's builder doesn't handle constraints at all — so **foreign keys still need CrackSQL translation**, even though tables don't.
4. Extended Phase 2's `schema_extractor_adapter` to capture DDL for views/procedures/functions/triggers (previously tables only) **and** a new `foreign_key` object type (synthesized `ALTER TABLE ADD CONSTRAINT` DDL from FK metadata).

### Files created
- `build_editable.py` — builds the editable package (copy → neuter Flask routes → rewrite imports → generate pruned setup.py, skips heavy ML deps).
- `agents/schema_agent/__init__.py`, `agents/schema_agent/metadata_store.py`
- `tool_adapters/cracksql_adapter/__init__.py` (was empty stub)
- `scripts/init_cracksql_kb.py` — one-time KB ingestion (never call `initkb()` from request-serving code, it does `sys.exit(1)` on failure)
- `scripts/_phase4_e2e.py` — manual 6-pair validation script
- `tests/unit/test_schema_agent.py`, `tests/unit/test_cracksql_adapter.py`
- `infra/docker/{postgres,mysql,oracle}-sample-extra-objects.sql` — sample view/function/trigger for testing (sample DBs previously had tables only)

### Files modified
- `dialects/base.py` + all 3 dialect plugins: added `get_view_definition`/`get_procedure_definition`/`get_function_definition`/`get_trigger_definition`
- `tool_adapters/schema_extractor_adapter/__init__.py`: fetch DDL for all 5 object types + new foreign_key catalog entries
- `orchestrator/graph.py`: real `_generate` node calling `translate_schema`; `orchestrator/connection_registry.py` no longer discards creds after Discover (now lives until job terminal state — Phase 4+ needs target connection too)
- `agents/planner_agent/risk.py`: added `foreign_key` risk default
- `pyproject.toml`: sqlglot bumped `^22.5`→`^26.6`, added `cracksql` path dependency
- `infra/docker/{postgres,mysql,oracle}-sample-init.sql`: added view/function/trigger objects for reproducibility
- CrackSQL source patches: `llm_model/implementations.py` (BedrockLLM), `llm_model/embeddings.py` (BedrockEmbeddings), `llm_model/llm_manager.py` (dispatch), `llm_model/base.py`/`chat.py` (langchain_core.messages fix), `vector_store/chroma_store.py` (Postgres rewrite), `app_factory.py` (Windows sqlite URI fix), `config/config.yaml` (disable scheduler), `config/init_config.yaml` (new, Bedrock model config), `modify_imports.py` (allowlist boto3/pgvector)

### Verified live (real Bedrock, real Postgres/MySQL/Oracle containers)
All 6 directed dialect pairs: tables → `SKIPPED_TABLE` (no cost), views/functions/triggers/foreign_keys → real CrackSQL+Bedrock translation with confidence scores. ~30/44 objects succeeded at avg confidence 0.96; failures are genuine CrackSQL/ANTLR grammar gaps (e.g. Oracle's `EDITIONABLE TRIGGER` keyword unsupported), not adapter bugs. 59/59 unit tests passing.

### Known gaps / things to watch next session
- Composite (multi-column) foreign keys aren't handled correctly (would emit duplicate partial constraint entries) — no sample data exercises this yet.
- CrackSQL's own `parse_llm_answer` uses `eval()` on LLM output text (OWASP A03 risk) — not patched, but our adapter never uses that eval'd value.
- Full details (gotchas, exact commands, env var names) are in repo memory at `/memories/repo/build-and-env.md` under "Phase 4" — read that first in a new session.
- Next up per `plan.md`: **Phase 5 (Data Migration / SeaTunnel adapter)** — the Data Agent that actually creates tables + migrates data, which Phase 4 now explicitly depends on for table DDL.