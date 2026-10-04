"""Code Agent: application code refactoring for dialect migration (architecture.md §5, §8.4).

Orchestrates two tool adapters based on the detected application stack:
- **Java/Spring** → ``OpenRewriteAdapter`` (AST-based, deterministic recipe)
- **Python / C++** → ``AiderAdapter`` (LLM-guided edits via Aider CLI)

Scope (Phase 6 — future extension)
------------------------------------
The ``CodeRefactor`` node in ``orchestrator/graph.py`` currently calls
``refactor_code()`` as a no-op passthrough.  When Phase 6 is activated,
replace the no-op with a real call to this module.

The agent is intentionally designed to be *best-effort*: if neither adapter
is available (tools not installed) or the repo path is not configured, it logs
a warning and returns an empty ``CodeRefactorResult`` so the graph can continue
to the ``DataMigrate`` phase without blocking.

Usage (from graph node)
-----------------------
    from agents.code_agent import refactor_code
    from orchestrator.state import MigrationState

    result = refactor_code(state)
    # result is a dict with "code_refactor" key containing CodeRefactorResult
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from orchestrator.state import CodeRefactorResult, MigrationState

logger = logging.getLogger(__name__)

# Environment variable that points to the application repository to refactor.
# Must be set when Phase 6 is activated; intentionally optional so local dev
# and earlier phases are unaffected.
_APP_REPO_ENV_VAR = "APP_REPO_PATH"


def refactor_code(state: MigrationState) -> dict[str, Any]:
    """LangGraph node: refactor application code for the target dialect.

    Detects the application stack from ``APP_REPO_PATH`` and dispatches to
    the appropriate adapter.  Returns a partial-state dict suitable for
    LangGraph node return values.

    Args:
        state: Current migration state (provides source/target dialect info).

    Returns:
        Dict with ``"code_refactor"`` key containing a ``CodeRefactorResult``.
    """
    source_dialect = state.dialects.source
    target_dialect = state.dialects.target

    repo_path_str = os.getenv(_APP_REPO_ENV_VAR, "")
    if not repo_path_str:
        logger.warning(
            "Code Agent: %s not set — skipping code refactor (Phase 6 not activated)",
            _APP_REPO_ENV_VAR,
        )
        return {
            "code_refactor": CodeRefactorResult(
                files_changed=[],
                diff=None,
            ).model_dump(),
            "current_phase": "CodeRefactor",
        }

    repo_path = Path(repo_path_str)
    if not repo_path.exists():
        logger.warning(
            "Code Agent: repo_path '%s' does not exist — skipping code refactor",
            repo_path,
        )
        return {
            "code_refactor": CodeRefactorResult(
                files_changed=[],
                diff=None,
            ).model_dump(),
            "current_phase": "CodeRefactor",
        }

    # Detect application stack and dispatch to the correct adapter.
    stack = _detect_app_stack(repo_path)
    logger.info(
        "Code Agent: detected stack=%s, running %s -> %s refactor in %s",
        stack,
        source_dialect,
        target_dialect,
        repo_path,
    )

    if stack == "java":
        result = _run_openrewrite(repo_path_str, source_dialect, target_dialect)
    else:
        # Python, C++, or unknown — use Aider.
        result = _run_aider(repo_path_str, source_dialect, target_dialect)

    files_changed: list[str] = result.output.get("files_changed", []) if result.success else []
    diff: str | None = result.output.get("diff") if result.success else result.error

    if result.success:
        logger.info(
            "Code Agent: refactor complete — %d files changed",
            len(files_changed),
        )
    else:
        logger.warning(
            "Code Agent: refactor failed (non-blocking) — %s",
            result.error,
        )

    return {
        "code_refactor": CodeRefactorResult(
            files_changed=files_changed,
            diff=diff,
        ).model_dump(),
        "current_phase": "CodeRefactor",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_app_stack(repo_path: Path) -> str:
    """Heuristically detect the application stack from the repository layout.

    Returns ``"java"`` if a Maven ``pom.xml`` or Gradle ``build.gradle`` is
    found at the root; otherwise returns ``"python"`` (covers Python, C++, and
    any other language handled by Aider).
    """
    if (repo_path / "pom.xml").exists() or (repo_path / "build.gradle").exists():
        return "java"
    return "python"


def _run_openrewrite(repo_path: str, source_dialect: str, target_dialect: str) -> Any:
    """Dispatch to OpenRewriteAdapter for Java/Spring repositories."""
    from tool_adapters.openrewrite_adapter import OpenRewriteAdapter

    adapter = OpenRewriteAdapter()
    try:
        config = adapter.prepare({
            "repo_path": repo_path,
            "source_dialect": source_dialect,
            "target_dialect": target_dialect,
        })
        return adapter.run(config)
    except Exception as exc:
        logger.warning("Code Agent (OpenRewrite): prepare/run failed: %s", exc)
        from tool_adapters.base import ToolResult
        return ToolResult(success=False, error=str(exc))


def _run_aider(repo_path: str, source_dialect: str, target_dialect: str) -> Any:
    """Dispatch to AiderAdapter for Python/C++ repositories."""
    from tool_adapters.aider_adapter import AiderAdapter

    adapter = AiderAdapter()
    try:
        config = adapter.prepare({
            "repo_path": repo_path,
            "source_dialect": source_dialect,
            "target_dialect": target_dialect,
        })
        return adapter.run(config)
    except Exception as exc:
        logger.warning("Code Agent (Aider): prepare/run failed: %s", exc)
        from tool_adapters.base import ToolResult
        return ToolResult(success=False, error=str(exc))
