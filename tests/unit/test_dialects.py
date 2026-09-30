"""Unit tests for dialect plugins (architecture.md §4/§15): pure SQL-string
generation and identifier validation, no live DB required.
"""

from __future__ import annotations

import pytest

from dialects import get_dialect
from dialects.base import validate_identifier
from dialects.mysql import MySQLDialect
from dialects.oracle import OracleDialect
from dialects.postgresql import PostgreSQLDialect


def test_get_dialect_returns_expected_instances():
    assert isinstance(get_dialect("oracle"), OracleDialect)
    assert isinstance(get_dialect("mysql"), MySQLDialect)
    assert isinstance(get_dialect("postgresql"), PostgreSQLDialect)


def test_get_dialect_rejects_unknown_name():
    with pytest.raises(ValueError):
        get_dialect("sqlserver")


@pytest.mark.parametrize("identifier", ["employees", "_private", "Table1", "T$1", "T#1"])
def test_validate_identifier_accepts_safe_names(identifier: str):
    assert validate_identifier(identifier) == identifier


@pytest.mark.parametrize(
    "identifier", ["", "1table", "table;drop table x", "table name", "table--", "table'"]
)
def test_validate_identifier_rejects_unsafe_names(identifier: str):
    with pytest.raises(ValueError):
        validate_identifier(identifier)


def test_postgresql_quote_identifier_and_queries():
    dialect = PostgreSQLDialect()
    assert dialect.quote_identifier('a"b') == '"a""b"'
    assert "information_schema.tables" in dialect.get_tables_query("sample")
    assert "table_schema = 'sample'" in dialect.get_tables_query("sample")
    with pytest.raises(ValueError):
        dialect.get_tables_query("bad schema;drop")


def test_mysql_quote_identifier_and_queries():
    dialect = MySQLDialect()
    assert dialect.quote_identifier("a`b") == "`a``b`"
    query = dialect.get_columns_query("employees", "sample_source")
    assert "table_name = 'employees'" in query
    assert "table_schema = 'sample_source'" in query


def test_oracle_quote_identifier_uppercases():
    dialect = OracleDialect()
    assert dialect.quote_identifier("employees") == '"EMPLOYEES"'
    query = dialect.get_tables_query("sample_user")
    assert "owner = 'SAMPLE_USER'" in query


def test_oracle_get_table_definition_uses_dbms_metadata():
    dialect = OracleDialect()
    query = dialect.get_table_definition("employees", "sample_user")
    assert "DBMS_METADATA.GET_DDL" in query
    assert "'EMPLOYEES'" in query
    assert "'SAMPLE_USER'" in query
