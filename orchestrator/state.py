"""Shared Pydantic state schema threaded through the LangGraph orchestrator.

Mirrors architecture.md §7 (Shared State Schema). This is the single source of
truth persisted at every checkpoint, enabling replay, audit, and mid-flight
resumption after human review or process restart.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# Allow-listed dialects (architecture.md §14: validate job config against an allow-list).
SUPPORTED_DIALECTS = ("oracle", "mysql", "postgresql")


class JobStatus(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DONE = "DONE"
    ABORTED = "ABORTED"
    ROLLED_BACK = "ROLLED_BACK"


class ReviewDecision(str, Enum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"
    RETRY = "retry"
    ABORT = "abort"


class DialectPair(BaseModel):
    source: str
    target: str


class ObjectRisk(BaseModel):
    object_name: str
    object_type: str
    risk_level: str
    reason: Optional[str] = None


class DiscoveryResult(BaseModel):
    object_catalog: list[dict[str, Any]] = Field(default_factory=list)
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)


class MigrationPlan(BaseModel):
    tables: int = 0
    views: int = 0
    procedures: int = 0
    functions: int = 0
    triggers: int = 0
    risk_register: list[ObjectRisk] = Field(default_factory=list)
    manual_review_objects: list[str] = Field(default_factory=list)


class ApprovalRecord(BaseModel):
    phase: str
    decision: str
    reviewer: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    comment: Optional[str] = None


class RetryRecord(BaseModel):
    phase: str
    attempt: int
    status: str  # "FAILED" or "SUCCESS"
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_seconds: Optional[float] = None


class TranslationResult(BaseModel):
    translated_objects: list[dict[str, Any]] = Field(default_factory=list)
    average_confidence: Optional[float] = None


class CodeRefactorResult(BaseModel):
    files_changed: list[str] = Field(default_factory=list)
    diff: Optional[str] = None


class DataMigrationResult(BaseModel):
    rows_moved: int = 0
    lag_seconds: Optional[float] = None
    tables: list[dict[str, Any]] = Field(default_factory=list)
    ddl_applications: list[dict[str, Any]] = Field(default_factory=list)


class ChecksumResult(BaseModel):
    table_name: str
    status: str
    checksum_source: Optional[str] = None
    checksum_target: Optional[str] = None


class ValidationReport(BaseModel):
    table_checksums: list[ChecksumResult] = Field(default_factory=list)
    mismatches: int = 0
    overall_status: str = "PENDING"


class TestReport(BaseModel):
    overall_status: str = "PENDING"
    details: list[dict[str, Any]] = Field(default_factory=list)


class DeploymentStatus(BaseModel):
    status: str = "PENDING"
    detail: Optional[str] = None


class MigrationState(BaseModel):
    """LangGraph state schema. Node functions return partial-update dicts of these fields."""

    job_id: str
    dialects: DialectPair
    discovery: Optional[DiscoveryResult] = None
    plan: Optional[MigrationPlan] = None
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    retry_history: list[RetryRecord] = Field(default_factory=list)
    schema_translation: Optional[TranslationResult] = None
    code_refactor: Optional[CodeRefactorResult] = None
    data_migration: Optional[DataMigrationResult] = None
    validation: Optional[ValidationReport] = None
    test_report: Optional[TestReport] = None
    deployment: Optional[DeploymentStatus] = None

    current_phase: str = "Discover"
    status: str = JobStatus.RUNNING.value
    retry_count: int = 0
    max_retries: int = 3

    # Transient routing fields: hold the latest reviewer decision for each human
    # gate so the graph's conditional edges can route without re-parsing approvals.
    plan_decision: Optional[str] = None
    validation_decision: Optional[str] = None
    cutover_decision: Optional[str] = None
