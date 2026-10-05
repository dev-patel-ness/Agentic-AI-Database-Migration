"""LangSmith tracing integration for the migration platform (architecture.md §13).

Wraps every LangGraph agent node, tool adapter call, and Bedrock LLM invocation
with a LangSmith run so prompt/tokens/latency/cost are captured per-job.

Usage
-----
    from observability.langsmith.tracer import get_tracer

    tracer = get_tracer()

    @tracer.trace_agent("planner_agent")
    def build_plan(state: MigrationState) -> dict:
        ...

    @tracer.trace_tool("cracksql_adapter")
    def run_translation(config: AdapterConfig) -> ToolResult:
        ...

    @tracer.trace_llm_call("amazon.nova-pro-v1:0")
    def call_bedrock(prompt: str) -> LLMResponse:
        ...
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# Graceful degradation: LangSmith is optional — platform works without it.
try:
    from langsmith import Client as LangSmithClient

    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    LangSmithClient = None  # type: ignore[assignment,misc]


# Module-level singleton so all agents share one tracer instance.
_tracer_instance: Optional["LangSmithTracer"] = None


def get_tracer(
    project_name: str | None = None,
    api_key: str | None = None,
) -> "LangSmithTracer":
    """Return the module-level singleton tracer (creates it on first call)."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = LangSmithTracer(
            project_name=project_name or os.getenv("LANGSMITH_PROJECT", "migration-platform"),
            api_key=api_key,
        )
    return _tracer_instance


