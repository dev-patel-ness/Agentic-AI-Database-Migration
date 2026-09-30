"""PostgreSQL dialect plugin (implements dialects.base.Dialect)."""

from __future__ import annotations

from typing import Any, Optional

from dialects.base import Dialect, SQLObject, validate_identifier

# information_schema/pg_catalog types -> canonical types used across the platform.
_TYPE_MAP: dict[str, str] = {
    "smallint": "SMALLINT",
    "integer": "INT",
    "bigint": "BIGINT",
    "numeric": "NUMERIC",
    "real": "FLOAT",
    "double precision": "DOUBLE",
    "boolean": "BOOLEAN",
    "character varying": "VARCHAR",
    "character": "CHAR",
    "text": "TEXT",
    "date": "DATE",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMPTZ",
    "bytea": "BLOB",
    "jsonb": "JSON",
    "json": "JSON",
    "uuid": "UUID",
}

_SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


class PostgreSQLDialect(Dialect):
    """Symmetric PostgreSQL plugin: usable as either migration source or target."""

    @property
    def name(self) -> str:
        return "postgresql"

    @property
    def version(self) -> str:
        return "14"

    def type_map(self) -> dict[str, str]:
        return dict(_TYPE_MAP)

    def export_ddl_command(self, connection_config: dict[str, Any]) -> list[str]:
        # Kept for interface parity/documentation; the schema_extractor_adapter
        # uses pure driver/SQL introspection instead (no local pg_dump binary
        # required, no credentials passed via process argv).
        conn_str = self.build_connection_string(connection_config)
        return ["pg_dump", "--schema-only", f"--dbname={conn_str}"]

    def quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def build_connection_string(self, config: dict[str, Any]) -> str:
        host = config.get("host", "localhost")
        port = config.get("port", 5432)
        user = config.get("username", "postgres")
        password = config.get("password", "")
        database = config.get("database", "postgres")
        return f"postgresql://{user}:{password}@{host}:{port}/{database}"

    def get_tables_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"AND table_schema = '{schema}'"
            if schema
            else "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        return (
            "SELECT table_schema, table_name FROM information_schema.tables "
            f"WHERE table_type = 'BASE TABLE' {where} ORDER BY table_schema, table_name"
        )

    def get_views_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"AND table_schema = '{schema}'"
            if schema
            else "AND table_schema NOT IN ('pg_catalog', 'information_schema')"
        )
        return f"SELECT table_schema, table_name FROM information_schema.views WHERE TRUE {where} ORDER BY table_schema, table_name"

    def get_procedures_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"AND n.nspname = '{schema}'"
            if schema
            else "AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
        )
        return (
            "SELECT n.nspname AS schema_name, p.proname AS proc_name "
            "FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            f"WHERE p.prokind = 'p' {where} ORDER BY n.nspname, p.proname"
        )

    def get_functions_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"AND n.nspname = '{schema}'"
            if schema
            else "AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
        )
        return (
            "SELECT n.nspname AS schema_name, p.proname AS func_name "
            "FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            f"WHERE p.prokind = 'f' {where} ORDER BY n.nspname, p.proname"
        )

    def get_triggers_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"AND n.nspname = '{schema}'"
            if schema
            else "AND n.nspname NOT IN ('pg_catalog', 'information_schema')"
        )
        return (
            "SELECT n.nspname AS schema_name, t.tgname AS trigger_name, c.relname AS table_name "
            "FROM pg_trigger t "
            "JOIN pg_class c ON t.tgrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            f"WHERE NOT t.tgisinternal {where} ORDER BY n.nspname, t.tgname"
        )

    def get_columns_query(self, table_name: str, schema: Optional[str] = None) -> str:
        table_name = validate_identifier(table_name)
        schema = validate_identifier(schema) if schema else "public"
        return (
            "SELECT c.column_name, c.data_type, "
            "(c.is_nullable = 'YES') AS is_nullable, c.column_default, "
            "(pk.column_name IS NOT NULL) AS is_primary_key "
            "FROM information_schema.columns c "
            "LEFT JOIN ( "
            "  SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "  JOIN information_schema.key_column_usage kcu "
            "    ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            f"  WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = '{schema}' AND tc.table_name = '{table_name}' "
            ") pk ON pk.column_name = c.column_name "
            f"WHERE c.table_schema = '{schema}' AND c.table_name = '{table_name}' "
            "ORDER BY c.ordinal_position"
        )

    def get_foreign_keys_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else "public"
        return (
            "SELECT tc.constraint_name, tc.table_name, kcu.column_name, "
            "ccu.table_name AS ref_table_name, ccu.column_name AS ref_column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema "
            f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = '{schema}' "
            "ORDER BY tc.table_name, kcu.column_name"
        )

    def get_table_definition(self, table_name: str, schema: str) -> str:
        table_name = validate_identifier(table_name)
        schema = validate_identifier(schema)
        # Synthesizes a CREATE TABLE statement from catalog views + built-in
        # pg_get_*def() functions -- no pg_dump binary required.
        return (
            "SELECT 'CREATE TABLE ' || quote_ident(n.nspname) || '.' || quote_ident(c.relname) || ' (' || "
            "string_agg(a.attname || ' ' || pg_catalog.format_type(a.atttypid, a.atttypmod) || "
            "CASE WHEN a.attnotnull THEN ' NOT NULL' ELSE '' END, ', ' ORDER BY a.attnum) || ');' AS ddl "
            "FROM pg_attribute a "
            "JOIN pg_class c ON a.attrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            f"WHERE n.nspname = '{schema}' AND c.relname = '{table_name}' "
            "AND a.attnum > 0 AND NOT a.attisdropped "
            "GROUP BY n.nspname, c.relname"
        )

    def get_view_definition(self, view_name: str, schema: str) -> str:
        view_name = validate_identifier(view_name)
        schema = validate_identifier(schema)
        return (
            "SELECT 'CREATE VIEW ' || quote_ident(n.nspname) || '.' || quote_ident(c.relname) || "
            "' AS ' || pg_get_viewdef(c.oid, true) AS ddl "
            "FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid "
            f"WHERE n.nspname = '{schema}' AND c.relname = '{view_name}'"
        )

    def get_procedure_definition(self, procedure_name: str, schema: str) -> str:
        procedure_name = validate_identifier(procedure_name)
        schema = validate_identifier(schema)
        return (
            "SELECT pg_get_functiondef(p.oid) AS ddl "
            "FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            f"WHERE n.nspname = '{schema}' AND p.proname = '{procedure_name}' AND p.prokind = 'p'"
        )

    def get_function_definition(self, function_name: str, schema: str) -> str:
        function_name = validate_identifier(function_name)
        schema = validate_identifier(schema)
        return (
            "SELECT pg_get_functiondef(p.oid) AS ddl "
            "FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
            f"WHERE n.nspname = '{schema}' AND p.proname = '{function_name}' AND p.prokind = 'f'"
        )

    def get_trigger_definition(self, trigger_name: str, schema: str, table_name: Optional[str] = None) -> str:
        trigger_name = validate_identifier(trigger_name)
        schema = validate_identifier(schema)
        return (
            "SELECT pg_get_triggerdef(t.oid, true) AS ddl "
            "FROM pg_trigger t "
            "JOIN pg_class c ON t.tgrelid = c.oid "
            "JOIN pg_namespace n ON c.relnamespace = n.oid "
            f"WHERE n.nspname = '{schema}' AND t.tgname = '{trigger_name}' AND NOT t.tgisinternal"
        )

    def is_system_object(self, obj: SQLObject) -> bool:
        return obj.schema in _SYSTEM_SCHEMAS
