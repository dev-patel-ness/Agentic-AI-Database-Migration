#!/usr/bin/env python3
"""Full End-to-End Data Migration Test: Source → Target with data verification.

Tests complete data migration pipeline:
1. Connect to source (PostgreSQL) and target (MySQL) databases
2. Verify connectivity and schema
3. Count source data
4. Migrate data via SeaTunnel
5. Count target data
6. Verify row counts match

Prerequisites:
- docker-compose stack running (postgres-sample, mysql-sample, seatunnel)
- .env with correct credentials
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import logging
from datetime import datetime

from dialects.connections import connect
from agents.data_agent import migrate_data
from agents.assessment_agent import run_discovery
from orchestrator.state import DiscoveryResult

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def get_connection_config(dialect: str) -> dict:
    """Get database connection config from environment."""
    if dialect.lower() == "postgresql":
        return {
            "host": os.getenv("POSTGRES_SAMPLE_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_SAMPLE_PORT", "5433")),
            "user": os.getenv("POSTGRES_SAMPLE_USER", "postgres"),
            "password": os.getenv("POSTGRES_SAMPLE_PASSWORD", "postgres_dev_password"),
            "database": os.getenv("POSTGRES_SAMPLE_DATABASE", "sample_source"),
            "schema_name": "sample",  # CRITICAL: specify the schema, not just database
        }
    elif dialect.lower() == "mysql":
        return {
            "host": os.getenv("MYSQL_SAMPLE_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_SAMPLE_PORT", "3306")),
            "username": os.getenv("MYSQL_SAMPLE_USER", "appuser"),
            "password": os.getenv("MYSQL_SAMPLE_PASSWORD", "mysql_dev_password"),
            "database": os.getenv("MYSQL_SAMPLE_DATABASE", "sample_source"),
        }
    else:
        raise ValueError(f"Unsupported dialect: {dialect}")


def verify_connection(dialect: str) -> bool:
    """Test connection to database."""
    try:
        config = get_connection_config(dialect)
        with connect(dialect, config) as conn:
            cursor = conn.cursor()
            if dialect.lower() == "postgresql":
                cursor.execute("SELECT version()")
            else:
                cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()
            cursor.close()
            logger.info("[%s] Connection successful: %s", dialect.upper(), version[0][:60])
            return True
    except Exception as exc:
        logger.error("[%s] Connection failed: %s", dialect.upper(), exc)
        return False


def count_table_rows(dialect: str, config: dict, namespace: str, table_name: str) -> int:
    """Count rows in a table."""
    try:
        with connect(dialect, config) as conn:
            cursor = conn.cursor()
            query = f"SELECT COUNT(*) FROM {namespace}.{table_name}"
            cursor.execute(query)
            count = cursor.fetchone()[0]
            cursor.close()
            return count
    except Exception as exc:
        logger.warning("Failed to count rows in %s.%s: %s", namespace, table_name, exc)
        return -1


def get_schema_details(dialect: str, config: dict, namespace: str, table_name: str) -> dict:
    """Get column details for a table."""
    try:
        with connect(dialect, config) as conn:
            cursor = conn.cursor()
            if dialect.lower() == "postgresql":
                query = f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                """
                cursor.execute(query, (namespace, table_name))
            else:  # MySQL
                query = f"""
                    SELECT column_name, column_type
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                """
                cursor.execute(query, (config.get("database"), table_name))
            
            columns = cursor.fetchall()
            cursor.close()
            return {"table": table_name, "column_count": len(columns), "columns": columns}
    except Exception as exc:
        logger.warning("Failed to get schema details for %s.%s: %s", namespace, table_name, exc)
        return {"table": table_name, "error": str(exc)}


