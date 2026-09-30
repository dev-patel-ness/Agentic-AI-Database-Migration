#!/usr/bin/env python3
"""
Test database connections for the migration platform.

Verifies that all local databases are accessible and properly configured.
Usage: poetry run python scripts/test_connections.py
"""

import os
import sys
from typing import Optional

from dotenv import load_dotenv


def test_postgres_metadata() -> bool:
    """Test connection to PostgreSQL metadata database."""
    try:
        import psycopg2

        config = {
            "host": os.getenv("POSTGRES_METADATA_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_METADATA_PORT", "5432")),
            "database": os.getenv("POSTGRES_METADATA_DATABASE", "migration_metadata"),
            "user": os.getenv("POSTGRES_METADATA_USER", "postgres"),
            "password": os.getenv("POSTGRES_METADATA_PASSWORD", "postgres_dev_password"),
        }

        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        print(f"✓ PostgreSQL Metadata: {version}")
        return True
    except Exception as e:
        print(f"✗ PostgreSQL Metadata failed: {e}")
        return False


def test_postgres_sample() -> bool:
    """Test connection to PostgreSQL sample database."""
    try:
        import psycopg2

        config = {
            "host": os.getenv("POSTGRES_SAMPLE_HOST", "localhost"),
            "port": int(os.getenv("POSTGRES_SAMPLE_PORT", "5433")),
            "database": os.getenv("POSTGRES_SAMPLE_DATABASE", "sample_source"),
            "user": os.getenv("POSTGRES_SAMPLE_USER", "postgres"),
            "password": os.getenv("POSTGRES_SAMPLE_PASSWORD", "postgres_dev_password"),
        }

        conn = psycopg2.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sample.employees;")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        print(f"✓ PostgreSQL Sample: Connected ({count} employees)")
        return True
    except Exception as e:
        print(f"✗ PostgreSQL Sample failed: {e}")
        return False


def test_mysql_sample() -> bool:
    """Test connection to MySQL sample database."""
    try:
        import mysql.connector

        config = {
            "host": os.getenv("MYSQL_SAMPLE_HOST", "localhost"),
            "port": int(os.getenv("MYSQL_SAMPLE_PORT", "3306")),
            "database": os.getenv("MYSQL_SAMPLE_DATABASE", "sample_source"),
            "user": os.getenv("MYSQL_SAMPLE_USER", "appuser"),
            "password": os.getenv("MYSQL_SAMPLE_PASSWORD", "mysql_dev_password"),
        }

        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM employees;")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        print(f"✓ MySQL Sample: Connected ({count} employees)")
        return True
    except Exception as e:
        print(f"✗ MySQL Sample failed: {e}")
        return False


def test_oracle_sample() -> Optional[bool]:
    """Test connection to Oracle sample database."""
    try:
        import oracledb

        # Sample data lives under the dedicated sample_user schema in the
        # XEPDB1 pluggable database (not the sys/sysdba CDB root).
        dsn = oracledb.makedsn(
            host=os.getenv("ORACLE_SAMPLE_HOST", "localhost"),
            port=int(os.getenv("ORACLE_SAMPLE_PORT", "1521")),
            service_name=os.getenv("ORACLE_SAMPLE_SERVICE_NAME", "XEPDB1"),
        )

        conn = oracledb.connect(
            user=os.getenv("ORACLE_SAMPLE_USER", "sample_user"),
            password=os.getenv("ORACLE_SAMPLE_PASSWORD", "oracle_dev_password"),
            dsn=dsn,
        )

        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM employees")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        print(f"✓ Oracle Sample: Connected ({count} employees)")
        return True
    except ImportError:
        print("⚠ Oracle: oracledb not installed (optional)")
        return None
    except Exception as e:
        print(f"✗ Oracle Sample failed: {e}")
        return False


def test_aws_bedrock() -> bool:
    """Test AWS Bedrock connectivity."""
    try:
        import boto3

        region = os.getenv("AWS_REGION", "us-east-1")
        client = boto3.client("bedrock", region_name=region)

        # List available models
        response = client.list_foundation_models()
        models = response.get("modelSummaries", [])

        print(f"✓ AWS Bedrock: Connected ({len(models)} models available)")
        return True
    except ImportError:
        print("⚠ AWS Bedrock: boto3 not installed (optional)")
        return None
    except Exception as e:
        print(f"✗ AWS Bedrock failed: {e}")
        return False


def main() -> int:
    """Run all connection tests."""
    print("=" * 60)
    print("Database Connection Tests")
    print("=" * 60)
    print()

    # Load environment variables from .env
    load_dotenv()

    results = []
    failures = 0

    # Test PostgreSQL connections
    print("🐘 PostgreSQL Tests:")
    if not test_postgres_metadata():
        failures += 1
    if not test_postgres_sample():
        failures += 1

    print()
    print("🐬 MySQL Tests:")
    if not test_mysql_sample():
        failures += 1

    print()
    print("🔴 Oracle Tests:")
    result = test_oracle_sample()
    if result is False:
        failures += 1

    print()
    print("☁️  AWS Tests:")
    result = test_aws_bedrock()
    if result is None:
        print("   (Skipped - credentials not configured)")
    elif not result:
        failures += 1

    print()
    print("=" * 60)
    if failures == 0:
        print("✓ All connection tests passed!")
        return 0
    else:
        print(f"✗ {failures} connection test(s) failed")
        print()
        print("Troubleshooting tips:")
        print("  1. Verify Docker services are running: docker-compose ps")
        print("  2. Check service logs: docker-compose logs <service_name>")
        print("  3. Ensure .env file has correct credentials")
        print("  4. Try restarting services: docker-compose restart")
        return 1


if __name__ == "__main__":
    sys.exit(main())
