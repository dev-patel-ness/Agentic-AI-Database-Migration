"""Persists Data Agent output into the Platform Metadata DB
(architecture.md §10 ERD: `data_migration_results`).
"""

from __future__ import annotations

from typing import Optional

import psycopg

from agents.assessment_agent.metadata_store import metadata_connection

__all__ = ["metadata_connection", "save_data_migration_result"]


def save_data_migration_result(
    conn: psycopg.Connection,
    job_id: str,
    table_name: str,
    source_row_count: Optional[int],
    target_row_count: Optional[int],
    migration_status: str,
    duration_seconds: Optional[float],
) -> None:
    rows_migrated = target_row_count if target_row_count is not None else 0
    throughput = (
        rows_migrated / duration_seconds if duration_seconds and duration_seconds > 0 else None
    )
    conn.execute(
        """
        INSERT INTO data_migration_results
            (job_id, table_name, source_row_count, target_row_count, rows_migrated,
             migration_status, duration_seconds, throughput_rows_per_sec)
        VALUES (%(job_id)s, %(table_name)s, %(source_row_count)s, %(target_row_count)s,
                %(rows_migrated)s, %(migration_status)s, %(duration_seconds)s, %(throughput)s)
        """,
        {
            "job_id": job_id,
            "table_name": table_name,
            "source_row_count": source_row_count,
            "target_row_count": target_row_count,
            "rows_migrated": rows_migrated,
            "migration_status": migration_status,
            "duration_seconds": int(duration_seconds) if duration_seconds is not None else None,
            "throughput": throughput,
        },
    )
