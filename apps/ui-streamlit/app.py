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
        "schema_name": "",
    },
}

st.set_page_config(page_title="Agentic Migration Platform", layout="centered")


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


st.title("Agentic AI-Powered Database Migration Platform")

with st.expander("Create a new migration job", expanded="job_id" not in st.session_state):
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

# Validation progress display (Phase 7)
validation_report = job.get("validation")
if validation_report:
    st.divider()
    st.subheader("Data Validation Progress")
    
    checksums = validation_report.get("table_checksums", [])
    total_tables = len(checksums)
    passed_tables = sum(1 for cs in checksums if cs.get("status") == "MATCH")
    
    if total_tables > 0:
        st.metric("Validation Progress", f"{passed_tables}/{total_tables} tables")
        
        # Checksum match rate bar
        match_rate = (passed_tables / total_tables) * 100
        st.progress(match_rate / 100.0, text=f"Checksum Match Rate: {match_rate:.1f}%")
        
        # Show mismatches if any
        mismatches = validation_report.get("mismatches", 0)
        if mismatches > 0:
            st.warning(f"⚠️ {mismatches} table(s) with checksum mismatches detected")
            
            # List tables with issues
            mismatch_tables = [cs for cs in checksums if cs.get("status") != "MATCH"]
            if mismatch_tables:
                with st.expander(f"Mismatched tables ({len(mismatch_tables)})"):
                    for table_result in mismatch_tables:
                        col1, col2, col3 = st.columns(3)
                        col1.write(f"**{table_result.get('table_name')}**")
                        col2.write(f"Status: {table_result.get('status')}")
                        if table_result.get("checksum_source"):
                            col3.write(f"Checksum: {table_result['checksum_source'][:8]}...")
        else:
            st.success("✅ All tables validated successfully")
    
    # Show retry history if available
    retry_history = job.get("retry_history", [])
    if retry_history:
        migrate_retries = [r for r in retry_history if r.get("phase") == "DataMigrate"]
        if migrate_retries:
            st.info(f"Data Migration Retries: {len(migrate_retries)}/2 attempts used")

if job["approvals"]:
    st.write("**Approval history**")
    st.table(job["approvals"])

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


interrupt = job.get("interrupt")
if interrupt:
    st.divider()
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
    "Auto-refresh every 2s", value=job["status"] not in {"DONE", "ABORTED", "ROLLED_BACK"}
)
if auto_refresh and job["status"] not in {"DONE", "ABORTED", "ROLLED_BACK"}:
    time.sleep(2)
    st.rerun()
