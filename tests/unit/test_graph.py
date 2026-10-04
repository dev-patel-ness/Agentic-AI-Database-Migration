"""Unit tests for the LangGraph orchestrator's stub workflow (architecture.md §6)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from orchestrator.graph import (
    _route_after_cutover_review,
    _route_after_plan_review,
    _route_after_test,
    _route_after_validation_review,
    _route_after_verify,
    compile_graph,
)
from orchestrator.state import (
    DeploymentStatus,
    DialectPair,
    MigrationState,
    TestReport as MigrationTestReport,
)


def _make_state(**overrides) -> MigrationState:
    base = {"job_id": "job-1", "dialects": DialectPair(source="oracle", target="postgresql")}
    base.update(overrides)
    return MigrationState(**base)


# --- Routing function unit tests ---------------------------------------------


def test_route_after_plan_review():
    assert _route_after_plan_review(_make_state(plan_decision="approve")) == "Transform"
    assert _route_after_plan_review(_make_state(plan_decision="modify")) == "Plan"
    assert _route_after_plan_review(_make_state(plan_decision="reject")) == "__end__"


def test_route_after_validation_review():
    assert _route_after_validation_review(_make_state(validation_decision="approve")) == "Test"
    assert (
        _route_after_validation_review(_make_state(validation_decision="modify")) == "DataMigrate"
    )
    assert _route_after_validation_review(_make_state(validation_decision="reject")) == "__end__"


def test_route_after_test():
    passing = _make_state(test_report=MigrationTestReport(overall_status="PASS"))
    failing = _make_state(test_report=MigrationTestReport(overall_status="FAIL"))
    assert _route_after_test(passing) == "HumanReviewCutover"
    assert _route_after_test(failing) == "Validate"


def test_route_after_cutover_review():
    assert _route_after_cutover_review(_make_state(cutover_decision="approve")) == "Cutover"
    assert _route_after_cutover_review(_make_state(cutover_decision="reject")) == "__end__"


def test_route_after_verify():
    healthy = _make_state(deployment=DeploymentStatus(status="HEALTHY"))
    unhealthy = _make_state(deployment=DeploymentStatus(status="DEGRADED"))
    assert _route_after_verify(healthy) == "Done"
    assert _route_after_verify(unhealthy) == "Rollback"


# --- Full-graph pause/resume tests (in-memory checkpointer) ------------------


def _job_config(job_id: str) -> dict:
    return {"configurable": {"thread_id": job_id}}


def test_graph_pauses_at_human_review_plan():
    graph = compile_graph(checkpointer=InMemorySaver())
    job_id = str(uuid.uuid4())
    initial = MigrationState(job_id=job_id, dialects=DialectPair(source="mysql", target="oracle"))

    graph.invoke(initial.model_dump(), config=_job_config(job_id))
    snapshot = graph.get_state(_job_config(job_id))

    assert snapshot.values["current_phase"] == "Plan"
    assert snapshot.values["status"] == "PAUSED"
    assert len(snapshot.interrupts) == 1
    assert snapshot.interrupts[0].value["type"] == "HumanReviewPlan"


def _mock_subprocess_run(cmd, **kwargs):
    """Fake successful terraform/kubectl CLI responses, keyed by command."""
    if cmd[0] == "terraform":
        return MagicMock(returncode=0, stdout="Terraform v1.5.0", stderr="")
    if cmd[:3] == ["kubectl", "get", "deployment"]:
        deployment_json = {
            "metadata": {"name": "capstone-app", "generation": "1"},
            "spec": {"replicas": 2, "template": {"spec": {"containers": [{"image": "capstone/app:latest"}]}}},
            "status": {"readyReplicas": 2, "availableReplicas": 2, "updatedReplicas": 2, "conditions": []},
        }
        return MagicMock(returncode=0, stdout=json.dumps(deployment_json), stderr="")
    return MagicMock(returncode=0, stdout="Client Version: v1.28.0", stderr="")


def test_graph_happy_path_reaches_done():
    graph = compile_graph(checkpointer=InMemorySaver())
    job_id = str(uuid.uuid4())
    initial = MigrationState(
        job_id=job_id, dialects=DialectPair(source="postgresql", target="mysql")
    )
    config = _job_config(job_id)

    with patch("tool_adapters.terraform_adapter.terraform.subprocess.run", side_effect=_mock_subprocess_run), \
         patch("tool_adapters.kubectl_adapter.kubectl.subprocess.run", side_effect=_mock_subprocess_run):
        graph.invoke(initial.model_dump(), config=config)
        for _ in range(3):  # HumanReviewPlan -> HumanReviewValidation -> HumanReviewCutover
            graph.invoke(
                Command(resume={"decision": "approve", "reviewer": "test-bot"}), config=config
            )

    snapshot = graph.get_state(config)
    assert snapshot.values["current_phase"] == "Done"
    assert snapshot.values["status"] == "DONE"
    assert not snapshot.interrupts
    assert len(snapshot.values["approvals"]) == 3


def test_graph_reject_at_plan_gate_aborts():
    graph = compile_graph(checkpointer=InMemorySaver())
    job_id = str(uuid.uuid4())
    initial = MigrationState(job_id=job_id, dialects=DialectPair(source="oracle", target="mysql"))
    config = _job_config(job_id)

    graph.invoke(initial.model_dump(), config=config)
    graph.invoke(Command(resume={"decision": "reject", "reviewer": "test-bot"}), config=config)

    snapshot = graph.get_state(config)
    assert snapshot.values["status"] == "ABORTED"
    assert not snapshot.interrupts


def test_graph_modify_at_plan_gate_loops_back_to_plan():
    graph = compile_graph(checkpointer=InMemorySaver())
    job_id = str(uuid.uuid4())
    initial = MigrationState(job_id=job_id, dialects=DialectPair(source="oracle", target="mysql"))
    config = _job_config(job_id)

    graph.invoke(initial.model_dump(), config=config)
    graph.invoke(Command(resume={"decision": "modify", "reviewer": "test-bot"}), config=config)

    snapshot = graph.get_state(config)
    # Looped back through Plan (which sets current_phase="Plan" on its way to
    # pausing again) and is once more waiting at the HumanReviewPlan interrupt.
    assert snapshot.values["current_phase"] == "Plan"
    assert snapshot.values["status"] == "PAUSED"
    assert snapshot.interrupts[0].value["type"] == "HumanReviewPlan"


def test_graph_resumes_correctly_from_a_fresh_checkpointer_instance():
    """Simulates a process restart: a new PostgresSaver/graph instance rehydrates
    from the same checkpoint storage and resumes exactly where it paused."""
    shared_saver = InMemorySaver()  # stands in for the Postgres-backed store
    job_id = str(uuid.uuid4())
    config = _job_config(job_id)
    initial = MigrationState(job_id=job_id, dialects=DialectPair(source="mysql", target="oracle"))

    first_process_graph = compile_graph(checkpointer=shared_saver)
    first_process_graph.invoke(initial.model_dump(), config=config)

    # "Restart": a brand-new compiled graph, same underlying checkpoint store.
    second_process_graph = compile_graph(checkpointer=shared_saver)
    snapshot = second_process_graph.get_state(config)
    assert snapshot.values["current_phase"] == "Plan"
    assert snapshot.interrupts[0].value["type"] == "HumanReviewPlan"

    second_process_graph.invoke(
        Command(resume={"decision": "approve", "reviewer": "test-bot"}), config=config
    )
    resumed_snapshot = second_process_graph.get_state(config)
    assert resumed_snapshot.values["current_phase"] == "Validate"
    assert resumed_snapshot.interrupts[0].value["type"] == "HumanReviewValidation"
