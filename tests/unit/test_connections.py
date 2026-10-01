"""Unit tests for dialects.connections.connect's Postgres search_path handling."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dialects.connections import connect


def test_connect_postgresql_sets_search_path_when_schema_name_given():
    fake_cursor = MagicMock()
    fake_cursor.__enter__.return_value = fake_cursor
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cursor
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn

    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        conn = connect("postgresql", {"host": "localhost", "schema_name": "sample"})

    assert conn is fake_conn
    fake_cursor.execute.assert_called_once_with('SET search_path TO "sample", public')
    fake_conn.commit.assert_called_once()


def test_connect_postgresql_skips_search_path_when_no_schema_name():
    fake_conn = MagicMock()
    fake_psycopg2 = MagicMock()
    fake_psycopg2.connect.return_value = fake_conn

    with patch.dict("sys.modules", {"psycopg2": fake_psycopg2}):
        conn = connect("postgresql", {"host": "localhost"})

    assert conn is fake_conn
    fake_conn.cursor.assert_not_called()
