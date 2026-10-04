"""Prometheus metrics for Phase 7 observability and monitoring.

Tracks validation progress, retry attempts, migration latency, and checksum results.
"""

from prometheus_client import Counter, Gauge, Histogram

# Validation metrics
migration_validation_total_tables = Gauge(
    'migration_validation_total_tables',
    'Total tables to validate',
    ['job_id', 'source_dialect', 'target_dialect']
)

migration_validation_passed_tables = Gauge(
    'migration_validation_passed_tables',
    'Number of tables that passed validation',
    ['job_id', 'source_dialect', 'target_dialect']
)

migration_validation_checksum_duration = Histogram(
    'migration_validation_checksum_duration_seconds',
    'Time to compute checksum for a table',
    ['table_name', 'source_dialect', 'target_dialect'],
    buckets=[1, 5, 10, 30, 60, 120, 300]
)

migration_validation_mismatches_total = Counter(
    'migration_validation_mismatches_total',
    'Total checksum mismatches detected',
    ['table_name', 'job_id', 'source_dialect', 'target_dialect']
)

migration_validation_row_count_mismatch = Counter(
    'migration_validation_row_count_mismatch',
    'Row count differences detected between source and target',
    ['table_name', 'job_id', 'source_dialect', 'target_dialect']
)

# Retry metrics
migration_retry_count = Counter(
    'migration_retry_count',
    'Number of retries per phase',
    ['job_id', 'phase', 'source_dialect', 'target_dialect']
)

migration_retry_success = Counter(
    'migration_retry_success',
    'Successful retries',
    ['job_id', 'phase', 'source_dialect', 'target_dialect']
)

migration_retry_failure = Counter(
    'migration_retry_failure',
    'Failed retries (exceeded max attempts)',
    ['job_id', 'phase', 'source_dialect', 'target_dialect']
)

# Latency metrics
migration_phase_duration = Histogram(
    'migration_phase_duration_seconds',
    'Time to complete each migration phase',
    ['phase', 'source_dialect', 'target_dialect'],
    buckets=[5, 30, 60, 300, 900, 3600]
)

migration_data_throughput = Gauge(
    'migration_data_throughput_rows_per_second',
    'Data migration throughput',
    ['table_name', 'job_id', 'source_dialect', 'target_dialect']
)

# Overall migration status
migration_job_status = Gauge(
    'migration_job_status',
    'Current job status (1=RUNNING, 0=PAUSED, 2=DONE, 3=ABORTED)',
    ['job_id', 'source_dialect', 'target_dialect']
)

migration_job_current_phase = Gauge(
    'migration_job_current_phase',
    'Current phase index (0=Discover, 1=Plan, 2=Translate, 3=Migrate, 4=Validate, 5=Test, 6=Cutover, 7=Done)',
    ['job_id', 'source_dialect', 'target_dialect']
)


def record_validation_progress(
    job_id: str,
    source_dialect: str,
    target_dialect: str,
    total_tables: int,
    passed_tables: int,
):
    """Record validation progress."""
    migration_validation_total_tables.labels(
        job_id=job_id,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).set(total_tables)
    
    migration_validation_passed_tables.labels(
        job_id=job_id,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).set(passed_tables)


def record_checksum_duration(
    table_name: str,
    source_dialect: str,
    target_dialect: str,
    duration_seconds: float,
):
    """Record checksum computation time."""
    migration_validation_checksum_duration.labels(
        table_name=table_name,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).observe(duration_seconds)


def record_checksum_mismatch(
    table_name: str,
    job_id: str,
    source_dialect: str,
    target_dialect: str,
):
    """Record a checksum mismatch."""
    migration_validation_mismatches_total.labels(
        table_name=table_name,
        job_id=job_id,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).inc()


def record_row_count_mismatch(
    table_name: str,
    job_id: str,
    source_dialect: str,
    target_dialect: str,
):
    """Record a row count mismatch."""
    migration_validation_row_count_mismatch.labels(
        table_name=table_name,
        job_id=job_id,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).inc()


