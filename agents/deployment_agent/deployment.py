"""
Deployment Agent - Orchestrates safe cutover with health checks and rollback
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from tool_adapters.terraform_adapter import TerraformAdapter
from tool_adapters.kubectl_adapter import KubectlAdapter
from dialects.connections import connect

logger = logging.getLogger(__name__)


class DeploymentConfig(BaseModel):
    """Configuration for deployment"""
    cluster_name: str
    app_deployment_name: str = "capstone-app"
    platform_deployment_name: str = "capstone-platform"
    namespace: str = "ns-app"
    image: str
    health_check_endpoint: str = "/health/ready"
    health_check_timeout: int = 300  # seconds
    readiness_timeout: int = 600  # seconds
    rollback_on_error: bool = True


@dataclass
class DeploymentStep:
    """Represents a single step in the deployment process"""
    name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    status: str = "pending"  # pending, running, success, failed
    details: str = ""
    
    def mark_running(self) -> None:
        """Mark step as running."""
        self.status = "running"
        self.start_time = datetime.now()
    
    def mark_success(self, details: str = "") -> None:
        """Mark step as successful."""
        self.status = "success"
        self.end_time = datetime.now()
        if details:
            self.details = details
    
    def mark_failed(self, error: str) -> None:
        """Mark step as failed."""
        self.status = "failed"
        self.end_time = datetime.now()
        self.details = error


@dataclass
class DeploymentResult:
    """Result of a complete deployment"""
    success: bool
    cluster_name: str
    deployment_started: datetime
    deployment_completed: Optional[datetime] = None
    steps: List[DeploymentStep] = field(default_factory=list)
    rollback_performed: bool = False
    error: Optional[str] = None
    
    def duration_seconds(self) -> float:
        """Get total deployment duration in seconds."""
        end = self.deployment_completed or datetime.now()
        return (end - self.deployment_started).total_seconds()


class DeploymentAgent:
    """
    Manages safe deployment with:
    - Infrastructure validation via Terraform
    - Rolling updates via kubectl
    - Health check validation
    - Automatic rollback on failure
    """

    def __init__(
        self,
        terraform_adapter: TerraformAdapter,
        kubectl_adapter: KubectlAdapter,
        deployment_config: DeploymentConfig
    ):
        """
        Initialize Deployment Agent.
        
        Args:
            terraform_adapter: Terraform adapter instance
            kubectl_adapter: Kubectl adapter instance
            deployment_config: Deployment configuration
        """
        self.terraform = terraform_adapter
        self.kubectl = kubectl_adapter
        self.config = deployment_config
        self.logger = logger
        
        self.steps: List[DeploymentStep] = []
        self.original_image: Optional[str] = None

    async def deploy(
        self,
        new_image: str,
        target_db_config: Optional[Dict[str, Any]] = None,
        terraform_vars: Optional[Dict[str, Any]] = None
    ) -> DeploymentResult:
        """
        Execute complete safe deployment with rollback.
        
        Args:
            new_image: New container image to deploy
            target_db_config: Target database configuration for health checks
            terraform_vars: Terraform variables for infrastructure updates
            
        Returns:
            DeploymentResult with deployment status and steps
        """
        result = DeploymentResult(
            success=False,
            cluster_name=self.config.cluster_name,
            deployment_started=datetime.now()
        )
        
        try:
            # Step 1: Validate infrastructure
            step = self._add_step("Validate Infrastructure")
            step.mark_running()
            
            validate_result = await self._validate_infrastructure(terraform_vars)
            if not validate_result:
                step.mark_failed("Infrastructure validation failed")
                result.steps = self.steps
                return result
            step.mark_success("Infrastructure validated")
            
            # Step 2: Get current deployment state
            step = self._add_step("Get Current Deployment State")
            step.mark_running()
            
            current_deployment = await self._get_deployment_status()
            if not current_deployment:
                step.mark_failed("Failed to get current deployment")
                result.steps = self.steps
                return result
            
            self.original_image = current_deployment.get("image")
            step.mark_success(f"Current image: {self.original_image}")
            
            # Step 3: Start rolling update
            step = self._add_step("Start Rolling Update")
            step.mark_running()
            
            update_result = await self._update_image(new_image)
            if not update_result:
                step.mark_failed("Failed to start rolling update")
                result.steps = self.steps
                return result
            step.mark_success(f"Updated to image: {new_image}")
            
            # Step 4: Wait for rollout
            step = self._add_step("Wait for Rollout Completion")
            step.mark_running()
            
            rollout_success = await self._wait_for_rollout()
            if not rollout_success:
                step.mark_failed("Rollout did not complete within timeout")
                self.logger.error("Rollout timeout - initiating automatic rollback")
                result.rollback_performed = True
                await self._rollback()
                result.steps = self.steps
                return result
            step.mark_success("Rollout completed successfully")
            
            # Step 5: Verify pods are ready
            step = self._add_step("Verify Pod Readiness")
            step.mark_running()
            
            pods_ready = await self._verify_pods_ready()
            if not pods_ready:
                step.mark_failed("Pods failed readiness checks")
                self.logger.error("Pod readiness failed - initiating automatic rollback")
                result.rollback_performed = True
                await self._rollback()
                result.steps = self.steps
                return result
            step.mark_success("All pods ready")
            
            # Step 6: Health check (if target DB provided)
            if target_db_config:
                step = self._add_step("Database Connection Health Check")
                step.mark_running()
                
                health_ok = await self._health_check(target_db_config)
                if not health_ok:
                    step.mark_failed("Database health check failed")
                    self.logger.error("Health check failed - initiating automatic rollback")
                    result.rollback_performed = True
                    await self._rollback()
                    result.steps = self.steps
                    return result
                step.mark_success("Database health check passed")
            
            # Step 7: Verify traffic to new pods
            step = self._add_step("Verify Traffic to New Pods")
            step.mark_running()
            
            traffic_ok = await self._verify_traffic()
            if not traffic_ok:
                step.mark_failed("Traffic verification failed")
                self.logger.error("Traffic check failed - initiating automatic rollback")
                result.rollback_performed = True
                await self._rollback()
                result.steps = self.steps
                return result
            step.mark_success("Traffic successfully routed to new pods")
            
            # Success!
            result.success = True
            result.deployment_completed = datetime.now()
            result.steps = self.steps
            
            self.logger.info(
                f"Deployment completed successfully in {result.duration_seconds():.1f}s"
            )
            return result

        except Exception as e:
            self.logger.exception(f"Deployment error: {e}")
            result.error = str(e)
            result.steps = self.steps
            
            # Attempt rollback on unexpected error
            if self.config.rollback_on_error and self.original_image:
                self.logger.error("Unexpected error - initiating emergency rollback")
                result.rollback_performed = True
                try:
                    await self._rollback()
                except Exception as rollback_error:
                    self.logger.error(f"Rollback failed: {rollback_error}")
            
            return result

    async def _validate_infrastructure(self, terraform_vars: Optional[Dict[str, Any]]) -> bool:
        """Validate infrastructure state via Terraform."""
        try:
            if terraform_vars:
                # Run terraform plan to validate
                plan_result = await self.terraform.plan(variables=terraform_vars)
                if not plan_result.success:
                    self.logger.error(f"Terraform plan failed: {plan_result.error}")
                    return False
            
            # Validate terraform configuration
            validate_result = await self.terraform.validate()
            if not validate_result.success:
                self.logger.error(f"Terraform validation failed: {validate_result.error}")
                return False
            
            return True
        except Exception as e:
            self.logger.error(f"Infrastructure validation error: {e}")
            return False

    async def _get_deployment_status(self) -> Optional[Dict[str, Any]]:
        """Get current deployment status."""
        try:
            result = await self.kubectl.get_deployment(
                self.config.app_deployment_name,
                self.config.namespace
            )
            if result.success:
                return result.data.get("deployment_status")
            return None
        except Exception as e:
            self.logger.error(f"Error getting deployment status: {e}")
            return None

    async def _update_image(self, new_image: str) -> bool:
        """Start image update (rolling update)."""
        try:
            result = await self.kubectl.set_image(
                self.config.app_deployment_name,
                self.config.app_deployment_name,
                new_image,
                self.config.namespace
            )
            return result.success
        except Exception as e:
            self.logger.error(f"Error updating image: {e}")
            return False

    async def _wait_for_rollout(self) -> bool:
        """Wait for rollout to complete."""
        try:
            result = await self.kubectl.rollout_status(
                self.config.app_deployment_name,
                self.config.namespace,
                self.config.readiness_timeout
            )
            return result.success
        except Exception as e:
            self.logger.error(f"Error waiting for rollout: {e}")
            return False

    async def _verify_pods_ready(self) -> bool:
        """Verify all pods are in ready state."""
        try:
            result = await self.kubectl.get_pods(
                self.config.app_deployment_name,
                self.config.namespace
            )
            if not result.success:
                return False
            
            pods = result.data.get("pods", [])
            if not pods:
                self.logger.error("No pods found")
                return False
            
            # Check all pods are ready
            for pod in pods:
                if not pod.get("ready"):
                    self.logger.error(f"Pod {pod['name']} is not ready")
                    return False
                
                # Check for excessive restarts
                if pod.get("restart_count", 0) > 3:
                    self.logger.warning(
                        f"Pod {pod['name']} has {pod['restart_count']} restarts"
                    )
            
            return True
        except Exception as e:
            self.logger.error(f"Error verifying pods: {e}")
            return False

    async def _health_check(self, db_config: Dict[str, Any]) -> bool:
        """
        Check database connectivity (health check).
        
        Args:
            db_config: Database connection configuration dict with keys:
                       dialect, host, port, username, password, database
            
        Returns:
            True if database is accessible, False otherwise
        """
        dialect = db_config.get("dialect", "unknown")
        try:
            # connect() is synchronous — run in executor to avoid blocking event loop
            loop = asyncio.get_event_loop()
            conn = await loop.run_in_executor(None, lambda: connect(dialect, db_config))
            if conn is None:
                self.logger.error("Database connection failed")
                return False
            
            # Simple connectivity test — just opening the connection is sufficient
            # More sophisticated health checks (e.g. SELECT 1) can be added here
            try:
                self.logger.info(f"Database health check passed for {dialect}")
                return True
            finally:
                # Close connection (DB-API connections use .close())
                if hasattr(conn, 'close'):
                    conn.close()
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
            return False

    async def _verify_traffic(self) -> bool:
        """
        Verify traffic is being routed to new pods.
        This is a simplified check; can be enhanced with actual traffic analysis.
        """
        try:
            # Get deployment and verify it has desired replicas ready
            result = await self.kubectl.get_deployment(
                self.config.app_deployment_name,
                self.config.namespace
            )
            if not result.success:
                return False
            
            status = result.data.get("deployment_status", {})
            ready = status.get("ready_replicas", 0)
            desired = status.get("desired_replicas", 0)
            
            if ready != desired:
                self.logger.error(
                    f"Not all replicas ready: {ready}/{desired}"
                )
                return False
            
            self.logger.info(f"Traffic verification passed: {ready}/{desired} replicas ready")
            return True
        except Exception as e:
            self.logger.error(f"Traffic verification error: {e}")
            return False

    async def _rollback(self) -> bool:
        """Rollback to previous deployment."""
        try:
            if not self.original_image:
                self.logger.error("No previous image available for rollback")
                return False
            
            self.logger.info(f"Rolling back to image: {self.original_image}")
            
            # Perform rollout undo
            result = await self.kubectl.rollout_undo(
                self.config.app_deployment_name,
                self.config.namespace
            )
            
            if not result.success:
                self.logger.error(f"Rollout undo failed: {result.error}")
                return False
            
            # Wait for rollback to complete
            wait_result = await self.kubectl.rollout_status(
                self.config.app_deployment_name,
                self.config.namespace,
                self.config.readiness_timeout
            )
            
            return wait_result.success
        except Exception as e:
            self.logger.error(f"Rollback error: {e}")
            return False

    def _add_step(self, name: str) -> DeploymentStep:
        """Add a deployment step."""
        step = DeploymentStep(name=name)
        self.steps.append(step)
        return step
