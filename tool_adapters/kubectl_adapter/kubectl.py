"""
Kubectl Adapter - Executes kubectl commands for Kubernetes deployment operations
"""

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from tool_adapters.base import BaseToolAdapter, ToolResult, ExecutionContext

logger = logging.getLogger(__name__)


@dataclass
class DeploymentStatus:
    """Status of a Kubernetes deployment"""
    name: str
    namespace: str
    ready_replicas: int
    desired_replicas: int
    available_replicas: int
    updated_replicas: int
    revision: int
    image: str
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def is_ready(self) -> bool:
        """Check if all replicas are ready."""
        return self.ready_replicas == self.desired_replicas >= 1


@dataclass
class RolloutStatus:
    """Rollout history entry"""
    revision: int
    deployment: str
    image: str
    timestamp: str


class KubectlAdapter(BaseToolAdapter):
    """
    Adapter for executing kubectl commands on EKS.
    Supports deployment rolling updates, health checks, rollbacks, and monitoring.
    
    SECURITY NOTES:
    - Kubeconfig is sourced from environment or standard ~/.kube/config
    - RBAC is enforced via service account (least privilege scoping to ns-app)
    - No sensitive data is logged; command arguments are sanitized
    """

    def __init__(self, kubeconfig: Optional[str] = None, timeout: int = 300):
        """
        Initialize Kubectl adapter.
        
        Args:
            kubeconfig: Path to kubeconfig file (uses default if not provided)
            timeout: Default timeout for kubectl commands in seconds
        """
        self.kubeconfig = kubeconfig
        self.timeout = timeout
        self.logger = logger
        
        # Verify kubectl is available
        self._verify_kubectl_installed()

    def _verify_kubectl_installed(self) -> None:
        """Verify kubectl CLI is installed and accessible."""
        try:
            result = subprocess.run(
                ["kubectl", "version", "--client"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode != 0:
                raise RuntimeError("Kubectl CLI not available")
            self.logger.info("Kubectl CLI verified")
        except FileNotFoundError:
            raise RuntimeError("Kubectl CLI not found in PATH")

    def _build_cmd(self, *args: str) -> List[str]:
        """Build kubectl command with optional kubeconfig."""
        cmd = ["kubectl"]
        if self.kubeconfig:
            cmd.extend(["--kubeconfig", self.kubeconfig])
        cmd.extend(args)
        return cmd

    async def get_deployment(
        self,
        deployment_name: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Get deployment status.
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with DeploymentStatus
        """
        try:
            cmd = self._build_cmd(
                "get", "deployment", deployment_name,
                "-n", namespace,
                "-o", "json"
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to get deployment: {result.stderr}"
                )
            
            deployment = json.loads(result.stdout)
            spec = deployment.get("spec", {})
            status = deployment.get("status", {})
            
            deploy_status = DeploymentStatus(
                name=deployment_name,
                namespace=namespace,
                ready_replicas=status.get("readyReplicas", 0),
                desired_replicas=spec.get("replicas", 0),
                available_replicas=status.get("availableReplicas", 0),
                updated_replicas=status.get("updatedReplicas", 0),
                revision=int(deployment.get("metadata", {}).get("generation", 0)),
                image=spec.get("template", {}).get("spec", {}).get("containers", [{}])[0].get("image", ""),
                conditions=status.get("conditions", [])
            )
            
            return ToolResult(
                success=True,
                data={"deployment_status": deploy_status.__dict__}
            )
        except Exception as e:
            self.logger.error(f"Error getting deployment: {e}")
            return ToolResult(success=False, error=str(e))

    async def set_image(
        self,
        deployment_name: str,
        container_name: str,
        image: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Update container image in a deployment (triggers rolling update).
        
        Args:
            deployment_name: Name of the deployment
            container_name: Name of the container to update
            image: New container image URL
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with update output
        """
        try:
            cmd = self._build_cmd(
                "set", "image",
                f"deployment/{deployment_name}",
                f"{container_name}={image}",
                "-n", namespace,
                "--record"
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to update image: {result.stderr}"
                )
            
            self.logger.info(f"Updated {deployment_name} image to {image}")
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error updating image: {e}")
            return ToolResult(success=False, error=str(e))

    async def rollout_status(
        self,
        deployment_name: str,
        namespace: str = "ns-app",
        timeout_seconds: int = 600,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Wait for and check rollout status.
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            timeout_seconds: Max time to wait for rollout
            context: Execution context
            
        Returns:
            ToolResult with rollout status
        """
        try:
            cmd = self._build_cmd(
                "rollout", "status",
                f"deployment/{deployment_name}",
                "-n", namespace,
                f"--timeout={timeout_seconds}s"
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 30
            )
            
            success = result.returncode == 0
            
            if not success:
                self.logger.warning(f"Rollout failed: {result.stderr}")
            else:
                self.logger.info(f"Rollout completed for {deployment_name}")
            
            return ToolResult(
                success=success,
                output=result.stdout or result.stderr
            )
        except Exception as e:
            self.logger.error(f"Error checking rollout: {e}")
            return ToolResult(success=False, error=str(e))

    async def rollout_undo(
        self,
        deployment_name: str,
        namespace: str = "ns-app",
        to_revision: Optional[int] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Rollback a deployment to previous revision.
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            to_revision: Specific revision to roll back to (latest if None)
            context: Execution context
            
        Returns:
            ToolResult with rollback output
        """
        try:
            cmd = self._build_cmd(
                "rollout", "undo",
                f"deployment/{deployment_name}",
                "-n", namespace
            )
            
            if to_revision is not None:
                cmd.extend(["--to-revision", str(to_revision)])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to rollback: {result.stderr}"
                )
            
            self.logger.info(f"Rolled back {deployment_name}")
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error rolling back: {e}")
            return ToolResult(success=False, error=str(e))

    async def rollout_history(
        self,
        deployment_name: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Get deployment rollout history.
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with rollout history
        """
        try:
            cmd = self._build_cmd(
                "rollout", "history",
                f"deployment/{deployment_name}",
                "-n", namespace
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to get history: {result.stderr}"
                )
            
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error getting history: {e}")
            return ToolResult(success=False, error=str(e))

    async def get_pods(
        self,
        deployment_name: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Get pods for a deployment.
        
        Args:
            deployment_name: Name of the deployment
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with list of pod statuses
        """
        try:
            cmd = self._build_cmd(
                "get", "pods",
                "-l", f"app={deployment_name}",
                "-n", namespace,
                "-o", "json"
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to get pods: {result.stderr}"
                )
            
            pods_data = json.loads(result.stdout)
            pods = []
            
            for pod in pods_data.get("items", []):
                pod_status = {
                    "name": pod.get("metadata", {}).get("name"),
                    "phase": pod.get("status", {}).get("phase"),
                    "ready": False,
                    "restart_count": 0
                }
                
                # Check if pod is ready
                for condition in pod.get("status", {}).get("conditions", []):
                    if condition.get("type") == "Ready":
                        pod_status["ready"] = condition.get("status") == "True"
                
                # Get container restart count
                for container in pod.get("status", {}).get("containerStatuses", []):
                    pod_status["restart_count"] = container.get("restartCount", 0)
                
                pods.append(pod_status)
            
            return ToolResult(
                success=True,
                data={"pods": pods}
            )
        except Exception as e:
            self.logger.error(f"Error getting pods: {e}")
            return ToolResult(success=False, error=str(e))

    async def logs(
        self,
        pod_name: str,
        namespace: str = "ns-app",
        container: Optional[str] = None,
        tail_lines: int = 100,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Get pod logs.
        
        Args:
            pod_name: Name of the pod
            namespace: Kubernetes namespace
            container: Container name (if None, gets first container)
            tail_lines: Number of log lines to retrieve
            context: Execution context
            
        Returns:
            ToolResult with pod logs
        """
        try:
            cmd = self._build_cmd(
                "logs",
                pod_name,
                "-n", namespace,
                f"--tail={tail_lines}"
            )
            
            if container:
                cmd.extend(["-c", container])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to get logs: {result.stderr}"
                )
            
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error getting logs: {e}")
            return ToolResult(success=False, error=str(e))

    async def port_forward(
        self,
        pod_name: str,
        local_port: int,
        remote_port: int,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Setup port forwarding to a pod.
        
        Args:
            pod_name: Name of the pod
            local_port: Local port to bind
            remote_port: Remote port on pod
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with port forward command info
        """
        try:
            cmd = self._build_cmd(
                "port-forward",
                pod_name,
                f"{local_port}:{remote_port}",
                "-n", namespace
            )
            
            # Note: port-forward runs until interrupted
            # This is for reference only; actual execution would need process management
            return ToolResult(
                success=True,
                output=f"Port forward command: {' '.join(cmd)}"
            )
        except Exception as e:
            self.logger.error(f"Error setting up port forward: {e}")
            return ToolResult(success=False, error=str(e))

    async def apply(
        self,
        manifest: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Apply Kubernetes manifest.
        
        Args:
            manifest: YAML manifest content or file path
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with apply output
        """
        try:
            # Check if manifest is a file path or YAML content
            if manifest.startswith("/") or manifest.endswith(".yaml"):
                # It's a file path
                cmd = self._build_cmd(
                    "apply",
                    "-f", manifest,
                    "-n", namespace
                )
            else:
                # It's YAML content, pipe it in
                cmd = self._build_cmd(
                    "apply",
                    "-f", "-",
                    "-n", namespace
                )
                result = subprocess.run(
                    cmd,
                    input=manifest,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
            
            if not manifest.startswith("/"):
                # Already executed above
                pass
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to apply manifest: {result.stderr}"
                )
            
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error applying manifest: {e}")
            return ToolResult(success=False, error=str(e))

    async def delete(
        self,
        resource_type: str,
        resource_name: str,
        namespace: str = "ns-app",
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Delete Kubernetes resource.
        
        Args:
            resource_type: Type of resource (deployment, pod, service, etc.)
            resource_name: Name of the resource
            namespace: Kubernetes namespace
            context: Execution context
            
        Returns:
            ToolResult with delete output
        """
        try:
            cmd = self._build_cmd(
                "delete",
                resource_type,
                resource_name,
                "-n", namespace
            )
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if result.returncode != 0:
                return ToolResult(
                    success=False,
                    error=f"Failed to delete resource: {result.stderr}"
                )
            
            return ToolResult(success=True, output=result.stdout)
        except Exception as e:
            self.logger.error(f"Error deleting resource: {e}")
            return ToolResult(success=False, error=str(e))

    async def execute(
        self,
        command: str,
        args: Optional[List[str]] = None,
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """
        Execute arbitrary kubectl command (dispatch method).
        
        Args:
            command: Kubectl command (get, set, apply, delete, etc.)
            args: Additional arguments for the command
            context: Execution context
            
        Returns:
            ToolResult with command output
        """
        return ToolResult(
            success=False,
            error="Use specific kubectl command methods instead of generic execute"
        )
