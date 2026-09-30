"""Shared DB-API connection helpers, used by any adapter/agent that needs a
live driver connection to a source or target DB (schema_extractor_adapter,
agents/schema_agent's DDL-application step, ...).

Deliberately avoids shelling out to native dump tools (pg_dump/mysqldump/
sqlplus) -- those aren't guaranteed to be installed on the host running the
platform, and would require passing DB credentials via process argv.
"""

from __future__ import annotations

from typing import Any


def connect(dialect_name: str, connection_config: dict[str, Any]):
    """Open a live DB-API connection for the given dialect."""
    if dialect_name == "postgresql":
        import psycopg2

        return psycopg2.connect(
            host=connection_config.get("host", "localhost"),
            port=connection_config.get("port", 5432),
            user=connection_config.get("username", "postgres"),
            password=connection_config.get("password", ""),
            dbname=connection_config.get("database", "postgres"),
        )
    if dialect_name == "mysql":
        import mysql.connector

        return mysql.connector.connect(
            host=connection_config.get("host", "localhost"),
            port=connection_config.get("port", 3306),
            user=connection_config.get("username", "root"),
            password=connection_config.get("password", ""),
            database=connection_config.get("database", ""),
        )
    if dialect_name == "oracle":
        import oracledb

        dsn = oracledb.makedsn(
            connection_config.get("host", "localhost"),
            connection_config.get("port", 1521),
            service_name=connection_config.get("database", "XE"),
        )
        conn = oracledb.connect(
            user=connection_config.get("username", "sample_user"),
            password=connection_config.get("password", ""),
            dsn=dsn,
        )
        # DBMS_METADATA.GET_DDL defaults to emitting full STORAGE/segment
        # clauses, which is measurably slow (multiple seconds) for tables
        # with LOB columns; suppressing them also yields cleaner DDL text.
        cursor = conn.cursor()
        cursor.execute(
            """
            BEGIN
                DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'STORAGE', FALSE);
                DBMS_METADATA.SET_TRANSFORM_PARAM(DBMS_METADATA.SESSION_TRANSFORM, 'SEGMENT_ATTRIBUTES', FALSE);
            END;
            """
        )
        cursor.close()
        return conn
    raise ValueError(f"Unsupported dialect: {dialect_name!r}")


def default_namespace(dialect_name: str, connection_config: dict[str, Any]) -> str:
    """The namespace to use: schema (Postgres), database (MySQL), or owner (Oracle)."""
    if dialect_name == "postgresql":
        return connection_config.get("schema_name") or "public"
    if dialect_name == "mysql":
        return connection_config.get("database", "")
    if dialect_name == "oracle":
        return connection_config.get("username", "")
    raise ValueError(f"Unsupported dialect: {dialect_name!r}")
