"""
LangSmith tracing integration for all agents, tools, and LLM calls.

Provides decorators for automatic instrumentation of agent methods, tool invocations,
and LLM calls with prompt/tokens/latency/cost tracking.
"""

import asyncio
import functools
import logging
import time
from typing import Any, Callable, Optional, TypeVar, Union

try:
    from langsmith import Client as LangSmithClient
    from langsmith.run_trees import RunTree
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False
    LangSmithClient = None
    RunTree = None

logger = logging.getLogger(__name__)

T = TypeVar("T")


class LangSmithTracer:
    """Wrapper around LangSmith client for structured tracing of agents and tools."""

    def __init__(self, project_name: str, api_key: Optional[str] = None):
        """
        Initialize LangSmith tracer.

        Args:
            project_name: LangSmith project name (e.g., "capstone-staging")
            api_key: LangSmith API key (optional, reads from LANGSMITH_API_KEY env var if not provided)
        """
        if not LANGSMITH_AVAILABLE:
            logger.warning("LangSmith not installed; tracing disabled. Install with: pip install langsmith")
            self.client = None
            return

        self.project_name = project_name
        self.client = LangSmithClient(api_key=api_key)
        self.active_run_stack: list[RunTree] = []

        logger.info(f"LangSmith tracer initialized for project: {project_name}")

    def _build_tags(self, base_tags: list[str], metadata: dict[str, Any]) -> list[str]:
        """Build tag list from base tags and metadata."""
        tags = base_tags.copy()
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    tags.append(f"{key}={value}")
        return tags

    def trace_agent(
        self,
        agent_name: str,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Callable:
        """
        Decorator to trace agent method execution.

        Records:
        - Agent name, input, output
        - Execution time
        - Success/failure status
        - Custom metadata (risk scores, migration phase, etc.)

        Args:
            agent_name: Agent name (e.g., "assessment_agent", "schema_agent")
            tags: Optional list of tags
            metadata: Optional metadata dict to attach to trace

        Returns:
            Decorated function that traces execution.
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return await func(*args, **kwargs)

                trace_tags = self._build_tags(["agent", agent_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time

                    self.client.create_run(
                        name=f"{agent_name}::{func.__name__}",
                        run_type="chain",
                        inputs={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
                        outputs={"result": str(result)[:100]},
                        tags=trace_tags,
                        metadata={"agent": agent_name, "duration_seconds": duration, **(metadata or {})},
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"{agent_name}::{func.__name__}",
                        run_type="chain",
                        inputs={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"agent": agent_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return func(*args, **kwargs)

                trace_tags = self._build_tags(["agent", agent_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    self.client.create_run(
                        name=f"{agent_name}::{func.__name__}",
                        run_type="chain",
                        inputs={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
                        outputs={"result": str(result)[:100]},
                        tags=trace_tags,
                        metadata={"agent": agent_name, "duration_seconds": duration, **(metadata or {})},
                    )

                    return result

                except Exception as e:
                    duration = time.time() - start_time
                    self.client.create_run(
                        name=f"{agent_name}::{func.__name__}",
                        run_type="chain",
                        inputs={"args": str(args)[:100], "kwargs": str(kwargs)[:100]},
                        error=str(e),
                        tags=trace_tags + ["error"],
                        metadata={"agent": agent_name, "duration_seconds": duration, "error": str(e)},
                    )
                    raise

            # Detect if coroutine
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    def trace_tool(
        self,
        tool_name: str,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Callable:
        """
        Decorator to trace tool adapter execution.

        Records:
        - Tool name, input, output
        - Success/failure status
        - Execution time
        - Tool-specific metadata

        Args:
            tool_name: Tool adapter name (e.g., "terraform_adapter", "kubectl_adapter")
            tags: Optional list of tags
            metadata: Optional metadata dict

        Returns:
            Decorated function that traces execution.
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                if not self.client:
                    return await func(*args, **kwargs)

                trace_tags = self._build_tags(["tool", tool_name] + (tags or []), metadata or {})

                try:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Extract success flag if result is a dict-like object
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
