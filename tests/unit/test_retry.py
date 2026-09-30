"""Unit tests for the bounded-retry wrapper (architecture.md §6.1)."""

from __future__ import annotations

from unittest.mock import patch

from orchestrator.retry import with_retry
from orchestrator.state import DialectPair, JobStatus, MigrationState


def _make_state(retry_count: int = 0, max_retries: int = 3) -> MigrationState:
    return MigrationState(
        job_id="job-1",
        dialects=DialectPair(source="oracle", target="postgresql"),
        retry_count=retry_count,
        max_retries=max_retries,
    )


def test_with_retry_succeeds_without_retrying():
    calls = []

    def node_fn(state: MigrationState) -> dict:
        calls.append(1)
        return {"current_phase": "Transform"}

    result = with_retry("Transform", node_fn)(_make_state())

    assert result == {"current_phase": "Transform", "retry_count": 0}
    assert len(calls) == 1


def test_with_retry_retries_then_succeeds():
    calls = []

    def node_fn(state: MigrationState) -> dict:
        calls.append(1)
        if len(calls) < 2:
            raise RuntimeError("transient failure")
        return {"current_phase": "Transform"}

    result = with_retry("Transform", node_fn)(_make_state())

    assert result["retry_count"] == 0
    assert len(calls) == 2


def test_with_retry_escalates_and_aborts_on_reject_decision():
    def node_fn(state: MigrationState) -> dict:
        raise RuntimeError("always fails")

    with patch(
        "orchestrator.retry.interrupt", return_value={"decision": "abort"}
    ) as mock_interrupt:
        result = with_retry("Transform", node_fn)(_make_state(max_retries=2))

    assert result == {"status": JobStatus.ABORTED.value}
    mock_interrupt.assert_called_once()
    payload = mock_interrupt.call_args.args[0]
    assert payload == {"type": "HumanReviewFailure", "phase": "Transform", "error": "always fails"}


def test_with_retry_escalates_and_re_runs_on_retry_decision():
    attempts = {"count": 0}

    def node_fn(state: MigrationState) -> dict:
        attempts["count"] += 1
        if attempts["count"] <= 2:
            raise RuntimeError("fails until the reviewer retries")
        return {"current_phase": "Transform"}

    with patch("orchestrator.retry.interrupt", return_value={"decision": "retry"}):
        result = with_retry("Transform", node_fn)(_make_state(max_retries=2))

    assert result["current_phase"] == "Transform"
    assert attempts["count"] == 3  # 2 failing attempts + 1 successful retry
