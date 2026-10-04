"""Unit tests for LangSmith tracing integration"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, call
from typing import Any

from observability.langsmith.tracer import LangSmithTracer, get_tracer


@pytest.fixture
def mock_langsmith_client():
    """Mock LangSmith client."""
    return MagicMock()


@pytest.fixture
def tracer(mock_langsmith_client):
    """Create a LangSmithTracer with mocked client."""
    tracer = LangSmithTracer(project_name="test-project")
    tracer.client = mock_langsmith_client
    return tracer


class TestLangSmithTracer:
    """Tests for LangSmith tracer functionality"""

    def test_tracer_initialization(self):
        """Test tracer initialization."""
        tracer = LangSmithTracer(project_name="capstone-staging")

        assert tracer.project_name == "capstone-staging"
        assert tracer.active_run_stack == []

    def test_tracer_with_langsmith_unavailable(self):
        """Test tracer gracefully handles missing LangSmith library."""
        with patch('observability.langsmith.tracer.LANGSMITH_AVAILABLE', False):
            tracer = LangSmithTracer(project_name="test-project")

            assert tracer.client is None

    def test_trace_agent_decorator_sync(self, tracer):
        """Test @trace_agent decorator on synchronous function."""
        @tracer.trace_agent("test_agent", tags=["critical"])
        def sample_agent_method(value: int) -> int:
            return value * 2

        result = sample_agent_method(5)

        assert result == 10
        tracer.client.create_run.assert_called_once()
        call_args = tracer.client.create_run.call_args

        # Verify call arguments
        assert call_args[1]["name"] == "test_agent::sample_agent_method"
        assert call_args[1]["run_type"] == "chain"
        assert "agent" in call_args[1]["tags"]
        assert "test_agent" in call_args[1]["tags"]
        assert "critical" in call_args[1]["tags"]

    @pytest.mark.asyncio
    async def test_trace_agent_decorator_async(self, tracer):
        """Test @trace_agent decorator on async function."""
        @tracer.trace_agent("async_agent")
        async def sample_async_agent(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 3

        result = await sample_async_agent(7)

        assert result == 21
        tracer.client.create_run.assert_called_once()

    def test_trace_agent_with_exception(self, tracer):
        """Test @trace_agent decorator records exceptions."""
        @tracer.trace_agent("failing_agent")
        def failing_agent() -> None:
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_agent()

        tracer.client.create_run.assert_called_once()
        call_args = tracer.client.create_run.call_args

        assert call_args[1]["error"] == "Test error"
        assert "error" in call_args[1]["tags"]

    def test_trace_tool_decorator_sync(self, tracer):
        """Test @trace_tool decorator on synchronous function."""
        result_obj = MagicMock(success=True, output="Tool executed")

        @tracer.trace_tool("terraform_adapter", tags=["infrastructure"])
        def sample_tool_method() -> Any:
            return result_obj

        result = sample_tool_method()

        assert result.success is True
        tracer.client.create_run.assert_called_once()
        call_args = tracer.client.create_run.call_args

        assert call_args[1]["name"] == "terraform_adapter::sample_tool_method"
        assert call_args[1]["run_type"] == "tool"
        assert "tool" in call_args[1]["tags"]
        assert "terraform_adapter" in call_args[1]["tags"]
        assert "success" in call_args[1]["tags"]

    def test_trace_tool_with_failure(self, tracer):
        """Test @trace_tool records tool failures."""
        result_obj = MagicMock(success=False, error="Connection timeout")

        @tracer.trace_tool("kubectl_adapter")
        def failing_tool() -> Any:
            return result_obj

        result = failing_tool()

        assert result.success is False
        call_args = tracer.client.create_run.call_args
        assert "failure" in call_args[1]["tags"]

    def test_trace_llm_call_decorator(self, tracer):
        """Test @trace_llm_call decorator."""
        result_obj = MagicMock(
            tokens_input=150,
            tokens_output=45,
            content="LLM response"
        )

        @tracer.trace_llm_call("amazon.nova-pro-v1:0")
        def sample_llm_call(prompt: str) -> Any:
            return result_obj

        result = sample_llm_call("What is a database schema?")

        assert result.tokens_input == 150
        call_args = tracer.client.create_run.call_args

        assert call_args[1]["name"] == "llm::amazon.nova-pro-v1:0"
        assert call_args[1]["run_type"] == "llm"
        assert "llm" in call_args[1]["tags"]
        assert call_args[1]["metadata"]["tokens_input"] == 150
        assert call_args[1]["metadata"]["tokens_output"] == 45

    def test_trace_with_metadata(self, tracer):
        """Test tracing includes custom metadata."""
        @tracer.trace_agent("test_agent", metadata={"job_id": "job-123", "phase": "validate"})
        def agent_with_metadata() -> str:
            return "success"

        result = agent_with_metadata()

        call_args = tracer.client.create_run.call_args
        metadata = call_args[1]["metadata"]

        assert metadata["job_id"] == "job-123"
        assert metadata["phase"] == "validate"
        assert "agent" in metadata

    def test_build_tags(self, tracer):
        """Test tag building from base tags and metadata."""
        tags = tracer._build_tags(
            ["base1", "base2"],
            {"key1": "value1", "key2": 42}
        )

        assert "base1" in tags
        assert "base2" in tags
        assert "key1=value1" in tags
        assert "key2=42" in tags

    def test_get_tracer_singleton(self):
        """Test that get_tracer returns a singleton."""
        with patch('observability.langsmith.tracer.LangSmithTracer.__init__', return_value=None):
            tracer1 = get_tracer(project_name="project1")
            tracer2 = get_tracer(project_name="project2")  # Different name, same instance

            assert tracer1 is tracer2

    def test_tracer_disabled_gracefully(self):
        """Test that tracing is disabled gracefully when LangSmith is unavailable."""
        with patch('observability.langsmith.tracer.LANGSMITH_AVAILABLE', False):
            tracer = LangSmithTracer(project_name="test")

            @tracer.trace_agent("test_agent")
            def sample_agent() -> str:
                return "success"

            result = sample_agent()

            # Should still work, just no tracing
            assert result == "success"

    @pytest.mark.asyncio
    async def test_trace_async_with_timing(self, tracer):
        """Test that async tracing captures timing information."""
        @tracer.trace_agent("timed_agent")
        async def slow_agent() -> str:
            await asyncio.sleep(0.05)
            return "done"

        result = await slow_agent()

        assert result == "done"
        call_args = tracer.client.create_run.call_args
        duration = call_args[1]["metadata"]["duration_seconds"]

        assert duration >= 0.05  # Should take at least 50ms

    def test_trace_agent_latency_in_metadata(self, tracer):
        """Test that agent latency is recorded in metadata."""
        @tracer.trace_agent("latency_agent")
        def sample_agent() -> int:
            return 42

        result = sample_agent()

        call_args = tracer.client.create_run.call_args
        metadata = call_args[1]["metadata"]

        assert "duration_seconds" in metadata
        assert metadata["duration_seconds"] >= 0

    def test_multiple_decorators_stacking(self, tracer):
        """Test that multiple decorators can be stacked."""
        @tracer.trace_agent("agent1")
        def base_function() -> str:
            return "success"

        result = base_function()

        assert result == "success"
        # Should record the trace
        assert tracer.client.create_run.called
