#!/usr/bin/env python3
"""Initialize PostgreSQL sample database with schema and sample data."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import logging
import psycopg

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def init_postgres_sample():
    """Load sample schema into PostgreSQL."""
    try:
        host = os.getenv("POSTGRES_SAMPLE_HOST", "localhost")
        port = int(os.getenv("POSTGRES_SAMPLE_PORT", "5433"))
        user = os.getenv("POSTGRES_SAMPLE_USER", "postgres")
        password = os.getenv("POSTGRES_SAMPLE_PASSWORD", "postgres_dev_password")
        database = os.getenv("POSTGRES_SAMPLE_DATABASE", "sample_source")
        
        logger.info("Connecting to PostgreSQL at %s:%d/%s", host, port, database)
        
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=database,
        ) as conn:
            with open("infra/docker/postgres-sample-init.sql") as f:
                sql = f.read()
            
            # Split by semicolon and execute each statement
            statements = [s.strip() for s in sql.split(";") if s.strip()]
            
            with conn.cursor() as cur:
                for i, stmt in enumerate(statements):
                    try:
                        cur.execute(stmt)
                        logger.info("✓ Statement %d executed", i + 1)
                    except Exception as e:
                        logger.warning("  (Statement %d may already exist or has warning: %s)", i + 1, e)
            
            conn.commit()
            logger.info("[SUCCESS] PostgreSQL sample database initialized")
            
            # Verify data
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM sample.employees")
                emp_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM sample.departments")
                dept_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM sample.projects")
                proj_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM sample.project_assignments")
                assign_count = cur.fetchone()[0]
                
                logger.info("\nData verification:")
                logger.info("  Employees: %d", emp_count)
                logger.info("  Departments: %d", dept_count)
                logger.info("  Projects: %d", proj_count)
                logger.info("  Assignments: %d", assign_count)
                
                if emp_count > 0:
                    logger.info("[SUCCESS] Sample data loaded successfully!")
                    return 0
                else:
                    logger.error("[FAILED] No data was loaded")
                    return 1
            
    except Exception as e:
        logger.error("[FAILED] %s", e)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(init_postgres_sample())
