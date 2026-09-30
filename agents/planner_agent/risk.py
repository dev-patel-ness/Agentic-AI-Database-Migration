"""Deterministic risk-scoring heuristic for discovered database objects.

This is the rule-based baseline the Planner Agent's LLM step (llm.py) then
refines with RAG context -- architecture.md §16 notes the formal risk-scoring
rubric is still an open question, so this starts simple and stays inspectable.
"""

from __future__ import annotations

from typing import Any, Optional

from orchestrator.state import ObjectRisk

# Executable/procedural logic is inherently harder to translate across dialects
# than passive schema objects, regardless of target dialect -- see the
# "Risk-scoring guidance" KB doc (knowledge_base/ingestion/documents.py).
_DEFAULT_RISK_BY_TYPE = {
    "table": "low",
    "view": "medium",
    "procedure": "high",
    "function": "high",
    "trigger": "high",
    "foreign_key": "medium",
}

# Column native types with no direct equivalent in the other two dialects --
# a seed list, not exhaustive (see the per-pair type_mapping KB docs).
_RISKY_COLUMN_TYPES = {
    "oracle": {"CLOB", "BLOB", "LONG", "LONG RAW", "RAW", "XMLTYPE", "ROWID", "UROWID", "BFILE"},
    "mysql": {"ENUM", "SET", "YEAR", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB", "GEOMETRY", "POINT"},
    "postgresql": {
        "JSONB",
        "JSON",
        "ARRAY",
        "HSTORE",
        "TSVECTOR",
        "XML",
        "CIDR",
        "INET",
        "MACADDR",
    },
}


def _table_risk(entry: dict[str, Any], source_dialect: str) -> tuple[str, Optional[str]]:
    risky_types = _RISKY_COLUMN_TYPES.get(source_dialect, set())
    hits = sorted(
        {
            col["native_type"].split("(")[0].strip().upper()
            for col in entry.get("columns", [])
            if col.get("native_type")
            and col["native_type"].split("(")[0].strip().upper() in risky_types
        }
    )
    if hits:
        return (
            "high",
            f"columns use vendor-specific type(s) with no direct equivalent: {', '.join(hits)}",
        )
    return "low", None


def score_object(entry: dict[str, Any], source_dialect: str) -> ObjectRisk:
    """Score a single object-catalog entry (tool_adapters/schema_extractor_adapter output)."""
    object_type = entry["object_type"]
    if object_type == "table":
        risk_level, reason = _table_risk(entry, source_dialect)
    else:
        risk_level = _DEFAULT_RISK_BY_TYPE.get(object_type, "medium")
        reason = f"{object_type} definitions typically require manual translation review"
    return ObjectRisk(
        object_name=entry["name"],
        object_type=object_type,
        risk_level=risk_level,
        reason=reason,
    )
