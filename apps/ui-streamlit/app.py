"""Streamlit UI: job creation, progress view, and Approve/Reject/Modify review screens.

Phase 1 scope: talks to the FastAPI gateway (apps/api-fastapi) over plain REST
polling (the gateway also exposes a WebSocket for other clients — Streamlit
doesn't have first-class websocket support, so REST polling is simpler here).
"""

from __future__ import annotations

import os
import time
from collections import Counter
from typing import Any, Optional

import requests
import streamlit as st

API_BASE_URL = os.getenv("MIGRATION_API_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTH_API_KEY")
SUPPORTED_DIALECTS = ["oracle", "mysql", "postgresql"]

# Pre-fill connection forms with this repo's local docker-compose sample DBs
# (infra/docker/*-sample-init.sql) so the happy path needs zero typing.
_SAMPLE_DEFAULTS: dict[str, dict[str, Any]] = {
    "postgresql": {
        "host": "localhost",
        "port": 5433,
        "username": "postgres",
        "password": "postgres_dev_password",
        "database": "sample_source",
        "schema_name": "sample",
    },
    "mysql": {
        "host": "localhost",
        "port": 3306,
        "username": "appuser",
        "password": "mysql_dev_password",
        "database": "sample_source",
        "schema_name": "",
    },
    "oracle": {
        "host": "localhost",
        "port": 1521,
        "username": "sample_user",
        "password": "oracle_dev_password",
        "database": "XEPDB1",
        "schema_name": "sample_user",
    },
}


# All 6 ordered pairs across the 3 supported dialects, for one-click test setup.
_SAMPLE_PRESETS: dict[str, tuple[str, str]] = {
    "MySQL -> PostgreSQL": ("mysql", "postgresql"),
    "PostgreSQL -> MySQL": ("postgresql", "mysql"),
    "MySQL -> Oracle": ("mysql", "oracle"),
    "Oracle -> MySQL": ("oracle", "mysql"),
    "PostgreSQL -> Oracle": ("postgresql", "oracle"),
    "Oracle -> PostgreSQL": ("oracle", "postgresql"),
}
_PRESET_PLACEHOLDER = "-- choose dialects manually --"

st.set_page_config(page_title="Agentic Migration Platform", layout="wide")


