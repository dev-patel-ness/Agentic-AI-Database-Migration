"""Schema Extractor Adapter: driver-based schema introspection -> object catalog + FK dependency graph.

Uses each dialect's SQL-query methods (dialects/base.py) executed over the
matching DB-API driver connection. Deliberately avoids shelling out to native
dump tools (pg_dump/mysqldump/sqlplus) -- those aren't guaranteed to be
installed on the host running the platform, and would require passing DB
credentials via process argv.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from dialects import get_dialect
from dialects.base import Dialect
from dialects.connections import connect as _connect
from dialects.connections import default_namespace as _default_namespace
from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    RollbackResult,
    ToolResult,
)
from tool_adapters.base import JobStatus as AdapterJobStatus


class SchemaExtractorAdapter(BaseToolAdapter):
    """Runs discovery queries against a live connection to build the object catalog."""

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.SCHEMA_EXTRACTOR

    @property
    def name(self) -> str:
        return "schema_extractor_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        if "dialect" not in config or "connection" not in config:
            raise ValueError("schema_extractor_adapter requires 'dialect' and 'connection' keys")
        return AdapterConfig(options=config)

    def run(self, config: AdapterConfig) -> ToolResult:
        start = time.monotonic()
        dialect_name: str = config.options["dialect"]
        connection_config: dict[str, Any] = config.options["connection"]
        dialect = get_dialect(dialect_name)
        namespace = _default_namespace(dialect_name, connection_config)

        conn = _connect(dialect_name, connection_config)
        try:
            catalog = self._build_catalog(dialect, namespace, conn)
            fk_rows = self._fetch_foreign_keys(dialect, namespace, conn)
            catalog.extend(self._build_foreign_key_catalog(dialect, namespace, fk_rows))
            dependency_graph = self._build_dependency_graph(fk_rows)
        finally:
            conn.close()

        return ToolResult(
            success=True,
            output={"object_catalog": catalog, "dependency_graph": dependency_graph},
            execution_time_seconds=time.monotonic() - start,
        )

    def status(self, job_id: str) -> AdapterJobStatus:
        # Discovery runs synchronously within run(); nothing long-running to poll.
        return AdapterJobStatus(job_id=job_id, state=ExecutionState.SUCCESS, progress_percent=100)

    def rollback(self, job_id: str) -> RollbackResult:
        # Read-only operation: nothing to undo.
        return RollbackResult(success=True, detail={"note": "schema discovery is read-only"})

    def _build_catalog(self, dialect: Dialect, namespace: str, conn: Any) -> list[dict[str, Any]]:
        catalog: list[dict[str, Any]] = []
        object_queries = {
            "table": dialect.get_tables_query(namespace),
            "view": dialect.get_views_query(namespace),
            "procedure": dialect.get_procedures_query(namespace),
            "function": dialect.get_functions_query(namespace),
            "trigger": dialect.get_triggers_query(namespace),
        }
        for object_type, query in object_queries.items():
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                # Triggers queries return a 3rd column (owning table_name); other
                # object types only return (schema, name).
                owner, obj_name = row[0], row[1]
                table_name = row[2] if object_type == "trigger" and len(row) > 2 else None
                entry: dict[str, Any] = {
                    "object_type": object_type,
                    "name": obj_name,
                    "schema": owner,
                    "definition": None,
                }
                if object_type == "table":
                    entry["columns"] = self._fetch_columns(dialect, namespace, obj_name, conn)
                entry["definition"] = self._fetch_definition(
                    dialect, object_type, owner, obj_name, table_name, conn
                )
                catalog.append(entry)
        return catalog

    def _fetch_columns(
        self, dialect: Dialect, namespace: str, table_name: str, conn: Any
    ) -> list[dict[str, Any]]:
        cursor = conn.cursor()
        cursor.execute(dialect.get_columns_query(table_name, namespace))
        columns = [
            {
                "name": row[0],
                "native_type": row[1],
                "nullable": bool(row[2]),
                "default_value": row[3],
                "is_primary_key": bool(row[4]),
            }
            for row in cursor.fetchall()
        ]
        cursor.close()
        return columns

    # MySQL's SHOW CREATE * statements return several trailing metadata columns
    # (character_set_client, collation_connection, ...) after the DDL column,
    # so (unlike Oracle/Postgres single-column results) the DDL text isn't
    # reliably the *last* column -- look it up by name instead.
    _MYSQL_DDL_COLUMN = {
        "table": "Create Table",
        "view": "Create View",
        "procedure": "Create Procedure",
        "function": "Create Function",
        "trigger": "SQL Original Statement",
    }

    def _fetch_definition(
        self,
        dialect: Dialect,
        object_type: str,
        owner: str,
        obj_name: str,
        table_name: Optional[str],
        conn: Any,
    ) -> Optional[str]:
        query_builders = {
            "table": lambda: dialect.get_table_definition(obj_name, owner),
            "view": lambda: dialect.get_view_definition(obj_name, owner),
            "procedure": lambda: dialect.get_procedure_definition(obj_name, owner),
            "function": lambda: dialect.get_function_definition(obj_name, owner),
            "trigger": lambda: dialect.get_trigger_definition(obj_name, owner, table_name),
        }
        try:
            query = query_builders[object_type]()
            if dialect.name == "mysql":
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query)
                row = cursor.fetchone()
                cursor.close()
                if row is None:
                    return None
                ddl = row.get(self._MYSQL_DDL_COLUMN[object_type])
            else:
                cursor = conn.cursor()
                cursor.execute(query)
                row = cursor.fetchone()
                cursor.close()
                if row is None:
                    return None
                ddl = row[-1]
            if hasattr(ddl, "read"):
                ddl = ddl.read()
            return str(ddl) if ddl is not None else None
        except Exception:
            return None  # DDL text is best-effort/for-display only; never fail discovery over it.

    def _build_dependency_graph(self, fk_rows: list[tuple]) -> dict[str, list[str]]:
        graph: dict[str, list[str]] = {}
        for _constraint_name, table_name, _column_name, ref_table_name, _ref_column_name in fk_rows:
            graph.setdefault(table_name, [])
            if ref_table_name not in graph[table_name]:
                graph[table_name].append(ref_table_name)
        return graph

    def _fetch_foreign_keys(self, dialect: Dialect, namespace: str, conn: Any) -> list[tuple]:
        cursor = conn.cursor()
        cursor.execute(dialect.get_foreign_keys_query(namespace))
        rows = cursor.fetchall()
        cursor.close()
        return rows

    def _build_foreign_key_catalog(
        self, dialect: Dialect, namespace: str, fk_rows: list[tuple]
    ) -> list[dict[str, Any]]:
        """Synthesizes standalone ALTER TABLE ADD CONSTRAINT DDL per foreign key.

        Kept as its own object_type (not folded into the owning table's DDL)
        so the Schema Agent can route it through CrackSQL translation while
        skipping CREATE TABLE DDL entirely -- table creation + data land via
        the Data Agent/SeaTunnel (whose JDBC sink auto-generates basic target
        schema via `schema_save_mode`), but SeaTunnel's create-table-sql
        builders explicitly skip FOREIGN_KEY generation for every dialect we
        support (MySQL/Postgres: no-op with a "todo"/"not available" comment;
        Oracle: constraint keys aren't handled at all) -- so constraints still
        need dialect-aware DDL translation here.
        """
        entries: list[dict[str, Any]] = []
        # NOTE: one row per (constraint, column) -- a composite multi-column FK
        # would produce multiple entries sharing a constraint_name, each a
        # partial (invalid) ADD CONSTRAINT; none of our sample schemas have one.
        for constraint_name, table_name, column_name, ref_table_name, ref_column_name in fk_rows:
            q = dialect.quote_identifier
            ddl = (
                f"ALTER TABLE {q(table_name)} ADD CONSTRAINT {q(constraint_name)} "
                f"FOREIGN KEY ({q(column_name)}) REFERENCES {q(ref_table_name)} ({q(ref_column_name)})"
            )
            entries.append(
                {
                    "object_type": "foreign_key",
                    "name": constraint_name,
                    "schema": namespace,
                    "table_name": table_name,
                    "definition": ddl,
                }
            )
        return entries
