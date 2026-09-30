"""Planner Agent: builds the MigrationPlan from a DiscoveryResult using a
deterministic risk heuristic (risk.py) refined by one bounded Bedrock Nova Pro
call grounded in RAG-retrieved knowledge-base context (architecture.md §5).
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from agents.planner_agent.llm import converse_json
from agents.planner_agent.risk import score_object
from knowledge_base.retrievers.similarity import retrieve
from orchestrator.state import DiscoveryResult, MigrationPlan, ObjectRisk

logger = logging.getLogger(__name__)

_VALID_RISK_LEVELS = {"low", "medium", "high"}
# Bounds prompt size/latency/cost regardless of schema size (plan.md risk:
# "Bedrock cost/rate limits during Phase 4/6 heavy LLM use" applies here too).
_MAX_LLM_CANDIDATES = 30

_SYSTEM_PROMPT = (
    "You are a database migration risk assessor. You are given a list of database "
    "objects flagged by a heuristic as medium or high risk, plus relevant migration "
    "knowledge-base notes. Reply with ONLY a JSON object of this exact shape, no other "
    'text: {"objects": [{"name": "<object name exactly as given>", "risk_level": '
    '"low"|"medium"|"high", "reason": "<one short sentence>"}]}. Include every object '
    "you were given, exactly once, using its exact given name."
)


def _refine_with_llm(
    risk_register: list[ObjectRisk], source_dialect: str, target_dialect: str
) -> list[ObjectRisk]:
    candidates = [r for r in risk_register if r.risk_level in {"medium", "high"}][
        :_MAX_LLM_CANDIDATES
    ]
    if not candidates:
        return risk_register

    try:
        context_docs = retrieve(
            f"migrating {source_dialect} to {target_dialect}: type mapping, syntax "
            "incompatibilities, known migration issues",
            source_dialect=source_dialect,
            target_dialect=target_dialect,
            top_k=5,
        )
        context_text = "\n\n".join(f"- {d['title']}: {d['content']}" for d in context_docs)
    except Exception:
        logger.exception("Planner Agent: KB retrieval failed, continuing without RAG context")
        context_text = ""
    context_text = context_text or "(no knowledge-base context retrieved)"

    object_lines = "\n".join(
        f"- {r.object_type} {r.object_name} (heuristic risk: {r.risk_level})" for r in candidates
    )
    user_prompt = (
        f"Source dialect: {source_dialect}\nTarget dialect: {target_dialect}\n\n"
        f"Knowledge base context:\n{context_text}\n\nObjects to assess:\n{object_lines}"
    )

    try:
        response = converse_json(_SYSTEM_PROMPT, user_prompt)
        refined_by_name = {
            obj["name"]: obj
            for obj in response.get("objects", [])
            if obj.get("risk_level") in _VALID_RISK_LEVELS
        }
    except Exception:
        # LLM refinement is best-effort on top of the deterministic heuristic;
        # never block plan generation over a Bedrock hiccup (same policy as
        # assessment_agent's embedding step).
        logger.exception("Planner Agent: LLM risk refinement failed, keeping heuristic scores")
        return risk_register

    refined_register = []
    for risk in risk_register:
        override = refined_by_name.get(risk.object_name)
        if override:
            refined_register.append(
                ObjectRisk(
                    object_name=risk.object_name,
                    object_type=risk.object_type,
                    risk_level=override["risk_level"],
                    reason=override.get("reason", risk.reason),
                )
            )
        else:
            refined_register.append(risk)
    return refined_register


def build_plan(
    discovery: DiscoveryResult, source_dialect: str, target_dialect: str
) -> MigrationPlan:
    catalog: list[dict[str, Any]] = discovery.object_catalog
    counts = Counter(entry["object_type"] for entry in catalog)

    risk_register = [score_object(entry, source_dialect) for entry in catalog]
    risk_register = _refine_with_llm(risk_register, source_dialect, target_dialect)

    manual_review_objects = [r.object_name for r in risk_register if r.risk_level == "high"]

    return MigrationPlan(
        tables=counts.get("table", 0),
        views=counts.get("view", 0),
        procedures=counts.get("procedure", 0),
        functions=counts.get("function", 0),
        triggers=counts.get("trigger", 0),
        risk_register=risk_register,
        manual_review_objects=manual_review_objects,
    )
