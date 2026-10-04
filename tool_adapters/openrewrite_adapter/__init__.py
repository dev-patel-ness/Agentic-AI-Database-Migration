"""OpenRewrite adapter stub — Phase 6 future extension (architecture.md §5, §17).

This adapter is intentionally left as a stub. The ``CodeRefactor`` node in
``orchestrator/graph.py`` is a no-op passthrough until Phase 6 is activated.

When implemented, this adapter will invoke the OpenRewrite CLI to apply
AST-based recipes that swap ORM/JDBC dialect and driver dependencies in
Java/Spring application repositories.

See docs/architecture.md §17 (Future Extension) for scope and design notes.
"""

from __future__ import annotations

from tool_adapters.base import (
    AdapterConfig,
    AdapterType,
    BaseToolAdapter,
    ExecutionState,
    JobStatus,
    RollbackResult,
    ToolResult,
)
from typing import Any


class OpenRewriteAdapter(BaseToolAdapter):
    """Stub: AST-based Java/Spring code refactoring via the OpenRewrite CLI.

    Not yet implemented — Phase 6 future extension.
    """

    @property
    def adapter_type(self) -> AdapterType:
        return AdapterType.CODE_REFACTORER

    @property
    def name(self) -> str:
        return "openrewrite_adapter"

    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        return AdapterConfig(options=config)

    def run(self, config: AdapterConfig) -> ToolResult:
        return ToolResult(
            success=False,
            error="OpenRewriteAdapter is not yet implemented (Phase 6 future extension).",
        )

    def status(self, job_id: str) -> JobStatus:
        return JobStatus(job_id=job_id, state=ExecutionState.PENDING)

    def rollback(self, job_id: str) -> RollbackResult:
        return RollbackResult(success=False, detail={"note": "Not implemented"})
