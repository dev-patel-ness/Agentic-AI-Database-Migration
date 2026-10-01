"""CrackSQL Adapter: hybrid AST + LLM SQL dialect translation (architecture.md §5 Schema Agent).

Wraps the editable ``cracksql`` package (vendor/CrackSQL, patched to use AWS
Bedrock instead of its default OpenAI backend -- see
vendor/CrackSQL/backend/llm_model/implementations.py::BedrockLLM). Prefers
CrackSQL's "local-to-global" hybrid mode (deterministic AST rewriting with
Bedrock Nova Pro resolving ambiguous constructs, validated live against the
real target DB connection) when a target connection is available, and falls
back to a single-shot LLM rewrite otherwise. CrackSQL's own rule-only mode
(pure sqlglot, no LLM) is used as a last-resort fallback if the hybrid/LLM
call raises.

CrackSQL relies on process cwd for its instance/logs directories (Flask app
factory) -- calls are serialized through ``_CRACKSQL_LOCK`` and wrapped in a
temporary chdir into CRACKSQL_HOME so concurrent adapter calls (e.g. multiple
objects translated across threads) don't race on cwd.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from typing import Any, Optional

from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    RollbackResult,
    ToolResult,
)
from tool_adapters.base import JobStatus as AdapterJobStatus

logger = logging.getLogger(__name__)

CRACKSQL_HOME = os.path.dirname(os.path.abspath(__file__))
_CRACKSQL_LOCK = threading.Lock()


@contextmanager
def _cracksql_cwd():
    """CrackSQL's Flask app factory resolves instance/logs/sqlite paths
    relative to process cwd -- pin it to this adapter's directory for the
    duration of the call, serialized so concurrent calls don't race on cwd."""
    os.makedirs(os.path.join(CRACKSQL_HOME, "instance"), exist_ok=True)
    os.makedirs(os.path.join(CRACKSQL_HOME, "logs"), exist_ok=True)
    with _CRACKSQL_LOCK:
        previous = os.getcwd()
        os.chdir(CRACKSQL_HOME)
        try:
            yield
        finally:
            os.chdir(previous)


def _map_connection(connection_config: dict[str, Any], dialect_name: str) -> dict[str, Any]:
    """Map this platform's connection-config shape (host/port/username/
    password/database) to CrackSQL's target_db_config shape (host/port/user/
    password/db_name). For Oracle, `database` must be the service name."""
    return {
        "host": connection_config.get("host", "localhost"),
        "port": str(connection_config.get("port", "")),
        "user": connection_config.get("username", ""),
        "password": connection_config.get("password", ""),
        "db_name": connection_config.get("database", ""),
    }


def _extract_confidences(model_ans_list: list[dict[str, Any]], pattern: str) -> list[float]:
    """Best-effort re-parse of each LLM response's self-reported confidence
    (CrackSQL's own TRANSLATION_ANSWER_PATTERN/JUDGE_ANSWER_PATTERN regex),
    using a safe float() parse -- NOT CrackSQL's internal `eval(confidence)`
    (translator/llm_translator.py), which is an OWASP-relevant injection risk
    since it runs eval() on raw LLM output text."""
    confidences: list[float] = []
    for entry in model_ans_list:
        content = entry.get("content") if isinstance(entry, dict) else None
        if not content:
            continue
        match = re.search(pattern, content, re.DOTALL)
        if not match or match.lastindex is None or match.lastindex < 3:
            continue
        raw = match.group(3).strip().strip('"')
        try:
            confidences.append(float(raw))
        except ValueError:
            continue
    return confidences


