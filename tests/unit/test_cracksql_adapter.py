"""Unit tests for the CrackSQL adapter's confidence-scoring and error-handling
logic (architecture.md §5 Schema Agent). Mocks `cracksql.cracksql.translate`
directly -- these tests never call Bedrock or a real target DB.
"""

from __future__ import annotations

from unittest.mock import patch

from tool_adapters.cracksql_adapter import CrackSQLAdapter, _extract_confidences


def _config(**overrides):
    base = {
        "source_dialect": "oracle",
        "target_dialect": "postgresql",
        "source_sql": "CREATE TABLE t1 (id NUMBER)",
    }
    base.update(overrides)
    return CrackSQLAdapter().prepare(base)


def test_prepare_requires_core_fields():
    import pytest

    with pytest.raises(ValueError):
        CrackSQLAdapter().prepare({"source_dialect": "oracle"})


def test_extract_confidences_parses_valid_pattern():
    pattern = r'"Answer":\s*(.*?)\s*,\s*"Reasoning":\s*(.*?),\s*"Confidence":\s*(.*?)\s'
    model_ans_list = [
        {"content": '{"Answer": "SELECT 1", "Reasoning": "trivial", "Confidence": 0.9 }'},
        {"content": '{"Answer": "SELECT 2", "Reasoning": "trivial", "Confidence": "0.8" }'},
    ]
    assert _extract_confidences(model_ans_list, pattern) == [0.9, 0.8]


def test_extract_confidences_ignores_unparseable_entries():
    pattern = r'"Answer":\s*(.*?)\s*,\s*"Reasoning":\s*(.*?),\s*"Confidence":\s*(.*?)\s'
    model_ans_list = [{"content": "not a match"}, {"role": "user"}]
    assert _extract_confidences(model_ans_list, pattern) == []


def test_run_success_with_parseable_confidence():
    translated = (
        "CREATE TABLE t1 (id INTEGER)",
        [{"content": '{"Answer": "x", "Reasoning": "y", "Confidence": 0.88 }'}],
        [{"piece": "x"}],
        [],
    )
    with patch("cracksql.cracksql.translate", return_value=translated):
        result = CrackSQLAdapter().run(_config())

    assert result.success is True
    assert result.output["translated_sql"] == "CREATE TABLE t1 (id INTEGER)"
    assert result.confidence_score == 0.88


def test_run_marks_failed_template_as_zero_confidence_but_adapter_success():
    from cracksql.utils.constants import FAILED_TEMPLATE

    translated = (FAILED_TEMPLATE, [], [], [])
    with patch("cracksql.cracksql.translate", return_value=translated):
        result = CrackSQLAdapter().run(_config())

    assert result.success is True
    assert result.output["translated_sql"] is None
    assert result.confidence_score == 0.0


def test_run_no_llm_needed_gets_full_confidence():
    translated = ("CREATE TABLE t1 (id INTEGER)", ["Warning: No piece find"], [], [])
    with patch("cracksql.cracksql.translate", return_value=translated):
        result = CrackSQLAdapter().run(_config())

    assert result.confidence_score == 1.0


def test_run_falls_back_to_rule_rewrite_on_hybrid_exception():
    with patch("cracksql.cracksql.translate", side_effect=[RuntimeError("bedrock down"), "CREATE TABLE t1 (id INTEGER)"]):
        result = CrackSQLAdapter().run(_config())

    assert result.success is True
    assert result.output["method"] == "rule_fallback"
    assert result.confidence_score == 0.5


def test_run_reports_failure_when_both_hybrid_and_fallback_raise():
    with patch("cracksql.cracksql.translate", side_effect=RuntimeError("bedrock down")):
        result = CrackSQLAdapter().run(_config())

    assert result.success is False
    assert "bedrock down" in (result.error or "")
