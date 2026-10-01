"""Validation Agent: row counts, checksums, referential integrity, aggregate comparisons (Phase 7).

Orchestrates data validation: runs checksum adapter on all tables, checks that
every non-table object (view/procedure/function/trigger/foreign_key) the
Schema Agent translated actually exists on the target, and compiles both into
a ValidationReport with mismatches flagged for human review.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from dialects import get_dialect
from dialects.connections import connect as _connect
from agents.schema_agent.metadata_store import fetch_applied_statuses, metadata_connection
from orchestrator.state import ChecksumResult, DiscoveryResult, ObjectValidationResult, ValidationReport
from tool_adapters.checksum_adapter import ChecksumAdapter

logger = logging.getLogger(__name__)

# object_type -> dialect query method name returning (schema, name[, ...]) rows
_EXISTENCE_QUERIES = {
    "view": "get_views_query",
    "procedure": "get_procedures_query",
    "function": "get_functions_query",
    "trigger": "get_triggers_query",
}


def _fetch_existing_names(dialect_name: str, connection: dict[str, Any], namespace: str) -> dict[str, set[str]]:
    """Fetch the set of existing object names per type from the target, case-insensitive."""
    dialect = get_dialect(dialect_name)
    existing: dict[str, set[str]] = {object_type: set() for object_type in _EXISTENCE_QUERIES}
    existing["foreign_key"] = set()

    with _connect(dialect_name, connection) as conn:
        for object_type, query_method in _EXISTENCE_QUERIES.items():
            cursor = conn.cursor()
            cursor.execute(getattr(dialect, query_method)(namespace))
            existing[object_type] = {row[1].lower() for row in cursor.fetchall()}
            cursor.close()

        cursor = conn.cursor()
        cursor.execute(dialect.get_foreign_keys_query(namespace))
        existing["foreign_key"] = {row[0].lower() for row in cursor.fetchall()}
        cursor.close()

    return existing


def _validate_schema_objects(
    job_id: str,
    discovery: DiscoveryResult,
    target_dialect: str,
    target_connection: dict[str, Any],
    target_namespace: str,
) -> list[ObjectValidationResult]:
    """Check that every discovered view/procedure/function/trigger/foreign_key exists on the target.

    Objects the Schema Agent deliberately skipped (flagged into
    `manual_review_objects`, applied_status=PENDING_MANUAL_REVIEW) are reported as
    such rather than as a hard MISSING failure -- they were never supposed to be on
    the target yet. Objects whose DDL application itself failed are reported as
    APPLY_FAILED with the underlying error. Only objects that were actually applied
    (or never flagged either way) but still aren't found on the target are real
    MISSING failures.
    """
    objects = [
        entry for entry in discovery.object_catalog if entry["object_type"] in _EXISTENCE_QUERIES or entry["object_type"] == "foreign_key"
    ]
    if not objects:
        return []

    try:
        existing = _fetch_existing_names(target_dialect, target_connection, target_namespace)
    except Exception:
        logger.exception("[job=%s] Failed to fetch target object catalog for validation", job_id)
        return [
            ObjectValidationResult(object_type=entry["object_type"], object_name=entry["name"], status="ERROR")
            for entry in objects
        ]

    try:
        with metadata_connection() as conn:
            applied_statuses = fetch_applied_statuses(conn, job_id)
    except Exception:
        logger.exception("[job=%s] Failed to fetch applied-translation statuses for validation", job_id)
        applied_statuses = {}

    results: list[ObjectValidationResult] = []
    for entry in objects:
        object_type = entry["object_type"]
        object_name = entry["name"]
        present = object_name.lower() in existing.get(object_type, set())
        if present:
            results.append(ObjectValidationResult(object_type=object_type, object_name=object_name, status="PRESENT"))
            continue

        applied = applied_statuses.get((object_type, object_name))
        applied_status = applied.get("applied_status") if applied else None
        if applied_status == "PENDING_MANUAL_REVIEW":
            logger.info("[job=%s] %s %s: pending manual review, not yet on target (expected)", job_id, object_type, object_name)
            results.append(
                ObjectValidationResult(
                    object_type=object_type,
                    object_name=object_name,
                    status="PENDING_MANUAL_REVIEW",
                    detail="Flagged for manual review (low-confidence translation); not applied to target yet.",
                )
            )
        elif applied_status == "APPLY_FAILED":
            logger.warning("[job=%s] %s %s: DDL application failed", job_id, object_type, object_name)
            results.append(
                ObjectValidationResult(
                    object_type=object_type,
                    object_name=object_name,
                    status="APPLY_FAILED",
                    detail=(applied or {}).get("applied_error"),
                )
            )
        else:
            logger.warning("[job=%s] %s %s: MISSING on target", job_id, object_type, object_name)
            results.append(ObjectValidationResult(object_type=object_type, object_name=object_name, status="MISSING"))
    return results


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
    """Validate all tables via checksum comparison and all other objects via existence
    check on the target; return a combined ValidationReport.
    
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
        ValidationReport with per-table checksum results, per-object existence
        results, and a combined mismatch count
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

    # Check that every non-table object (view/procedure/function/trigger/foreign_key)
    # the Schema Agent translated actually exists on the target.
    object_validations = _validate_schema_objects(
        job_id, discovery, target_dialect, target_connection, target_namespace
    )
    # PENDING_MANUAL_REVIEW is an expected, deliberate skip (not yet applied) --
    # it isn't a validation failure, just a pending human action.
    mismatches += sum(
        1 for ov in object_validations if ov.status not in ("PRESENT", "PENDING_MANUAL_REVIEW")
    )

    # Determine overall status
    overall_status = "PASS" if mismatches == 0 else "FAIL"
    
    report = ValidationReport(
        table_checksums=table_checksums,
        object_validations=object_validations,
        mismatches=mismatches,
        overall_status=overall_status,
    )
    
    logger.info(
        "[job=%s] Validation complete: %d tables, %d other objects, %d mismatches, status=%s",
        job_id,
        len(tables),
        len(object_validations),
        mismatches,
        overall_status,
    )
    
    return report

