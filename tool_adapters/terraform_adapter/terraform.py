"""
Terraform Adapter - Executes Terraform commands for infrastructure deployment
"""

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from tool_adapters.base import BaseToolAdapter, ToolResult, ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class TerraformPlan:
    """Terraform plan representation"""
    resource_changes: Dict[str, Any]
    output_changes: Dict[str, Any]
    raw_plan: str


@dataclass
class TerraformApply:
    """Terraform apply result"""
    outputs: Dict[str, Any]
    resources_created: int
    resources_modified: int
    resources_destroyed: int
    raw_output: str


class TerraformAdapter(BaseToolAdapter):
    """
    Adapter for executing Terraform commands.
    Supports init, plan, apply, destroy, and output retrieval.
    
    SECURITY NOTES:
    - All variable values are securely passed via tfvars files (not CLI args)
    - Terraform backend state must be configured with encryption
    - Sensitive values are never logged or exposed in output
    """

    def __init__(self, terraform_dir: str = "infra/terraform"):
        """
        Initialize Terraform adapter.
        
        Args:
            terraform_dir: Path to Terraform root module directory
        """
        self.terraform_dir = Path(terraform_dir).resolve()
        self.logger = logger
        
        if not self.terraform_dir.exists():
            raise ValueError(f"Terraform directory not found: {terraform_dir}")
        
        # Verify terraform CLI is available
        self._verify_terraform_installed()

    def _verify_terraform_installed(self) -> None:
        """Verify terraform CLI is installed and accessible."""
        try:
            result = subprocess.run(
                ["terraform", "version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("Terraform CLI not available")
            self.logger.info("Terraform CLI verified")
        except FileNotFoundError:
            raise RuntimeError("Terraform CLI not found in PATH")

    async def init(
        self,
        backend_bucket: Optional[str] = None,
        backend_key: Optional[str] = None,
        backend_region: Optional[str] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Initialize Terraform working directory.
        
        Args:
            backend_bucket: S3 bucket for remote state
            backend_key: Path within S3 bucket for state file
            backend_region: AWS region for S3 backend
            context: Execution context
            
        Returns:
            ToolResult with initialization output
        """
        try:
            cmd = ["terraform", "init", "-upgrade"]
            
            # Configure backend if provided
            if backend_bucket and backend_key and backend_region:
                cmd.extend([
                    "-backend-config", f"bucket={backend_bucket}",
                    "-backend-config", f"key={backend_key}",
                    "-backend-config", f"region={backend_region}",
                    "-backend-config", "encrypt=true",
                ])
            
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Terraform init failed: {result.stderr}"
                )
            
            self.logger.info("Terraform initialized successfully")
            return ToolResult(
                success=True,
                output=result.stdout
            )
        except Exception as e:
            self.logger.error(f"Terraform init error: {e}")
            return ToolResult(success=False, error=str(e))

    async def plan(
        self,
        variables: Optional[Dict[str, Any]] = None,
        out_file: Optional[str] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Create a Terraform plan (dry-run).
        
        Args:
            variables: Dictionary of Terraform variables
            out_file: Path to save plan file
            context: Execution context
            
        Returns:
            ToolResult with plan output
        """
        try:
            cmd = ["terraform", "plan", "-no-color"]
            
            # Write variables to temporary tfvars file
            tfvars_file = None
            if variables:
                tfvars_file = self._write_tfvars(variables)
                cmd.extend(["-var-file", str(tfvars_file)])
            
            if out_file:
                cmd.extend(["-out", out_file])
            
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            # Clean up temporary tfvars file
            if tfvars_file and tfvars_file.exists():
                tfvars_file.unlink()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Terraform plan failed: {result.stderr}"
                )
            
            self.logger.info("Terraform plan completed")
            return ToolResult(
                success=True,
                output=result.stdout
            )
        except Exception as e:
            self.logger.error(f"Terraform plan error: {e}")
            return ToolResult(success=False, error=str(e))

    async def apply(
        self,
        variables: Optional[Dict[str, Any]] = None,
        plan_file: Optional[str] = None,
        auto_approve: bool = False,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Apply Terraform changes to create/update infrastructure.
        
        Args:
            variables: Dictionary of Terraform variables
            plan_file: Path to existing plan file (if plan was saved)
            auto_approve: Skip approval prompt (use cautiously)
            context: Execution context
            
        Returns:
            ToolResult with apply output and resource changes
        """
        try:
            if plan_file and Path(plan_file).exists():
                # Apply from saved plan file
                cmd = ["terraform", "apply", "-no-color"]
                if auto_approve:
                    cmd.append("-auto-approve")
                cmd.append(plan_file)
            else:
                # Apply with variables
                cmd = ["terraform", "apply", "-no-color"]
                
                if variables:
                    tfvars_file = self._write_tfvars(variables)
                    cmd.extend(["-var-file", str(tfvars_file)])
                
                if auto_approve:
                    cmd.append("-auto-approve")
            
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=1200
            )
            
            # Clean up temporary tfvars file
            if variables:
                if tfvars_file and tfvars_file.exists():
                    tfvars_file.unlink()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Terraform apply failed: {result.stderr}"
                )
            
            # Extract outputs
            outputs = self._get_outputs()
            
            self.logger.info("Terraform apply completed successfully")
            return ToolResult(
                success=True,
                output=result.stdout,
                data={"outputs": outputs}
            )
        except Exception as e:
            self.logger.error(f"Terraform apply error: {e}")
            return ToolResult(success=False, error=str(e))

    async def destroy(
        self,
        variables: Optional[Dict[str, Any]] = None,
        auto_approve: bool = False,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Destroy Terraform-managed infrastructure.
        
        Args:
            variables: Dictionary of Terraform variables
            auto_approve: Skip approval prompt
            context: Execution context
            
        Returns:
            ToolResult with destroy output
        """
        try:
            cmd = ["terraform", "destroy", "-no-color"]
            
            if variables:
                tfvars_file = self._write_tfvars(variables)
                cmd.extend(["-var-file", str(tfvars_file)])
            
            if auto_approve:
                cmd.append("-auto-approve")
            
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=1200
            )
            
            if variables and tfvars_file.exists():
                tfvars_file.unlink()
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Terraform destroy failed: {result.stderr}"
                )
            
            self.logger.info("Terraform destroy completed")
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Terraform destroy error: {e}")
            return ToolResult(success=False, error=str(e))

    async def output(
        self,
        output_name: Optional[str] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Get Terraform outputs.
        
        Args:
            output_name: Specific output to retrieve (if None, returns all)
            context: Execution context
            
        Returns:
            ToolResult with output values
        """
        try:
            outputs = self._get_outputs(output_name)
            return ToolResult(
                success=True,
                data={"outputs": outputs}
            )
        except Exception as e:
            self.logger.error(f"Terraform output error: {e}")
            return ToolResult(success=False, error=str(e))

    def _write_tfvars(self, variables: Dict[str, Any]) -> Path:
        """Write variables to a temporary HCL tfvars file."""
        # Create secure temporary file (not world-readable)
        fd, path = tempfile.mkstemp(suffix=".tfvars.json", dir=self.terraform_dir)
        tfvars_path = Path(path)
        
        # Remove default permissions and set to 600
        os.chmod(tfvars_path, 0o600)
        
        try:
            # Write as JSON (Terraform can parse both HCL and JSON)
            with open(fd, 'w') as f:
                json.dump(variables, f, indent=2, default=str)
            return tfvars_path
        except Exception as e:
            # Clean up on error
            if tfvars_path.exists():
                tfvars_path.unlink()
            raise e

    def _get_outputs(self, output_name: Optional[str] = None) -> Dict[str, Any]:
        """Get Terraform outputs as dictionary."""
        try:
            cmd = ["terraform", "output", "-json"]
            if output_name:
                cmd.append(output_name)
            
            result = subprocess.run(
                cmd,
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                self.logger.warning(f"Failed to get outputs: {result.stderr}")
                return {}
            
            # Parse JSON output
            outputs_raw = json.loads(result.stdout)
            
            # Convert Terraform output format to simple dict
            if output_name:
                return {output_name: outputs_raw.get("value")}
            
            outputs = {}
            for key, value in outputs_raw.items():
                outputs[key] = value.get("value") if isinstance(value, dict) else value
            
            return outputs
        except json.JSONDecodeError:
            self.logger.warning("Failed to parse terraform output as JSON")
            return {}
        except Exception as e:
            self.logger.error(f"Error getting outputs: {e}")
            return {}

    async def validate(
        self,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Validate Terraform configuration syntax.
        
        Args:
            context: Execution context
            
        Returns:
            ToolResult with validation status
        """
        try:
            result = subprocess.run(
                ["terraform", "validate", "-no-color"],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Terraform validation failed: {result.stderr}"
                )
            
            self.logger.info("Terraform configuration valid")
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Terraform validation error: {e}")
            return ToolResult(success=False, error=str(e))

    async def execute(
        self,
        command: str,
        args: Optional[List[str]] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Execute arbitrary terraform command (dispatch method).
        
        Args:
            command: Terraform command (init, plan, apply, destroy, etc.)
            args: Additional arguments for the command
            context: Execution context
            
        Returns:
            ToolResult with command output
        """
        if command == "init":
            return await self.init(context=context)
        elif command == "plan":
            return await self.plan(context=context)
        elif command == "apply":
            return await self.apply(context=context)
        elif command == "destroy":
            return await self.destroy(context=context)
        elif command == "output":
            return await self.output(context=context)
        elif command == "validate":
            return await self.validate(context=context)
        else:
            return ToolResult(
                success=False,
                error=f"Unknown terraform command: {command}"
            )