class CrackSQLAdapter(BaseToolAdapter):
    """Translates a single SQL/DDL snippet from one dialect to another."""

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.SQL_TRANSLATOR

    @property
    def name(self) -> str:
        return "cracksql_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        required = ("source_dialect", "target_dialect", "source_sql")
        missing = [k for k in required if not config.get(k)]
        if missing:
            raise ValueError(f"cracksql_adapter requires {required}; missing {missing}")
        return AdapterConfig(options=config)

    def run(self, config: AdapterConfig) -> ToolResult:
        start = time.monotonic()
        opts = config.options
        source_dialect: str = opts["source_dialect"]
        target_dialect: str = opts["target_dialect"]
        source_sql: str = opts["source_sql"]
        target_connection: Optional[dict[str, Any]] = opts.get("target_connection")

        try:
            from cracksql.cracksql import translate
            from cracksql.utils.constants import FAILED_TEMPLATE, TRANSLATION_ANSWER_PATTERN
        except Exception as exc:  # pragma: no cover - packaging/environment issue
            return ToolResult(
                success=False,
                error=f"cracksql package unavailable: {exc}",
                execution_time_seconds=time.monotonic() - start,
            )

        model_name = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
        vector_config = {
            "src_kb_name": f"{source_dialect}_knowledge",
            "tgt_kb_name": f"{target_dialect}_knowledge",
        }
        target_db_config = (
            _map_connection(target_connection, target_dialect) if target_connection else None
        )

        try:
            with _cracksql_cwd():
                result = translate(
                    src_sql=source_sql,
                    src_dialect=source_dialect,
                    tgt_dialect=target_dialect,
                    model_name=model_name,
                    target_db_config=target_db_config,
                    vector_config=vector_config,
                    out_dir="./instance/translations",
                    retrieval_on=True,
                    top_k=3,
                    max_retry_time=2,
                )
        except Exception as exc:
            # Hard failure of the hybrid/LLM path (Bedrock outage, KB
            # misconfiguration, etc.) -- fall back to CrackSQL's deterministic
            # sqlglot-only rule_rewrite so the caller always gets *something*
            # rather than blocking the whole batch on one bad object.
            logger.warning(
                "[Hybrid translation FAILED] source_sql=%s (first 100 chars), error: %s",
                source_sql[:100] if source_sql else "?",
                str(exc),
            )
            try:
                with _cracksql_cwd():
                    fallback = translate(
                        src_sql=source_sql, src_dialect=source_dialect, tgt_dialect=target_dialect
                    )
                translated_sql = fallback if isinstance(fallback, str) else fallback[0]
                return ToolResult(
                    success=True,
                    output={
                        "translated_sql": translated_sql,
                        "method": "rule_fallback",
                        "note": f"hybrid translation raised, used rule-only fallback: {exc}",
                    },
                    confidence_score=0.5,
                    execution_time_seconds=time.monotonic() - start,
                )
            except Exception as fallback_exc:
                return ToolResult(
                    success=False,
                    error=f"translate() failed ({exc}); rule fallback also failed ({fallback_exc})",
                    execution_time_seconds=time.monotonic() - start,
                )

        translated_sql, model_ans_list, used_pieces, lift_histories = result

        if translated_sql == FAILED_TEMPLATE:
            # Hybrid validation failed, but if we were using target_db_config,
            # try pure LLM mode (direct_llm without validation) as fallback.
            # Never report confidence 0.0 if we can get *something* usable.
            if target_db_config:
                logger.info(
                    "[Hybrid validation FAILED for %s -> %s] retrying with pure LLM mode (no DB validation)",
                    source_dialect, target_dialect
                )
                try:
                    with _cracksql_cwd():
                        llm_only_result = translate(
                            src_sql=source_sql,
                            src_dialect=source_dialect,
                            tgt_dialect=target_dialect,
                            model_name=model_name,
                            target_db_config=None,  # Pure LLM, no validation
                            vector_config=vector_config,
                            out_dir="./instance/translations",
                            retrieval_on=True,
                            top_k=3,
                            max_retry_time=2,
                        )
                    llm_translated_sql, llm_model_ans_list, llm_used_pieces, llm_lift_histories = llm_only_result
                    if llm_translated_sql and llm_translated_sql != FAILED_TEMPLATE:
                        # Use the LLM-only result but mark it as fallback with confidence penalty
                        confidences = _extract_confidences(llm_model_ans_list, TRANSLATION_ANSWER_PATTERN)
                        if confidences:
                            confidence = sum(confidences) / len(confidences)
                        else:
                            confidence = 0.75
                        confidence = max(0.0, confidence - 0.1 * len(llm_lift_histories))
                        # Penalty for hybrid validation failure
                        confidence = max(0.2, confidence - 0.15)
                        return ToolResult(
                            success=True,
                            output={
                                "translated_sql": llm_translated_sql,
                                "method": "direct_llm_fallback",
                                "note": "hybrid validation failed, using pure LLM result",
                                "used_pieces": len(llm_used_pieces),
                                "lift_count": len(llm_lift_histories),
                            },
                            confidence_score=round(confidence, 4),
                            execution_time_seconds=time.monotonic() - start,
                        )
                except Exception as llm_exc:
                    logger.warning(
                        "[Pure LLM fallback also failed] hybrid failed, LLM fallback raised: %s",
                        str(llm_exc)
                    )
                    # If pure LLM also fails, fall through to rule-only below

            # Last resort: try rule-only fallback if we haven't already
            try:
                with _cracksql_cwd():
                    rule_fallback = translate(
                        src_sql=source_sql, src_dialect=source_dialect, tgt_dialect=target_dialect
                    )
                rule_translated_sql = rule_fallback if isinstance(rule_fallback, str) else rule_fallback[0]
                return ToolResult(
                    success=True,
                    output={
                        "translated_sql": rule_translated_sql,
                        "method": "rule_only_fallback",
                        "note": "hybrid validation failed, using rule-only fallback",
                    },
                    confidence_score=0.5,
                    execution_time_seconds=time.monotonic() - start,
                )
            except Exception as rule_exc:
                logger.error(
                    "[All translation methods exhausted] hybrid FAILED, LLM fallback FAILED, rule fallback FAILED: %s",
                    str(rule_exc)
                )
                return ToolResult(
                    success=False,
                    error=f"All translation methods failed: hybrid returned FAILED_TEMPLATE, LLM fallback failed, rule fallback failed ({rule_exc})",
                    execution_time_seconds=time.monotonic() - start,
                )

        confidences = _extract_confidences(model_ans_list, TRANSLATION_ANSWER_PATTERN)
        if confidences:
            confidence = sum(confidences) / len(confidences)
        elif not model_ans_list or model_ans_list == ["Warning: No piece find"]:
            # No LLM call was needed at all -- source was already compatible.
            confidence = 1.0
        else:
            confidence = 0.75  # LLM was invoked but didn't self-report a parseable confidence
        # Each lift (escalating to a broader SQL fragment after repeated
        # per-piece failures) is a signal the object needed more rework.
        confidence = max(0.0, confidence - 0.05 * len(lift_histories))

        return ToolResult(
            success=True,
            output={
                "translated_sql": translated_sql,
                "method": "local_to_global" if target_db_config else "direct_llm",
                "used_pieces": len(used_pieces),
                "lift_count": len(lift_histories),
            },
            confidence_score=round(confidence, 4),
            execution_time_seconds=time.monotonic() - start,
        )

    def status(self, job_id: str) -> AdapterJobStatus:
        # Translation runs synchronously within run(); nothing long-running to poll.
        return AdapterJobStatus(job_id=job_id, state=ExecutionState.SUCCESS, progress_percent=100)

    def rollback(self, job_id: str) -> RollbackResult:
        # Pure translation, no external side effects (CrackSQL's own target-DB
        # validation queries always end in rollback() -- see
        # vendor/CrackSQL/backend/utils/db_connector.py).
        return RollbackResult(success=True, detail={"note": "SQL translation has no side effects to roll back"})

