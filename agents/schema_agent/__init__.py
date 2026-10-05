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

# NOTE: previously this module also force-lowercased every quoted identifier
# here, on the assumption that SeaTunnel's JDBC sink creates target Postgres
# tables/columns unquoted (which Postgres folds to lowercase). Verified
# against an actual run: generate_sink_sql=true quotes and preserves the
# exact catalog-original case (e.g. Oracle's "EMPLOYEES" lands as the quoted,
# mixed/upper-case "EMPLOYEES", not lowercase "employees"). CrackSQL's
# translated DDL already carries that same original-case identifier, so
# folding it to lowercase made the DDL reference a table that doesn't exist
# ("relation ... does not exist") -- removed; only the schema name (which
# dialects/connections.py creates lowercase/unquoted) needs remapping.


def _strip_oracle_noise(ddl: str) -> str:
    """Remove Oracle-only cosmetic keywords; shared by source-side
    pre-cleaning (ANTLR chokes on EDITIONABLE/FORCE -- see
    _ORACLE_NOISE_KEYWORDS_RE) and target-side post-cleaning."""
    if not ddl:
        return ddl
    cleaned = _ORACLE_NOISE_KEYWORDS_RE.sub("", ddl)
    return re.sub(r"[ \t]+", " ", cleaned)


def _build_identifier_case_map(discovery: DiscoveryResult) -> dict[str, str]:
    """Lowercase name -> catalog-original-case name, for every table and
    column discovered. CrackSQL quotes+preserves case in a translated
    object's own declaration (e.g. CREATE VIEW "ACTIVE_EMPLOYEES" ("EMPLOYEE_ID", ...))
    but leaves bare/unquoted identifiers inside the SELECT body as-is --
    those need the same case restored so they resolve against the
    case-preserved quoted tables SeaTunnel actually creates (see
    _sanitize_target_ddl)."""
    case_map: dict[str, str] = {}
    for entry in discovery.object_catalog:
        if entry.get("object_type") != "table":
            continue
        name = entry.get("name")
        if name:
            case_map[name.lower()] = name
        for column in entry.get("columns") or []:
            column_name = column.get("name")
            if column_name:
                case_map[column_name.lower()] = column_name
    return case_map


def _requote_bare_identifiers(ddl: str, identifier_case_map: dict[str, str]) -> str:
    """Quote-wrap bare (unquoted) occurrences of known table/column names with
    their catalog-original case, leaving already-quoted identifiers alone."""
    if not identifier_case_map or not ddl:
        return ddl
    names = sorted(identifier_case_map, key=len, reverse=True)
    pattern = re.compile(
        r'(?<!")\b(' + "|".join(re.escape(name) for name in names) + r')\b(?!")',
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f'"{identifier_case_map[m.group(0).lower()]}"', ddl)


