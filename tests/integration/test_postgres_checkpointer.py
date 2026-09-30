"""Integration test: real Postgres-backed checkpointer proves pause/resume across
separate process/graph instances (Phase 1 DoD). Requires `docker compose up
postgres-metadata` (see docker-compose.yml) and the POSTGRES_METADATA_* env vars.
"""

from __future__ import annotations

import uuid

import pytest
from langgraph.types import Command

from orchestrator.checkpointer import build_checkpointer, build_checkpointer_pool
from orchestrator.graph import compile_graph
from orchestrator.state import DialectPair, MigrationState


@pytest.fixture()
def checkpointer_pool():
    pool = build_checkpointer_pool(min_size=1, max_size=2)
    try:
        pool.wait(timeout=5)
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means "skip"
        pool.close()
        pytest.skip(f"postgres-metadata is not reachable: {exc}")
    yield pool
    pool.close()


def _job_config(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id}}


def test_postgres_checkpoint_survives_new_graph_instance(checkpointer_pool):
    job_id = str(uuid.uuid4())
    config = _job_config(job_id)
    initial = MigrationState(job_id=job_id, dialects=DialectPair(source="oracle", target="mysql"))

    checkpointer_a = build_checkpointer(checkpointer_pool)
    graph_a = compile_graph(checkpointer=checkpointer_a)
    graph_a.invoke(initial.model_dump(), config=config)

    snapshot = graph_a.get_state(config)
    assert snapshot.values["current_phase"] == "Plan"
    assert snapshot.values["status"] == "PAUSED"
    assert snapshot.interrupts[0].value["type"] == "HumanReviewPlan"

    # A brand-new checkpointer/graph (as if the app process restarted) backed by
    # the same Postgres pool must rehydrate the identical paused state.
    checkpointer_b = build_checkpointer(checkpointer_pool)
    graph_b = compile_graph(checkpointer=checkpointer_b)
    rehydrated = graph_b.get_state(config)
    assert rehydrated.values["current_phase"] == "Plan"
    assert rehydrated.interrupts[0].value["type"] == "HumanReviewPlan"

    graph_b.invoke(Command(resume={"decision": "approve", "reviewer": "test-bot"}), config=config)
    resumed = graph_b.get_state(config)
    assert resumed.values["current_phase"] == "Validate"
    assert resumed.values["approvals"][0]["decision"] == "approve"
