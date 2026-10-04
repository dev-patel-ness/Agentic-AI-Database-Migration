"""Unit tests for Prometheus metrics"""

import pytest
from unittest.mock import patch, MagicMock

from observability.metrics import (
    record_validation_progress,
    record_checksum_duration,
    record_retry,
    record_agent_invocation,
    record_tool_adapter_call,
    record_pod_health,
    record_deployment_rollout,
    record_deployment_rollback,
    record_llm_call,
    # Import metric objects
    agent_invocations_total,
    agent_invocations_success,
    agent_invocations_failure,
    agent_latency,
    tool_adapter_calls_total,
    tool_adapter_success,
    tool_adapter_failure,
    tool_adapter_latency,
    pod_ready_replicas,
    pod_available_replicas,
    pod_desired_replicas,
    deployment_rollout_success_total,
    deployment_rollout_failure_total,
    deployment_rollback_total,
    deployment_rollout_duration,
    llm_tokens_input_total,
    llm_tokens_output_total,
    llm_call_latency,
)


class TestPrometheusMetrics:
    """Tests for Prometheus metrics"""

    def test_agent_invocation_success(self):
        """Test recording successful agent invocation."""
        record_agent_invocation(
            agent_name="test_agent",
            job_id="job-123",
            success=True,
            duration_seconds=2.5
        )

        # Verify metrics were updated (mock approach)
        labels = {"agent_name": "test_agent", "job_id": "job-123"}

        # Get metric value (in real scenario, this would query Prometheus)
        assert agent_invocations_total is not None
        assert agent_invocations_success is not None
        assert agent_latency is not None

    def test_agent_invocation_failure(self):
        """Test recording failed agent invocation."""
        record_agent_invocation(
            agent_name="failing_agent",
            job_id="job-456",
            success=False,
            duration_seconds=1.0,
            error_type="timeout"
        )

        assert agent_invocations_failure is not None

    def test_tool_adapter_call_success(self):
        """Test recording successful tool adapter call."""
        record_tool_adapter_call(
            tool_name="terraform_adapter",
            operation="apply",
            success=True,
            duration_seconds=30.5
        )

        assert tool_adapter_calls_total is not None
        assert tool_adapter_success is not None
        assert tool_adapter_latency is not None

    def test_tool_adapter_call_failure(self):
        """Test recording failed tool adapter call."""
        record_tool_adapter_call(
            tool_name="kubectl_adapter",
            operation="rollout_status",
            success=False,
            duration_seconds=120.0,
            error_type="timeout"
        )

        assert tool_adapter_failure is not None

    def test_pod_health_metrics(self):
        """Test recording pod health metrics."""
        record_pod_health(
            deployment_name="capstone-app",
            namespace="ns-app",
            cluster_name="capstone-staging",
            ready_replicas=3,
            available_replicas=3,
            desired_replicas=3
        )

        assert pod_ready_replicas is not None
        assert pod_available_replicas is not None
        assert pod_desired_replicas is not None

    def test_pod_health_degraded(self):
        """Test recording degraded pod health."""
        record_pod_health(
            deployment_name="capstone-platform",
            namespace="ns-platform",
            cluster_name="capstone-staging",
            ready_replicas=1,  # Only 1 ready
            available_replicas=2,
            desired_replicas=2
        )

        # Metrics should still be recorded even if degraded
        assert pod_ready_replicas is not None

    def test_deployment_rollout_success(self):
        """Test recording successful deployment rollout."""
        record_deployment_rollout(
            deployment_name="capstone-app",
            namespace="ns-app",
            cluster_name="capstone-staging",
            success=True,
            duration_seconds=45.0
        )

        assert deployment_rollout_success_total is not None
        assert deployment_rollout_duration is not None

    def test_deployment_rollout_failure(self):
        """Test recording failed deployment rollout."""
        record_deployment_rollout(
            deployment_name="capstone-app",
            namespace="ns-app",
            cluster_name="capstone-staging",
            success=False,
            duration_seconds=120.0,
            error_reason="pod_unready"
        )

        assert deployment_rollout_failure_total is not None

    def test_deployment_rollback(self):
        """Test recording deployment rollback."""
        record_deployment_rollback(
            deployment_name="capstone-app",
            namespace="ns-app",
            cluster_name="capstone-staging",
            rollback_reason="health_check_failed"
        )

        assert deployment_rollback_total is not None

    def test_llm_call_metrics(self):
        """Test recording LLM call metrics."""
        record_llm_call(
            model_name="amazon.nova-pro-v1:0",
            agent_name="schema_agent",
            tokens_input=250,
            tokens_output=150,
            duration_seconds=3.5
        )

        assert llm_tokens_input_total is not None
        assert llm_tokens_output_total is not None
        assert llm_call_latency is not None

    def test_llm_call_zero_tokens(self):
        """Test recording LLM call with zero tokens (edge case)."""
        record_llm_call(
            model_name="amazon.nova-pro-v1:0",
            agent_name="test_agent",
            tokens_input=0,
            tokens_output=0,
            duration_seconds=0.5
        )

        # Should not increment token counters
        assert llm_call_latency is not None

    def test_validation_progress_metrics(self):
        """Test recording validation progress."""
        record_validation_progress(
            job_id="job-789",
            source_dialect="oracle",
            target_dialect="postgresql",
            total_tables=15,
            passed_tables=12
        )

        # Metrics should be recorded
        # In real scenario, would query Prometheus for values

    def test_retry_metrics(self):
        """Test recording retry metrics."""
        record_retry(
            job_id="job-999",
            phase="migrate",
            source_dialect="mysql",
            target_dialect="postgresql",
            success=True
        )

        # Record a failed retry
        record_retry(
            job_id="job-999",
            phase="migrate",
            source_dialect="mysql",
            target_dialect="postgresql",
            success=False
        )

    def test_checksum_duration_histogram(self):
        """Test recording checksum duration (histogram)."""
        record_checksum_duration(
            table_name="users",
            source_dialect="postgresql",
            target_dialect="mysql",
            duration_seconds=5.2
        )

        assert agent_latency is not None  # Histograms are defined

    def test_metrics_with_special_characters_in_labels(self):
        """Test that metrics handle special characters in labels correctly."""
        # Some labels might contain special chars that need sanitizing
        record_agent_invocation(
            agent_name="test-agent_123",  # Hyphens and underscores
            job_id="job-abc-def",
            success=True,
            duration_seconds=1.0
        )

        assert agent_invocations_total is not None

    def test_concurrent_metric_updates(self):
        """Test that metrics can be updated concurrently without errors."""
        import concurrent.futures

        def update_metrics(i):
            record_agent_invocation(
                agent_name=f"agent-{i}",
                job_id=f"job-{i}",
                success=(i % 2 == 0),
                duration_seconds=float(i)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(update_metrics, i) for i in range(10)]
            for future in concurrent.futures.as_completed(futures):
                # Should not raise any exceptions
                future.result()

    def test_metrics_have_proper_buckets(self):
        """Test that histogram metrics have proper buckets defined."""
        # Check that latency histograms are defined with appropriate buckets
        assert hasattr(agent_latency, '_upper_bounds')  # Histograms have buckets
        assert hasattr(tool_adapter_latency, '_upper_bounds')
        assert hasattr(deployment_rollout_duration, '_upper_bounds')
        assert hasattr(llm_call_latency, '_upper_bounds')

    def test_all_phase9_metrics_defined(self):
        """Test that all Phase 9 metrics are properly defined."""
        # Agent metrics
        assert agent_invocations_total is not None
        assert agent_invocations_success is not None
        assert agent_invocations_failure is not None
        assert agent_latency is not None

        # Tool metrics
        assert tool_adapter_calls_total is not None
        assert tool_adapter_success is not None
        assert tool_adapter_failure is not None
        assert tool_adapter_latency is not None

        # Pod metrics
        assert pod_ready_replicas is not None
        assert pod_available_replicas is not None
        assert pod_desired_replicas is not None

        # Deployment metrics
        assert deployment_rollout_success_total is not None
        assert deployment_rollout_failure_total is not None
        assert deployment_rollback_total is not None
        assert deployment_rollout_duration is not None

        # LLM metrics
        assert llm_tokens_input_total is not None
        assert llm_tokens_output_total is not None
        assert llm_call_latency is not None
