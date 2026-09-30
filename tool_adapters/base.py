"""
Abstract contract every tool adapter (CrackSQL, SeaTunnel, OpenRewrite, ...) must implement.

This module defines the unified interface that all tool adapters follow, ensuring
consistent integration with the LangGraph orchestrator and Agent nodes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class AdapterType(str, Enum):
    """Types of tools supported by adapters."""

    SQL_TRANSLATOR = "sql_translator"  # CrackSQL
    CODE_REFACTORER = "code_refactorer"  # OpenRewrite, Aider
    DATA_MIGRATOR = "data_migrator"  # SeaTunnel
    SCHEMA_EXTRACTOR = "schema_extractor"  # SQL parser
    VALIDATOR = "validator"  # Checksum, integrity checks
    ORCHESTRATOR = "orchestrator"  # Terraform, Kubectl


class ExecutionState(str, Enum):
    """States of tool execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


@dataclass
class AdapterConfig:
    """Normalized, validated configuration handed to `run()`."""

    options: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 3600
    dry_run: bool = False
    verbose: bool = False


@dataclass
class ToolResult:
    """Outcome of a single adapter invocation."""

    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    execution_time_seconds: float = 0.0
    confidence_score: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobStatus:
    """Point-in-time status of a long-running adapter job."""

    job_id: str
    state: ExecutionState
    progress_percent: int = 0
    detail: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RollbackResult:
    """Outcome of a rollback attempt for a previously run adapter job."""

    success: bool
    detail: dict[str, Any] = field(default_factory=dict)
    rollback_time_seconds: float = 0.0


class BaseToolAdapter(ABC):
    """
    Plugin interface: agents call adapters generically through this contract only.

    Every tool adapter must implement these core methods:
    - prepare: Validate and normalize raw config
    - run: Execute the tool synchronously
    - status: Report long-running job status
    - rollback: Undo effects of a previous execution
    """

    @abstractmethod
    def prepare(self, config: dict[str, Any]) -> AdapterConfig:
        """
        Validate and normalize raw job config into an `AdapterConfig`.

        Args:
            config: Raw configuration dictionary from the agent/orchestrator.

        Returns:
            Normalized AdapterConfig ready to pass to run().

        Raises:
            ValueError: If configuration is invalid.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, config: AdapterConfig) -> ToolResult:
        """
        Execute the underlying tool and return its result.

        Args:
            config: Normalized configuration from prepare().

        Returns:
            ToolResult with success status and output.
        """
        raise NotImplementedError

    @abstractmethod
    def status(self, job_id: str) -> JobStatus:
        """
        Report the current status of a previously started job.

        Args:
            job_id: Identifier of a long-running job.

        Returns:
            JobStatus with current state and progress.
        """
        raise NotImplementedError

    @abstractmethod
    def rollback(self, job_id: str) -> RollbackResult:
        """
        Undo the effects of a previously run job, where supported.

        Args:
            job_id: Identifier of the job to rollback.

        Returns:
            RollbackResult indicating success/failure of rollback.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def adapter_type(self) -> AdapterType:
        """Return the type of tool this adapter supports."""
        raise NotImplementedError

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of this adapter and tool."""
        raise NotImplementedError
