"""Dialect plugin registry: name -> Dialect instance (architecture.md §15)."""

from __future__ import annotations

from dialects.base import Dialect
from dialects.mysql import MySQLDialect
from dialects.oracle import OracleDialect
from dialects.postgresql import PostgreSQLDialect

_DIALECTS: dict[str, Dialect] = {
    "oracle": OracleDialect(),
    "mysql": MySQLDialect(),
    "postgresql": PostgreSQLDialect(),
}


def get_dialect(name: str) -> Dialect:
    try:
        return _DIALECTS[name]
    except KeyError:
        raise ValueError(f"Unsupported dialect: {name!r} (expected one of {sorted(_DIALECTS)})")