def _headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _get_job(job_id: str) -> Optional[dict[str, Any]]:
    resp = requests.get(f"{API_BASE_URL}/jobs/{job_id}", headers=_headers(), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def _create_job(
    source_dialect: str,
    target_dialect: str,
    source_connection: dict[str, Any],
    target_connection: dict[str, Any],
) -> str:
    resp = requests.post(
        f"{API_BASE_URL}/jobs",
        json={
            "source_dialect": source_dialect,
            "target_dialect": target_dialect,
            "source_connection": source_connection,
            "target_connection": target_connection,
        },
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["job_id"]


def _submit_review(job_id: str, decision: str, reviewer: str, comment: str) -> None:
    resp = requests.post(
        f"{API_BASE_URL}/jobs/{job_id}/review",
        json={"decision": decision, "reviewer": reviewer, "comment": comment or None},
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()


def _get_schema_sql(job_id: str) -> dict[str, Any]:
    resp = requests.get(f"{API_BASE_URL}/jobs/{job_id}/schema-sql", headers=_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


def _connection_form(label: str, dialect: str, key_prefix: str) -> dict[str, Any]:
    defaults = _SAMPLE_DEFAULTS.get(dialect, {})
    st.markdown(f"**{label} connection** ({dialect})")
    c1, c2 = st.columns(2)
    host = c1.text_input("Host", value=defaults.get("host", "localhost"), key=f"{key_prefix}_host")
    port = c2.number_input(
        "Port", value=defaults.get("port", 5432), step=1, key=f"{key_prefix}_port"
    )
    username = c1.text_input(
        "Username", value=defaults.get("username", ""), key=f"{key_prefix}_user"
    )
    password = c2.text_input(
        "Password", value=defaults.get("password", ""), type="password", key=f"{key_prefix}_pw"
    )
    database = c1.text_input(
        "Database / service name", value=defaults.get("database", ""), key=f"{key_prefix}_db"
    )
    schema_name = c2.text_input(
        "Schema (Postgres only, optional)",
        value=defaults.get("schema_name", ""),
        key=f"{key_prefix}_schema",
    )
    return {
        "host": host,
        "port": int(port),
        "username": username,
        "password": password,
        "database": database,
        "schema_name": schema_name or None,
    }


def _apply_preset() -> None:
    pair = _SAMPLE_PRESETS.get(st.session_state.get("preset_choice", ""))
    if pair is None:
        return
    source_dialect, target_dialect = pair
    st.session_state["source_dialect"] = source_dialect
    st.session_state["target_dialect"] = target_dialect
    for key_prefix, dialect in (("src", source_dialect), ("tgt", target_dialect)):
        defaults = _SAMPLE_DEFAULTS.get(dialect, {})
        st.session_state[f"{key_prefix}_host"] = defaults.get("host", "localhost")
        st.session_state[f"{key_prefix}_port"] = defaults.get("port", 5432)
        st.session_state[f"{key_prefix}_user"] = defaults.get("username", "")
        st.session_state[f"{key_prefix}_pw"] = defaults.get("password", "")
        st.session_state[f"{key_prefix}_db"] = defaults.get("database", "")
        st.session_state[f"{key_prefix}_schema"] = defaults.get("schema_name", "")


st.title("Agentic AI-Powered Database Migration Platform")

with st.expander("Create a new migration job", expanded="job_id" not in st.session_state):
    st.selectbox(
        "Quick sample: pick a source -> target pair (fills in docker-compose sample DB creds)",
        [_PRESET_PLACEHOLDER, *_SAMPLE_PRESETS.keys()],
        key="preset_choice",
        on_change=_apply_preset,
    )

    col1, col2 = st.columns(2)
    source_dialect = col1.selectbox("Source dialect", SUPPORTED_DIALECTS, key="source_dialect")
    target_dialect = col2.selectbox(
        "Target dialect", SUPPORTED_DIALECTS, index=2, key="target_dialect"
    )

    st.divider()
    source_connection = _connection_form("Source", source_dialect, "src")
    st.divider()
    target_connection = _connection_form("Target", target_dialect, "tgt")

    if st.button("Create job", type="primary"):
        if source_dialect == target_dialect:
            st.warning("Source and target dialect are the same — proceeding anyway.")
        try:
            st.session_state["job_id"] = _create_job(
                source_dialect, target_dialect, source_connection, target_connection
            )
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"Failed to create job: {exc}")

job_id = st.session_state.get("job_id")
if not job_id:
    st.info("Create a job above to see progress here.")
    st.stop()

st.subheader(f"Job `{job_id}`")

try:
    job = _get_job(job_id)
except requests.RequestException as exc:
    st.error(f"Failed to fetch job status: {exc}")
    st.stop()

if job is None:
    st.error("Job not found.")
    st.stop()

st.metric("Current phase", job["current_phase"])
st.metric("Status", job["status"])
st.progress(min(job["retry_count"] / max(job.get("retry_count", 0) or 1, 1), 1.0))


def _render_plan_summary(plan: dict[str, Any]) -> None:
    """Structured plan-summary view (counts + risk breakdown + per-object
    drill-down), per plan.md Phase 3 DoD -- richer than a raw JSON dump."""
    cols = st.columns(5)
    for col, key in zip(cols, ["tables", "views", "procedures", "functions", "triggers"]):
        col.metric(key.capitalize(), plan.get(key, 0))

    risk_register = plan.get("risk_register") or []
    risk_counts = Counter(r["risk_level"] for r in risk_register)
    st.write(
        f"**Risk breakdown:** {risk_counts.get('low', 0)} low / "
        f"{risk_counts.get('medium', 0)} medium / {risk_counts.get('high', 0)} high"
    )

    manual_review = plan.get("manual_review_objects") or []
    if manual_review:
        st.warning(f"{len(manual_review)} object(s) flagged for manual review: "
                   + ", ".join(manual_review))

    if risk_register:
        with st.expander(f"Per-object risk drill-down ({len(risk_register)} objects)"):
            st.dataframe(
                [
                    {
                        "object": r["object_name"],
                        "type": r["object_type"],
                        "risk": r["risk_level"],
                        "reason": r.get("reason") or "",
                    }
                    for r in risk_register
                ],
                use_container_width=True,
                hide_index=True,
            )


def _render_discovery(discovery: dict[str, Any]) -> None:
    catalog = discovery.get("object_catalog") or []
    counts = Counter(entry["object_type"] for entry in catalog)
    cols = st.columns(5)
    for col, key in zip(cols, ["table", "view", "procedure", "function", "trigger"]):
        col.metric(key.capitalize(), counts.get(key, 0))
    with st.expander(f"Object catalog ({len(catalog)} objects)"):
        st.dataframe(
            [{"type": e["object_type"], "name": e["name"], "schema": e.get("schema")} for e in catalog],
            use_container_width=True,
            hide_index=True,
        )


def _render_schema_translation(translation: dict[str, Any]) -> None:
    objects = translation.get("translated_objects") or []
    avg_conf = translation.get("average_confidence")
    st.metric("Avg. translation confidence", f"{avg_conf:.2f}" if avg_conf is not None else "n/a")
    status_counts = Counter(o["status"] for o in objects)
    st.write(", ".join(f"{count} {status}" for status, count in status_counts.items()) or "no objects")
    
    # Filter objects with actual DDL translations (not skipped tables)
    ddl_objects = [o for o in objects if o.get("status") != "SKIPPED_TABLE" and o.get("translated_ddl")]
    
    if ddl_objects:
        with st.expander(f"📝 View Source & Target DDL ({len(ddl_objects)} objects)"):
            st.markdown("**Side-by-side schema comparison: Source SQL → Target SQL**")
            
            # Create tabs for each object with DDL
            tabs = st.tabs([f"{o['object_name']} ({o['object_type']})" for o in ddl_objects])
            
            for tab, obj in zip(tabs, ddl_objects):
                with tab:
                    col1, col2 = st.columns(2)
                    
                    # Source DDL
                    with col1:
                        st.markdown("**Source DDL**")
                        source_ddl = obj.get("source_ddl", "N/A")
                        st.code(source_ddl or "No DDL available", language="sql")
                    
                    # Target DDL
                    with col2:
                        st.markdown("**Target DDL**")
                        target_ddl = obj.get("translated_ddl", "N/A")
                        confidence = obj.get("confidence")
                        if confidence is not None:
                            conf_color = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.7 else "🔴"
                            st.caption(f"Confidence: {conf_color} {confidence:.2f}")
                        st.code(target_ddl or "No DDL available", language="sql")
                    
                    # Additional metadata
                    st.divider()
                    meta_col1, meta_col2, meta_col3 = st.columns(3)
                    meta_col1.metric("Type", obj.get("object_type", "unknown"))
                    meta_col2.metric("Status", obj.get("status", "unknown"))
                    meta_col3.metric("Method", obj.get("method", "N/A") or "N/A")
    
    with st.expander(f"Translated objects summary ({len(objects)})"):
        st.dataframe(
            [
                {
                    "type": o["object_type"],
                    "name": o["object_name"],
                    "status": o["status"],
                    "confidence": o.get("confidence"),
                }
                for o in objects
            ],
            use_container_width=True,
            hide_index=True,
        )


def _render_data_migration(data_migration: dict[str, Any]) -> None:
    st.metric("Rows moved", data_migration.get("rows_moved", 0))
    tables = data_migration.get("tables") or []
    with st.expander(f"Per-table migration results ({len(tables)})"):
        st.dataframe(tables, use_container_width=True, hide_index=True)
    ddl_applications = data_migration.get("ddl_applications") or []
    if ddl_applications:
        with st.expander(f"Applied DDL (views/procedures/triggers/FKs) ({len(ddl_applications)})"):
            st.dataframe(ddl_applications, use_container_width=True, hide_index=True)


def _render_validation(validation_report: dict[str, Any]) -> None:
    checksums = validation_report.get("table_checksums", [])
    total_tables = len(checksums)
    passed_tables = sum(1 for cs in checksums if cs.get("status") == "MATCH")

    if total_tables > 0:
        st.metric("Table validation", f"{passed_tables}/{total_tables} tables")
        match_rate = (passed_tables / total_tables) * 100
        st.progress(match_rate / 100.0, text=f"Checksum Match Rate: {match_rate:.1f}%")
        mismatch_tables = [cs for cs in checksums if cs.get("status") != "MATCH"]
        if mismatch_tables:
            with st.expander(f"Mismatched tables ({len(mismatch_tables)})"):
                st.dataframe(mismatch_tables, use_container_width=True, hide_index=True)
        else:
            st.success("✅ All tables validated successfully")

    object_validations = validation_report.get("object_validations", [])
    if object_validations:
        present = sum(1 for ov in object_validations if ov.get("status") == "PRESENT")
        pending_review = [ov for ov in object_validations if ov.get("status") == "PENDING_MANUAL_REVIEW"]
        failed = [
            ov
            for ov in object_validations
            if ov.get("status") not in ("PRESENT", "PENDING_MANUAL_REVIEW")
        ]
        st.metric("Non-table objects on target", f"{present}/{len(object_validations)} present")
        if pending_review:
            with st.expander(f"Pending manual review ({len(pending_review)})"):
                st.info("Low-confidence translations intentionally skipped -- not yet applied to target.")
                st.dataframe(pending_review, use_container_width=True, hide_index=True)
        if failed:
            st.warning(f"⚠️ {len(failed)} object(s) missing/errored on target")
            with st.expander(f"Missing/errored objects ({len(failed)})"):
                st.dataframe(failed, use_container_width=True, hide_index=True)
        elif not pending_review:
            st.success("✅ All views/procedures/functions/triggers/FKs present on target")

    mismatches = validation_report.get("mismatches", 0)
    overall_status = validation_report.get("overall_status", "PENDING")
    st.write(f"**Overall validation status:** {overall_status} ({mismatches} mismatches)")


def _render_test_report(test_report: dict[str, Any]) -> None:
    st.write(f"**Overall test status:** {test_report.get('overall_status', 'PENDING')}")
    details = test_report.get("details") or []
    if details:
        with st.expander(f"Test details ({len(details)})"):
            st.dataframe(details, use_container_width=True, hide_index=True)


def _render_deployment(deployment: dict[str, Any]) -> None:
    st.write(f"**Deployment status:** {deployment.get('status', 'PENDING')}")
    if deployment.get("detail"):
        st.caption(deployment["detail"])


def _render_execution_trace(trace: list[dict[str, Any]]) -> None:
    """Display detailed execution steps in a timeline format."""
    if not trace:
        st.info("No execution steps recorded yet.")
        return

    # Group steps by phase
    by_phase = {}
    for step in trace:
        phase = step.get("phase", "Unknown")
        if phase not in by_phase:
            by_phase[phase] = []
        by_phase[phase].append(step)

    # Display each phase's steps
    for phase in by_phase.keys():
        with st.expander(f"📍 **{phase}**", expanded=False):
            steps = by_phase[phase]
            for i, step in enumerate(steps, 1):
                # Determine status icon
                status = step.get("status", "SUCCESS")
                status_icon = "✅" if status == "SUCCESS" else "⏳" if status == "IN_PROGRESS" else "❌"

                # Display step header
                col1, col2, col3 = st.columns([1, 3, 2])
                col1.write(f"{status_icon}")
                col2.write(f"**{step.get('operation', 'Unknown operation')}**")

                timestamp = step.get("timestamp")
                if timestamp:
                    col3.caption(timestamp.strftime("%H:%M:%S") if hasattr(timestamp, "strftime") else str(timestamp))

                # Display details
                if step.get("details"):
                    st.caption(f"📝 {step['details']}")

                # Display error if present
                if step.get("error"):
                    st.error(f"❌ Error: {step['error']}")

                # Add spacing between steps
                if i < len(steps):
                    st.divider()


def _render_phase_technical_details(job: dict[str, Any], phase_field: str | None) -> None:
    """Show collapsible technical execution details for the current phase."""
    trace = job.get("execution_trace", [])
    if not trace or not phase_field:
        return

    # Filter trace to steps for this phase (based on phase field mapping)
    phase_name_to_display = {
        "discovery": ["Discover", "Analyse"],
        "plan": ["Plan", "HumanReviewPlan"],
        "schema_translation": ["Transform", "Generate", "CodeRefactor"],
        "data_migration": ["DataMigrate"],
        "validation": ["Validate", "HumanReviewValidation"],
        "test_report": ["Test", "HumanReviewCutover"],
        "deployment": ["Cutover", "Verify"],
    }

    phase_names = phase_name_to_display.get(phase_field, [])
    phase_steps = [s for s in trace if s.get("phase") in phase_names]

    if phase_steps:
        with st.expander("🔧 Technical Details (what's being done behind the scenes)", expanded=False):
            for step in phase_steps:
                status = step.get("status", "SUCCESS")
                status_icon = "✅" if status == "SUCCESS" else "⏳" if status == "IN_PROGRESS" else "❌"
                st.write(f"{status_icon} **{step.get('operation', 'Unknown')}**")
                if step.get("details"):
                    st.caption(f"   {step['details']}")
                if step.get("error"):
                    st.error(f"   Error: {step['error']}")


# Pipeline progress: every completed phase gets its own expander, populated
# directly from the job state (not just whatever happens to ride along with
# the current interrupt payload) so judges can see history after it's approved.
_PHASE_SECTIONS: list[tuple[str, str, Any]] = [
    ("discovery", "🔍 Discovery", _render_discovery),
    ("plan", "📋 Migration Plan", _render_plan_summary),
    ("schema_translation", "🔁 Schema Translation", _render_schema_translation),
    ("data_migration", "📦 Data Migration", _render_data_migration),
    ("validation", "✅ Validation", _render_validation),
    ("test_report", "🧪 Test Report", _render_test_report),
    ("deployment", "🚀 Deployment", _render_deployment),
]

# Orchestrator phase names (orchestrator/graph.py) -> the _PHASE_SECTIONS field
# they belong to, so the active tab can show a "currently running" banner.
_PHASE_NAME_TO_FIELD = {
    "Discover": "discovery",
    "Analyse": "discovery",
    "Plan": "plan",
    "HumanReviewPlan": "plan",
    "Transform": "schema_translation",
    "Generate": "schema_translation",
    "CodeRefactor": "schema_translation",
    "DataMigrate": "data_migration",
    "Validate": "validation",
    "HumanReviewValidation": "validation",
    "Test": "test_report",
    "HumanReviewCutover": "test_report",
    "Cutover": "deployment",
    "Verify": "deployment",
}

st.divider()
st.subheader("Pipeline Progress")

active_field = _PHASE_NAME_TO_FIELD.get(job.get("current_phase", ""))
is_job_active = job["status"] not in {"DONE", "ABORTED", "ROLLED_BACK"}

tab_labels = [label for _, label, _ in _PHASE_SECTIONS] + [
    "📊 Execution Log",
    "🧬 Schema SQL Compare",
    "👤 Review",
    "🕘 History",
]
tabs = st.tabs(tab_labels)

for tab, (field, label, renderer) in zip(tabs, _PHASE_SECTIONS):
    with tab:
        data = job.get(field)
        if is_job_active and field == active_field:
            st.info(f"▶ Currently running: {job['current_phase']}")
        if data:
            renderer(data)
            # Show technical details for this phase
            _render_phase_technical_details(job, field)
        else:
            st.caption("Not reached yet.")

# Add Execution Log tab (first after phase tabs)
exec_log_tab = tabs[len(_PHASE_SECTIONS)]
with exec_log_tab:
    st.subheader("📊 Full Execution Timeline")
    trace = job.get("execution_trace", [])
    if trace:
        st.caption(f"Total steps: {len(trace)}")
        # Add refresh button for the trace
        if st.button("🔄 Refresh trace", key="refresh_trace"):
            st.rerun()
        _render_execution_trace(trace)
    else:
        st.info("No execution steps recorded yet. Steps will appear here as the migration progresses.")

schema_tab, review_tab, history_tab = tabs[-3], tabs[-2], tabs[-1]

with schema_tab:
    st.caption(
        "Live introspection of the ENTIRE source and target databases (every "
        "table/view/procedure/function/trigger, not just migrated objects) — "
        "can be run anytime while the job's connections are still live."
    )
    if st.button("Fetch schema.sql for source & target", key="fetch_schema_sql"):
        try:
            st.session_state["schema_sql"] = _get_schema_sql(job_id)
        except requests.HTTPError as exc:
            detail = exc.response.json().get("detail", str(exc)) if exc.response is not None else str(exc)
            st.error(f"Failed to fetch schema.sql: {detail}")
        except requests.RequestException as exc:
            st.error(f"Failed to fetch schema.sql: {exc}")

    schema_sql = st.session_state.get("schema_sql")
    if schema_sql:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Source schema.sql** ({schema_sql['source_dialect']})")
            st.download_button(
                "Download source schema.sql",
                schema_sql["source_schema_sql"],
                file_name=f"source_{schema_sql['source_dialect']}_schema.sql",
                mime="text/plain",
                key="dl_source_schema",
            )
            st.code(schema_sql["source_schema_sql"], language="sql")
        with col2:
            st.markdown(f"**Target schema.sql** ({schema_sql['target_dialect']})")
            st.download_button(
                "Download target schema.sql",
                schema_sql["target_schema_sql"],
                file_name=f"target_{schema_sql['target_dialect']}_schema.sql",
                mime="text/plain",
                key="dl_target_schema",
            )
            st.code(schema_sql["target_schema_sql"], language="sql")
    else:
        st.info("Click the button above to fetch and compare the full source/target schema.sql.")

with history_tab:
    retry_history = job.get("retry_history", [])
    if retry_history:
        st.write("**Retry history**")
        st.table(retry_history)
    else:
        st.caption("No retries yet.")

    if job["approvals"]:
        st.write("**Approval history**")
        st.table(job["approvals"])
    else:
        st.caption("No approvals yet.")

with review_tab:
    interrupt = job.get("interrupt")
    if interrupt:
        st.subheader(f"Review required: {interrupt.get('phase', interrupt.get('type', 'unknown'))}")
        st.write(interrupt.get("prompt", ""))

        plan = interrupt.get("plan")
        if interrupt.get("type") == "HumanReviewPlan" and plan:
            _render_plan_summary(plan)
            with st.expander("Raw plan JSON"):
                st.json(plan)
        else:
            with st.expander("Details", expanded=True):
                st.json({k: v for k, v in interrupt.items() if k not in {"prompt", "phase", "type"}})

        reviewer = st.text_input("Reviewer name")
        comment = st.text_area("Comment (optional)")
        decision_options = (
            ["retry", "abort"]
            if interrupt.get("type") == "HumanReviewFailure"
            else ["approve", "modify", "reject"]
        )
        cols = st.columns(len(decision_options))
        for col, decision in zip(cols, decision_options):
            if col.button(decision.capitalize(), disabled=not reviewer):
                try:
                    _submit_review(job_id, decision, reviewer, comment)
                    st.success(f"Submitted decision: {decision}")
                    time.sleep(1)
                    st.rerun()
                except requests.RequestException as exc:
                    st.error(f"Failed to submit review: {exc}")
        if not reviewer:
            st.caption("Enter a reviewer name to enable the decision buttons.")
    else:
        st.caption("No review currently pending for this job.")

if st.button("Refresh"):
    st.rerun()

auto_refresh = st.checkbox(
    "Auto-refresh every 5s", value=job["status"] not in {"DONE", "ABORTED", "ROLLED_BACK"}
)
if auto_refresh and job["status"] not in {"DONE", "ABORTED", "ROLLED_BACK"}:
    time.sleep(5)
    st.rerun()
