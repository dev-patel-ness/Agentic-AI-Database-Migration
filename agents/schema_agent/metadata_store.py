"""Persists Schema Agent translation output into the Platform Metadata DB
(architecture.md §10 ERD: `translation_results`, linked to the matching
`object_catalog_entries` row saved by Phase 2's Assessment Agent).
"""

from __future__ import annotations

from typing import Any, Optional

import psycopg

from agents.assessment_agent.metadata_store import metadata_connection

__all__ = [
    "metadata_connection",
    "save_translation_result",
    "fetch_applicable_translations",
    "mark_translation_applied",
]


def save_translation_result(
    conn: psycopg.Connection,
    job_id: str,
    object_type: str,
    object_name: str,
    source_ddl: Optional[str],
    target_ddl: Optional[str],
    status: str,
    confidence: Optional[float],
    warnings: Optional[list[str]] = None,
) -> None:
    conn.execute(
        """
        INSERT INTO translation_results
            (job_id, source_object_id, source_ddl, target_ddl, translation_status,
             confidence_score, warnings)
        VALUES (
            %(job_id)s,
            (SELECT id FROM object_catalog_entries
             WHERE job_id = %(job_id)s AND object_type = %(object_type)s
               AND object_name = %(object_name)s
             LIMIT 1),
            %(source_ddl)s, %(target_ddl)s, %(status)s, %(confidence)s, %(warnings)s
        )
        """,
        {
            "job_id": job_id,
            "object_type": object_type,
            "object_name": object_name,
            "source_ddl": source_ddl,
            "target_ddl": target_ddl,
            "status": status,
            "confidence": confidence,
            "warnings": warnings or [],
        },
    )


def fetch_applicable_translations(conn: psycopg.Connection, job_id: str) -> list[dict[str, Any]]:
    """Successfully-translated, not-yet-applied non-table objects for this job
    (Phase 5's DDL-application step -- SKIPPED_TABLE/ERROR/NO_SOURCE_DDL rows
    and rows with no translated DDL text are never eligible)."""
    cur = conn.execute(
        """
        SELECT tr.id, oce.object_type, oce.object_name, tr.target_ddl
        FROM translation_results tr
        JOIN object_catalog_entries oce ON oce.id = tr.source_object_id
        WHERE tr.job_id = %(job_id)s
          AND tr.translation_status = 'SUCCESS'
          AND tr.target_ddl IS NOT NULL
          AND tr.applied_status IS NULL
        """,
        {"job_id": job_id},
    )
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def mark_translation_applied(
    conn: psycopg.Connection, translation_id: str, status: str, error: Optional[str] = None
) -> None:
    conn.execute(
        "UPDATE translation_results SET applied_status = %(status)s, applied_error = %(error)s "
        "WHERE id = %(id)s",
        {"status": status, "error": error, "id": translation_id},
    )
