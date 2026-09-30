"""MySQL dialect plugin (implements dialects.base.Dialect)."""

from __future__ import annotations

from typing import Any, Optional

from dialects.base import Dialect, SQLObject, validate_identifier

# information_schema types -> canonical types used across the platform.
_TYPE_MAP: dict[str, str] = {
    "tinyint": "SMALLINT",
    "smallint": "SMALLINT",
    "int": "INT",
    "bigint": "BIGINT",
    "decimal": "NUMERIC",
    "float": "FLOAT",
    "double": "DOUBLE",
    "varchar": "VARCHAR",
    "char": "CHAR",
    "text": "TEXT",
    "longtext": "TEXT",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "timestamp": "TIMESTAMP",
    "blob": "BLOB",
    "json": "JSON",
}

_SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys"}


class MySQLDialect(Dialect):
    """Symmetric MySQL plugin: usable as either migration source or target.

    Note: in MySQL, "schema" and "database" are the same concept.
    """

    @property
    def name(self) -> str:
        return "mysql"

    @property
    def version(self) -> str:
        return "8.0"

    def type_map(self) -> dict[str, str]:
        return dict(_TYPE_MAP)

    def export_ddl_command(self, connection_config: dict[str, Any]) -> list[str]:
        # Kept for interface parity/documentation; the schema_extractor_adapter
        # uses pure driver/SQL introspection instead (no local mysqldump binary
        # required, no credentials passed via process argv).
        host = connection_config.get("host", "localhost")
        user = connection_config.get("username", "root")
        password = connection_config.get("password", "")
        database = connection_config.get("database", "")
        return [
            "mysqldump",
            "--no-data",
            "-h",
            host,
            "-u",
            user,
            f"--password={password}",
            database,
        ]

    def quote_identifier(self, identifier: str) -> str:
        return "`" + identifier.replace("`", "``") + "`"

    def build_connection_string(self, config: dict[str, Any]) -> str:
        host = config.get("host", "localhost")
        port = config.get("port", 3306)
        user = config.get("username", "root")
        password = config.get("password", "")
        database = config.get("database", "")
        return f"mysql://{user}:{password}@{host}:{port}/{database}"

    def get_tables_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"table_schema = '{schema}'"
            if schema
            else "table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
        )
        return (
            "SELECT table_schema, table_name FROM information_schema.tables "
            f"WHERE table_type = 'BASE TABLE' AND {where} ORDER BY table_schema, table_name"
        )

    def get_views_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"table_schema = '{schema}'"
            if schema
            else "table_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
        )
        return f"SELECT table_schema, table_name FROM information_schema.views WHERE {where} ORDER BY table_schema, table_name"

    def get_procedures_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"routine_schema = '{schema}'"
            if schema
            else "routine_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
        )
        return (
            "SELECT routine_schema, routine_name FROM information_schema.routines "
            f"WHERE routine_type = 'PROCEDURE' AND {where} ORDER BY routine_schema, routine_name"
        )

    def get_functions_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"routine_schema = '{schema}'"
            if schema
            else "routine_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
        )
        return (
            "SELECT routine_schema, routine_name FROM information_schema.routines "
            f"WHERE routine_type = 'FUNCTION' AND {where} ORDER BY routine_schema, routine_name"
        )

    def get_triggers_query(self, schema: Optional[str] = None) -> str:
        schema = validate_identifier(schema) if schema else None
        where = (
            f"trigger_schema = '{schema}'"
            if schema
            else "trigger_schema NOT IN ('information_schema', 'mysql', 'performance_schema', 'sys')"
        )
        return (
            "SELECT trigger_schema, trigger_name, event_object_table FROM information_schema.triggers "
            f"WHERE {where} ORDER BY trigger_schema, trigger_name"
        )

    def get_columns_query(self, table_name: str, schema: Optional[str] = None) -> str:
        table_name = validate_identifier(table_name)
        db_clause = (
            f"AND table_schema = '{validate_identifier(schema)}'"
            if schema
            else "AND table_schema = DATABASE()"
        )
        return (
            "SELECT c.column_name, c.data_type, (c.is_nullable = 'YES') AS is_nullable, "
            "c.column_default, (c.column_key = 'PRI') AS is_primary_key "
            f"FROM information_schema.columns c WHERE c.table_name = '{table_name}' {db_clause} "
            "ORDER BY c.ordinal_position"
        )

    def get_foreign_keys_query(self, schema: Optional[str] = None) -> str:
        db_clause = (
            f"table_schema = '{validate_identifier(schema)}'"
            if schema
            else "table_schema = DATABASE()"
        )
        return (
            "SELECT constraint_name, table_name, column_name, "
            "referenced_table_name AS ref_table_name, referenced_column_name AS ref_column_name "
            f"FROM information_schema.key_column_usage WHERE {db_clause} "
            "AND referenced_table_name IS NOT NULL ORDER BY table_name, column_name"
        )

    def get_table_definition(self, table_name: str, schema: str) -> str:
        table_name = validate_identifier(table_name)
        schema = validate_identifier(schema)
        return f"SHOW CREATE TABLE `{schema}`.`{table_name}`"

    def get_view_definition(self, view_name: str, schema: str) -> str:
        view_name = validate_identifier(view_name)
        schema = validate_identifier(schema)
        return f"SHOW CREATE VIEW `{schema}`.`{view_name}`"

    def get_procedure_definition(self, procedure_name: str, schema: str) -> str:
        procedure_name = validate_identifier(procedure_name)
        schema = validate_identifier(schema)
        return f"SHOW CREATE PROCEDURE `{schema}`.`{procedure_name}`"

    def get_function_definition(self, function_name: str, schema: str) -> str:
        function_name = validate_identifier(function_name)
        schema = validate_identifier(schema)
        return f"SHOW CREATE FUNCTION `{schema}`.`{function_name}`"

    def get_trigger_definition(self, trigger_name: str, schema: str, table_name: Optional[str] = None) -> str:
        trigger_name = validate_identifier(trigger_name)
        schema = validate_identifier(schema)
        return f"SHOW CREATE TRIGGER `{schema}`.`{trigger_name}`"

    def is_system_object(self, obj: SQLObject) -> bool:
        return obj.schema in _SYSTEM_SCHEMAS
