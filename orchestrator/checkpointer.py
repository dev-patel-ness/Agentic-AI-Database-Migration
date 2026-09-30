"""Postgres-backed LangGraph checkpointer for the platform metadata DB (architecture.md §6, §10).

Backed by the same ``postgres-metadata`` service from docker-compose.yml. The
connection pool is owned by the caller (typically the FastAPI app lifespan) so
it can be shared across requests and closed cleanly on shutdown.
"""

from __future__ import annotations

import os

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


def get_metadata_db_uri() -> str:
    host = os.getenv("POSTGRES_METADATA_HOST", "localhost")
    port = os.getenv("POSTGRES_METADATA_PORT", "5432")
    database = os.getenv("POSTGRES_METADATA_DATABASE", "migration_metadata")
    user = os.getenv("POSTGRES_METADATA_USER", "postgres")
    password = os.getenv("POSTGRES_METADATA_PASSWORD", "postgres_dev_password")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def build_checkpointer_pool(min_size: int = 1, max_size: int = 10) -> ConnectionPool:
    """Open the connection pool backing the checkpointer. Caller owns its lifecycle."""
    return ConnectionPool(
        conninfo=get_metadata_db_uri(),
        min_size=min_size,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=True,
    )


def build_checkpointer(pool: ConnectionPool) -> PostgresSaver:
    """Wrap a connection pool as a LangGraph checkpointer, ensuring its schema exists."""
    saver = PostgresSaver(pool)
    saver.setup()  # idempotent: creates/migrates checkpoint tables if missing
    return saver
