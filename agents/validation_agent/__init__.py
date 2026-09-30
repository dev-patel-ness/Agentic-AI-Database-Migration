"""Validation Agent: row counts, checksums, referential integrity, aggregate comparisons (Phase 7).

Orchestrates data validation: runs checksum adapter on all tables, compiles results
into a ValidationReport, and identifies mismatches for human review.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from orchestrator.state import ChecksumResult, ValidationReport, DiscoveryResult
from tool_adapters.checksum_adapter import ChecksumAdapter

logger = logging.getLogger(__name__)


def validate_data(
    job_id: str,
    discovery: DiscoveryResult,
    source_dialect: str,
    target_dialect: str,
    source_connection: dict[str, Any],
    target_connection: dict[str, Any],
    source_namespace: str,
    target_namespace: str,
) -> ValidationReport:
    """Validate all tables via checksum comparison; return overall ValidationReport.
    
    Args:
        job_id: Migration job ID (for logging)
        discovery: Catalog of discovered objects
        source_dialect: Source database type
        target_dialect: Target database type
        source_connection: Source connection config
        target_connection: Target connection config
        source_namespace: Source schema/namespace
        target_namespace: Target schema/namespace
    
    Returns:
        ValidationReport with per-table checksum results and mismatch count
    """
    adapter = ChecksumAdapter()
    table_checksums: list[ChecksumResult] = []
    mismatches = 0

    # Extract table list from discovery
    tables = [
        entry for entry in discovery.object_catalog 
        if entry["object_type"] == "table"
    ]
    
    logger.info("[job=%s] Starting data validation for %d tables", job_id, len(tables))

    for entry in tables:
        table_name = entry["name"]
        try:
            config = adapter.prepare(
                {
                    "table_name": table_name,
                    "source_dialect": source_dialect,
                    "target_dialect": target_dialect,
                    "source_connection": source_connection,
                    "target_connection": target_connection,
                    "source_namespace": source_namespace,
                    "target_namespace": target_namespace,
                }
            )
            result = adapter.run(config)

            if result.success:
                output = result.output or {}
                checksum_result = ChecksumResult(
                    table_name=table_name,
                    status="MATCH",
                    checksum_source=output.get("checksum_source"),
                    checksum_target=output.get("checksum_target"),
                )
                logger.info(
                    "[job=%s] Table %s: MATCH (rows %d vs %d)",
                    job_id,
                    table_name,
                    output.get("row_count_source", 0),
                    output.get("row_count_target", 0),
                )
            else:
                # Mismatch detected
                output = result.output or {}
                checksum_result = ChecksumResult(
                    table_name=table_name,
                    status="MISMATCH",
                    checksum_source=output.get("checksum_source"),
                    checksum_target=output.get("checksum_target"),
                )
                mismatches += 1
                logger.warning(
                    "[job=%s] Table %s: MISMATCH (source rows %d, target rows %d, error: %s)",
                    job_id,
                    table_name,
                    output.get("row_count_source", "?"),
                    output.get("row_count_target", "?"),
                    result.error or "checksum mismatch",
                )
        except Exception:
            logger.exception(
                "[job=%s] Validation failed for table %s",
                job_id,
                table_name,
            )
            checksum_result = ChecksumResult(
                table_name=table_name,
                status="ERROR",
            )
            mismatches += 1

        table_checksums.append(checksum_result)

    # Determine overall status
    overall_status = "PASS" if mismatches == 0 else "FAIL"
    
    report = ValidationReport(
        table_checksums=table_checksums,
        mismatches=mismatches,
        overall_status=overall_status,
    )
    
    logger.info(
        "[job=%s] Validation complete: %d tables, %d mismatches, status=%s",
        job_id,
        len(tables),
        mismatches,
        overall_status,
    )
    
    return report

