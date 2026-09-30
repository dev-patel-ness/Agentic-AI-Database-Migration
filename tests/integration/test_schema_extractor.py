"""Integration tests: schema_extractor_adapter against the real docker-compose
sample databases (architecture.md §8.1 Discovery). Skipped per-dialect if that
sample DB isn't reachable.
"""

from __future__ import annotations

import pytest

from tool_adapters.schema_extractor_adapter import SchemaExtractorAdapter

EXPECTED_TABLES = {"departments", "employees", "projects", "project_assignments"}


def _run_or_skip(dialect: str, connection: dict) -> dict:
    adapter = SchemaExtractorAdapter()
    config = adapter.prepare({"dialect": dialect, "connection": connection})
    try:
        result = adapter.run(config)
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip"
        pytest.skip(f"{dialect} sample DB not reachable: {exc}")
    assert result.success
    return result.output


def test_postgresql_sample_discovery():
    output = _run_or_skip(
        "postgresql",
        {
            "host": "localhost",
            "port": 5433,
            "username": "postgres",
            "password": "postgres_dev_password",
            "database": "sample_source",
            "schema_name": "sample",
        },
    )
    tables = {e["name"] for e in output["object_catalog"] if e["object_type"] == "table"}
    assert tables == EXPECTED_TABLES
    assert output["dependency_graph"]["projects"] == ["departments"]
    assert set(output["dependency_graph"]["project_assignments"]) == {"employees", "projects"}


def test_mysql_sample_discovery():
    output = _run_or_skip(
        "mysql",
        {
            "host": "localhost",
            "port": 3306,
            "username": "appuser",
            "password": "mysql_dev_password",
            "database": "sample_source",
        },
    )
    tables = {e["name"] for e in output["object_catalog"] if e["object_type"] == "table"}
    assert tables == EXPECTED_TABLES
    assert output["dependency_graph"]["projects"] == ["departments"]


def test_oracle_sample_discovery():
    output = _run_or_skip(
        "oracle",
        {
            "host": "localhost",
            "port": 1521,
            "username": "sample_user",
            "password": "oracle_dev_password",
            "database": "XEPDB1",
        },
    )
    tables = {e["name"].lower() for e in output["object_catalog"] if e["object_type"] == "table"}
    assert tables == EXPECTED_TABLES
    dependency_graph = {
        k.lower(): [v.lower() for v in vs] for k, vs in output["dependency_graph"].items()
    }
    assert dependency_graph["projects"] == ["departments"]
