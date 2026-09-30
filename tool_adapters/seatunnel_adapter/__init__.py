"""Apache SeaTunnel (Zeta) adapter: bulk historical load + streaming CDC (Data Agent).

Runs the Zeta engine's *local* execution mode (no persistent cluster/REST
needed) inside a long-lived `seatunnel` Docker container (see
`infra/docker/seatunnel/` + the `seatunnel` service in docker-compose.yml),
one job per table: `docker exec seatunnel ./bin/seatunnel.sh -m local -c
/jobs/<file>.conf`. The JDBC sink's `schema_save_mode=CREATE_SCHEMA_WHEN_NOT_EXIST`
auto-creates the target table from the source's discovered schema -- this is
"whatever SeaTunnel can do" per architecture.md's Schema Agent scope note;
non-table objects (views/procedures/functions/triggers/foreign_keys) are
translated by CrackSQL instead (agents/schema_agent).

Phase 5 scope: bulk (batch) load only, no streaming CDC yet.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from typing import Any

from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    RollbackResult,
    ToolResult,
)
from tool_adapters.base import JobStatus as AdapterJobStatus

# Host-side directory bind-mounted into the seatunnel container at /jobs
# (docker-compose.yml: `./tool_adapters/seatunnel_adapter/jobs:/jobs`).
JOBS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jobs")
CONTAINER_NAME = os.getenv("SEATUNNEL_CONTAINER", "seatunnel")

# jdbc driver class + url template per dialect. Driver jars are baked into
# the seatunnel image (infra/docker/seatunnel/Dockerfile).
_JDBC_DRIVERS = {
    "postgresql": "org.postgresql.Driver",
    "mysql": "com.mysql.cj.jdbc.Driver",
    "oracle": "oracle.jdbc.OracleDriver",
}

_READ_COUNT_RE = re.compile(r"Total Read Count\s*:\s*(\d+)")
_WRITE_COUNT_RE = re.compile(r"Total Write Count\s*:\s*(\d+)")

_SANITIZE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def _sanitize(value: str) -> str:
    return _SANITIZE_RE.sub("_", value)


def _resolve_host(host: str) -> str:
    """Job configs run *inside* the seatunnel container, not on this host --
    "localhost"/"127.0.0.1" there means the container itself. Our local dev
    sample DBs publish ports to the Docker host, so redirect to Docker's
    well-known host-gateway alias instead (works on Docker Desktop out of the
    box; docker-compose.yml adds `extra_hosts: host.docker.internal:host-gateway`
    for Linux Docker engines too)."""
    if host in ("localhost", "127.0.0.1", ""):
        return "host.docker.internal"
    return host


def _jdbc_url(dialect_name: str, connection_config: dict[str, Any]) -> str:
    host = _resolve_host(connection_config.get("host", "localhost"))
    port = connection_config.get("port")
    database = connection_config.get("database", "")
    if dialect_name == "postgresql":
        return f"jdbc:postgresql://{host}:{port or 5432}/{database}"
    if dialect_name == "mysql":
        return f"jdbc:mysql://{host}:{port or 3306}/{database}?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
    if dialect_name == "oracle":
        return f"jdbc:oracle:thin:@//{host}:{port or 1521}/{database}"
    raise ValueError(f"Unsupported dialect: {dialect_name!r}")


def _table_path(namespace: str, table_name: str) -> str:
    """`schema.table` (Postgres/Oracle) or `database.table` (MySQL) -- the
    format SeaTunnel's Jdbc connector expects for `table_path`/`table`."""
    return f"{namespace}.{table_name}"


