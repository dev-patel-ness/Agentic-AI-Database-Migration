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

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"{tool_name}::{func.__name__}",
                        run_type="tool",
                        inputs={"kwargs": str(kwargs)[:100]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"tool": tool_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return func(*args, **kwargs)

                trace_tags = self._build_tags(["tool", tool_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    success = getattr(result, "success", None)

                    self.client.create_run(
                        name=f"{tool_name}::{func.__name__}",
                        run_type="tool",
                        inputs={"kwargs": str(kwargs)[:100]},
                        outputs={"success": success, "output": str(result)[:100]},
                        tags=trace_tags + (["success"] if success else ["failure"] if success is False else []),
                        metadata={"tool": tool_name, "duration_seconds": duration, "success": success, **(metadata or {})},
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"{tool_name}::{func.__name__}",
                        run_type="tool",
                        inputs={"kwargs": str(kwargs)[:100]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"tool": tool_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def trace_llm_call(
        self,
        model_name: str,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Callable:
        """
        Decorator to trace LLM calls (Bedrock, CrackSQL fallback, etc.).

        Records:
        - Model name, prompt, completion
        - Token usage (input/output)
        - Latency and cost estimation
        - Custom metadata

        Args:
            model_name: LLM model name (e.g., "amazon.nova-pro-v1:0")
            tags: Optional list of tags
            metadata: Optional metadata dict

        Returns:
            Decorated function that traces LLM execution.
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return await func(*args, **kwargs)

                trace_tags = self._build_tags(["llm", model_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Try to extract token usage if available
                    tokens_input = getattr(result, "tokens_input", None)
                    tokens_output = getattr(result, "tokens_output", None)

                    self.client.create_run(
                        name=f"llm::{model_name}",
                        run_type="llm",
                        inputs={"prompt": str(kwargs.get("prompt", ""))[:200]},
                        outputs={"completion": str(result)[:200]},
                        tags=trace_tags,
                        metadata={
                            "model": model_name,
                            "duration_seconds": duration,
                            "tokens_input": tokens_input,
                            "tokens_output": tokens_output,
                            **(metadata or {}),
                        },
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"llm::{model_name}",
                        run_type="llm",
                        inputs={"prompt": str(kwargs.get("prompt", ""))[:200]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"model": model_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return func(*args, **kwargs)

                trace_tags = self._build_tags(["llm", model_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    tokens_input = getattr(result, "tokens_input", None)
                    tokens_output = getattr(result, "tokens_output", None)

                    self.client.create_run(
                        name=f"llm::{model_name}",
                        run_type="llm",
                        inputs={"prompt": str(kwargs.get("prompt", ""))[:200]},
                        outputs={"completion": str(result)[:200]},
                        tags=trace_tags,
                        metadata={
                            "model": model_name,
                            "duration_seconds": duration,
                            "tokens_input": tokens_input,
                            "tokens_output": tokens_output,
                            **(metadata or {}),
                        },
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"llm::{model_name}",
                        run_type="llm",
                        inputs={"prompt": str(kwargs.get("prompt", ""))[:200]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"model": model_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator


# Singleton tracer instance
_tracer: Optional[LangSmithTracer] = None


def get_tracer(project_name: str = "capstone", api_key: Optional[str] = None) -> LangSmithTracer:
    """
    Get or create the singleton LangSmith tracer.

    Args:
        project_name: LangSmith project name
        api_key: LangSmith API key (optional, reads from env if not provided)

    Returns:
        LangSmithTracer singleton.
    """
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTracer(project_name, api_key)
    return _tracer