def main():
    """Run full end-to-end data migration test."""
    logger.info("=" * 80)
    logger.info("FULL DATA MIGRATION TEST: PostgreSQL → MySQL")
    logger.info("=" * 80)
    
    job_id = str(uuid4())
    source_dialect = "postgresql"
    target_dialect = "mysql"
    source_namespace = "sample"
    target_namespace = "sample_source"
    
    # Step 1: Test connectivity
    logger.info("\n[STEP 1] Testing database connectivity...")
    source_config = get_connection_config(source_dialect)
    target_config = get_connection_config(target_dialect)
    
    source_ok = verify_connection(source_dialect)
    target_ok = verify_connection(target_dialect)
    
    if not (source_ok and target_ok):
        logger.error("Database connectivity check failed")
        return 1
    
    logger.info("[SUCCESS] Both databases are reachable")
    
    # Step 2: Discover schema
    logger.info("\n[STEP 2] Discovering source schema...")
    try:
        discovery = run_discovery(job_id, source_dialect, target_dialect, source_config)
        logger.info("Discovered %d objects", len(discovery.object_catalog))
        
        tables = [e for e in discovery.object_catalog if e["object_type"] == "table"]
        logger.info("[SUCCESS] Found %d tables: %s", len(tables), [t["name"] for t in tables])
    except Exception as exc:
        logger.error("Discovery failed: %s", exc)
        return 1
    
    # Step 3: Count source data
    logger.info("\n[STEP 3] Counting source data...")
    source_counts = {}
    for table in tables:
        table_name = table["name"]
        count = count_table_rows(source_dialect, source_config, source_namespace, table_name)
        source_counts[table_name] = count
        logger.info("  %s: %d rows", table_name, count)
    
    total_source_rows = sum(c for c in source_counts.values() if c >= 0)
    logger.info("[SUMMARY] Total source rows: %d", total_source_rows)
    
    # Step 4: Check target schema (should be empty initially)
    logger.info("\n[STEP 4] Checking target database (pre-migration)...")
    target_pre_counts = {}
    for table in tables:
        table_name = table["name"]
        try:
            count = count_table_rows(target_dialect, target_config, target_namespace, table_name)
            target_pre_counts[table_name] = count
        except:
            target_pre_counts[table_name] = 0  # Table doesn't exist yet
    
    logger.info("[INFO] Target pre-migration row counts: %s", target_pre_counts)
    
    # Step 5: Migrate data
    logger.info("\n[STEP 5] Running data migration via SeaTunnel...")
    try:
        migration_result = migrate_data(
            job_id,
            discovery,
            source_dialect,
            target_dialect,
            source_config,
            target_config,
        )
        
        logger.info("[SUCCESS] Data migration completed")
        logger.info("  Total rows moved: %d", migration_result.rows_moved)
        logger.info("  Tables processed: %d", len(migration_result.tables))
        
        for table_result in migration_result.tables:
            logger.info("    %s: %s (rows: %s → %s)",
                       table_result.get("table_name"),
                       table_result.get("status"),
                       table_result.get("rows_read", "?"),
                       table_result.get("rows_written", "?"))
    except Exception as exc:
        logger.error("Data migration failed: %s", exc)
        logger.exception("Full traceback")
        return 1
    
    # Step 6: Verify target data
    logger.info("\n[STEP 6] Verifying target data...")
    target_counts = {}
    for table in tables:
        table_name = table["name"]
        count = count_table_rows(target_dialect, target_config, target_namespace, table_name)
        target_counts[table_name] = count
        logger.info("  %s: %d rows", table_name, count)
    
    total_target_rows = sum(c for c in target_counts.values() if c >= 0)
    logger.info("[SUMMARY] Total target rows: %d", total_target_rows)
    
    # Step 7: Validate results
    logger.info("\n[STEP 7] Validating results...")
    all_match = True
    for table_name in source_counts:
        source_count = source_counts.get(table_name, 0)
        target_count = target_counts.get(table_name, 0)
        match = "✓" if source_count == target_count else "✗"
        logger.info("  %s %s: %d → %d", match, table_name, source_count, target_count)
        if source_count != target_count:
            all_match = False
    
    # Final summary
    logger.info("\n" + "=" * 80)
    if all_match and total_source_rows > 0:
        logger.info("DATA MIGRATION TEST PASSED")
        logger.info("=" * 80)
        logger.info("✓ All databases connected successfully")
        logger.info("✓ Schema discovered correctly")
        logger.info("✓ All %d rows migrated from source to target", total_source_rows)
        logger.info("✓ Row counts match perfectly")
        logger.info("\nMigration Details:")
        logger.info("  Source rows: %d", total_source_rows)
        logger.info("  Target rows: %d", total_target_rows)
        logger.info("  Tables: %d", len(tables))
        logger.info("  Job ID: %s", job_id)
        logger.info("  Duration: %s", migration_result)
        return 0
    elif total_source_rows == 0:
        logger.warning("DATA MIGRATION TEST INCONCLUSIVE")
        logger.info("=" * 80)
        logger.warning("Source database has 0 rows")
        logger.warning("Populate source database with sample data and re-run test")
        return 1
    else:
        logger.error("DATA MIGRATION TEST FAILED")
        logger.info("=" * 80)
        logger.error("✗ Row counts do not match")
        logger.error("  Source: %d rows", total_source_rows)
        logger.error("  Target: %d rows", total_target_rows)
        return 1


if __name__ == "__main__":
    sys.exit(main())
