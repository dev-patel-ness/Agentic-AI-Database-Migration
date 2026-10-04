"""Unit tests for TerraformAdapter"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from tool_adapters.terraform_adapter import TerraformAdapter


@pytest.fixture
def terraform_adapter():
    """Create a TerraformAdapter instance for testing."""
    with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
        # Mock terraform version check
        mock_run.return_value = MagicMock(returncode=0, stdout="Terraform v1.5.0")
        adapter = TerraformAdapter(terraform_dir="infra/terraform")
    return adapter


class TestTerraformAdapter:
    """Tests for TerraformAdapter functionality"""

    @patch('tool_adapters.terraform_adapter.terraform.subprocess.run')
    @pytest.mark.asyncio
    async def test_init_success(self, mock_run, terraform_adapter):
        """Test successful Terraform initialization."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Terraform has been successfully initialized!",
            stderr=""
        )
        
        result = await terraform_adapter.init(
            backend_bucket="my-bucket",
            backend_key="terraform.tfstate",
            backend_region="us-east-1"
        )
        
        assert result.success
        assert "initialized" in result.output.lower()

    @pytest.mark.asyncio
    async def test_init_failure(self, terraform_adapter):
        """Test Terraform initialization failure."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Backend initialization failed"
            )
            
            result = await terraform_adapter.init()
            
            assert not result.success
            assert "failed" in result.error.lower()

    @pytest.mark.asyncio
    async def test_plan_with_variables(self, terraform_adapter):
        """Test Terraform plan with variables."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Plan: 5 to add, 0 to change, 0 to destroy",
                stderr=""
            )
            
            result = await terraform_adapter.plan(
                variables={"environment": "staging", "app_replicas": 3}
            )
            
            assert result.success
            assert "Plan:" in result.output

    @pytest.mark.asyncio
    async def test_apply_with_auto_approve(self, terraform_adapter):
        """Test Terraform apply with auto-approve."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Apply complete! Resources: 5 added, 0 changed, 0 destroyed",
                stderr=""
            )
            
            with patch.object(terraform_adapter, '_get_outputs', return_value={"cluster_endpoint": "example.com"}):
                result = await terraform_adapter.apply(
                    variables={"environment": "staging"},
                    auto_approve=True
                )
            
            assert result.success
            assert "complete" in result.output.lower()

    @pytest.mark.asyncio
    async def test_destroy_with_auto_approve(self, terraform_adapter):
        """Test Terraform destroy with auto-approve."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Destroy complete! Resources: 0 added, 0 changed, 5 destroyed",
                stderr=""
            )
            
            result = await terraform_adapter.destroy(auto_approve=True)
            
            assert result.success
            assert "destroyed" in result.output.lower()

    @pytest.mark.asyncio
    async def test_output_retrieval(self, terraform_adapter):
        """Test getting Terraform outputs."""
        expected_outputs = {
            "cluster_endpoint": {"value": "eks-cluster.example.com"},
            "postgres_endpoint": {"value": "postgres.example.com"}
        }
        
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps(expected_outputs),
                stderr=""
            )
            
            result = await terraform_adapter.output()
            
            assert result.success
            assert "cluster_endpoint" in result.data["outputs"]

    @pytest.mark.asyncio
    async def test_validate_configuration(self, terraform_adapter):
        """Test Terraform configuration validation."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Success! The configuration is valid.",
                stderr=""
            )
            
            result = await terraform_adapter.validate()
            
            assert result.success
            assert "valid" in result.output.lower()

    @pytest.mark.asyncio
    async def test_validate_failure(self, terraform_adapter):
        """Test Terraform validation failure."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error: invalid resource type"
            )
            
            result = await terraform_adapter.validate()
            
            assert not result.success
            assert "invalid" in result.error.lower()

    def test_write_tfvars_security(self, terraform_adapter):
        """Test that tfvars file is created with secure permissions."""
        variables = {"db_password": "secret123", "environment": "staging"}
        
        tfvars_path = terraform_adapter._write_tfvars(variables)
        
        try:
            assert tfvars_path.exists()
            # Check file permissions are restricted (0o600)
            import stat
            file_stat = tfvars_path.stat()
            mode = stat.S_IMODE(file_stat.st_mode)
            # Verify file is readable/writable by owner only
            assert mode & stat.S_IROTH == 0  # Not readable by others
            assert mode & stat.S_IWGRP == 0  # Not writable by group
        finally:
            if tfvars_path.exists():
                tfvars_path.unlink()

    @pytest.mark.asyncio
    async def test_execute_dispatch(self, terraform_adapter):
        """Test execute method dispatches to correct function."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Terraform v1.5.0",
                stderr=""
            )
            
            result = await terraform_adapter.execute("validate")
            
            assert result.success
            assert mock_run.called

    @pytest.mark.asyncio
    async def test_execute_unknown_command(self, terraform_adapter):
        """Test execute with unknown command."""
        result = await terraform_adapter.execute("unknown_command")
        
        assert not result.success
        assert "unknown" in result.error.lower()

    def test_terraform_cli_verification(self):
        """Test terraform CLI is verified on initialization."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            
            with pytest.raises(RuntimeError):
                TerraformAdapter(terraform_dir="infra/terraform")

    def test_terraform_not_found(self):
        """Test error when terraform CLI not found."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError()
            
            with pytest.raises(RuntimeError):
                TerraformAdapter(terraform_dir="infra/terraform")

    def test_invalid_terraform_dir(self):
        """Test error with non-existent terraform directory."""
        with patch('tool_adapters.terraform_adapter.terraform.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            with pytest.raises(ValueError):
                TerraformAdapter(terraform_dir="/non/existent/path")