def _sanitize_target_ddl(
    ddl: str,
    target_dialect: str,
    source_schema: Optional[str] = None,
    target_schema: Optional[str] = None,
    identifier_case_map: Optional[dict[str, str]] = None,
) -> str:
    """Strip Oracle-only cosmetic DDL keywords when they leak through to a
    non-Oracle target, map source schema name to target schema name, fold
    and unescape JSON escape sequences (which CrackSQL may return in
    translated DDL).
    
    Args:
        ddl: The translated DDL to sanitize
        target_dialect: The target dialect (e.g., 'postgresql', 'oracle')
        source_schema: The source schema name (e.g., 'SAMPLE_USER') to replace
        target_schema: The target schema name (e.g., 'sample') to replace with
        identifier_case_map: lowercase table/column name -> catalog-original
            case, used to re-quote bare identifiers left unquoted by CrackSQL
    """
    if target_dialect == "oracle" or not ddl:
        return ddl
    
    # Unescape JSON escape sequences that may come from CrackSQL's output
    # (e.g., \n → actual newline, \t → tab, \" → quote, \\ → backslash)
    cleaned = ddl.encode('utf-8').decode('unicode_escape')
    
    cleaned = _strip_oracle_noise(cleaned)
    if target_dialect == "postgresql":
        # Map source schema name to target schema name (schema names are
        # created lowercase/unquoted by dialects/connections.py, unlike
        # table/column identifiers which SeaTunnel creates case-preserved).
        if source_schema and target_schema:
            # Replace quoted schema names: "SAMPLE_USER"."table" → "sample"."table"
            # Use case-insensitive match to handle UPPERCASE, lowercase, or MixedCase
            cleaned = re.sub(
                f'"{re.escape(source_schema)}"(?=\\W)',
                f'"{target_schema.lower()}"',
                cleaned,
                flags=re.IGNORECASE,
            )
        # CrackSQL quotes+preserves case in an object's own declaration (e.g.
        # CREATE VIEW "ACTIVE_EMPLOYEES" ("EMPLOYEE_ID", ...)) but leaves bare
        # identifiers inside the body (e.g. "FROM employees") unquoted --
        # those fold to lowercase in Postgres and fail to resolve against the
        # case-preserved quoted tables SeaTunnel actually creates. Restore it.
        cleaned = _requote_bare_identifiers(cleaned, identifier_case_map or {})
    elif target_dialect == "mysql" and source_schema:
        # MySQL's "schema" IS the database, already selected via the target
        # connection -- a literal "sample.table" qualifier carried over from
        # the source dialect either points at a database that doesn't exist
        # on the target server or one the migration user has no grants on
        # (surfaces as a confusing "CREATE VIEW command denied" error rather
        # than "unknown database"). Strip it so identifiers resolve against
        # the connected database instead.
        cleaned = re.sub(rf"`{re.escape(source_schema)}`\.", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(rf"\b{re.escape(source_schema)}\.", "", cleaned, flags=re.IGNORECASE)
    return cleaned

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
    identifier_case_map = _build_identifier_case_map(discovery)

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

            if source_dialect == "oracle":
                # ANTLR's Oracle grammar chokes on EDITIONABLE/FORCE before
                # translation even starts -- strip them from the source too,
                # not just the final output (see _sanitize_target_ddl).
                source_ddl = _strip_oracle_noise(source_ddl)

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
                source_schema = entry.get("schema")  # catalog key is "schema", not "schema_name"
                target_schema = target_connection.get("schema_name") if target_connection else None
                translated_sql = _sanitize_target_ddl(
                    translated_sql, target_dialect, source_schema, target_schema, identifier_case_map
                )
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


def _topological_sort_by_dependencies(
    pending: list[dict[str, Any]], job_id: str
) -> list[dict[str, Any]]:
    """Sort objects respecting both type-based priority (_APPLY_ORDER) and
    actual source-code dependencies. Objects with dependencies are ordered
    after their dependencies (respecting _APPLY_ORDER for type-based grouping).
    """
    if not pending:
        return pending

    # Build a dependency map by querying the object catalog
    name_to_deps: dict[str, list[str]] = {}
    with metadata_connection() as conn:
        for row in pending:
            object_name = row["object_name"]
            try:
                result = conn.execute(
                    "SELECT dependencies FROM object_catalog_entries WHERE job_id = %s AND object_name = %s LIMIT 1",
                    (job_id, object_name),
                )
                row_data = result.fetchone()
                if row_data and row_data[0]:
                    # dependencies is a PostgreSQL array, stored as text
                    deps_text = row_data[0]
                    if isinstance(deps_text, str):
                        # Parse PostgreSQL array format: "{dep1,dep2,dep3}" or similar
                        deps = [d.strip('"{} ') for d in deps_text.split(',') if d.strip('"{} ')]
                        name_to_deps[object_name] = [d for d in deps if d]
                    else:
                        name_to_deps[object_name] = list(deps_text) if deps_text else []
                else:
                    name_to_deps[object_name] = []
            except Exception as e:
                logger.warning(
                    "Failed to fetch dependencies for %s in job %s: %s", object_name, job_id, e
                )
                name_to_deps[object_name] = []

    # First sort by type order (already done by caller), then by dependencies
    # within each type group
    name_to_row = {row["object_name"]: row for row in pending}
    type_groups: dict[int, list[dict[str, Any]]] = {}
    for row in pending:
        type_order = _APPLY_ORDER.get(row["object_type"], 99)
        if type_order not in type_groups:
            type_groups[type_order] = []
        type_groups[type_order].append(row)

    # Topological sort within each type group
    def topo_sort_group(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Topological sort a group of objects by dependencies."""
        if len(group) <= 1:
            return group
        
        visited: set[str] = set()
        sorted_group: list[dict[str, Any]] = []
        
        def visit(obj_name: str) -> None:
            if obj_name in visited:
                return
            visited.add(obj_name)
            deps = name_to_deps.get(obj_name, [])
            for dep in deps:
                if dep in name_to_row and name_to_row[dep]["object_type"] == group[0]["object_type"]:
                    # Only enforce order if dep is in the same type group
                    visit(dep)
            if obj_name in name_to_row:
                sorted_group.append(name_to_row[obj_name])
        
        for row in group:
            visit(row["object_name"])
        
        return sorted_group

    result: list[dict[str, Any]] = []
    for type_order in sorted(type_groups.keys()):
        result.extend(topo_sort_group(type_groups[type_order]))

    return result


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
    statement is executed and committed independently. Duplicate constraint
    errors (common in replay scenarios) are treated as idempotent success.
    """
    skip_names = set(manual_review_objects or [])
    results: list[dict[str, Any]] = []
    with metadata_connection() as meta_conn:
        pending = fetch_applicable_translations(meta_conn, job_id)
        # Sort by both type order and dependencies
        pending = _topological_sort_by_dependencies(pending, job_id)

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
                    exc_str = str(exc)
                    
                    # Idempotent: if constraint already exists (common in replay/retry),
                    # treat as success since it's the same constraint being (re)created
                    if object_type == "foreign_key" and "already exists" in exc_str.lower():
                        logger.info(
                            "job=%s: FK %s already exists on target (idempotent), marking APPLIED",
                            job_id,
                            object_name,
                        )
                        mark_translation_applied(meta_conn, row["id"], "APPLIED")
                        results.append(
                            {"object_type": object_type, "object_name": object_name, "status": "APPLIED"}
                        )
                    else:
                        logger.exception(
                            "job=%s: failed to apply translated DDL for %s %s", job_id, object_type, object_name
                        )
                        mark_translation_applied(meta_conn, row["id"], "APPLY_FAILED", exc_str)
                        results.append(
                            {
                                "object_type": object_type,
                                "object_name": object_name,
                                "status": "APPLY_FAILED",
                                "error": exc_str,
                            }
                        )
        finally:
            target_conn.close()
    return results

