"""Data Agent: bulk historical load and streaming CDC data migration.

Per architecture.md §8.3 / plan.md Phase 5: generates + runs a SeaTunnel Zeta
job per discovered table (bulk load only -- see seatunnel_adapter's module
docstring for CDC scope note), whose JDBC sink auto-creates the target table
(`schema_save_mode=CREATE_SCHEMA_WHEN_NOT_EXIST`) -- this is "whatever
SeaTunnel can do". Everything SeaTunnel *can't* create (views/procedures/
functions/triggers/foreign_keys) was already translated by the Schema Agent
(agents/schema_agent) in the Generate phase; once every table exists here,
`apply_schema_translations` executes that translated DDL against the target.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.data_agent.metadata_store import metadata_connection, save_data_migration_result
from agents.schema_agent import apply_schema_translations
from dialects.connections import default_namespace
from orchestrator.state import DataMigrationResult, DiscoveryResult
from tool_adapters.seatunnel_adapter import SeaTunnelAdapter

logger = logging.getLogger(__name__)


def migrate_data(
    job_id: str,
    discovery: DiscoveryResult,
    source_dialect: str,
    target_dialect: str,
    source_connection: dict[str, Any],
    target_connection: dict[str, Any],
) -> DataMigrationResult:
    """Bulk-load every discovered table source->target, then apply the
    Schema Agent's translated non-table DDL now that tables exist."""
    adapter = SeaTunnelAdapter()
    source_namespace = default_namespace(source_dialect, source_connection)
    target_namespace = default_namespace(target_dialect, target_connection)

    tables = [entry for entry in discovery.object_catalog if entry["object_type"] == "table"]
    table_results: list[dict[str, Any]] = []
    total_rows = 0

    with metadata_connection() as conn:
        for entry in tables:
            table_name = entry["name"]
            try:
                config = adapter.prepare(
                    {
                        "job_id": job_id,
                        "table_name": table_name,
                        "source_dialect": source_dialect,
                        "target_dialect": target_dialect,
                        "source_connection": source_connection,
                        "target_connection": target_connection,
                        "source_namespace": source_namespace,
                        "target_namespace": target_namespace,
                    }
                )
                result = adapter.run(config)
            except Exception:
                # One bad table must never block the whole batch (same
                # non-fatal-step pattern as the Schema Agent's per-object loop).
                logger.exception("job=%s: seatunnel_adapter crashed migrating table %s", job_id, table_name)
                table_results.append({"table_name": table_name, "status": "ERROR"})
                save_data_migration_result(conn, job_id, table_name, None, None, "ERROR", None)
                continue

            if not result.success:
                table_results.append({"table_name": table_name, "status": "ERROR", "error": result.error})
                save_data_migration_result(conn, job_id, table_name, None, None, "ERROR", None)
                continue

            rows_read = result.output.get("rows_read")
            rows_written = result.output.get("rows_written")
            total_rows += rows_written or 0
            table_results.append(
                {
                    "table_name": table_name,
                    "status": "SUCCESS",
                    "rows_read": rows_read,
                    "rows_written": rows_written,
                }
            )
            save_data_migration_result(
                conn, job_id, table_name, rows_read, rows_written, "SUCCESS", result.execution_time_seconds
            )

    ddl_applications = apply_schema_translations(job_id, target_dialect, target_connection)

    return DataMigrationResult(rows_moved=total_rows, tables=table_results, ddl_applications=ddl_applications)

