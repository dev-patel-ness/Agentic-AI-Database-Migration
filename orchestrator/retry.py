"""Bounded-retry wrapper for LangGraph nodes (architecture.md §6.1).

Wraps a node function so that raised exceptions (LLM call failures, tool-adapter
errors, timeouts, malformed output) are retried in-process up to
``state.max_retries`` attempts. Once exhausted, it raises a
``HumanReviewFailure`` interrupt so a reviewer can choose to retry (resets the
attempt count and re-runs the node) or abort the job.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from langgraph.types import interrupt

from orchestrator.state import JobStatus, MigrationState

logger = logging.getLogger(__name__)

NodeFn = Callable[[MigrationState], dict[str, Any]]


def with_retry(phase: str, node_fn: NodeFn, backoff_seconds: float = 0.0) -> NodeFn:
    """Return a node function that retries ``node_fn`` on exception before escalating.

    On final failure, raises a ``HumanReviewFailure``-style interrupt carrying the
    phase name and error message; the reviewer's resume payload must include
    ``{"decision": "retry"}`` (re-run from scratch) or anything else (treated as abort).
    """

    def run(state: MigrationState) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(state.max_retries):
            try:
                result = node_fn(state)
                result.setdefault("retry_count", 0)
                return result
            except Exception as exc:  # noqa: BLE001 - any node failure is retryable here
                last_exc = exc
                logger.warning(
                    "Phase %s failed (attempt %d/%d): %s",
                    phase,
                    attempt + 1,
                    state.max_retries,
                    exc,
                )
                if backoff_seconds:
                    time.sleep(backoff_seconds * (2**attempt))

        logger.error("Phase %s exhausted %d retries: %s", phase, state.max_retries, last_exc)
        decision = interrupt(
            {
                "type": "HumanReviewFailure",
                "phase": phase,
                "error": str(last_exc),
            }
        )
        if isinstance(decision, dict) and decision.get("decision") == "retry":
            return run(state)
        return {"status": JobStatus.ABORTED.value}

    return run
