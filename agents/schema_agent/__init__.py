"""Schema Agent: DDL/procedure/function/trigger translation source->target dialect.

Per architecture.md §8.2: retrieves discovered object DDL from the catalog,
invokes the CrackSQL adapter (hybrid AST + Bedrock LLM translation with
confidence scores) per object, and persists `TRANSLATION_RESULT` rows.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from agents.schema_agent.metadata_store import (
    fetch_applicable_translations,
    mark_translation_applied,
    metadata_connection,
    save_translation_result,
)
from dialects.connections import connect as _connect
from orchestrator.state import DiscoveryResult, TranslationResult
from tool_adapters.cracksql_adapter import CrackSQLAdapter

logger = logging.getLogger(__name__)

# Oracle DDL carries cosmetic keywords (EDITIONABLE/NONEDITIONABLE on
# views/functions/procedures/triggers, FORCE on views) that are invalid
# syntax on every other dialect. CrackSQL sometimes judges a simple object
# "already compatible" and passes it through unchanged (high confidence, no
# LLM call) without stripping these -- strip them ourselves rather than
# relying on CrackSQL for syntax noise that isn't a real translation problem.
_ORACLE_NOISE_KEYWORDS_RE = re.compile(r"\b(EDITIONABLE|NONEDITIONABLE|FORCE)\b\s*", re.IGNORECASE)


def _sanitize_target_ddl(ddl: str, target_dialect: str) -> str:
    """Strip Oracle-only cosmetic DDL keywords when they leak through to a
    non-Oracle target; a no-op for everything else."""
    if target_dialect == "oracle" or not ddl:
        return ddl
    cleaned = _ORACLE_NOISE_KEYWORDS_RE.sub("", ddl)
    return re.sub(r"[ \t]+", " ", cleaned)

# Views/procedures/triggers/FKs aren't linked by the (table-only) dependency
# graph, so apply in this fixed, generally-safe order rather than an inferred
# one: routines first (least likely to depend on other translated objects),
# then views, then triggers (need their owning table, already created by the
# Data Agent by the time this runs), then foreign keys last (need every
# referenced table to already exist and be loaded).
_APPLY_ORDER = {"procedure": 0, "function": 0, "view": 1, "trigger": 2, "foreign_key": 3}

# Objects at/below this confidence get flagged for a manual-review pass
# (plan.md Phase 4: "below-threshold objects get flagged into
# manual_review_objects for a later human pass").
LOW_CONFIDENCE_THRESHOLD = 0.7


def translate_schema(
    job_id: str,
    discovery: DiscoveryResult,
    source_dialect: str,
    target_dialect: str,
    target_connection: Optional[dict[str, Any]] = None,
) -> tuple[TranslationResult, list[str]]:
    """Translate every catalog object's DDL and persist results.

    Returns the aggregate `TranslationResult` plus the list of object names
    that fell at/below `LOW_CONFIDENCE_THRESHOLD` (for the caller to merge
    into `MigrationPlan.manual_review_objects`).
    """
    adapter = CrackSQLAdapter()
    translated_objects: list[dict[str, Any]] = []
    confidences: list[float] = []
    low_confidence_objects: list[str] = []

    with metadata_connection() as conn:
        for entry in discovery.object_catalog:
            object_type = entry["object_type"]
            object_name = entry["name"]
            source_ddl = entry.get("definition")

            if object_type == "table":
                # Table creation + data land via the Data Agent/SeaTunnel
                # (JDBC sink auto-generates basic target schema via
                # schema_save_mode) -- routing CREATE TABLE DDL through
                # CrackSQL too would be redundant. Foreign keys are handled
                # separately below (SeaTunnel's create-table-sql builders
                # explicitly skip FOREIGN_KEY generation for every dialect we
                # support), so they still go through translation.
                translated_objects.append(
                    {
                        "object_type": object_type,
                        "object_name": object_name,
                        "status": "SKIPPED_TABLE",
                        "confidence": None,
                    }
                )
                save_translation_result(
                    conn, job_id, object_type, object_name, source_ddl, None, "SKIPPED_TABLE", None
                )
                continue

            if not source_ddl:
                # Known Phase 2 gap for some object types on some dialects
                # (schema_extractor_adapter couldn't fetch DDL text) -- flag
                # for manual review rather than silently skipping.
                translated_objects.append(
                    {
                        "object_type": object_type,
                        "object_name": object_name,
                        "status": "NO_SOURCE_DDL",
                        "confidence": None,
                    }
                )
                low_confidence_objects.append(object_name)
                save_translation_result(
                    conn, job_id, object_type, object_name, None, None, "NO_SOURCE_DDL", None
                )
                continue

            try:
                config = adapter.prepare(
                    {
                        "source_dialect": source_dialect,
                        "target_dialect": target_dialect,
                        "source_sql": source_ddl,
                        "target_connection": target_connection,
                    }
                )
                result = adapter.run(config)
            except Exception:
                # One bad object must never block the whole batch (same
                # non-fatal-step pattern as assessment/planner agents).
                logger.exception(
                    "job=%s: cracksql_adapter crashed translating %s %s",
                    job_id,
                    object_type,
                    object_name,
                )
                translated_objects.append(
                    {
                        "object_type": object_type,
                        "object_name": object_name,
                        "status": "ERROR",
                        "confidence": None,
                    }
                )
                low_confidence_objects.append(object_name)
                save_translation_result(
                    conn, job_id, object_type, object_name, source_ddl, None, "ERROR", None
                )
                continue

            if not result.success:
                translated_objects.append(
                    {
                        "object_type": object_type,
                        "object_name": object_name,
                        "status": "ERROR",
                        "error": result.error,
                        "confidence": None,
                    }
                )
                low_confidence_objects.append(object_name)
                save_translation_result(
                    conn, job_id, object_type, object_name, source_ddl, None, "ERROR", None,
                    warnings=[result.error] if result.error else None,
                )
                continue

            translated_sql = result.output.get("translated_sql")
            if translated_sql:
                translated_sql = _sanitize_target_ddl(translated_sql, target_dialect)
            confidence = result.confidence_score
            status = "SUCCESS" if translated_sql else "FAILED"
            translated_objects.append(
                {
                    "object_type": object_type,
                    "object_name": object_name,
                    "source_ddl": source_ddl,
                    "translated_ddl": translated_sql,
                    "confidence": confidence,
                    "method": result.output.get("method"),
                    "status": status,
                }
            )
            if confidence is not None:
                confidences.append(confidence)
                if confidence <= LOW_CONFIDENCE_THRESHOLD:
                    low_confidence_objects.append(object_name)
            save_translation_result(
                conn, job_id, object_type, object_name, source_ddl, translated_sql, status, confidence
            )

    average_confidence = sum(confidences) / len(confidences) if confidences else None
    return (
        TranslationResult(translated_objects=translated_objects, average_confidence=average_confidence),
        low_confidence_objects,
    )


def apply_schema_translations(
    job_id: str,
    target_dialect: str,
    target_connection: dict[str, Any],
    manual_review_objects: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Execute every not-yet-applied SUCCESSful translation's target DDL
    against the target DB (views/procedures/functions/triggers/foreign_keys --
    SeaTunnel's JDBC sink only auto-creates tables, see translate_schema's
    SKIPPED_TABLE branch above). Called by the DataMigrate node *after* the
    Data Agent has created the target tables via SeaTunnel.

    Objects the Planner flagged into `manual_review_objects` (low-confidence
    translation) are skipped rather than auto-applied -- per plan.md Phase 4,
    those are meant for a human pass, not blind execution against the target.

    One bad object must never block the rest of the batch -- each DDL
    statement is executed and committed independently.
    """
    skip_names = set(manual_review_objects or [])
    results: list[dict[str, Any]] = []
    with metadata_connection() as meta_conn:
        pending = fetch_applicable_translations(meta_conn, job_id)
        pending.sort(key=lambda row: _APPLY_ORDER.get(row["object_type"], 99))

        if not pending:
            return results

        target_conn = _connect(target_dialect, target_connection)
        try:
            for row in pending:
                object_type, object_name, ddl = row["object_type"], row["object_name"], row["target_ddl"]
                if object_name in skip_names:
                    mark_translation_applied(meta_conn, row["id"], "PENDING_MANUAL_REVIEW")
                    results.append(
                        {"object_type": object_type, "object_name": object_name, "status": "PENDING_MANUAL_REVIEW"}
                    )
                    continue
                try:
                    cursor = target_conn.cursor()
                    cursor.execute(ddl)
                    cursor.close()
                    target_conn.commit()
                    mark_translation_applied(meta_conn, row["id"], "APPLIED")
                    results.append({"object_type": object_type, "object_name": object_name, "status": "APPLIED"})
                except Exception as exc:
                    target_conn.rollback()
                    logger.exception(
                        "job=%s: failed to apply translated DDL for %s %s", job_id, object_type, object_name
                    )
                    mark_translation_applied(meta_conn, row["id"], "APPLY_FAILED", str(exc))
                    results.append(
                        {
                            "object_type": object_type,
                            "object_name": object_name,
                            "status": "APPLY_FAILED",
                            "error": str(exc),
                        }
                    )
        finally:
            target_conn.close()
    return results

