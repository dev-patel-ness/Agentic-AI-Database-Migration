"""Unit tests for the SeaTunnel adapter's job-config generation and stdout
parsing (architecture.md §5 Data Agent). Docker is never invoked directly --
`subprocess.run` is mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tool_adapters.seatunnel_adapter import SeaTunnelAdapter, _jdbc_url, _resolve_host


def _config(**overrides):
    base = {
        "job_id": "job-1",
        "table_name": "employees",
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_connection": {
            "host": "localhost",
            "port": 1521,
            "username": "sample",
            "password": "pw",
            "database": "XEPDB1",
        },
        "target_connection": {
            "host": "localhost",
            "port": 5433,
            "username": "postgres",
            "password": "pw",
            "database": "sample_target",
        },
        "source_namespace": "SAMPLE",
        "target_namespace": "public",
    }
    base.update(overrides)
    return SeaTunnelAdapter().prepare(base)


def test_prepare_requires_core_fields():
    with pytest.raises(ValueError):
        SeaTunnelAdapter().prepare({"job_id": "job-1"})


def test_resolve_host_redirects_localhost():
    assert _resolve_host("localhost") == "host.docker.internal"
    assert _resolve_host("127.0.0.1") == "host.docker.internal"
    assert _resolve_host("postgres-sample") == "postgres-sample"


def test_jdbc_url_per_dialect():
    assert (
        _jdbc_url("postgresql", {"host": "localhost", "port": 5433, "database": "db"})
        == "jdbc:postgresql://host.docker.internal:5433/db"
    )
    assert _jdbc_url("mysql", {"host": "localhost", "port": 3306, "database": "db"}).startswith(
        "jdbc:mysql://host.docker.internal:3306/db"
    )
    assert (
        _jdbc_url("oracle", {"host": "localhost", "port": 1521, "database": "XEPDB1"})
        == "jdbc:oracle:thin:@//host.docker.internal:1521/XEPDB1"
    )


def test_run_parses_row_counts_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr("tool_adapters.seatunnel_adapter.JOBS_DIR", str(tmp_path))
    fake_proc = MagicMock(
        returncode=0,
        stdout="Total Read Count          :                100\nTotal Write Count         :                100\n",
        stderr="",
    )
    with patch("tool_adapters.seatunnel_adapter.subprocess.run", return_value=fake_proc):
        result = SeaTunnelAdapter().run(_config())

    assert result.success is True
    assert result.output["rows_read"] == 100
    assert result.output["rows_written"] == 100


def test_run_reports_failure_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr("tool_adapters.seatunnel_adapter.JOBS_DIR", str(tmp_path))
    fake_proc = MagicMock(returncode=1, stdout="", stderr="job failed: driver not found")
    with patch("tool_adapters.seatunnel_adapter.subprocess.run", return_value=fake_proc):
        result = SeaTunnelAdapter().run(_config())

    assert result.success is False
    assert "driver not found" in result.error
