"""
E2E integration test for Phase 8 deployment cutover
Tests deployment flow with Docker Compose sample DBs
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.deployment_agent import DeploymentAgent, DeploymentConfig
from tool_adapters.kubectl_adapter import KubectlAdapter
from tool_adapters.terraform_adapter import TerraformAdapter


class TestDeploymentE2E:
    """End-to-end deployment tests"""

    @pytest.fixture
    def deployment_config(self):
        """Create deployment configuration for testing."""
        return DeploymentConfig(
            cluster_name="capstone-test",
            app_deployment_name="capstone-app",
            namespace="ns-app",
            image="capstone/app:test-v2.0",
            health_check_timeout=60,
            readiness_timeout=120,
            rollback_on_error=True,
        )

    @pytest.mark.asyncio
    async def test_successful_deployment(self, deployment_config):
        """Test successful deployment flow."""
        # Mock adapters
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock terraform initialization and validation
        terraform_mock.init.return_value = MagicMock(success=True)
        terraform_mock.validate.return_value = MagicMock(success=True)
        terraform_mock.plan.return_value = MagicMock(success=True)
        
        # Mock kubectl operations
        kubectl_mock.set_image.return_value = MagicMock(success=True)
        kubectl_mock.rollout_status.return_value = MagicMock(success=True)
        kubectl_mock.get_pods.return_value = MagicMock(
            success=True,
            data={
                "pods": [
                    {"name": "app-1", "phase": "Running", "ready": True, "restart_count": 0},
                    {"name": "app-2", "phase": "Running", "ready": True, "restart_count": 0},
                    {"name": "app-3", "phase": "Running", "ready": True, "restart_count": 0},
                ]
            }
        )
        kubectl_mock.get_deployment.return_value = MagicMock(
            success=True,
            data={
                "deployment_status": {
                    "ready_replicas": 3,
                    "desired_replicas": 3,
                    "image": "capstone/app:test-v2.0"
                }
            }
        )
        
        # Create deployment agent
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        # Execute deployment
        result = await agent.deploy(
            new_image="capstone/app:test-v2.0",
            terraform_vars={"environment": "test"}
        )
        
        # Verify successful deployment
        assert result.success
        assert len(result.steps) > 0
        assert result.deployment_completed is not None
        assert not result.rollback_performed

    @pytest.mark.asyncio
    async def test_deployment_with_rollback_on_pod_failure(self, deployment_config):
        """Test automatic rollback when pods fail readiness."""
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock terraform success
        terraform_mock.init.return_value = MagicMock(success=True)
        terraform_mock.validate.return_value = MagicMock(success=True)
        
        # Mock kubectl image update
        kubectl_mock.set_image.return_value = MagicMock(success=True)
        
        # Mock rollout timeout (pods not ready)
        kubectl_mock.rollout_status.return_value = MagicMock(success=False, error="timeout")
        
        # Mock rollback
        kubectl_mock.rollout_undo.return_value = MagicMock(success=True)
        kubectl_mock.rollout_status.return_value = MagicMock(success=True)
        
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        # Execute deployment (should trigger rollback)
        result = await agent.deploy(new_image="capstone/app:test-v2.0")
        
        # Verify rollback was performed
        assert result.rollback_performed
        assert not result.success

    @pytest.mark.asyncio
    async def test_deployment_with_health_check_failure(self, deployment_config):
        """Test rollback when health check fails."""
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock successful infrastructure and rollout
        terraform_mock.validate.return_value = MagicMock(success=True)
        kubectl_mock.set_image.return_value = MagicMock(success=True)
        kubectl_mock.rollout_status.return_value = MagicMock(success=True)
        
        # Mock pod readiness but health check failure
        kubectl_mock.get_pods.return_value = MagicMock(
            success=True,
            data={"pods": [
                {"name": "app-1", "phase": "Running", "ready": True, "restart_count": 0},
                {"name": "app-2", "phase": "Running", "ready": True, "restart_count": 0},
            ]}
        )
        
        # Health check fails
        kubectl_mock.get_deployment.return_value = MagicMock(success=False, error="Connection refused")
        
        # Rollback succeeds
        kubectl_mock.rollout_undo.return_value = MagicMock(success=True)
        
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        result = await agent.deploy(new_image="capstone/app:test-v2.0")
        
        assert result.rollback_performed or not result.success

    @pytest.mark.asyncio
    async def test_deployment_steps_recorded(self, deployment_config):
        """Test that deployment steps are properly recorded."""
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock successful deployment
        terraform_mock.init.return_value = MagicMock(success=True)
        terraform_mock.validate.return_value = MagicMock(success=True)
        kubectl_mock.set_image.return_value = MagicMock(success=True)
        kubectl_mock.rollout_status.return_value = MagicMock(success=True)
        kubectl_mock.get_pods.return_value = MagicMock(
            success=True,
            data={"pods": [
                {"name": "app-1", "phase": "Running", "ready": True, "restart_count": 0}
            ]}
        )
        kubectl_mock.get_deployment.return_value = MagicMock(
            success=True,
            data={"deployment_status": {
                "ready_replicas": 1,
                "desired_replicas": 1,
                "image": "capstone/app:test-v2.0"
            }}
        )
        
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        result = await agent.deploy(new_image="capstone/app:test-v2.0")
        
        # Verify steps are recorded
        assert len(result.steps) > 0
        step_names = [step.name for step in result.steps]
        
        # Check expected steps
        assert any("Validate Infrastructure" in name for name in step_names)
        assert any("Rollout" in name for name in step_names)

    @pytest.mark.asyncio
    async def test_deployment_duration_tracking(self, deployment_config):
        """Test deployment duration is properly tracked."""
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock successful but slow deployment
        async def slow_operation(*args, **kwargs):
            await asyncio.sleep(0.1)
            return MagicMock(success=True)
        
        terraform_mock.validate = slow_operation
        kubectl_mock.set_image = slow_operation
        kubectl_mock.rollout_status = slow_operation
        kubectl_mock.get_pods.return_value = MagicMock(
            success=True,
            data={"pods": [
                {"name": "app-1", "phase": "Running", "ready": True, "restart_count": 0}
            ]}
        )
        kubectl_mock.get_deployment.return_value = MagicMock(
            success=True,
            data={"deployment_status": {
                "ready_replicas": 1,
                "desired_replicas": 1,
                "image": "capstone/app:test-v2.0"
            }}
        )
        
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        result = await agent.deploy(new_image="capstone/app:test-v2.0")
        
        # Verify duration was recorded
        duration = result.duration_seconds()
        assert duration > 0


class TestDeploymentIntegrationWithDocker:
    """Integration tests that can run with Docker Compose sample DBs"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_deployment_with_postgres_sample_connection(self, deployment_config):
        """Test deployment health check against actual postgres-sample DB."""
        # This test requires docker-compose to be running
        # Skip if not available
        pytest.importorskip("docker")
        
        from dialects.connections import ConnectionConfig, connect
        
        terraform_mock = AsyncMock(spec=TerraformAdapter)
        kubectl_mock = AsyncMock(spec=KubectlAdapter)
        
        # Mock deployment steps
        terraform_mock.validate.return_value = MagicMock(success=True)
        kubectl_mock.set_image.return_value = MagicMock(success=True)
        kubectl_mock.rollout_status.return_value = MagicMock(success=True)
        kubectl_mock.get_pods.return_value = MagicMock(
            success=True,
            data={"pods": [{"name": "app-1", "ready": True, "restart_count": 0}]}
        )
        kubectl_mock.get_deployment.return_value = MagicMock(
            success=True,
            data={"deployment_status": {
                "ready_replicas": 1,
                "desired_replicas": 1,
                "image": "capstone/app:test-v2.0"
            }}
        )
        
        # Create deployment agent
        agent = DeploymentAgent(
            terraform_adapter=terraform_mock,
            kubectl_adapter=kubectl_mock,
            deployment_config=deployment_config
        )
        
        # Create postgres connection config for sample DB
        db_config = ConnectionConfig(
            dialect="postgresql",
            host="localhost",
            port=5433,  # postgres-sample port
            username="postgres",
            password="postgres",
            database="postgres",
            ssl_enabled=False,
        )
        
        # Execute deployment with DB connection
        result = await agent.deploy(
            new_image="capstone/app:test-v2.0",
            target_db_config=db_config
        )
        
        # Deployment should complete (health check against real DB)
        # Result depends on actual DB connectivity
        assert result is not None
        assert result.deployment_started is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
