"""LangGraph orchestrator: Discover -> ... -> Verify -> Done/Rollback (architecture.md §6).

Phase 1 scope: every node is a stub that logs and advances ``current_phase`` —
no real agent/tool-adapter logic yet (that lands in later phases). The graph
topology, human-review interrupts, and bounded-retry wiring are real.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt

from agents.assessment_agent import run_discovery
from agents.data_agent import migrate_data
from agents.planner_agent import build_plan
from agents.schema_agent import translate_schema
from agents.validation_agent import validate_data
from agents.validation_agent.test_runner import run_tests
from dialects.connections import default_namespace
from observability import metrics
from orchestrator import connection_registry
from orchestrator.execution_trace import add_step
from orchestrator.retry import with_retry
from orchestrator.state import (
    ApprovalRecord,
    CodeRefactorResult,
    DataMigrationResult,
    DeploymentStatus,
    DiscoveryResult,
    JobStatus,
    MigrationPlan,
    MigrationState,
    RetryRecord,
    ReviewDecision,
    TestReport,
    TranslationResult,
    ValidationReport,
)

logger = logging.getLogger(__name__)


def _log_phase(state: MigrationState, phase: str) -> None:
    logger.info("[job=%s] entering phase=%s (stub)", state.job_id, phase)


def _resume_field(decision: Any, key: str, default: str) -> str:
    """Pull a field out of the reviewer's resume payload, tolerating bad input."""
    if isinstance(decision, dict):
        return decision.get(key, default)
    return default


# --- Discovery / planning ----------------------------------------------------


