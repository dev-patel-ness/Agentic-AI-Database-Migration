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
from typing import Any, Optional

from agents.data_agent.metadata_store import metadata_connection, save_data_migration_result
from agents.schema_agent import apply_schema_translations
from dialects import get_dialect
from dialects.connections import connect as _connect, default_namespace
from orchestrator.state import DataMigrationResult, DiscoveryResult
from tool_adapters.seatunnel_adapter import SeaTunnelAdapter

logger = logging.getLogger(__name__)


def _restore_primary_keys(
    job_id: str,
    tables: list[dict[str, Any]],
    target_dialect: str,
    target_connection: dict[str, Any],
    target_namespace: str,
) -> None:
    """SeaTunnel's JDBC sink auto-creates each target table from the source
    query's JDBC result-set metadata (`generate_sink_sql`/`schema_save_mode=
    CREATE_SCHEMA_WHEN_NOT_EXIST`) -- a plain SELECT result set carries no
    primary-key info, so those auto-created tables land with *no* primary
    key/index at all. Left as-is, every foreign key referencing one of them
    fails (MySQL: 'Missing index for constraint ... in the referenced
    table'). Re-apply each table's PK (already captured during Discover) now
    that the tables exist, before the Schema Agent applies foreign keys.
    """
    table_pks = {
        entry["name"]: [c["name"] for c in entry.get("columns", []) if c.get("is_primary_key")]
        for entry in tables
    }
    table_pks = {name: cols for name, cols in table_pks.items() if cols}
    if not table_pks:
        return

    dialect = get_dialect(target_dialect)
    conn = _connect(target_dialect, target_connection)
    try:
        cursor = conn.cursor()
        for table_name, pk_columns in table_pks.items():
            quoted_table = dialect.quote_identifier(table_name)
            quoted_cols = ", ".join(dialect.quote_identifier(c) for c in pk_columns)
            ddl = (
                f"ALTER TABLE {target_namespace}.{quoted_table} "
                f"ADD PRIMARY KEY ({quoted_cols})"
                if target_dialect == "mysql"
                else f"ALTER TABLE {quoted_table} ADD PRIMARY KEY ({quoted_cols})"
            )
            try:
                cursor.execute(ddl)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                # Already has one (replay/retry) -- not fatal, FKs will just work.
                logger.warning(
                    "job=%s: failed to restore primary key on table %s: %s", job_id, table_name, exc
                )
        cursor.close()
    finally:
        conn.close()


def _topological_sort_tables(
    tables: list[dict[str, Any]], dependency_graph: dict[str, list[str]], job_id: str
) -> list[dict[str, Any]]:
    """Order tables so FK-referenced (parent) tables load before their
    dependents, per the FK dependency graph schema_extractor_adapter built
    during discovery. Falls back to catalog order for any table caught in a
    cycle (e.g. DEPARTMENTS.manager_id -> EMPLOYEES while EMPLOYEES.dept_id ->
    DEPARTMENTS) rather than failing the batch -- SeaTunnel only loads rows,
    it doesn't enforce FK constraints, so load order here is a best-effort
    correctness improvement (avoids transient orphaned-FK data), not a hard
    requirement the way DDL application order is.
    """
    names = [t["name"] for t in tables]
    name_set = set(names)
    by_name = {t["name"]: t for t in tables}

    deps = {n: [d for d in dependency_graph.get(n, []) if d in name_set and d != n] for n in names}
    children: dict[str, list[str]] = {n: [] for n in names}
    for n in names:
        for d in deps[n]:
            children[d].append(n)
    in_degree = {n: len(deps[n]) for n in names}

    remaining = set(names)
    ready = [n for n in names if in_degree[n] == 0]
    ordered: list[str] = []
    while ready:
        ready.sort(key=names.index)  # stable: preserve catalog order among same-degree tables
        current = ready.pop(0)
        remaining.discard(current)
        ordered.append(current)
        for child in children[current]:
            in_degree[child] -= 1
            if in_degree[child] == 0 and child in remaining:
                ready.append(child)

    if remaining:
        logger.warning(
            "job=%s: FK dependency cycle detected among tables %s, falling back to catalog "
            "order for them",
            job_id,
            sorted(remaining),
        )
        ordered.extend(n for n in names if n in remaining)

    return [by_name[n] for n in ordered]



def migrate_data(
    job_id: str,
    discovery: DiscoveryResult,
    source_dialect: str,
    target_dialect: str,
    source_connection: dict[str, Any],
    target_connection: dict[str, Any],
    manual_review_objects: Optional[list[str]] = None,
) -> DataMigrationResult:
    """Bulk-load every discovered table source->target, then apply the
    Schema Agent's translated non-table DDL now that tables exist."""
    adapter = SeaTunnelAdapter()
    source_namespace = default_namespace(source_dialect, source_connection)
    target_namespace = default_namespace(target_dialect, target_connection)

    tables = [entry for entry in discovery.object_catalog if entry["object_type"] == "table"]
    tables = _topological_sort_tables(tables, discovery.dependency_graph, job_id)
    logger.info(
        "job=%s: table load order (dependency-graph sorted): %s",
        job_id,
        [t["name"] for t in tables],
    )
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

    _restore_primary_keys(job_id, tables, target_dialect, target_connection, target_namespace)

    ddl_applications = apply_schema_translations(
        job_id, target_dialect, target_connection, manual_review_objects
    )

    return DataMigrationResult(rows_moved=total_rows, tables=table_results, ddl_applications=ddl_applications)

