"""Persists discovery output into the Platform Metadata DB (architecture.md §10 ERD)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from pgvector.psycopg import register_vector

from orchestrator.checkpointer import get_metadata_db_uri


@contextmanager
def metadata_connection() -> Iterator[psycopg.Connection]:
    """One connection shared across a discovery run's writes (opening a fresh
    connection per statement is needlessly slow: each pays TCP/TLS handshake
    plus register_vector()'s pg_type lookup)."""
    conn = psycopg.connect(get_metadata_db_uri(), autocommit=True)
    register_vector(conn)
    try:
        yield conn
    finally:
        conn.close()


def upsert_migration_job(
    conn: psycopg.Connection, job_id: str, source_dialect: str, target_dialect: str, status: str
) -> None:
    conn.execute(
        """
        INSERT INTO migration_jobs
            (id, name, source_dialect, target_dialect, source_config, target_config, status)
        VALUES
            (%(id)s, %(name)s, %(source_dialect)s, %(target_dialect)s, '{}'::jsonb, '{}'::jsonb, %(status)s)
        ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, updated_at = CURRENT_TIMESTAMP
        """,
        {
            "id": job_id,
            "name": f"{source_dialect}->{target_dialect}",
            "source_dialect": source_dialect,
            "target_dialect": target_dialect,
            "status": status,
        },
    )


def save_object_catalog(
    conn: psycopg.Connection,
    job_id: str,
    catalog: list[dict[str, Any]],
    dependency_graph: dict[str, list[str]],
) -> None:
    conn.execute("DELETE FROM object_catalog_entries WHERE job_id = %s", (job_id,))
    for entry in catalog:
        conn.execute(
            """
            INSERT INTO object_catalog_entries
                (job_id, object_type, object_name, schema_name, definition, dependencies)
            VALUES
                (%(job_id)s, %(object_type)s, %(object_name)s, %(schema_name)s, %(definition)s, %(dependencies)s)
            """,
            {
                "job_id": job_id,
                "object_type": entry["object_type"],
                "object_name": entry["name"],
                "schema_name": entry["schema"],
                "definition": entry.get("definition"),
                "dependencies": dependency_graph.get(entry["name"], []),
            },
        )


def save_discovery_embedding(
    conn: psycopg.Connection,
    job_id: str,
    object_type: str,
    object_name: str,
    embedding: list[float],
) -> None:
    conn.execute(
        "INSERT INTO discovery_embeddings (job_id, object_type, object_name, embedding) "
        "VALUES (%s, %s, %s, %s)",
        (job_id, object_type, object_name, embedding),
    )
