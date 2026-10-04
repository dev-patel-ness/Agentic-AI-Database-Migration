"""Helpers for agents to log execution steps to the MigrationState execution_trace.

Usage in agents:
    from orchestrator.execution_trace import add_step, log_step
    
    # When returning from a node, include the trace updates
    return {
        "execution_trace": add_step(state.execution_trace, phase="Discover", 
                                    operation="Running SchemaExtractorAdapter",
                                    details="Fetching schema for 'employees' table"),
        # ... other state updates ...
    }
    
    # Or use log_step() for convenience in sequential logging
    trace = log_step(trace, phase, operation, details, status, error)
"""

from __future__ import annotations

from orchestrator.state import ExecutionStep


def add_step(
    trace: list[ExecutionStep],
    phase: str,
    operation: str,
    details: str | None = None,
    status: str = "SUCCESS",
    error: str | None = None,
) -> list[ExecutionStep]:
    """Add a new execution step to the trace.
    
    Args:
        trace: Current execution trace list
        phase: Phase name (e.g., "Discover", "Analyse", "Transform", etc.)
        operation: Descriptive operation (e.g., "Running SchemaExtractorAdapter", "LLM call for employees schema")
        details: Additional context (prompt, parameters, result summary, etc.)
        status: "IN_PROGRESS", "SUCCESS", or "FAILED"
        error: Error message if status is FAILED
        
    Returns:
        Updated trace with new step appended
    """
    new_step = ExecutionStep(
        phase=phase,
        operation=operation,
        details=details,
        status=status,
        error=error,
    )
    return trace + [new_step]


def log_step(
    trace: list[ExecutionStep],
    phase: str,
    operation: str,
    details: str | None = None,
    status: str = "SUCCESS",
    error: str | None = None,
) -> list[ExecutionStep]:
    """Alias for add_step (same functionality)."""
    return add_step(trace, phase, operation, details, status, error)