class SeaTunnelAdapter(BaseToolAdapter):
    """Generates + runs a single-table SeaTunnel Zeta batch job (JDBC -> JDBC)."""

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.DATA_MIGRATOR

    @property
    def name(self) -> str:
        return "seatunnel_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        required = (
            "job_id",
            "table_name",
            "source_dialect",
            "target_dialect",
            "source_connection",
            "target_connection",
            "source_namespace",
            "target_namespace",
        )
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"seatunnel_adapter requires {required}; missing {missing}")
        return AdapterConfig(options=config, timeout_seconds=config.get("timeout_seconds", 600))

    def _build_job_conf(self, opts: dict[str, Any]) -> str:
        source_dialect = opts["source_dialect"]
        target_dialect = opts["target_dialect"]
        source_connection = opts["source_connection"]
        target_connection = opts["target_connection"]
        table_name = opts["table_name"]
        source_table_path = _table_path(opts["source_namespace"], table_name)
        target_table_path = _table_path(opts["target_namespace"], table_name)

        return f"""
env {{
  parallelism = 1
  job.mode = "BATCH"
}}

source {{
  Jdbc {{
    url = "{_jdbc_url(source_dialect, source_connection)}"
    driver = "{_JDBC_DRIVERS[source_dialect]}"
    username = "{source_connection.get("username", "")}"
    user = "{source_connection.get("username", "")}"
    password = "{source_connection.get("password", "")}"
    query = "SELECT * FROM {source_table_path}"
    result_table_name = "src"
  }}
}}

sink {{
  Jdbc {{
    url = "{_jdbc_url(target_dialect, target_connection)}"
    driver = "{_JDBC_DRIVERS[target_dialect]}"
    username = "{target_connection.get("username", "")}"
    user = "{target_connection.get("username", "")}"
    password = "{target_connection.get("password", "")}"
    generate_sink_sql = true
    database = "{target_connection.get("database", "")}"
    table = "{target_table_path}"
    schema_save_mode = "CREATE_SCHEMA_WHEN_NOT_EXIST"
    data_save_mode = "APPEND_DATA"
    source_table_name = "src"
  }}
}}
""".strip()

    def run(self, config: AdapterConfig) -> ToolResult:
        start = time.monotonic()
        opts = config.options
        job_id = opts["job_id"]
        table_name = opts["table_name"]

        os.makedirs(JOBS_DIR, exist_ok=True)
        filename = f"{_sanitize(job_id)}__{_sanitize(table_name)}.conf"
        host_path = os.path.join(JOBS_DIR, filename)
        try:
            with open(host_path, "w", encoding="utf-8") as f:
                f.write(self._build_job_conf(opts))

            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    CONTAINER_NAME,
                    "./bin/seatunnel.sh",
                    "-m",
                    "local",
                    "-c",
                    f"/jobs/{filename}",
                ],
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                error=f"failed to invoke seatunnel container: {exc}",
                execution_time_seconds=time.monotonic() - start,
            )
        finally:
            try:
                os.remove(host_path)
            except OSError:
                pass

        stdout = proc.stdout or ""
        if proc.returncode != 0:
            return ToolResult(
                success=False,
                error=(proc.stderr or stdout)[-4000:],
                output={"table_name": table_name, "returncode": proc.returncode},
                execution_time_seconds=time.monotonic() - start,
            )

        read_match = _READ_COUNT_RE.search(stdout)
        write_match = _WRITE_COUNT_RE.search(stdout)
        rows_read = int(read_match.group(1)) if read_match else None
        rows_written = int(write_match.group(1)) if write_match else None

        return ToolResult(
            success=True,
            output={
                "table_name": table_name,
                "rows_read": rows_read,
                "rows_written": rows_written,
            },
            execution_time_seconds=time.monotonic() - start,
        )

    def status(self, job_id: str) -> AdapterJobStatus:
        # Local-mode jobs run synchronously within run(); nothing to poll.
        return AdapterJobStatus(job_id=job_id, state=ExecutionState.SUCCESS, progress_percent=100)

    def rollback(self, job_id: str) -> RollbackResult:
        # Bulk load has no built-in undo (target rows already committed);
        # a real rollback would need a TRUNCATE issued by the caller with
        # explicit confirmation -- out of scope for Phase 5.
        return RollbackResult(
            success=False,
            detail={"note": "seatunnel_adapter does not support automatic rollback of loaded data"},
        )
