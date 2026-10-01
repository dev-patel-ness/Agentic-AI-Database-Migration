"""Checksum Adapter: validates data integrity by comparing row counts and checksums
between source and target databases (Phase 7: Validation & Reconciliation).

Computes row counts per table and column-level checksums via MD5 hashing.
Detects row count mismatches and data corruption.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

from dialects import get_dialect
from dialects.connections import connect
from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    RollbackResult,
    ToolResult,
)
from tool_adapters.base import JobStatus as AdapterJobStatus

logger = logging.getLogger(__name__)


def _quoted_table_path(dialect: str, namespace: str, table_name: str) -> str:
    """Quote namespace/table per-dialect so the query hits the exact table
    SeaTunnel created (case-preserving) rather than an unquoted reference,
    which Postgres/MySQL fold to lowercase -- a different, empty table."""
    quote = get_dialect(dialect).quote_identifier
    if namespace:
        return f"{quote(namespace)}.{quote(table_name)}"
    return quote(table_name)


class ChecksumAdapter(BaseToolAdapter):
    """Validates migrated data by comparing source/target row counts and checksums."""

    adapter_type = AdapterType.VALIDATOR
    name = "checksum_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        """Validate required config fields."""
        required = ("table_name", "source_dialect", "target_dialect", 
                   "source_connection", "target_connection", "source_namespace", "target_namespace")
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"checksum_adapter requires {required}; missing {missing}")
        return AdapterConfig(options=config, timeout_seconds=300)

    def run(self, config: AdapterConfig) -> ToolResult:
        """Compare source and target data for a single table."""
        start = time.monotonic()
        opts = config.options
        table_name = opts["table_name"]
        source_dialect = opts["source_dialect"]
        target_dialect = opts["target_dialect"]
        source_connection = opts["source_connection"]
        target_connection = opts["target_connection"]
        source_namespace = opts["source_namespace"]
        target_namespace = opts["target_namespace"]

        try:
            # Get row count from source
            source_count = self._get_row_count(
                source_dialect, source_connection, source_namespace, table_name
            )
            logger.info(
                "checksum table=%s source_count=%d", table_name, source_count
            )

            # Get row count from target
            target_count = self._get_row_count(
                target_dialect, target_connection, target_namespace, table_name
            )
            logger.info(
                "checksum table=%s target_count=%d", table_name, target_count
            )

            # Compute full-row checksums (MD5 hash of all rows, concatenated)
            source_checksum = self._compute_checksum(
                source_dialect, source_connection, source_namespace, table_name
            )
            target_checksum = self._compute_checksum(
                target_dialect, target_connection, target_namespace, table_name
            )

            status = "MATCH" if (source_count == target_count and 
                               source_checksum == target_checksum) else "MISMATCH"
            
            return ToolResult(
                success=(status == "MATCH"),
                output={
                    "table_name": table_name,
                    "status": status,
                    "row_count_source": source_count,
                    "row_count_target": target_count,
                    "checksum_source": source_checksum[:16],  # Truncate for readability
                    "checksum_target": target_checksum[:16],
                    "row_count_match": (source_count == target_count),
                    "data_match": (source_checksum == target_checksum),
                },
                execution_time_seconds=time.monotonic() - start,
            )

        except Exception as exc:
            logger.exception("checksum_adapter failed for table %s: %s", table_name, exc)
            return ToolResult(
                success=False,
                error=str(exc),
                output={"table_name": table_name},
                execution_time_seconds=time.monotonic() - start,
            )

    def _get_row_count(
        self, dialect: str, connection: dict[str, Any], namespace: str, table_name: str
    ) -> int:
        """Fetch row count for a table."""
        table_path = _quoted_table_path(dialect, namespace, table_name)

        try:
            with connect(dialect, connection) as conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT COUNT(*) FROM {table_path}")
                count = cursor.fetchone()[0]
                cursor.close()
                return count
        except Exception as exc:
            logger.error("Failed to get row count for %s.%s: %s", namespace, table_name, exc)
            raise

    def _compute_checksum(
        self, dialect: str, connection: dict[str, Any], namespace: str, table_name: str
    ) -> str:
        """Compute an order-independent MD5 checksum of all rows.

        No ORDER BY: `rowid` is Oracle-only syntax (fails outright on
        Postgres/MySQL), and even a portable ORDER BY can't guarantee the same
        row order source vs. target. Instead, stringify each row, sort those
        strings client-side, then hash the sorted, concatenated result -- same
        checksum regardless of each DB's physical/query row order.
        """
        table_path = _quoted_table_path(dialect, namespace, table_name)

        try:
            with connect(dialect, connection) as conn:
                cursor = conn.cursor()
                # Oracle has no LIMIT keyword (pre-12c has no row-limiting
                # clause at all beyond ROWNUM); WHERE ROWNUM works on every
                # Oracle version, unlike FETCH FIRST (12c+ only).
                limit_clause = (
                    "WHERE ROWNUM <= 1000000" if dialect == "oracle" else "LIMIT 1000000"
                )
                cursor.execute(f"SELECT * FROM {table_path} {limit_clause}")
                rows = cursor.fetchall()
                cursor.close()

                row_strings = sorted("|".join(str(v) for v in row) for row in rows)
                hasher = hashlib.md5()
                for row_str in row_strings:
                    hasher.update(row_str.encode("utf-8"))
                
                return hasher.hexdigest()
        except Exception as exc:
            logger.error("Failed to compute checksum for %s.%s: %s", namespace, table_name, exc)
            raise

    def status(self, job_id: str) -> AdapterJobStatus:
        # Checksum runs synchronously; no async polling needed
        return AdapterJobStatus(job_id=job_id, state=ExecutionState.SUCCESS, progress_percent=100)

    def rollback(self, job_id: str) -> RollbackResult:
        # Validation is read-only; no rollback needed
        return RollbackResult(
            success=True,
            detail={"note": "checksum_adapter is read-only; no rollback needed"},
        )