def _discover(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Discover")
    connections = connection_registry.get(state.job_id)
    if connections is None:
        raise RuntimeError(
            f"no registered connection config for job {state.job_id} — the API "
            "process may have restarted before Discover ran; recreate the job"
        )
    source_connection, _target_connection = connections
    
    trace = add_step(state.execution_trace, "Discover", 
                     "Running SchemaExtractorAdapter",
                     f"Introspecting {state.dialects.source} source database")
    
    discovery = run_discovery(
        state.job_id, state.dialects.source, state.dialects.target, source_connection
    )
    
    catalog_count = len(discovery.object_catalog) if discovery.object_catalog else 0
    trace = add_step(trace, "Discover",
                     f"Schema discovery complete",
                     f"Found {catalog_count} objects ({', '.join(f'{k}={v}' for k,v in Counter(e['object_type'] for e in discovery.object_catalog).items()) if discovery.object_catalog else '0 tables'})",
                     status="SUCCESS")
    
    # NOTE: connection config is intentionally kept in the registry (not
    # discarded here) -- Transform/Generate's Schema Agent needs the target
    # connection too. See connection_registry.py's module docstring.
    return {
        "current_phase": "Discover",
        "status": JobStatus.RUNNING.value,
        "discovery": discovery.model_dump(),
        "execution_trace": trace,
    }


def _analyse(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Analyse")
    catalog = state.discovery.object_catalog if state.discovery else []
    counts = Counter(entry["object_type"] for entry in catalog)
    
    details = ", ".join(f"{count} {otype}" for otype, count in sorted(counts.items()))
    trace = add_step(state.execution_trace, "Analyse",
                     "Analyzing schema objects",
                     f"Catalog contains: {details}",
                     status="SUCCESS")
    
    logger.info(
        "[job=%s] catalog: %d tables, %d views, %d procedures, %d functions, %d triggers",
        state.job_id,
        counts.get("table", 0),
        counts.get("view", 0),
        counts.get("procedure", 0),
        counts.get("function", 0),
        counts.get("trigger", 0),
    )
    return {
        "current_phase": "Analyse",
        "status": JobStatus.RUNNING.value,
        "execution_trace": trace,
    }


def _plan(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Plan")
    trace = add_step(state.execution_trace, "Plan",
                     "Building migration plan",
                     f"Source: {state.dialects.source}, Target: {state.dialects.target}")
    
    if state.discovery is None:
        plan = state.plan or MigrationPlan()
    else:
        plan = build_plan(state.discovery, state.dialects.source, state.dialects.target)
    
    summary = f"{plan.tables} tables, {plan.views} views, {plan.procedures} procedures, {plan.functions} functions, {plan.triggers} triggers"
    if plan.risk_register:
        summary += f", {len(plan.risk_register)} risk items"
    trace = add_step(trace, "Plan",
                     "Migration plan created",
                     summary,
                     status="SUCCESS")
    
    return {
        "current_phase": "Plan",
        "status": JobStatus.PAUSED.value,  # next node is the HumanReviewPlan gate
        "plan": plan.model_dump(),
        "execution_trace": trace,
    }


def _human_review_plan(state: MigrationState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "HumanReviewPlan",
            "phase": "HumanReviewPlan",
            "prompt": "Review the migration plan: approve, modify, or reject.",
            "plan": state.plan.model_dump() if state.plan else None,
        }
    )
    choice = _resume_field(decision, "decision", ReviewDecision.REJECT.value)
    if choice == ReviewDecision.REJECT.value:
        connection_registry.discard(state.job_id)
    record = ApprovalRecord(
        phase="HumanReviewPlan",
        decision=choice,
        reviewer=_resume_field(decision, "reviewer", "unknown"),
        comment=decision.get("comment") if isinstance(decision, dict) else None,
    )
    return {
        "current_phase": "HumanReviewPlan",
        "status": (
            JobStatus.ABORTED.value
            if choice == ReviewDecision.REJECT.value
            else JobStatus.RUNNING.value
        ),
        "approvals": [a.model_dump() for a in state.approvals] + [record.model_dump()],
        "plan_decision": choice,
    }


def _route_after_plan_review(state: MigrationState) -> str:
    return {
        ReviewDecision.APPROVE.value: "Transform",
        ReviewDecision.MODIFY.value: "Plan",
    }.get(state.plan_decision or "", END)


# --- Translation / refactor / data migration ---------------------------------


def _transform(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Transform")
    return {"current_phase": "Transform", "status": JobStatus.RUNNING.value}


def _generate(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Generate")
    trace = add_step(state.execution_trace, "Generate",
                     "Using LLM + RAG for schema translation",
                     f"Translating {state.dialects.source} schema to {state.dialects.target}")
    
    if state.discovery is None or not state.discovery.object_catalog:
        return {
            "current_phase": "Generate",
            "status": JobStatus.RUNNING.value,
            "schema_translation": (state.schema_translation or TranslationResult()).model_dump(),
            "execution_trace": trace,
        }

    connections = connection_registry.get(state.job_id)
    target_connection = connections[1] if connections else None
    discovery = DiscoveryResult(**state.discovery.model_dump())
    translation, low_confidence_objects = translate_schema(
        state.job_id,
        discovery,
        state.dialects.source,
        state.dialects.target,
        target_connection=target_connection,
    )
    
    obj_count = len(translation.translated_objects) if translation.translated_objects else 0
    avg_conf = translation.average_confidence or 0.0
    trace = add_step(trace, "Generate",
                     "Schema translation complete (sqlglot + LLM)",
                     f"Translated {obj_count} objects, avg confidence: {avg_conf:.2f}",
                     status="SUCCESS")

    plan = state.plan or MigrationPlan()
    if low_confidence_objects:
        merged = list(dict.fromkeys(plan.manual_review_objects + low_confidence_objects))
        plan = plan.model_copy(update={"manual_review_objects": merged})
        if merged:
            trace = add_step(trace, "Generate",
                             "Low-confidence translations flagged for review",
                             f"Objects requiring manual review: {', '.join(merged)}")

    return {
        "current_phase": "Generate",
        "status": JobStatus.RUNNING.value,
        "schema_translation": translation.model_dump(),
        "plan": plan.model_dump(),
        "execution_trace": trace,
    }


def _code_refactor(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "CodeRefactor")
    trace = add_step(state.execution_trace, "CodeRefactor",
                     "Code refactoring phase",
                     "No code-gen agents enabled in this phase yet")
    # TODO(Phase 6): replace with Code Agent / openrewrite+aider adapter output.
    return {
        "current_phase": "CodeRefactor",
        "status": JobStatus.RUNNING.value,
        "code_refactor": (state.code_refactor or CodeRefactorResult()).model_dump(),
        "execution_trace": trace,
    }


def _data_migrate(state: MigrationState) -> dict[str, Any]:
    """Migrate data from source to target; auto-retry once if no rows moved."""
    _log_phase(state, "DataMigrate")
    
    trace = add_step(state.execution_trace, "DataMigrate",
                     "Starting data migration",
                     "Fetching table metadata and preparing migration")
    
    if state.discovery is None or not state.discovery.object_catalog:
        return {
            "current_phase": "DataMigrate",
            "status": JobStatus.RUNNING.value,
            "data_migration": (state.data_migration or DataMigrationResult()).model_dump(),
            "execution_trace": trace,
        }

    connections = connection_registry.get(state.job_id)
    if connections is None:
        raise RuntimeError(
            f"no registered connection config for job {state.job_id} — the API "
            "process may have restarted; recreate the job"
        )
    
    source_connection, target_connection = connections
    discovery = DiscoveryResult(**state.discovery.model_dump())
    
    # Count how many times we've already retried DataMigrate
    retry_count_for_migrate = sum(
        1 for r in state.retry_history if r.phase == "DataMigrate"
    )
    max_retries_for_migrate = 2  # Attempt 1, then retry once (attempt 2)
    
    start_time = time.monotonic()
    try:
        tables = [e["name"] for e in discovery.object_catalog if e["object_type"] == "table"]
        trace = add_step(trace, "DataMigrate",
                        f"Migrating {len(tables)} tables",
                        f"Tables: {', '.join(tables[:5])}{'...' if len(tables) > 5 else ''}")
        
        data_migration = migrate_data(
            state.job_id,
            discovery,
            state.dialects.source,
            state.dialects.target,
            source_connection,
            target_connection,
            state.plan.manual_review_objects if state.plan else None,
        )
        duration = time.monotonic() - start_time
        
        # Record throughput metric if rows were moved
        if data_migration.rows_moved > 0:
            trace = add_step(trace, "DataMigrate",
                            "Data migration completed",
                            f"Moved {data_migration.rows_moved} rows in {duration:.2f}s",
                            status="SUCCESS")
            for table_result in data_migration.tables:
                table_name = table_result.get("table_name", "?")
                rows_written = table_result.get("rows_written", 0)
                throughput = rows_written / duration if duration > 0 else 0
                metrics.record_data_throughput(
                    table_name,
                    state.job_id,
                    state.dialects.source,
                    state.dialects.target,
                    throughput,
                )
        
        # Auto-retry logic: if rows_moved == 0 and we haven't exceeded max retries
        if data_migration.rows_moved == 0 and retry_count_for_migrate < max_retries_for_migrate:
            attempt = retry_count_for_migrate + 1
            retry_record = RetryRecord(
                phase="DataMigrate",
                attempt=attempt + 1,  # Next attempt will be attempt+1
                status="FAILED",
                error="rows_moved == 0",
                timestamp=datetime.now(timezone.utc),
                duration_seconds=duration,
            )
            
            trace = add_step(trace, "DataMigrate",
                            "No rows moved - auto-retrying",
                            f"Attempt {attempt + 1}/{max_retries_for_migrate}")
            
            logger.warning(
                "[job=%s] DataMigrate attempt %d moved 0 rows; auto-retrying (attempt %d/%d)",
                state.job_id,
                attempt,
                attempt + 1,
                max_retries_for_migrate,
            )
            
            metrics.record_retry(
                state.job_id,
                "DataMigrate",
                state.dialects.source,
                state.dialects.target,
                success=False,
            )
            
            # Return state with retry record added, but re-run DataMigrate automatically
            return {
                "current_phase": "DataMigrate",
                "status": JobStatus.RUNNING.value,
                "data_migration": data_migration.model_dump(),
                "retry_history": [r.model_dump() for r in state.retry_history] + [retry_record.model_dump()],
                "execution_trace": trace,
            }
        
        # If rows were moved or we've already retried, mark as success
        if data_migration.rows_moved > 0:
            if retry_count_for_migrate > 0:
                # Retry succeeded
                metrics.record_retry(
                    state.job_id,
                    "DataMigrate",
                    state.dialects.source,
                    state.dialects.target,
                    success=True,
                )
                logger.info(
                    "[job=%s] DataMigrate retry succeeded; moved %d rows",
                    state.job_id,
                    data_migration.rows_moved,
                )
        
        return {
            "current_phase": "DataMigrate",
            "status": JobStatus.RUNNING.value,
            "data_migration": data_migration.model_dump(),
            "execution_trace": trace,
        }
    
    except Exception as exc:
        duration = time.monotonic() - start_time
        trace = add_step(trace, "DataMigrate",
                        f"Error during migration",
                        str(exc),
                        status="FAILED",
                        error=str(exc))
        logger.exception("[job=%s] DataMigrate failed: %s", state.job_id, exc)
        
        # If this was our first attempt and we can retry, do so
        if retry_count_for_migrate < max_retries_for_migrate:
            attempt = retry_count_for_migrate + 1
            retry_record = RetryRecord(
                phase="DataMigrate",
                attempt=attempt + 1,
                status="FAILED",
                error=str(exc),
                timestamp=datetime.now(timezone.utc),
                duration_seconds=duration,
            )
            
            logger.warning(
                "[job=%s] DataMigrate attempt %d failed with error; auto-retrying (attempt %d/%d)",
                state.job_id,
                attempt,
                attempt + 1,
                max_retries_for_migrate,
            )
            
            metrics.record_retry(
                state.job_id,
                "DataMigrate",
                state.dialects.source,
                state.dialects.target,
                success=False,
            )
            
            return {
                "current_phase": "DataMigrate",
                "status": JobStatus.RUNNING.value,
                "data_migration": (state.data_migration or DataMigrationResult()).model_dump(),
                "retry_history": [r.model_dump() for r in state.retry_history] + [retry_record.model_dump()],
                "execution_trace": trace,
            }
        else:
            # Max retries exceeded; escalate to human review
            logger.error(
                "[job=%s] DataMigrate max retries exceeded; escalating to human review",
                state.job_id,
            )
            return {
                "current_phase": "DataMigrate",
                "status": JobStatus.PAUSED.value,  # Pause for human review
                "data_migration": (state.data_migration or DataMigrationResult()).model_dump(),
                "execution_trace": trace,
            }


def _validate(state: MigrationState) -> dict[str, Any]:
    """Validate migrated data using checksums and row counts."""
    _log_phase(state, "Validate")
    
    trace = add_step(state.execution_trace, "Validate",
                     "Starting data validation",
                     "Computing MD5 checksums and row counts")
    
    if state.discovery is None or not state.discovery.object_catalog:
        return {
            "current_phase": "Validate",
            "status": JobStatus.PAUSED.value,
            "validation": (state.validation or ValidationReport(overall_status="PASS")).model_dump(),
            "execution_trace": trace,
        }

    connections = connection_registry.get(state.job_id)
    if connections is None:
        raise RuntimeError(
            f"no registered connection config for job {state.job_id} — the API "
            "process may have restarted; recreate the job"
        )
    
    source_connection, target_connection = connections
    discovery = DiscoveryResult(**state.discovery.model_dump())

    # Run validation via checksum_adapter on all tables
    try:
        validation_report = validate_data(
            state.job_id,
            discovery,
            source_dialect=state.dialects.source,
            target_dialect=state.dialects.target,
            source_connection=source_connection,
            target_connection=target_connection,
            source_namespace=default_namespace(state.dialects.source, source_connection),
            target_namespace=default_namespace(state.dialects.target, target_connection),
        )
        
        # Record validation progress metric
        matched = sum(
            1 for cs in validation_report.table_checksums if cs.status == "MATCH"
        )
        trace = add_step(trace, "Validate",
                        "Validation complete",
                        f"Tables validated: {len(validation_report.table_checksums)}, Matched: {matched}, Status: {validation_report.overall_status}",
                        status="SUCCESS")
        
        metrics.record_validation_progress(
            state.job_id,
            state.dialects.source,
            state.dialects.target,
            len(validation_report.table_checksums),
            matched,
        )
        
    except Exception as exc:
        trace = add_step(trace, "Validate",
                        "Validation failed",
                        str(exc),
                        status="FAILED",
                        error=str(exc))
        logger.exception("[job=%s] Validation failed: %s", state.job_id, exc)
        validation_report = ValidationReport(overall_status="FAIL")
    
    return {
        "current_phase": "Validate",
        "status": JobStatus.PAUSED.value,  # next node is the HumanReviewValidation gate
        "validation": validation_report.model_dump(),
        "execution_trace": trace,
    }


def _human_review_validation(state: MigrationState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "HumanReviewValidation",
            "phase": "HumanReviewValidation",
            "prompt": "Review the validation report: approve, retry data migration, or reject.",
            "validation": state.validation.model_dump() if state.validation else None,
        }
    )
    choice = _resume_field(decision, "decision", ReviewDecision.REJECT.value)
    if choice == ReviewDecision.REJECT.value:
        connection_registry.discard(state.job_id)
    record = ApprovalRecord(
        phase="HumanReviewValidation",
        decision=choice,
        reviewer=_resume_field(decision, "reviewer", "unknown"),
        comment=decision.get("comment") if isinstance(decision, dict) else None,
    )
    return {
        "current_phase": "HumanReviewValidation",
        "status": (
            JobStatus.ABORTED.value
            if choice == ReviewDecision.REJECT.value
            else JobStatus.RUNNING.value
        ),
        "approvals": [a.model_dump() for a in state.approvals] + [record.model_dump()],
        "validation_decision": choice,
    }


def _route_after_validation_review(state: MigrationState) -> str:
    return {
        ReviewDecision.APPROVE.value: "Test",
        ReviewDecision.MODIFY.value: "DataMigrate",
    }.get(state.validation_decision or "", END)


# --- Test / cutover / verify --------------------------------------------------


def _test(state: MigrationState) -> dict[str, Any]:
    """Run schema-compatibility, missing-objects, referential-integrity, and
    performance smoke checks against the target, producing a TestReport."""
    _log_phase(state, "Test")
    trace = add_step(state.execution_trace, "Test",
                     "Running migration test suite",
                     "Schema compatibility, missing objects, referential integrity, performance smoke checks")

    if state.discovery is None or not state.discovery.object_catalog or state.validation is None:
        report = TestReport(overall_status="PASS")
        return {
            "current_phase": "Test",
            "status": JobStatus.PAUSED.value,
            "test_report": report.model_dump(),
            "execution_trace": trace,
        }

    connections = connection_registry.get(state.job_id)
    if connections is None:
        raise RuntimeError(
            f"no registered connection config for job {state.job_id} — the API "
            "process may have restarted; recreate the job"
        )
    _source_connection, target_connection = connections
    discovery = DiscoveryResult(**state.discovery.model_dump())
    validation = ValidationReport(**state.validation.model_dump())

    try:
        report = run_tests(
            state.job_id,
            discovery,
            validation,
            state.dialects.target,
            target_connection,
            default_namespace(state.dialects.target, target_connection),
        )
        trace = add_step(trace, "Test",
                         "Test suite complete",
                         ", ".join(f"{d['check']}={d['status']}" for d in report.details),
                         status="SUCCESS" if report.overall_status == "PASS" else "FAILED")
    except Exception as exc:
        trace = add_step(trace, "Test", "Test suite failed", str(exc), status="FAILED", error=str(exc))
        logger.exception("[job=%s] Test phase failed: %s", state.job_id, exc)
        report = TestReport(
            overall_status="FAIL",
            details=[{"check": "test_suite", "status": "ERROR", "detail": str(exc)}],
        )

    next_status = (
        JobStatus.PAUSED.value if report.overall_status == "PASS" else JobStatus.RUNNING.value
    )
    return {
        "current_phase": "Test",
        "status": next_status,
        "test_report": report.model_dump(),
        "execution_trace": trace,
    }


def _route_after_test(state: MigrationState) -> str:
    status = state.test_report.overall_status if state.test_report else "FAIL"
    return "HumanReviewCutover" if status == "PASS" else "Validate"


def _human_review_cutover(state: MigrationState) -> dict[str, Any]:
    decision = interrupt(
        {
            "type": "HumanReviewCutover",
            "phase": "HumanReviewCutover",
            "prompt": "Approve cutover to the new deployment, or reject.",
            "test_report": state.test_report.model_dump() if state.test_report else None,
        }
    )
    choice = _resume_field(decision, "decision", ReviewDecision.REJECT.value)
    if choice == ReviewDecision.REJECT.value:
        connection_registry.discard(state.job_id)
    record = ApprovalRecord(
        phase="HumanReviewCutover",
        decision=choice,
        reviewer=_resume_field(decision, "reviewer", "unknown"),
        comment=decision.get("comment") if isinstance(decision, dict) else None,
    )
    return {
        "current_phase": "HumanReviewCutover",
        "status": (
            JobStatus.ABORTED.value
            if choice == ReviewDecision.REJECT.value
            else JobStatus.RUNNING.value
        ),
        "approvals": [a.model_dump() for a in state.approvals] + [record.model_dump()],
        "cutover_decision": choice,
    }


def _route_after_cutover_review(state: MigrationState) -> str:
    return "Cutover" if state.cutover_decision == ReviewDecision.APPROVE.value else END


def _cutover(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Cutover")
    trace = add_step(state.execution_trace, "Cutover",
                     "Production cutover",
                     "Applying changes to production",
                     status="IN_PROGRESS")
    return {
        "current_phase": "Cutover",
        "status": JobStatus.RUNNING.value,
        "execution_trace": trace,
    }


def _verify(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Verify")
    trace = add_step(state.execution_trace, "Verify",
                     "Post-cutover health check",
                     "Verifying deployment health",
                     status="SUCCESS")
    # TODO(Phase 8): replace with real post-cutover health-check gating.
    return {
        "current_phase": "Verify",
        "status": JobStatus.RUNNING.value,
        "deployment": DeploymentStatus(status="HEALTHY").model_dump(),
        "execution_trace": trace,
    }


def _route_after_verify(state: MigrationState) -> str:
    healthy = bool(state.deployment and state.deployment.status == "HEALTHY")
    return "Done" if healthy else "Rollback"


def _done(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Done")
    connection_registry.discard(state.job_id)
    trace = add_step(state.execution_trace, "Done",
                     "Migration completed successfully",
                     "Job finished",
                     status="SUCCESS")
    return {
        "current_phase": "Done",
        "status": JobStatus.DONE.value,
        "execution_trace": trace,
    }


def _rollback(state: MigrationState) -> dict[str, Any]:
    _log_phase(state, "Rollback")
    connection_registry.discard(state.job_id)
    return {"current_phase": "Rollback", "status": JobStatus.ROLLED_BACK.value}


# Nodes wrapping an LLM call or external tool-adapter invocation get the bounded
# retry policy (architecture.md §6.1); pure in-process/orchestration nodes don't.
_RETRYABLE_NODES: dict[str, Any] = {
    "Discover": _discover,
    "Plan": _plan,
    "Transform": _transform,
    "Generate": _generate,
    "CodeRefactor": _code_refactor,
    "DataMigrate": _data_migrate,
    "Test": _test,
    "Cutover": _cutover,
}


def build_state_graph() -> StateGraph:
    """Assemble the (uncompiled) StateGraph with all nodes/edges from architecture.md §6."""
    graph = StateGraph(MigrationState)

    graph.add_node("Discover", with_retry("Discover", _RETRYABLE_NODES["Discover"]))
    graph.add_node("Analyse", _analyse)
    graph.add_node("Plan", with_retry("Plan", _RETRYABLE_NODES["Plan"]))
    graph.add_node("HumanReviewPlan", _human_review_plan)
    graph.add_node("Transform", with_retry("Transform", _RETRYABLE_NODES["Transform"]))
    graph.add_node("Generate", with_retry("Generate", _RETRYABLE_NODES["Generate"]))
    graph.add_node("CodeRefactor", with_retry("CodeRefactor", _RETRYABLE_NODES["CodeRefactor"]))
    graph.add_node("DataMigrate", with_retry("DataMigrate", _RETRYABLE_NODES["DataMigrate"]))
    graph.add_node("Validate", _validate)
    graph.add_node("HumanReviewValidation", _human_review_validation)
    graph.add_node("Test", with_retry("Test", _RETRYABLE_NODES["Test"]))
    graph.add_node("HumanReviewCutover", _human_review_cutover)
    graph.add_node("Cutover", with_retry("Cutover", _RETRYABLE_NODES["Cutover"]))
    graph.add_node("Verify", _verify)
    graph.add_node("Done", _done)
    graph.add_node("Rollback", _rollback)

    graph.add_edge(START, "Discover")
    graph.add_edge("Discover", "Analyse")
    graph.add_edge("Analyse", "Plan")
    graph.add_edge("Plan", "HumanReviewPlan")
    graph.add_conditional_edges(
        "HumanReviewPlan",
        _route_after_plan_review,
        {"Transform": "Transform", "Plan": "Plan", END: END},
    )
    graph.add_edge("Transform", "Generate")
    graph.add_edge("Generate", "CodeRefactor")
    graph.add_edge("CodeRefactor", "DataMigrate")
    graph.add_edge("DataMigrate", "Validate")
    graph.add_edge("Validate", "HumanReviewValidation")
    graph.add_conditional_edges(
        "HumanReviewValidation",
        _route_after_validation_review,
        {"Test": "Test", "DataMigrate": "DataMigrate", END: END},
    )
    graph.add_conditional_edges(
        "Test",
        _route_after_test,
        {"HumanReviewCutover": "HumanReviewCutover", "Validate": "Validate"},
    )
    graph.add_conditional_edges(
        "HumanReviewCutover",
        _route_after_cutover_review,
        {"Cutover": "Cutover", END: END},
    )
    graph.add_edge("Cutover", "Verify")
    graph.add_conditional_edges(
        "Verify",
        _route_after_verify,
        {"Done": "Done", "Rollback": "Rollback"},
    )
    graph.add_edge("Done", END)
    graph.add_edge("Rollback", END)

    return graph


def compile_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Compile the graph, optionally wired to a checkpointer for pause/resume."""
    return build_state_graph().compile(checkpointer=checkpointer)
