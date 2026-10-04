"""Aider adapter stub — Phase 6 future extension (architecture.md §5, §17).

This adapter is intentionally left as a stub. The ``CodeRefactor`` node in
``orchestrator/graph.py`` is a no-op passthrough until Phase 6 is activated.

When implemented, this adapter will invoke the Aider CLI to perform
LLM-guided edits on Python/C++ application code — translating raw SQL strings,
SQLAlchemy connection strings, and ORM configurations from the source dialect
to the target dialect.

See docs/architecture.md §17 (Future Extension) for scope and design notes.
"""

from __future__ import annotations

from typing import Any

from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    JobStatus,
    RollbackResult,
    ToolResult,
)


class AiderAdapter(BaseToolAdapter):
    """Stub: LLM-guided code editing via the Aider CLI.

    Not yet implemented — Phase 6 future extension.
    """

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.CODE_REFACTORER

    @property
    def name(self) -> str:
        return "aider_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        return AdapterConfig(options=config)

    def run(self, config: AdapterConfig) -> ToolResult:
        return ToolResult(
            success=False,
            error="AiderAdapter is not yet implemented (Phase 6 future extension).",
        )

    def status(self, job_id: str) -> JobStatus:
        return JobStatus(job_id=job_id, state=ExecutionState.PENDING)

    def rollback(self, job_id: str) -> RollbackResult:
        return RollbackResult(success=False, detail={"note": "Not implemented"})
