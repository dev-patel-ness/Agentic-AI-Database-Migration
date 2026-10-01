"""Unit tests for the Schema Agent (architecture.md §5 Schema Agent, §8.2).
The CrackSQL adapter and metadata DB connection are mocked -- these tests
exercise the per-object dispatch/confidence-aggregation logic only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agents.schema_agent import LOW_CONFIDENCE_THRESHOLD, _sanitize_target_ddl, translate_schema
from orchestrator.state import DiscoveryResult
from tool_adapters.base import AdapterConfig, ToolResult


def _discovery_with(catalog: list[dict]) -> DiscoveryResult:
    return DiscoveryResult(object_catalog=catalog, dependency_graph={})


@contextmanager
def _fake_metadata_connection():
    yield MagicMock()


def test_translate_schema_strips_oracle_noise_keywords_from_source_ddl_before_adapter_call():
    # ANTLR's Oracle grammar chokes on EDITIONABLE/FORCE before translation
    # even starts -- these must be stripped from the source DDL CrackSQL
    # receives, not just the translated output.
    discovery = _discovery_with(
        [
            {
                "object_type": "view",
                "name": "v1",
                "schema": "public",
                "definition": 'CREATE OR REPLACE FORCE EDITIONABLE VIEW "V1" AS SELECT 1',
            }
        ]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(
        success=True,
        output={"translated_sql": "CREATE VIEW v1 AS SELECT 1", "method": "local_to_global"},
        confidence_score=0.95,
    )

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translate_schema("job-1", discovery, "oracle", "postgresql")

    sent_sql = fake_adapter.prepare.call_args[0][0]["source_sql"]
    assert "EDITIONABLE" not in sent_sql
    assert "FORCE" not in sent_sql


def test_sanitize_target_ddl_folds_quoted_identifiers_to_lowercase_for_postgresql():
    # CrackSQL preserves Oracle's uppercase quoted identifiers, but SeaTunnel
    # creates target Postgres tables/columns unquoted (folded lowercase) --
    # the translated FK DDL must match or "ALTER TABLE" fails at apply time.
    ddl = 'ALTER TABLE "DEPARTMENTS" ADD CONSTRAINT "FK_X" FOREIGN KEY ( "MANAGER_ID" ) REFERENCES "EMPLOYEES" ( "EMPLOYEE_ID" )'

    result = _sanitize_target_ddl(ddl, "postgresql")

    assert result == (
        'ALTER TABLE "departments" ADD CONSTRAINT "fk_x" FOREIGN KEY ( "manager_id" ) '
        'REFERENCES "employees" ( "employee_id" )'
    )


def test_sanitize_target_ddl_leaves_oracle_target_untouched():
    ddl = 'ALTER TABLE "DEPARTMENTS" ADD CONSTRAINT "FK_X" FOREIGN KEY ("MANAGER_ID") REFERENCES "EMPLOYEES" ("EMPLOYEE_ID")'

    assert _sanitize_target_ddl(ddl, "oracle") == ddl


def test_sanitize_target_ddl_maps_source_schema_to_target_schema_for_postgresql():
    # When translating from Oracle to Postgres, schema names must be mapped:
    # Oracle: SAMPLE_USER.ACTIVE_EMPLOYEES → Postgres: sample.active_employees
    # Schema mapping happens BEFORE case-folding so we can match the original case
    ddl = 'CREATE OR REPLACE VIEW "SAMPLE_USER"."ACTIVE_EMPLOYEES" ("ID") AS SELECT id FROM "SAMPLE_USER"."EMPLOYEES"'

    result = _sanitize_target_ddl(
        ddl, "postgresql", source_schema="SAMPLE_USER", target_schema="sample"
    )

    # Schema should be mapped to lowercase target schema
    assert '"sample"."active_employees"' in result
    assert '"sample"."employees"' in result
    # Original schema name should not appear
    assert "SAMPLE_USER" not in result


def test_translate_schema_success_high_confidence():
    discovery = _discovery_with(
        [{"object_type": "view", "name": "v1", "schema": "public", "definition": "CREATE VIEW v1 AS SELECT 1"}]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(
        success=True,
        output={"translated_sql": "CREATE VIEW v1 AS SELECT 1", "method": "local_to_global"},
        confidence_score=0.95,
    )

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    assert translation.average_confidence == 0.95
    assert translation.translated_objects[0]["status"] == "SUCCESS"
    assert low_confidence == []


def test_translate_schema_maps_catalog_schema_key_to_target_schema():
    """Regression test: the catalog entry's schema key is "schema" (set by
    schema_extractor_adapter), not "schema_name" -- translate_schema must read
    the right key or source_schema is always None and the mapping in
    _sanitize_target_ddl silently never fires."""
    discovery = _discovery_with(
        [
            {
                "object_type": "view",
                "name": "ACTIVE_EMPLOYEES",
                "schema": "SAMPLE_USER",
                "definition": "CREATE VIEW \"SAMPLE_USER\".\"ACTIVE_EMPLOYEES\" AS SELECT 1",
            }
        ]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(
        success=True,
        output={
            "translated_sql": 'CREATE VIEW "SAMPLE_USER"."ACTIVE_EMPLOYEES" AS SELECT 1',
            "method": "local_to_global",
        },
        confidence_score=0.95,
    )

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, _ = translate_schema(
            "job-1",
            discovery,
            "oracle",
            "postgresql",
            target_connection={"schema_name": "sample"},
        )

    translated_ddl = translation.translated_objects[0]["translated_ddl"]
    assert '"sample"."active_employees"' in translated_ddl
    assert "SAMPLE_USER" not in translated_ddl


def test_translate_schema_skips_tables_without_calling_adapter():
    discovery = _discovery_with(
        [{"object_type": "table", "name": "t1", "schema": "public", "definition": "CREATE TABLE t1 (id INT)"}]
    )
    fake_adapter = MagicMock()

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    fake_adapter.prepare.assert_not_called()
    fake_adapter.run.assert_not_called()
    assert translation.translated_objects[0]["status"] == "SKIPPED_TABLE"
    assert translation.average_confidence is None
    assert low_confidence == []


def test_translate_schema_translates_foreign_key_ddl():
    discovery = _discovery_with(
        [
            {
                "object_type": "foreign_key",
                "name": "fk_t1_t2",
                "schema": "public",
                "table_name": "t1",
                "definition": "ALTER TABLE t1 ADD CONSTRAINT fk_t1_t2 FOREIGN KEY (t2_id) REFERENCES t2 (id)",
            }
        ]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(
        success=True,
        output={
            "translated_sql": 'ALTER TABLE "t1" ADD CONSTRAINT "fk_t1_t2" FOREIGN KEY ("t2_id") REFERENCES "t2" ("id")',
            "method": "local_to_global",
        },
        confidence_score=1.0,
    )

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    fake_adapter.run.assert_called_once()
    assert translation.translated_objects[0]["status"] == "SUCCESS"
    assert low_confidence == []


def test_translate_schema_flags_low_confidence_object():
    discovery = _discovery_with(
        [{"object_type": "procedure", "name": "p1", "schema": "public", "definition": "CREATE PROCEDURE p1 AS BEGIN NULL; END;"}]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(
        success=True,
        output={"translated_sql": "-- best effort", "method": "direct_llm"},
        confidence_score=0.4,
    )

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    assert 0.4 <= LOW_CONFIDENCE_THRESHOLD
    assert low_confidence == ["p1"]
    assert translation.average_confidence == 0.4


def test_translate_schema_flags_missing_source_ddl_for_manual_review():
    discovery = _discovery_with(
        [{"object_type": "trigger", "name": "trg1", "schema": "public", "definition": None}]
    )
    with patch("agents.schema_agent.CrackSQLAdapter"), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    assert translation.translated_objects[0]["status"] == "NO_SOURCE_DDL"
    assert low_confidence == ["trg1"]
    assert translation.average_confidence is None


def test_translate_schema_handles_adapter_exception_without_raising():
    discovery = _discovery_with(
        [{"object_type": "function", "name": "f1", "schema": "public", "definition": "CREATE FUNCTION f1() ..."}]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.side_effect = RuntimeError("boom")

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    assert translation.translated_objects[0]["status"] == "ERROR"
    assert low_confidence == ["f1"]


def test_translate_schema_handles_unsuccessful_adapter_result():
    discovery = _discovery_with(
        [{"object_type": "view", "name": "v1", "schema": "public", "definition": "CREATE VIEW v1 AS SELECT 1"}]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(success=False, error="cracksql package unavailable")

    with patch("agents.schema_agent.CrackSQLAdapter", return_value=fake_adapter), patch(
        "agents.schema_agent.metadata_connection", _fake_metadata_connection
    ):
        translation, low_confidence = translate_schema("job-1", discovery, "oracle", "postgresql")

    assert translation.translated_objects[0]["status"] == "ERROR"
    assert translation.translated_objects[0]["error"] == "cracksql package unavailable"
    assert low_confidence == ["v1"]


def test_apply_schema_translations_executes_ddl_in_dependency_order():
    from agents.schema_agent import apply_schema_translations

    pending = [
        {"id": "fk-1", "object_type": "foreign_key", "object_name": "fk1", "target_ddl": "ALTER TABLE ..."},
        {"id": "view-1", "object_type": "view", "object_name": "v1", "target_ddl": "CREATE VIEW ..."},
        {"id": "proc-1", "object_type": "procedure", "object_name": "p1", "target_ddl": "CREATE PROCEDURE ..."},
    ]
    fake_target_conn = MagicMock()
    fake_target_conn.cursor.return_value = MagicMock()

    with patch("agents.schema_agent.metadata_connection", _fake_metadata_connection), patch(
        "agents.schema_agent.fetch_applicable_translations", return_value=pending
    ), patch("agents.schema_agent.mark_translation_applied") as fake_mark, patch(
        "agents.schema_agent._connect", return_value=fake_target_conn
    ):
        results = apply_schema_translations("job-1", "postgresql", {"host": "localhost"})

    applied_order = [r["object_type"] for r in results]
    assert applied_order == ["procedure", "view", "foreign_key"]
    assert all(r["status"] == "APPLIED" for r in results)
    assert fake_mark.call_count == 3


def test_apply_schema_translations_one_failure_does_not_block_others():
    from agents.schema_agent import apply_schema_translations

    pending = [
        {"id": "view-1", "object_type": "view", "object_name": "v1", "target_ddl": "CREATE VIEW ..."},
        {"id": "trg-1", "object_type": "trigger", "object_name": "t1", "target_ddl": "CREATE TRIGGER ..."},
    ]
    fake_cursor = MagicMock()
    fake_cursor.execute.side_effect = [RuntimeError("bad ddl"), None]
    fake_target_conn = MagicMock()
    fake_target_conn.cursor.return_value = fake_cursor

    with patch("agents.schema_agent.metadata_connection", _fake_metadata_connection), patch(
        "agents.schema_agent.fetch_applicable_translations", return_value=pending
    ), patch("agents.schema_agent.mark_translation_applied"), patch(
        "agents.schema_agent._connect", return_value=fake_target_conn
    ):
        results = apply_schema_translations("job-1", "postgresql", {"host": "localhost"})

    assert results[0]["status"] == "APPLY_FAILED"
    assert results[1]["status"] == "APPLIED"


def test_apply_schema_translations_noop_when_nothing_pending():
    from agents.schema_agent import apply_schema_translations

    with patch("agents.schema_agent.metadata_connection", _fake_metadata_connection), patch(
        "agents.schema_agent.fetch_applicable_translations", return_value=[]
    ), patch("agents.schema_agent._connect") as fake_connect:
        results = apply_schema_translations("job-1", "postgresql", {"host": "localhost"})

    assert results == []
    fake_connect.assert_not_called()


def test_sanitize_target_ddl_unescapes_json_escape_sequences():
    """Regression test: CrackSQL may return DDL with JSON escape sequences
    (\\n, \\t, \\", \\\\, etc.). These must be unescaped so PostgreSQL can
    parse actual newlines instead of literal 'backslash n' sequences.
    Example: 'CREATE VIEW ... AS \\nSELECT ...' must become 'CREATE VIEW ... AS \nSELECT ...'
    """
    # Simulate CrackSQL returning DDL with escaped newlines
    ddl_with_escaped_newlines = 'CREATE OR REPLACE VIEW "sample"."active_employees" AS \\nSELECT \\n  id, name \\nFROM employees'
    
    result = _sanitize_target_ddl(ddl_with_escaped_newlines, "postgresql")
    
    # After unescaping, should contain actual newlines, not literal \\n sequences
    assert "\\n" not in result  # No literal backslash-n
    assert "\n" in result  # Actual newlines present
    assert "CREATE OR REPLACE VIEW" in result
    assert "FROM employees" in result
    # SQL should be properly formatted with actual line breaks
    lines = result.split("\n")
    assert len(lines) > 1  # Should have multiple lines after unescaping


def test_apply_schema_translations_treats_duplicate_fk_as_idempotent():
    """Regression test: FK constraints that already exist on the target
    (from a previous run or incomplete cleanup) should be treated as
    idempotent success, not hard failure. This allows replay/retry
    scenarios to proceed without manual cleanup.
    """
    from agents.schema_agent import apply_schema_translations

    pending = [
        {
            "id": "fk-1",
            "object_type": "foreign_key",
            "object_name": "fk_departments_manager",
            "target_ddl": "ALTER TABLE departments ADD CONSTRAINT fk_departments_manager ...",
        }
    ]
    
    fake_cursor = MagicMock()
    # Simulate "constraint already exists" error
    fake_cursor.execute.side_effect = Exception('constraint "fk_departments_manager" for relation "departments" already exists')
    fake_target_conn = MagicMock()
    fake_target_conn.cursor.return_value = fake_cursor

    with patch("agents.schema_agent.metadata_connection", _fake_metadata_connection), patch(
        "agents.schema_agent.fetch_applicable_translations", return_value=pending
    ), patch("agents.schema_agent.mark_translation_applied") as fake_mark, patch(
        "agents.schema_agent._connect", return_value=fake_target_conn
    ):
        results = apply_schema_translations("job-1", "postgresql", {"host": "localhost"})

    # Should be treated as APPLIED (idempotent), not APPLY_FAILED
    assert len(results) == 1
    assert results[0]["status"] == "APPLIED"
    assert results[0]["object_name"] == "fk_departments_manager"
    # mark_translation_applied should be called with APPLIED status
    assert fake_mark.called
    call_args = fake_mark.call_args[0]
    assert call_args[2] == "APPLIED"  # Second positional arg is status