def record_retry(
    job_id: str,
    phase: str,
    source_dialect: str,
    target_dialect: str,
    success: bool,
):
    """Record a retry attempt."""
    migration_retry_count.labels(
        job_id=job_id,
        phase=phase,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).inc()
    
    if success:
        migration_retry_success.labels(
            job_id=job_id,
            phase=phase,
            source_dialect=source_dialect,
            target_dialect=target_dialect
        ).inc()
    else:
        migration_retry_failure.labels(
            job_id=job_id,
            phase=phase,
            source_dialect=source_dialect,
            target_dialect=target_dialect
        ).inc()


def record_phase_duration(
    phase: str,
    source_dialect: str,
    target_dialect: str,
    duration_seconds: float,
):
    """Record phase completion time."""
    migration_phase_duration.labels(
        phase=phase,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).observe(duration_seconds)


def record_data_throughput(
    table_name: str,
    job_id: str,
    source_dialect: str,
    target_dialect: str,
    rows_per_second: float,
):
    """Record data migration throughput."""
    migration_data_throughput.labels(
        table_name=table_name,
        job_id=job_id,
        source_dialect=source_dialect,
        target_dialect=target_dialect
    ).set(rows_per_second)


# ===== Phase 9: Observability & Deployment Metrics =====

# Agent invocation metrics
agent_invocations_total = Counter(
    'agent_invocations_total',
    'Total number of agent invocations',
    ['agent_name', 'job_id']
)

agent_invocations_success = Counter(
    'agent_invocations_success_total',
    'Successful agent invocations',
    ['agent_name', 'job_id']
)

agent_invocations_failure = Counter(
    'agent_invocations_failure_total',
    'Failed agent invocations',
    ['agent_name', 'job_id', 'error_type']
)

agent_latency = Histogram(
    'agent_latency_seconds',
    'Agent execution latency',
    ['agent_name', 'job_id'],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 300]
)

# Tool adapter metrics
tool_adapter_calls_total = Counter(
    'tool_adapter_calls_total',
    'Total tool adapter invocations',
    ['tool_name', 'operation']
)

tool_adapter_success = Counter(
    'tool_adapter_success_total',
    'Successful tool adapter calls',
    ['tool_name', 'operation']
)

tool_adapter_failure = Counter(
    'tool_adapter_failure_total',
    'Failed tool adapter calls',
    ['tool_name', 'operation', 'error_type']
)

tool_adapter_latency = Histogram(
    'tool_adapter_latency_seconds',
    'Tool adapter execution latency',
    ['tool_name', 'operation'],
    buckets=[0.5, 1, 5, 10, 30, 60, 120, 300, 600]
)

# Pod health metrics
pod_ready_replicas = Gauge(
    'pod_ready_replicas',
    'Number of ready pod replicas',
    ['deployment_name', 'namespace', 'cluster_name']
)

pod_available_replicas = Gauge(
    'pod_available_replicas',
    'Number of available pod replicas',
    ['deployment_name', 'namespace', 'cluster_name']
)

pod_desired_replicas = Gauge(
    'pod_desired_replicas',
    'Desired number of pod replicas',
    ['deployment_name', 'namespace', 'cluster_name']
)

pod_restart_count = Gauge(
    'pod_restart_count',
    'Total pod restarts',
    ['pod_name', 'namespace', 'cluster_name']
)

# Deployment rollout metrics
deployment_rollout_success_total = Counter(
    'deployment_rollout_success_total',
    'Successful deployment rollouts',
    ['deployment_name', 'namespace', 'cluster_name']
)

deployment_rollout_failure_total = Counter(
    'deployment_rollout_failure_total',
    'Failed deployment rollouts',
    ['deployment_name', 'namespace', 'cluster_name', 'error_reason']
)

deployment_rollback_total = Counter(
    'deployment_rollback_total',
    'Number of deployment rollbacks triggered',
    ['deployment_name', 'namespace', 'cluster_name', 'rollback_reason']
)

deployment_rollout_duration = Histogram(
    'deployment_rollout_duration_seconds',
    'Time to complete deployment rollout',
    ['deployment_name', 'namespace', 'cluster_name'],
    buckets=[10, 30, 60, 120, 300, 600]
)

# LLM cost and token tracking
llm_tokens_input_total = Counter(
    'llm_tokens_input_total',
    'Total LLM input tokens consumed',
    ['model_name', 'agent_name']
)

