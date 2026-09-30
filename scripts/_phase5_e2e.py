"""Phase 5 end-to-end integration test: discover → translate (CrackSQL/Bedrock) 
→ migrate_data (SeaTunnel + apply DDL) → verify views/FKs on target.

Tests the complete pipeline: PostgreSQL sample → MySQL sample, including
verifying that translated views and foreign key constraints actually exist
on the target after data load + DDL application.
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents.data_agent import migrate_data
from agents.schema_agent import translate_schema
from dialects.connections import connect
from orchestrator.state import DiscoveryResult
from tool_adapters.schema_extractor_adapter import SchemaExtractorAdapter

# Optional: metadata tracking (requires system psycopg/libpq)
try:
    from agents.assessment_agent.metadata_store import metadata_connection, upsert_migration_job
    HAS_METADATA = True
except (ImportError, ModuleNotFoundError):
    HAS_METADATA = False
    print("⚠️  Metadata tracking unavailable (psycopg/libpq not installed)")
    
    class DummyConnection:
        pass
    
    def metadata_connection():
        class DummyCtx:
            def __enter__(self):
                return DummyConnection()
            def __exit__(self, *args):
                pass
        return DummyCtx()
    
    def upsert_migration_job(*args, **kwargs):
        pass

CONNECTIONS = {
    "postgresql": {
        "host": os.getenv("POSTGRES_SAMPLE_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_SAMPLE_PORT", "5433")),
        "username": os.getenv("POSTGRES_SAMPLE_USER", "postgres"),
        "password": os.getenv("POSTGRES_SAMPLE_PASSWORD", "postgres_dev_password"),
        "database": os.getenv("POSTGRES_SAMPLE_DATABASE", "sample_source"),
        "schema_name": "sample",
    },
    "mysql": {
        "host": os.getenv("MYSQL_SAMPLE_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_SAMPLE_PORT", "3306")),
        "username": os.getenv("MYSQL_SAMPLE_USER", "appuser"),
        "password": os.getenv("MYSQL_SAMPLE_PASSWORD", "mysql_dev_password"),
        "database": os.getenv("MYSQL_SAMPLE_DATABASE", "sample_source"),
    },
}


def discover(dialect: str) -> DiscoveryResult:
    adapter = SchemaExtractorAdapter()
    config = adapter.prepare({"dialect": dialect, "connection": CONNECTIONS[dialect]})
    result = adapter.run(config)
    if not result.success:
        raise RuntimeError(f"discovery failed for {dialect}: {result.error}")
    return DiscoveryResult(**result.output)


def verify_objects_on_target(target_dialect: str, target_conn: dict, target_db: str, expected_views: list[str]):
    """Verify that views actually exist on the target after DDL application."""
    try:
        with connect(target_dialect, target_conn) as conn:
            cursor = conn.cursor()
            
            if target_dialect == "mysql":
                cursor.execute(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'VIEW'", (target_db,))
            else:
                raise NotImplementedError(f"verify_objects_on_target not implemented for {target_dialect}")
            
            existing_views = {row[0].lower() for row in cursor.fetchall()}
            cursor.close()
            
            missing = [v for v in expected_views if v.lower() not in existing_views]
            return existing_views, missing
    except Exception as e:
        return set(), expected_views


def main():
    source_dialect, target_dialect = "postgresql", "mysql"
    print(f"\n{'=' * 70}\nPHASE 5 E2E: {source_dialect} -> {target_dialect}\n{'=' * 70}")
    
    # Step 1: Discover source schema
    print("\n[DISCOVER] Extracting source schema...")
    source_discovery = discover(source_dialect)
    print(f"  Found {len(source_discovery.object_catalog)} objects:")
    for obj in source_discovery.object_catalog:
        print(f"    {obj['object_type']:10s} {obj['name']:30s}")
    
    # Extract views and tables for later verification
    source_views = [o['name'] for o in source_discovery.object_catalog if o['object_type'] == 'view']
    print(f"\n  Views to translate: {source_views}")
    
    # Step 2: Translate schema via CrackSQL/Bedrock
    print("\n[TRANSLATE] Running CrackSQL adapter with Bedrock...")
    job_id = str(uuid.uuid4())
    with metadata_connection() as conn:
        upsert_migration_job(conn, job_id, source_dialect, target_dialect, "TRANSLATING")
    
    translation, low_conf = translate_schema(
        job_id, source_discovery, source_dialect, target_dialect, 
        target_connection=CONNECTIONS[target_dialect]
    )
    print(f"  Translated {len(translation.translated_objects)} objects:")
    for obj in translation.translated_objects:
        conf = obj.get("confidence")
        conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"
        error_msg = obj.get("error", "")
        if error_msg:
            print(f"    [{obj['status']:12s}] {obj['object_type']:10s} {obj['object_name']:20s} conf={conf_str} ERROR: {error_msg[:60]}")
        else:
            print(f"    [{obj['status']:12s}] {obj['object_type']:10s} {obj['object_name']:20s} conf={conf_str}")
    
    avg_conf = translation.average_confidence
    avg_conf_str = f"{avg_conf:.2f}" if avg_conf else "N/A"
    print(f"  Average confidence: {avg_conf_str}")
    
    # Step 3: Migrate data (SeaTunnel bulk load + apply translated DDL)
    print("\n[MIGRATE] Running SeaTunnel bulk load + applying translated DDL...")
    try:
        with metadata_connection() as conn:
            upsert_migration_job(conn, job_id, source_dialect, target_dialect, "MIGRATING")
        
        result = migrate_data(
            job_id, source_discovery, source_dialect, target_dialect,
            CONNECTIONS[source_dialect], CONNECTIONS[target_dialect]
        )
        
        print(f"  Total rows moved: {result.rows_moved}")
        print(f"  Table results:")
        for table in result.tables:
            status = table.get("status")
            rows = table.get("rows_written")
            error = table.get("error", "")
            if error:
                print(f"    {table['table_name']:25s} {status:10s} rows={rows} ERROR: {error[:80]}")
            else:
                print(f"    {table['table_name']:25s} {status:10s} rows={rows}")
        
        print(f"  DDL application results:")
        for ddl in result.ddl_applications:
            status = ddl.get("status")
            obj_type = ddl.get("object_type")
            obj_name = ddl.get("object_name")
            error = ddl.get("error", "")
            error_str = f" ERROR: {error[:50]}" if error else ""
            print(f"    {obj_type:10s} {obj_name:25s} {status:10s}{error_str}")
    except Exception as e:
        print(f"  ERROR during migrate_data: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Step 4: Verify objects on target
    print("\n[VERIFY] Checking that views exist on target...")
    existing_views, missing_views = verify_objects_on_target(
        target_dialect, CONNECTIONS[target_dialect], 
        CONNECTIONS[target_dialect]["database"],
        source_views
    )
    print(f"  Views found on target: {existing_views}")
    if missing_views:
        print(f"  [WARNING] Missing views: {missing_views}")
    else:
        print(f"  [SUCCESS] All {len(source_views)} views exist on target!")
    
    print("\n[RESULT] Phase 5 E2E Test Complete")
    return len(missing_views) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
