"""Oracle dialect plugin (implements dialects.base.Dialect)."""

from __future__ import annotations

from typing import Any, Optional

from dialects.base import Dialect, SQLObject, validate_identifier

# ALL_TAB_COLUMNS native types -> canonical types used across the platform.
_TYPE_MAP: dict[str, str] = {
    "NUMBER": "NUMERIC",
    "VARCHAR2": "VARCHAR",
    "NVARCHAR2": "VARCHAR",
    "CHAR": "CHAR",
    "CLOB": "TEXT",
    "NCLOB": "TEXT",
    "BLOB": "BLOB",
    "DATE": "TIMESTAMP",
    "TIMESTAMP": "TIMESTAMP",
    "FLOAT": "FLOAT",
    "RAW": "BLOB",
}

_SYSTEM_SCHEMAS = {
    "SYS",
    "SYSTEM",
    "OUTLN",
    "XDB",
    "CTXSYS",
    "MDSYS",
    "ORDSYS",
    "ORDDATA",
    "DBSNMP",
    "APPQOSSYS",
    "GSMADMIN_INTERNAL",
    "WMSYS",
    "LBACSYS",
}


class OracleDialect(Dialect):
    """Symmetric Oracle plugin: usable as either migration source or target.

    Oracle folds unquoted identifiers to uppercase; queries against the
    ALL_* data dictionary views therefore uppercase schema/table names.
    """

    @property
    def name(self) -> str:
        return "oracle"

    @property
    def version(self) -> str:
        return "21c"

    def type_map(self) -> dict[str, str]:
        return dict(_TYPE_MAP)

    def export_ddl_command(self, connection_config: dict[str, Any]) -> list[str]:
        # Kept for interface parity/documentation; the schema_extractor_adapter
        # calls DBMS_METADATA.GET_DDL over the driver connection instead (no
        # local sqlplus binary required, no credentials passed via process argv).
        host = connection_config.get("host", "localhost")
        port = connection_config.get("port", 1521)
        service_name = connection_config.get("database", "XE")
        user = connection_config.get("username", "sample_user")
        return ["sqlplus", "-S", f"{user}/***@{host}:{port}/{service_name}", "@export.sql"]

    def quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.upper().replace('"', '""') + '"'

    def build_connection_string(self, config: dict[str, Any]) -> str:
        host = config.get("host", "localhost")
        port = config.get("port", 1521)
        service_name = config.get("database", "XE")
        return f"{host}:{port}/{service_name}"

    def get_tables_query(self, schema: Optional[str] = None) -> str:
        owner = validate_identifier(schema).upper() if schema else None
        where = (
            f"owner = '{owner}'"
            if owner
            else f"owner NOT IN ({','.join(repr(s) for s in _SYSTEM_SCHEMAS)})"
        )
        return f"SELECT owner, table_name FROM all_tables WHERE {where} ORDER BY owner, table_name"

    def get_views_query(self, schema: Optional[str] = None) -> str:
        owner = validate_identifier(schema).upper() if schema else None
        where = (
            f"owner = '{owner}'"
            if owner
            else f"owner NOT IN ({','.join(repr(s) for s in _SYSTEM_SCHEMAS)})"
        )
        return f"SELECT owner, view_name FROM all_views WHERE {where} ORDER BY owner, view_name"

    def get_procedures_query(self, schema: Optional[str] = None) -> str:
        owner = validate_identifier(schema).upper() if schema else None
        where = (
            f"owner = '{owner}'"
            if owner
            else f"owner NOT IN ({','.join(repr(s) for s in _SYSTEM_SCHEMAS)})"
        )
        return (
            "SELECT owner, object_name FROM all_procedures "
            f"WHERE object_type = 'PROCEDURE' AND {where} ORDER BY owner, object_name"
        )

    def get_functions_query(self, schema: Optional[str] = None) -> str:
        owner = validate_identifier(schema).upper() if schema else None
        where = (
            f"owner = '{owner}'"
            if owner
            else f"owner NOT IN ({','.join(repr(s) for s in _SYSTEM_SCHEMAS)})"
        )
        return (
            "SELECT owner, object_name FROM all_procedures "
            f"WHERE object_type = 'FUNCTION' AND {where} ORDER BY owner, object_name"
        )

    def get_triggers_query(self, schema: Optional[str] = None) -> str:
        owner = validate_identifier(schema).upper() if schema else None
        where = (
            f"owner = '{owner}'"
            if owner
            else f"owner NOT IN ({','.join(repr(s) for s in _SYSTEM_SCHEMAS)})"
        )
        return (
            "SELECT owner, trigger_name, table_name FROM all_triggers "
            f"WHERE {where} ORDER BY owner, trigger_name"
        )

    def get_columns_query(self, table_name: str, schema: Optional[str] = None) -> str:
        table_name = validate_identifier(table_name).upper()
        owner = validate_identifier(schema).upper() if schema else None
        pk_owner_clause = f"AND ac.owner = '{owner}'" if owner else ""
        col_owner_clause = f"AND c.owner = '{owner}'" if owner else ""
        return (
            "SELECT c.column_name, c.data_type, "
            "CASE WHEN c.nullable = 'Y' THEN 1 ELSE 0 END AS is_nullable, c.data_default, "
            "CASE WHEN pk.column_name IS NOT NULL THEN 1 ELSE 0 END AS is_primary_key "
            "FROM all_tab_columns c "
            "LEFT JOIN ( "
            "  SELECT acc.column_name FROM all_constraints ac "
            "  JOIN all_cons_columns acc ON ac.constraint_name = acc.constraint_name AND ac.owner = acc.owner "
            f"  WHERE ac.constraint_type = 'P' AND ac.table_name = '{table_name}' {pk_owner_clause} "
            ") pk ON pk.column_name = c.column_name "
            f"WHERE c.table_name = '{table_name}' {col_owner_clause} "
            "ORDER BY c.column_id"
        )

    def get_foreign_keys_query(self, schema: Optional[str] = None) -> str:
        owner_clause = (
            f"AND child.owner = '{validate_identifier(schema).upper()}'" if schema else ""
        )
        return (
            "SELECT child.constraint_name, child.table_name, child_col.column_name, "
            "parent_col.table_name AS ref_table_name, parent_col.column_name AS ref_column_name "
            "FROM all_constraints child "
            "JOIN all_cons_columns child_col "
            "  ON child.constraint_name = child_col.constraint_name AND child.owner = child_col.owner "
            "JOIN all_constraints parent "
            "  ON child.r_constraint_name = parent.constraint_name AND child.r_owner = parent.owner "
            "JOIN all_cons_columns parent_col "
            "  ON parent.constraint_name = parent_col.constraint_name AND parent.owner = parent_col.owner "
            f"WHERE child.constraint_type = 'R' {owner_clause} "
            "ORDER BY child.table_name, child_col.column_name"
        )

    def get_table_definition(self, table_name: str, schema: str) -> str:
        table_name = validate_identifier(table_name).upper()
        schema = validate_identifier(schema).upper()
        return f"SELECT DBMS_METADATA.GET_DDL('TABLE', '{table_name}', '{schema}') AS ddl FROM DUAL"

    def get_view_definition(self, view_name: str, schema: str) -> str:
        view_name = validate_identifier(view_name).upper()
        schema = validate_identifier(schema).upper()
        return f"SELECT DBMS_METADATA.GET_DDL('VIEW', '{view_name}', '{schema}') AS ddl FROM DUAL"

    def get_procedure_definition(self, procedure_name: str, schema: str) -> str:
        procedure_name = validate_identifier(procedure_name).upper()
        schema = validate_identifier(schema).upper()
        return f"SELECT DBMS_METADATA.GET_DDL('PROCEDURE', '{procedure_name}', '{schema}') AS ddl FROM DUAL"

    def get_function_definition(self, function_name: str, schema: str) -> str:
        function_name = validate_identifier(function_name).upper()
        schema = validate_identifier(schema).upper()
        return f"SELECT DBMS_METADATA.GET_DDL('FUNCTION', '{function_name}', '{schema}') AS ddl FROM DUAL"

    def get_trigger_definition(self, trigger_name: str, schema: str, table_name: Optional[str] = None) -> str:
        trigger_name = validate_identifier(trigger_name).upper()
        schema = validate_identifier(schema).upper()
        return f"SELECT DBMS_METADATA.GET_DDL('TRIGGER', '{trigger_name}', '{schema}') AS ddl FROM DUAL"

    def is_system_object(self, obj: SQLObject) -> bool:
        return obj.schema.upper() in _SYSTEM_SCHEMAS