llm_tokens_output_total = Counter(
    'llm_tokens_output_total',
    'Total LLM output tokens generated',
    ['model_name', 'agent_name']
)

llm_call_latency = Histogram(
    'llm_call_latency_seconds',
    'Latency of individual LLM calls',
    ['model_name', 'agent_name'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

# Helper functions for Phase 9 metrics

def record_agent_invocation(
    agent_name: str,
    job_id: str,
    success: bool,
    duration_seconds: float,
    error_type: str = None,
):
    """Record agent invocation metrics."""
    agent_invocations_total.labels(agent_name=agent_name, job_id=job_id).inc()
    agent_latency.labels(agent_name=agent_name, job_id=job_id).observe(duration_seconds)
    
    if success:
        agent_invocations_success.labels(agent_name=agent_name, job_id=job_id).inc()
    else:
        agent_invocations_failure.labels(
            agent_name=agent_name,
            job_id=job_id,
            error_type=error_type or "unknown"
        ).inc()


def record_tool_adapter_call(
    tool_name: str,
    operation: str,
    success: bool,
    duration_seconds: float,
    error_type: str = None,
):
    """Record tool adapter call metrics."""
    tool_adapter_calls_total.labels(tool_name=tool_name, operation=operation).inc()
    tool_adapter_latency.labels(tool_name=tool_name, operation=operation).observe(duration_seconds)
    
    if success:
        tool_adapter_success.labels(tool_name=tool_name, operation=operation).inc()
    else:
        tool_adapter_failure.labels(
            tool_name=tool_name,
            operation=operation,
            error_type=error_type or "unknown"
        ).inc()


def record_pod_health(
    deployment_name: str,
    namespace: str,
    cluster_name: str,
    ready_replicas: int,
    available_replicas: int,
    desired_replicas: int,
):
    """Record pod health metrics."""
    pod_ready_replicas.labels(
        deployment_name=deployment_name,
        namespace=namespace,
        cluster_name=cluster_name
    ).set(ready_replicas)
    
    pod_available_replicas.labels(
        deployment_name=deployment_name,
        namespace=namespace,
        cluster_name=cluster_name
    ).set(available_replicas)
    
    pod_desired_replicas.labels(
        deployment_name=deployment_name,
        namespace=namespace,
        cluster_name=cluster_name
    ).set(desired_replicas)


def record_deployment_rollout(
    deployment_name: str,
    namespace: str,
    cluster_name: str,
    success: bool,
    duration_seconds: float,
    error_reason: str = None,
):
    """Record deployment rollout metrics."""
    deployment_rollout_duration.labels(
        deployment_name=deployment_name,
        namespace=namespace,
        cluster_name=cluster_name
    ).observe(duration_seconds)
    
    if success:
        deployment_rollout_success_total.labels(
            deployment_name=deployment_name,
            namespace=namespace,
            cluster_name=cluster_name
        ).inc()
    else:
        deployment_rollout_failure_total.labels(
            deployment_name=deployment_name,
            namespace=namespace,
            cluster_name=cluster_name,
            error_reason=error_reason or "unknown"
        ).inc()


def record_deployment_rollback(
    deployment_name: str,
    namespace: str,
    cluster_name: str,
    rollback_reason: str,
):
    """Record deployment rollback metrics."""
    deployment_rollback_total.labels(
        deployment_name=deployment_name,
        namespace=namespace,
        cluster_name=cluster_name,
        rollback_reason=rollback_reason
    ).inc()


def record_llm_call(
    model_name: str,
    agent_name: str,
    tokens_input: int = 0,
    tokens_output: int = 0,
    duration_seconds: float = 0,
):
    """Record LLM call metrics (tokens and latency)."""
    if tokens_input > 0:
        llm_tokens_input_total.labels(model_name=model_name, agent_name=agent_name).inc(tokens_input)
    
    if tokens_output > 0:
        llm_tokens_output_total.labels(model_name=model_name, agent_name=agent_name).inc(tokens_output)
    
    if duration_seconds > 0:
        llm_call_latency.labels(model_name=model_name, agent_name=agent_name).observe(duration_seconds)
