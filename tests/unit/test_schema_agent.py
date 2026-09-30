"""Unit tests for the Schema Agent (architecture.md §5 Schema Agent, §8.2).
The CrackSQL adapter and metadata DB connection are mocked -- these tests
exercise the per-object dispatch/confidence-aggregation logic only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agents.schema_agent import LOW_CONFIDENCE_THRESHOLD, translate_schema
from orchestrator.state import DiscoveryResult
from tool_adapters.base import AdapterConfig, ToolResult


def _discovery_with(catalog: list[dict]) -> DiscoveryResult:
    return DiscoveryResult(object_catalog=catalog, dependency_graph={})


@contextmanager
def _fake_metadata_connection():
    yield MagicMock()


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
