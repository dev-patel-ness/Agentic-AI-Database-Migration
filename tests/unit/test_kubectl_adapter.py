"""Unit tests for KubectlAdapter"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tool_adapters.kubectl_adapter import KubectlAdapter, DeploymentStatus, RolloutStatus


@pytest.fixture
def kubectl_adapter():
    """Create a KubectlAdapter instance for testing."""
    with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
        # Mock kubectl version check
        mock_run.return_value = MagicMock(returncode=0, stdout="Client Version: v1.28.0")
        adapter = KubectlAdapter()
    return adapter


class TestKubectlAdapter:
    """Tests for KubectlAdapter functionality"""

    @patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run')
    @pytest.mark.asyncio
    async def test_get_deployment(self, mock_run, kubectl_adapter):
        """Test getting deployment status."""
        deployment_json = {
            "metadata": {"name": "test-app", "generation": "1"},
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [{"image": "test-app:v1.0"}]
                    }
                }
            },
            "status": {
                "readyReplicas": 3,
                "availableReplicas": 3,
                "updatedReplicas": 3,
                "conditions": [
                    {
                        "type": "Progressing",
                        "status": "True",
                        "reason": "NewReplicaSetAvailable"
                    }
                ]
            }
        }
        
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(deployment_json),
            stderr=""
        )
        
        result = await kubectl_adapter.get_deployment("test-app", "default")
        
        assert result.success
        status = result.data.get("deployment_status", {})
        assert status["ready_replicas"] == 3
        assert status["desired_replicas"] == 3
        assert status["image"] == "test-app:v1.0"

    @pytest.mark.asyncio
    async def test_get_deployment_failure(self, kubectl_adapter):
        """Test get deployment failure."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="deployment not found"
            )
            
            result = await kubectl_adapter.get_deployment("nonexistent", "default")
            
            assert not result.success

    @pytest.mark.asyncio
    async def test_set_image(self, kubectl_adapter):
        """Test updating container image."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="deployment.apps/test-app image updated",
                stderr=""
            )
            
            result = await kubectl_adapter.set_image(
                "test-app",
                "test-app",
                "test-app:v2.0",
                "default"
            )
            
            assert result.success
            assert "updated" in result.output.lower()

    @pytest.mark.asyncio
    async def test_rollout_status_success(self, kubectl_adapter):
        """Test rollout status check when successful."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="deployment "test-app" successfully rolled out",
                stderr=""
            )
            
            result = await kubectl_adapter.rollout_status(
                "test-app",
                "default",
                timeout_seconds=300
            )
            
            assert result.success

    @pytest.mark.asyncio
    async def test_rollout_status_timeout(self, kubectl_adapter):
        """Test rollout status check timeout."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error waiting for rollout: timeout"
            )
            
            result = await kubectl_adapter.rollout_status(
                "test-app",
                "default",
                timeout_seconds=10
            )
            
            assert not result.success

    @pytest.mark.asyncio
    async def test_rollout_undo(self, kubectl_adapter):
        """Test rolling back to previous revision."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="rollout history for deployment",
                stderr=""
            )
            
            result = await kubectl_adapter.rollout_undo("test-app", "default")
            
            assert result.success

    @pytest.mark.asyncio
    async def test_rollout_undo_to_specific_revision(self, kubectl_adapter):
        """Test rolling back to specific revision."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="rolled back to revision 2",
                stderr=""
            )
            
            result = await kubectl_adapter.rollout_undo(
                "test-app",
                "default",
                to_revision=2
            )
            
            assert result.success
            # Verify --to-revision was included
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert "--to-revision" in args

    @pytest.mark.asyncio
    async def test_rollout_history(self, kubectl_adapter):
        """Test getting rollout history."""
        history_output = """REVISION  CHANGE-CAUSE
1         Initial deployment
2         Rolled out new version
3         Updated to v3.0"""
        
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=history_output,
                stderr=""
            )
            
            result = await kubectl_adapter.rollout_history("test-app", "default")
            
            assert result.success
            assert "REVISION" in result.output

    @pytest.mark.asyncio
    async def test_get_pods(self, kubectl_adapter):
        """Test getting pods for a deployment."""
        pods_json = {
            "items": [
                {
                    "metadata": {"name": "test-app-abc123"},
                    "status": {
                        "phase": "Running",
                        "conditions": [
                            {"type": "Ready", "status": "True"}
                        ],
                        "containerStatuses": [
                            {"restartCount": 0}
                        ]
                    }
                },
                {
                    "metadata": {"name": "test-app-def456"},
                    "status": {
                        "phase": "Running",
                        "conditions": [
                            {"type": "Ready", "status": "True"}
                        ],
                        "containerStatuses": [
                            {"restartCount": 0}
                        ]
                    }
                }
            ]
        }
        
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pods_json),
                stderr=""
            )
            
            result = await kubectl_adapter.get_pods("test-app", "default")
            
            assert result.success
            pods = result.data.get("pods", [])
            assert len(pods) == 2
            assert all(pod["ready"] for pod in pods)

    @pytest.mark.asyncio
    async def test_get_pods_with_restarts(self, kubectl_adapter):
        """Test getting pods with restart count warnings."""
        pods_json = {
            "items": [
                {
                    "metadata": {"name": "test-app-abc123"},
                    "status": {
                        "phase": "Running",
                        "conditions": [
                            {"type": "Ready", "status": "True"}
                        ],
                        "containerStatuses": [
                            {"restartCount": 5}
                        ]
                    }
                }
            ]
        }
        
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(pods_json),
                stderr=""
            )
            
            result = await kubectl_adapter.get_pods("test-app", "default")
            
            assert result.success
            pods = result.data.get("pods", [])
            assert pods[0]["restart_count"] == 5

    @pytest.mark.asyncio
    async def test_logs_retrieval(self, kubectl_adapter):
        """Test getting pod logs."""
        log_output = "2024-01-15 10:00:00 INFO Application started\n2024-01-15 10:00:01 INFO Ready to accept connections"
        
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=log_output,
                stderr=""
            )
            
            result = await kubectl_adapter.logs("test-app-abc123", "default", tail_lines=100)
            
            assert result.success
            assert "Application started" in result.output

    @pytest.mark.asyncio
    async def test_apply_manifest_from_content(self, kubectl_adapter):
        """Test applying manifest from YAML content."""
        manifest = """
apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  key: value
"""
        
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="configmap/test-config created",
                stderr=""
            )
            
            result = await kubectl_adapter.apply(manifest, "default")
            
            assert result.success
            assert "created" in result.output.lower()

    @pytest.mark.asyncio
    async def test_delete_resource(self, kubectl_adapter):
        """Test deleting a resource."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="deployment.apps "test-app" deleted",
                stderr=""
            )
            
            result = await kubectl_adapter.delete("deployment", "test-app", "default")
            
            assert result.success
            assert "deleted" in result.output.lower()

    def test_kubectl_cli_verification(self):
        """Test kubectl CLI is verified on initialization."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            
            with pytest.raises(RuntimeError):
                KubectlAdapter()

    def test_kubectl_not_found(self):
        """Test error when kubectl CLI not found."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            
            with pytest.raises(RuntimeError):
                KubectlAdapter()

    @pytest.mark.asyncio
    async def test_build_cmd_with_kubeconfig(self):
        """Test command building with custom kubeconfig."""
        with patch('tool_adapters.kubectl_adapter.kubectl.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            adapter = KubectlAdapter(kubeconfig="/custom/kubeconfig")
            cmd = adapter._build_cmd("get", "pods")
            
            assert "--kubeconfig" in cmd
            assert "/custom/kubeconfig" in cmd
