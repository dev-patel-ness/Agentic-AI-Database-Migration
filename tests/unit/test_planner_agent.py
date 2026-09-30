"""Unit tests for the Planner Agent's deterministic risk heuristic and the
LLM-refinement merge logic (architecture.md §5 Planner Agent). Bedrock and the
knowledge base are mocked -- these tests exercise pure logic only.
"""

from __future__ import annotations

from unittest.mock import patch

from agents.planner_agent import build_plan
from agents.planner_agent.risk import score_object
from orchestrator.state import DiscoveryResult, ObjectRisk


def test_score_object_table_low_risk_by_default():
    entry = {"object_type": "table", "name": "employees", "columns": [{"native_type": "VARCHAR2"}]}
    risk = score_object(entry, "oracle")
    assert risk.risk_level == "low"
    assert risk.reason is None


def test_score_object_table_high_risk_for_vendor_specific_column_type():
    entry = {
        "object_type": "table",
        "name": "documents",
        "columns": [{"native_type": "CLOB"}, {"native_type": "NUMBER(10,2)"}],
    }
    risk = score_object(entry, "oracle")
    assert risk.risk_level == "high"
    assert "CLOB" in (risk.reason or "")


def test_score_object_procedure_defaults_high():
    entry = {"object_type": "procedure", "name": "recalc_totals"}
    risk = score_object(entry, "mysql")
    assert risk.risk_level == "high"


def test_score_object_view_defaults_medium():
    entry = {"object_type": "view", "name": "active_customers"}
    risk = score_object(entry, "postgresql")
    assert risk.risk_level == "medium"


def _discovery_with(catalog: list[dict]) -> DiscoveryResult:
    return DiscoveryResult(object_catalog=catalog, dependency_graph={})


def test_build_plan_counts_objects_by_type():
    discovery = _discovery_with(
        [
            {"object_type": "table", "name": "t1", "columns": []},
            {"object_type": "table", "name": "t2", "columns": []},
            {"object_type": "view", "name": "v1"},
            {"object_type": "procedure", "name": "p1"},
        ]
    )
    with patch("agents.planner_agent._refine_with_llm", side_effect=lambda reg, *_: reg):
        plan = build_plan(discovery, "oracle", "postgresql")

    assert plan.tables == 2
    assert plan.views == 1
    assert plan.procedures == 1
    assert plan.functions == 0
    assert plan.triggers == 0


def test_build_plan_manual_review_objects_are_high_risk_only():
    discovery = _discovery_with(
        [
            {"object_type": "table", "name": "t1", "columns": []},
            {"object_type": "procedure", "name": "p1"},
        ]
    )
    with patch("agents.planner_agent._refine_with_llm", side_effect=lambda reg, *_: reg):
        plan = build_plan(discovery, "oracle", "postgresql")

    assert plan.manual_review_objects == ["p1"]


def test_build_plan_skips_llm_refinement_when_no_medium_or_high_risk_objects():
    discovery = _discovery_with([{"object_type": "table", "name": "t1", "columns": []}])
    with patch("agents.planner_agent.converse_json") as mock_llm:
        plan = build_plan(discovery, "oracle", "postgresql")
    mock_llm.assert_not_called()
    assert plan.manual_review_objects == []


def test_build_plan_falls_back_to_heuristic_when_llm_fails():
    discovery = _discovery_with([{"object_type": "procedure", "name": "p1"}])
    with patch("agents.planner_agent.retrieve", return_value=[]), patch(
        "agents.planner_agent.converse_json", side_effect=RuntimeError("bedrock unavailable")
    ):
        plan = build_plan(discovery, "oracle", "postgresql")

    assert plan.manual_review_objects == ["p1"]
    assert plan.risk_register[0].risk_level == "high"


def test_build_plan_applies_llm_override():
    discovery = _discovery_with([{"object_type": "view", "name": "v1"}])
    llm_response = {"objects": [{"name": "v1", "risk_level": "high", "reason": "uses ROWNUM"}]}
    with patch("agents.planner_agent.retrieve", return_value=[]), patch(
        "agents.planner_agent.converse_json", return_value=llm_response
    ):
        plan = build_plan(discovery, "oracle", "postgresql")

    assert plan.risk_register[0].risk_level == "high"
    assert plan.risk_register[0].reason == "uses ROWNUM"
    assert plan.manual_review_objects == ["v1"]


def test_build_plan_ignores_llm_override_with_invalid_risk_level():
    discovery = _discovery_with([{"object_type": "view", "name": "v1"}])
    llm_response = {"objects": [{"name": "v1", "risk_level": "critical", "reason": "bad value"}]}
    with patch("agents.planner_agent.retrieve", return_value=[]), patch(
        "agents.planner_agent.converse_json", return_value=llm_response
    ):
        plan = build_plan(discovery, "oracle", "postgresql")

    # invalid enum value from the model is dropped -- heuristic score kept.
    assert plan.risk_register[0].risk_level == "medium"


def test_object_risk_reason_is_optional():
    risk = ObjectRisk(object_name="t1", object_type="table", risk_level="low")
    assert risk.reason is None