class LangSmithTracer:
    """Decorator-based LangSmith tracer for agents, tools, and LLM calls.

    All decorators are no-ops when LangSmith is unavailable or when
    ``LANGSMITH_TRACING_ENABLED`` is not ``"true"`` — the wrapped function
    executes normally without any tracing overhead.
    """

    def __init__(
        self,
        project_name: str = "migration-platform",
        api_key: str | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.project_name = project_name
        # Stack of active run IDs for parent-child nesting (thread-local would
        # be safer in multi-threaded servers, but LangGraph runs are
        # single-threaded per job so a list is sufficient here).
        self.active_run_stack: list[str] = []

        self.client: Any = None
        self._enabled = (
            LANGSMITH_AVAILABLE
            and os.getenv("LANGSMITH_TRACING_ENABLED", "false").lower() == "true"
        )

        if self._enabled:
            try:
                self.client = LangSmithClient(
                    api_key=api_key or os.getenv("LANGSMITH_API_KEY"),
                    api_url=endpoint or os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
                )
                logger.info("LangSmith tracing enabled (project=%s)", project_name)
            except Exception as exc:
                logger.warning("LangSmith client init failed (%s) — tracing disabled", exc)
                self._enabled = False
                self.client = None

    # ------------------------------------------------------------------
    # Public decorator API
    # ------------------------------------------------------------------

    def trace_agent(
        self,
        agent_name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Callable:
        """Decorator: trace a LangGraph agent node function."""

        def decorator(fn: Callable) -> Callable:
            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self._run_async(
                        fn, args, kwargs,
                        run_name=f"{agent_name}::{fn.__name__}",
                        run_type="chain",
                        base_tags=["agent", agent_name] + (tags or []),
                        extra_metadata={"agent": agent_name, **(metadata or {})},
                    )
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return self._run_sync(
                        fn, args, kwargs,
                        run_name=f"{agent_name}::{fn.__name__}",
                        run_type="chain",
                        base_tags=["agent", agent_name] + (tags or []),
                        extra_metadata={"agent": agent_name, **(metadata or {})},
                    )
                return sync_wrapper

        return decorator

    def trace_tool(
        self,
        tool_name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Callable:
        """Decorator: trace a tool adapter ``run()`` call."""

        def decorator(fn: Callable) -> Callable:
            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self._run_async(
                        fn, args, kwargs,
                        run_name=f"{tool_name}::{fn.__name__}",
                        run_type="tool",
                        base_tags=["tool", tool_name] + (tags or []),
                        extra_metadata={"tool": tool_name, **(metadata or {})},
                        capture_tool_result=True,
                    )
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return self._run_sync(
                        fn, args, kwargs,
                        run_name=f"{tool_name}::{fn.__name__}",
                        run_type="tool",
                        base_tags=["tool", tool_name] + (tags or []),
                        extra_metadata={"tool": tool_name, **(metadata or {})},
                        capture_tool_result=True,
                    )
                return sync_wrapper

        return decorator

    def trace_llm_call(
        self,
        model_name: str,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Callable:
        """Decorator: trace a Bedrock LLM invocation (captures tokens + latency)."""

        def decorator(fn: Callable) -> Callable:
            if asyncio.iscoroutinefunction(fn):
                @functools.wraps(fn)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return await self._run_async(
                        fn, args, kwargs,
                        run_name=f"llm::{model_name}",
                        run_type="llm",
                        base_tags=["llm", model_name] + (tags or []),
                        extra_metadata={"model": model_name, **(metadata or {})},
                        capture_llm_tokens=True,
                    )
                return async_wrapper
            else:
                @functools.wraps(fn)
                def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                    return self._run_sync(
                        fn, args, kwargs,
                        run_name=f"llm::{model_name}",
                        run_type="llm",
                        base_tags=["llm", model_name] + (tags or []),
                        extra_metadata={"model": model_name, **(metadata or {})},
                        capture_llm_tokens=True,
                    )
                return sync_wrapper

        return decorator

    # ------------------------------------------------------------------
    # Internal execution helpers
    # ------------------------------------------------------------------

    def _run_sync(
        self,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        run_name: str,
        run_type: str,
        base_tags: list[str],
        extra_metadata: dict[str, Any],
        capture_tool_result: bool = False,
        capture_llm_tokens: bool = False,
    ) -> Any:
        """Execute ``fn`` synchronously, creating a LangSmith run around it."""
        if self.client is None:
            return fn(*args, **kwargs)

        start_time = datetime.now(timezone.utc)
        start = time.perf_counter()
        error: str | None = None
        result: Any = None
        run_tags = list(base_tags)

        try:
            result = fn(*args, **kwargs)
            if capture_tool_result and hasattr(result, "success"):
                run_tags.append("success" if result.success else "failure")
            return result
        except Exception as exc:
            error = str(exc)
            run_tags.append("error")
            raise
        finally:
            duration = time.perf_counter() - start
            run_meta = {**extra_metadata, "duration_seconds": duration}
            if capture_llm_tokens and result is not None:
                run_meta["tokens_input"] = getattr(result, "tokens_input", 0)
                run_meta["tokens_output"] = getattr(result, "tokens_output", 0)

            self._submit_run(
                name=run_name,
                run_type=run_type,
                tags=self._build_tags(run_tags, extra_metadata),
                metadata=run_meta,
                error=error,
                start_time=start_time,
                outputs=result if error is None else None,
            )

    async def _run_async(
        self,
        fn: Callable,
        args: tuple,
        kwargs: dict,
        run_name: str,
        run_type: str,
        base_tags: list[str],
        extra_metadata: dict[str, Any],
        capture_tool_result: bool = False,
        capture_llm_tokens: bool = False,
    ) -> Any:
        """Execute ``fn`` asynchronously, creating a LangSmith run around it."""
        if self.client is None:
            return await fn(*args, **kwargs)

        start_time = datetime.now(timezone.utc)
        start = time.perf_counter()
        error: str | None = None
        result: Any = None
        run_tags = list(base_tags)

        try:
            result = await fn(*args, **kwargs)
            if capture_tool_result and hasattr(result, "success"):
                run_tags.append("success" if result.success else "failure")
            return result
        except Exception as exc:
            error = str(exc)
            run_tags.append("error")
            raise
        finally:
            duration = time.perf_counter() - start
            run_meta = {**extra_metadata, "duration_seconds": duration}
            if capture_llm_tokens and result is not None:
                run_meta["tokens_input"] = getattr(result, "tokens_input", 0)
                run_meta["tokens_output"] = getattr(result, "tokens_output", 0)

            self._submit_run(
                name=run_name,
                run_type=run_type,
                tags=self._build_tags(run_tags, extra_metadata),
                metadata=run_meta,
                error=error,
                start_time=start_time,
                outputs=result if error is None else None,
            )

    def _submit_run(
        self,
        name: str,
        run_type: str,
        tags: list[str],
        metadata: dict[str, Any],
        error: str | None,
        start_time: datetime,
        outputs: Any = None,
    ) -> None:
        """Fire-and-forget: post a completed run to LangSmith."""
        end_time = datetime.now(timezone.utc)
        try:
            self.client.create_run(
                name=name,
                run_type=run_type,
                project_name=self.project_name,
                tags=tags,
                metadata=metadata,
                error=error,
                inputs={},
                outputs=outputs if isinstance(outputs, dict) else ({"result": repr(outputs)} if outputs is not None else None),
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as exc:
            # Tracing must never break the migration workflow.
            logger.warning("LangSmith run submission failed (non-fatal): %s", exc)

    @staticmethod
    def _build_tags(
        base_tags: list[str],
        metadata: dict[str, Any],
    ) -> list[str]:
        """Merge base tags with key=value pairs from metadata."""
        tags = list(base_tags)
        for k, v in metadata.items():
            if k != "duration_seconds":  # skip internal timing key
                tags.append(f"{k}={v}")
        return tags
