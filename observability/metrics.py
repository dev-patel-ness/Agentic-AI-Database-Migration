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
