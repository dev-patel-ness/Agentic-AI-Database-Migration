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

        conn = psycopg2.connect(
            host=connection_config.get("host", "localhost"),
            port=connection_config.get("port", 5432),
            user=connection_config.get("username", "postgres"),
            password=connection_config.get("password", ""),
            dbname=connection_config.get("database", "postgres"),
        )
        # Unqualified identifiers in translated DDL (views/triggers/FKs --
        # schema_agent's apply step doesn't schema-qualify them) resolve
        # against the connection's search_path, which defaults to "public".
        # Without this, DDL against a non-public target schema fails with
        # "relation ... does not exist" even though the table exists.
        schema_name = connection_config.get("schema_name")
        if schema_name:
            quoted_schema = '"' + schema_name.replace('"', '""') + '"'
            with conn.cursor() as cursor:
                cursor.execute(f"SET search_path TO {quoted_schema}, public")
            conn.commit()
        return conn
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


def reset_target_namespace(dialect_name: str, connection_config: dict[str, Any]) -> None:
    """Wipe every object out of the target namespace (schema/database/owner)
    before a job starts, so a run's results always reflect a clean target --
    never leftovers from a previous migration that used the same connection.
    Only touches the target namespace; a connection used as *source* in
    another job is never modified by this (per-job, target-side only).
    """
    namespace = default_namespace(dialect_name, connection_config)

    if dialect_name == "postgresql":
        quoted = '"' + namespace.replace('"', '""') + '"'
        conn = connect(dialect_name, connection_config)
        try:
            with conn.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {quoted} CASCADE")
                cursor.execute(f"CREATE SCHEMA {quoted}")
            conn.commit()
        finally:
            conn.close()
        return

    if dialect_name == "mysql":
        import mysql.connector

        quoted = "`" + namespace.replace("`", "``") + "`"
        # Connect without selecting the target database -- can't DROP
        # DATABASE while USE'd into it.
        conn = mysql.connector.connect(
            host=connection_config.get("host", "localhost"),
            port=connection_config.get("port", 3306),
            user=connection_config.get("username", "root"),
            password=connection_config.get("password", ""),
        )
        try:
            cursor = conn.cursor()
            cursor.execute(f"DROP DATABASE IF EXISTS {quoted}")
            cursor.execute(
                f"CREATE DATABASE {quoted} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return

    if dialect_name == "oracle":
        # No DROP USER privilege expected for the app's own schema user --
        # drop every object the user owns instead (self-service, no DBA
        # grant required). WHEN OTHERS THEN NULL per-object so one dependent
        # object that fails to drop doesn't abort the whole cleanup.
        conn = connect(dialect_name, connection_config)
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                BEGIN
                    FOR rec IN (
                        SELECT object_name, object_type
                        FROM user_objects
                        WHERE object_type IN (
                            'TABLE','VIEW','PACKAGE','PACKAGE BODY','PROCEDURE',
                            'FUNCTION','TRIGGER','SEQUENCE','TYPE','MATERIALIZED VIEW'
                        )
                        ORDER BY DECODE(object_type,
                            'MATERIALIZED VIEW', 0, 'TRIGGER', 0, 'VIEW', 0,
                            'PACKAGE BODY', 0, 'PACKAGE', 0, 'FUNCTION', 0,
                            'PROCEDURE', 0, 'TABLE', 1, 'SEQUENCE', 2, 'TYPE', 2, 3)
                    )
                    LOOP
                        BEGIN
                            IF rec.object_type = 'TABLE' THEN
                                EXECUTE IMMEDIATE
                                    'DROP TABLE "' || rec.object_name || '" CASCADE CONSTRAINTS PURGE';
                            ELSIF rec.object_type = 'TYPE' THEN
                                EXECUTE IMMEDIATE 'DROP TYPE "' || rec.object_name || '" FORCE';
                            ELSE
                                EXECUTE IMMEDIATE
                                    'DROP ' || rec.object_type || ' "' || rec.object_name || '"';
                            END IF;
                        EXCEPTION
                            WHEN OTHERS THEN NULL;
                        END;
                    END LOOP;
                END;
                """
            )
            conn.commit()
            cursor.close()
        finally:
            conn.close()
        return

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
