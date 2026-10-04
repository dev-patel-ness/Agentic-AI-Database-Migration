"""Test phase: generates & executes structured migration test cases (Phase 7).

Runs four checks against the target database and compiles them into a
TestReport: schema/SQL compatibility and missing-objects (derived from the
Validation Agent's object_validations), referential integrity (orphan-row
queries per foreign key), and a performance smoke check (timed COUNT(*) per
table). Any non-PASS check fails the overall report, routing the graph back
to Validate per architecture.md §6.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from dialects import get_dialect
from dialects.connections import connect
from orchestrator.state import DiscoveryResult, TestReport, ValidationReport

logger = logging.getLogger(__name__)

PERFORMANCE_THRESHOLD_SECONDS = 5.0


def _quoted_table_path(dialect: str, namespace: str, table_name: str) -> str:
    quote = get_dialect(dialect).quote_identifier
    return f"{quote(namespace)}.{quote(table_name)}" if namespace else quote(table_name)


def _check_schema_compatibility(validation: ValidationReport) -> dict[str, Any]:
    object_validations = validation.object_validations if validation else []
    present = sum(1 for ov in object_validations if ov.status == "PRESENT")
    total = len(object_validations)
    status = (
        "PASS"
        if all(ov.status in ("PRESENT", "PENDING_MANUAL_REVIEW") for ov in object_validations)
        else "FAIL"
    )
    return {
        "check": "schema_compatibility",
        "status": status,
        "detail": f"{present}/{total} translated objects present on target",
    }


def _check_missing_objects(validation: ValidationReport) -> dict[str, Any]:
    object_validations = validation.object_validations if validation else []
    missing = [ov for ov in object_validations if ov.status in ("MISSING", "APPLY_FAILED", "ERROR")]
    status = "PASS" if not missing else "FAIL"
    detail = (
        "No missing objects detected"
        if not missing
        else f"{len(missing)} missing/failed: "
        + ", ".join(f"{ov.object_type}:{ov.object_name}" for ov in missing)
    )
    return {"check": "missing_objects", "status": status, "detail": detail}


def _check_referential_integrity(
    job_id: str, target_dialect: str, target_connection: dict[str, Any], target_namespace: str
) -> dict[str, Any]:
    dialect = get_dialect(target_dialect)
    orphan_findings: list[str] = []
    try:
        with connect(target_dialect, target_connection) as conn:
            cursor = conn.cursor()
            cursor.execute(dialect.get_foreign_keys_query(target_namespace))
            fk_rows = cursor.fetchall()
            cursor.close()

            for constraint_name, table_name, column_name, ref_table_name, ref_column_name in fk_rows:
                child_path = _quoted_table_path(target_dialect, target_namespace, table_name)
                parent_path = _quoted_table_path(target_dialect, target_namespace, ref_table_name)
                q = dialect.quote_identifier
                query = (
                    f"SELECT COUNT(*) FROM {child_path} c WHERE c.{q(column_name)} IS NOT NULL "
                    f"AND NOT EXISTS (SELECT 1 FROM {parent_path} p WHERE p.{q(ref_column_name)} = c.{q(column_name)})"
                )
                check_cursor = conn.cursor()
                try:
                    check_cursor.execute(query)
                    orphan_count = check_cursor.fetchone()[0]
                finally:
                    check_cursor.close()
                if orphan_count:
                    orphan_findings.append(
                        f"{constraint_name} ({table_name}.{column_name} -> "
                        f"{ref_table_name}.{ref_column_name}): {orphan_count} orphan rows"
                    )
    except Exception as exc:
        logger.exception("[job=%s] Referential integrity check failed: %s", job_id, exc)
        return {"check": "referential_integrity", "status": "ERROR", "detail": str(exc)}

    status = "PASS" if not orphan_findings else "FAIL"
    detail = "All foreign keys reference valid rows" if not orphan_findings else "; ".join(orphan_findings)
    return {"check": "referential_integrity", "status": status, "detail": detail}


def _check_performance_smoke(
    job_id: str,
    discovery: DiscoveryResult,
    target_dialect: str,
    target_connection: dict[str, Any],
    target_namespace: str,
) -> dict[str, Any]:
    tables = [e["name"] for e in discovery.object_catalog if e["object_type"] == "table"]
    slow_tables: list[str] = []
    try:
        with connect(target_dialect, target_connection) as conn:
            for table_name in tables:
                table_path = _quoted_table_path(target_dialect, target_namespace, table_name)
                cursor = conn.cursor()
                start = time.monotonic()
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_path}")
                    cursor.fetchone()
                finally:
                    cursor.close()
                elapsed = time.monotonic() - start
                if elapsed > PERFORMANCE_THRESHOLD_SECONDS:
                    slow_tables.append(f"{table_name} ({elapsed:.2f}s)")
    except Exception as exc:
        logger.exception("[job=%s] Performance smoke check failed: %s", job_id, exc)
        return {"check": "performance_smoke", "status": "ERROR", "detail": str(exc)}

    status = "PASS" if not slow_tables else "FAIL"
    detail = (
        f"All {len(tables)} table(s) respond within {PERFORMANCE_THRESHOLD_SECONDS:.0f}s"
        if not slow_tables
        else f"Slow tables (> {PERFORMANCE_THRESHOLD_SECONDS:.0f}s): " + ", ".join(slow_tables)
    )
    return {"check": "performance_smoke", "status": status, "detail": detail}


def run_tests(
    job_id: str,
    discovery: DiscoveryResult,
    validation: ValidationReport,
    target_dialect: str,
    target_connection: dict[str, Any],
    target_namespace: str,
) -> TestReport:
    """Generate & execute migration test cases, returning a structured TestReport."""
    details: list[dict[str, Any]] = [
        _check_schema_compatibility(validation),
        _check_missing_objects(validation),
        _check_referential_integrity(job_id, target_dialect, target_connection, target_namespace),
        _check_performance_smoke(job_id, discovery, target_dialect, target_connection, target_namespace),
    ]
    overall_status = "PASS" if all(d["status"] == "PASS" for d in details) else "FAIL"
    logger.info(
        "[job=%s] Test phase complete: %s (%s)",
        job_id,
        overall_status,
        ", ".join(f"{d['check']}={d['status']}" for d in details),
    )
    return TestReport(overall_status=overall_status, details=details)
