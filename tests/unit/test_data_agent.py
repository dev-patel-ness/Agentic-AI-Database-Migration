"""Unit tests for the Data Agent (architecture.md §5 Data Agent, §8.3).
The SeaTunnel adapter, metadata DB connection, and the Schema Agent's
DDL-apply step are mocked -- these tests exercise per-table dispatch and row
aggregation only.
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from agents.data_agent import _topological_sort_tables, migrate_data
from orchestrator.state import DiscoveryResult
from tool_adapters.base import AdapterConfig, ToolResult


def _discovery_with(catalog: list[dict]) -> DiscoveryResult:
    return DiscoveryResult(object_catalog=catalog, dependency_graph={})


@contextmanager
def _fake_metadata_connection():
    yield MagicMock()


def test_migrate_data_success_sums_rows_and_applies_ddl():
    discovery = _discovery_with(
        [
            {"object_type": "table", "name": "t1", "schema": "public"},
            {"object_type": "table", "name": "t2", "schema": "public"},
        ]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.side_effect = [
        ToolResult(success=True, output={"table_name": "t1", "rows_read": 10, "rows_written": 10}),
        ToolResult(success=True, output={"table_name": "t2", "rows_read": 5, "rows_written": 5}),
    ]

    with patch("agents.data_agent.SeaTunnelAdapter", return_value=fake_adapter), patch(
        "agents.data_agent.metadata_connection", _fake_metadata_connection
    ), patch(
        "agents.data_agent.apply_schema_translations",
        return_value=[{"object_type": "view", "object_name": "v1", "status": "APPLIED"}],
    ) as fake_apply:
        result = migrate_data(
            "job-1",
            discovery,
            "oracle",
            "postgresql",
            {"host": "localhost"},
            {"host": "localhost", "database": "sample_target"},
        )

    assert result.rows_moved == 15
    assert len(result.tables) == 2
    assert all(t["status"] == "SUCCESS" for t in result.tables)
    assert result.ddl_applications[0]["status"] == "APPLIED"
    fake_apply.assert_called_once()


def test_migrate_data_one_table_error_does_not_block_others():
    discovery = _discovery_with(
        [
            {"object_type": "table", "name": "t1", "schema": "public"},
            {"object_type": "table", "name": "t2", "schema": "public"},
        ]
    )
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.side_effect = [
        ToolResult(success=False, error="boom"),
        ToolResult(success=True, output={"table_name": "t2", "rows_read": 3, "rows_written": 3}),
    ]

    with patch("agents.data_agent.SeaTunnelAdapter", return_value=fake_adapter), patch(
        "agents.data_agent.metadata_connection", _fake_metadata_connection
    ), patch("agents.data_agent.apply_schema_translations", return_value=[]):
        result = migrate_data(
            "job-1",
            discovery,
            "oracle",
            "postgresql",
            {"host": "localhost"},
            {"host": "localhost", "database": "sample_target"},
        )

    assert result.rows_moved == 3
    assert result.tables[0]["status"] == "ERROR"
    assert result.tables[1]["status"] == "SUCCESS"


def test_migrate_data_skips_non_table_objects():
    discovery = _discovery_with([{"object_type": "view", "name": "v1", "schema": "public"}])
    fake_adapter = MagicMock()

    with patch("agents.data_agent.SeaTunnelAdapter", return_value=fake_adapter), patch(
        "agents.data_agent.metadata_connection", _fake_metadata_connection
    ), patch("agents.data_agent.apply_schema_translations", return_value=[]):
        result = migrate_data(
            "job-1",
            discovery,
            "oracle",
            "postgresql",
            {"host": "localhost"},
            {"host": "localhost", "database": "sample_target"},
        )

    fake_adapter.prepare.assert_not_called()
    assert result.tables == []


def test_migrate_data_loads_parent_tables_before_dependents():
    """DEPARTMENTS/EMPLOYEES/PROJECTS listed child-before-parent in the
    catalog; dependency_graph says PROJECTS -> DEPARTMENTS and
    PROJECT_ASSIGNMENTS -> {EMPLOYEES, PROJECTS} -- parents must load first."""
    discovery = _discovery_with(
        [
            {"object_type": "table", "name": "PROJECT_ASSIGNMENTS", "schema": "public"},
            {"object_type": "table", "name": "PROJECTS", "schema": "public"},
            {"object_type": "table", "name": "EMPLOYEES", "schema": "public"},
            {"object_type": "table", "name": "DEPARTMENTS", "schema": "public"},
        ]
    )
    discovery.dependency_graph = {
        "PROJECT_ASSIGNMENTS": ["EMPLOYEES", "PROJECTS"],
        "PROJECTS": ["DEPARTMENTS"],
        "EMPLOYEES": ["DEPARTMENTS"],
        "DEPARTMENTS": [],
    }
    fake_adapter = MagicMock()
    fake_adapter.prepare.return_value = AdapterConfig(options={})
    fake_adapter.run.return_value = ToolResult(success=True, output={"rows_read": 1, "rows_written": 1})

    with patch("agents.data_agent.SeaTunnelAdapter", return_value=fake_adapter), patch(
        "agents.data_agent.metadata_connection", _fake_metadata_connection
    ), patch("agents.data_agent.apply_schema_translations", return_value=[]):
        result = migrate_data(
            "job-1",
            discovery,
            "oracle",
            "postgresql",
            {"host": "localhost"},
            {"host": "localhost", "database": "sample_target"},
        )

    order = [t["table_name"] for t in result.tables]
    assert order.index("DEPARTMENTS") < order.index("PROJECTS")
    assert order.index("DEPARTMENTS") < order.index("EMPLOYEES")
    assert order.index("PROJECTS") < order.index("PROJECT_ASSIGNMENTS")
    assert order.index("EMPLOYEES") < order.index("PROJECT_ASSIGNMENTS")


def test_topological_sort_tables_falls_back_to_catalog_order_on_cycle():
    """Mutually-referencing FKs (DEPARTMENTS.manager_id -> EMPLOYEES while
    EMPLOYEES.department_id -> DEPARTMENTS) must not hang or crash -- fall
    back to original catalog order for the cyclic tables."""
    tables = [
        {"object_type": "table", "name": "DEPARTMENTS"},
        {"object_type": "table", "name": "EMPLOYEES"},
    ]
    dependency_graph = {"DEPARTMENTS": ["EMPLOYEES"], "EMPLOYEES": ["DEPARTMENTS"]}

    ordered = _topological_sort_tables(tables, dependency_graph, "job-1")

    assert [t["name"] for t in ordered] == ["DEPARTMENTS", "EMPLOYEES"]


def test_topological_sort_tables_ignores_self_reference():
    tables = [{"object_type": "table", "name": "EMPLOYEES"}]
    dependency_graph = {"EMPLOYEES": ["EMPLOYEES"]}

    ordered = _topological_sort_tables(tables, dependency_graph, "job-1")

    assert [t["name"] for t in ordered] == ["EMPLOYEES"]
