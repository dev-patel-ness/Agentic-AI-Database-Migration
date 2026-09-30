"""
Abstract contract every dialect plugin (Oracle, MySQL, PostgreSQL) must implement.

A dialect is symmetric: the same class is used whether the engine is acting
as migration source or target (see architecture.md's `DialectPair`).

Each dialect must implement:
- Type mapping between native and canonical types
- DDL export/import commands
- SQL generation (identifier quoting, DDL syntax)
- Connection management
- Schema introspection queries
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$#]*$")


def validate_identifier(identifier: str) -> str:
    """Defensively validate a schema/table/column name before interpolating it
    into generated SQL text (identifiers can't be bind-parameterized like
    values can — see architecture.md §14). Raises ValueError on anything that
    isn't a plain alphanumeric/underscore identifier.
    """
    if not identifier or not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"Unsafe or invalid SQL identifier: {identifier!r}")
    return identifier


class SQLObjectType(str, Enum):
    """Types of database objects."""

    TABLE = "table"
    VIEW = "view"
    INDEX = "index"
    PROCEDURE = "procedure"
    FUNCTION = "function"
    TRIGGER = "trigger"
    SEQUENCE = "sequence"
    PACKAGE = "package"
    CONSTRAINT = "constraint"


@dataclass
class SQLObject:
    """Represents a database object."""

    object_type: SQLObjectType
    name: str
    schema: str
    definition: Optional[str] = None
    dependencies: list[str] = None
    is_system: bool = False

    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


@dataclass
class ColumnMetadata:
    """Metadata for a table column."""

    name: str
    native_type: str
    nullable: bool = True
    default_value: Optional[str] = None
    is_primary_key: bool = False
    comment: Optional[str] = None


@dataclass
class TableMetadata:
    """Metadata for a table."""

    name: str
    schema: str
    columns: list[ColumnMetadata]
    primary_key_columns: list[str]
    comment: Optional[str] = None
    row_count: Optional[int] = None


@dataclass
class ForeignKeyMetadata:
    """A single foreign-key relationship, used to build the dependency graph."""

    constraint_name: str
    table_name: str
    column_name: str
    ref_table_name: str
    ref_column_name: str


class Dialect(ABC):
    """
    Type map + SQL grammar hooks for a single database engine.

    Symmetric: the same class is used whether the engine is acting
    as migration source or target.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the dialect name (e.g., 'oracle', 'mysql', 'postgresql')."""
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """Return the target/tested version of this dialect (e.g., '23c', '8.0', '14')."""
        raise NotImplementedError

    @abstractmethod
    def type_map(self) -> dict[str, str]:
        """
        Return the native-type -> canonical-type mapping for this dialect.

        Example:
            {
                'INTEGER': 'INT',
                'BIGINT': 'BIGINT',
                'VARCHAR': 'STRING',
                'CLOB': 'TEXT',
            }
        """
        raise NotImplementedError

    @abstractmethod
    def export_ddl_command(self, connection_config: dict[str, Any]) -> list[str]:
        """
        Return the native command used to export schema-only DDL.

        Example for PostgreSQL:
            ['pg_dump', '--schema-only', '--dbname=postgresql://...']

        Example for MySQL:
            ['mysqldump', '--no-data', '-h', 'host', '-u', 'user', '--password=...', 'database']

        Example for Oracle:
            ['sqlplus', '-S', 'user/pass@host:port/sid', '@', 'export.sql']
        """
        raise NotImplementedError

    @abstractmethod
    def quote_identifier(self, identifier: str) -> str:
        """
        Quote a table/column/object identifier per this dialect's grammar.

        Example:
            - PostgreSQL: 'my_table' -> '"my_table"'
            - MySQL: 'my_table' -> '`my_table`'
            - Oracle: 'my_table' -> '"MY_TABLE"'  (Oracle folds to uppercase)
        """
        raise NotImplementedError

    @abstractmethod
    def build_connection_string(self, config: dict[str, Any]) -> str:
        """
        Build a connection string from the config dictionary.

        Args:
            config: Dictionary with keys like 'host', 'port', 'username', 'password', 'database'.

        Returns:
            Connection string in the dialect's native format.
        """
        raise NotImplementedError

    @abstractmethod
    def get_tables_query(self, schema: Optional[str] = None) -> str:
        """
        Return a SQL query that lists all tables in the database (or schema).

        Returns a query that produces columns: [schema_name, table_name, row_count (optional)]
        """
        raise NotImplementedError

    @abstractmethod
    def get_views_query(self, schema: Optional[str] = None) -> str:
        """Return a SQL query that lists all views in the database (or schema)."""
        raise NotImplementedError

    @abstractmethod
    def get_procedures_query(self, schema: Optional[str] = None) -> str:
        """Return a SQL query that lists all stored procedures in the database (or schema)."""
        raise NotImplementedError

    @abstractmethod
    def get_functions_query(self, schema: Optional[str] = None) -> str:
        """Return a SQL query that lists all functions in the database (or schema)."""
        raise NotImplementedError

    @abstractmethod
    def get_triggers_query(self, schema: Optional[str] = None) -> str:
        """Return a SQL query that lists all triggers in the database (or schema)."""
        raise NotImplementedError

    @abstractmethod
    def get_columns_query(self, table_name: str, schema: Optional[str] = None) -> str:
        """
        Return a SQL query listing all columns for a table.

        Returns a query that produces columns (in ordinal position order):
        [column_name, native_type, is_nullable, default_value, is_primary_key]
        """
        raise NotImplementedError

    @abstractmethod
    def get_foreign_keys_query(self, schema: Optional[str] = None) -> str:
        """
        Return a SQL query listing all foreign-key relationships in the schema.

        Returns a query that produces columns:
        [constraint_name, table_name, column_name, ref_table_name, ref_column_name]

        This is the primary source for the object dependency graph — more
        reliable than parsing DDL text, and available via every dialect's
        system catalog without needing a native DDL-export CLI tool.
        """
        raise NotImplementedError

    @abstractmethod
    def get_table_definition(self, table_name: str, schema: str) -> str:
        """
        Return a SQL query whose single-row/single-column result is the
        CREATE TABLE statement (or closest native equivalent) for a table —
        e.g. `SHOW CREATE TABLE` (MySQL), `DBMS_METADATA.GET_DDL` (Oracle), or
        a synthesized definition from catalog views (PostgreSQL). Executed via
        the same DB-API connection as the other query methods; no native CLI
        dump tool required.
        """
        raise NotImplementedError

    @abstractmethod
    def get_view_definition(self, view_name: str, schema: str) -> str:
        """Return a query whose single-row/single-column result is the
        CREATE VIEW statement (or closest native equivalent) for a view."""
        raise NotImplementedError

    @abstractmethod
    def get_procedure_definition(self, procedure_name: str, schema: str) -> str:
        """Return a query whose single-row/single-column result is the
        CREATE PROCEDURE statement (or closest native equivalent)."""
        raise NotImplementedError

    @abstractmethod
    def get_function_definition(self, function_name: str, schema: str) -> str:
        """Return a query whose single-row/single-column result is the
        CREATE FUNCTION statement (or closest native equivalent)."""
        raise NotImplementedError

    @abstractmethod
    def get_trigger_definition(self, trigger_name: str, schema: str, table_name: Optional[str] = None) -> str:
        """Return a query whose single-row/single-column result is the
        CREATE TRIGGER statement (or closest native equivalent). Some
        dialects (e.g. MySQL's SHOW CREATE TRIGGER) don't need `table_name`;
        others accept it for convenience."""
        raise NotImplementedError

    def get_object_dependencies(self, obj: SQLObject) -> list[str]:
        """
        Get a list of object names that this object depends on.

        Override in subclasses if the dialect supports dependency tracking.
        Default: empty list.
        """
        return []

    def is_system_object(self, obj: SQLObject) -> bool:
        """
        Determine if an object is a system/internal object that should be skipped.

        Override in subclasses to define system object patterns.
        Default: False.
        """
        return False
