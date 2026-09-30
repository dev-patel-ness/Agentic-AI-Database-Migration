"""In-process registry for DB connection credentials, kept deliberately OUT of
the LangGraph checkpointed state (architecture.md §14: secrets are never
stored in state or logs). Later phases (Transform/Generate's Schema Agent,
DataMigrate, Validate) all need live source/target connection info, so the
registry is kept for a job's whole in-process lifetime and discarded only at
a terminal state (Done/Aborted/RolledBack) -- see graph.py's `_done`,
`_rollback`, and the reviewer-REJECT branches of the HumanReview* nodes.

Trade-off: if the API process restarts while a job is paused at a human
review gate (or mid-phase), connection config is lost even though the
LangGraph checkpoint itself survives -- the job must be recreated. Accepted
for this deployment (same trade-off Phase 2 already made for Discover alone;
this just extends the window to cover later phases that also need DB access).
"""

from __future__ import annotations

import threading
from typing import Any, Optional

_lock = threading.Lock()
_connections: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}


def register(
    job_id: str, source_connection: dict[str, Any], target_connection: dict[str, Any]
) -> None:
    with _lock:
        _connections[job_id] = (source_connection, target_connection)


def get(job_id: str) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
    with _lock:
        return _connections.get(job_id)


def discard(job_id: str) -> None:
    with _lock:
        _connections.pop(job_id, None)
