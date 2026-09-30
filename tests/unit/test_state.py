"""Unit tests for the MigrationState schema (architecture.md §7)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from orchestrator.state import DialectPair, JobStatus, MigrationState


def test_migration_state_defaults():
    state = MigrationState(job_id="job-1", dialects=DialectPair(source="oracle", target="mysql"))

    assert state.current_phase == "Discover"
    assert state.status == JobStatus.RUNNING.value
    assert state.retry_count == 0
    assert state.max_retries == 3
    assert state.approvals == []
    assert state.plan is None


def test_migration_state_requires_job_id_and_dialects():
    with pytest.raises(ValidationError):
        MigrationState()  # type: ignore[call-arg]
