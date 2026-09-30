"""Phase 4 end-to-end validation: for all 6 directed Oracle/MySQL/PostgreSQL
pairs, discover the live sample DB's object catalog (tables/views/procedures/
functions/triggers with DDL) and run the Schema Agent (CrackSQL adapter,
Bedrock-backed hybrid translation) against it. Prints a summary table per
pair. Not a pytest test -- a manual verification script (hits real Bedrock/
Postgres/MySQL/Oracle), run once to prove Phase 4's DoD.
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from agents.assessment_agent.metadata_store import metadata_connection, upsert_migration_job  # noqa: E402
from agents.schema_agent import translate_schema  # noqa: E402
from orchestrator.state import DiscoveryResult  # noqa: E402
from tool_adapters.schema_extractor_adapter import SchemaExtractorAdapter  # noqa: E402

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
        "username": "root",
        "password": os.getenv("MYSQL_ROOT_PASSWORD", "mysql_root_dev_password"),
        "database": os.getenv("MYSQL_SAMPLE_DATABASE", "sample_source"),
    },
    "oracle": {
        "host": os.getenv("ORACLE_SAMPLE_HOST", "localhost"),
        "port": int(os.getenv("ORACLE_SAMPLE_PORT", "1521")),
        "username": os.getenv("ORACLE_SAMPLE_USER", "sample_user"),
        "password": os.getenv("ORACLE_SAMPLE_PASSWORD", "oracle_dev_password"),
        "database": os.getenv("ORACLE_SAMPLE_SERVICE_NAME", "XEPDB1"),
    },
}

DIALECTS = ["oracle", "mysql", "postgresql"]


def discover(dialect: str) -> DiscoveryResult:
    adapter = SchemaExtractorAdapter()
    config = adapter.prepare({"dialect": dialect, "connection": CONNECTIONS[dialect]})
    result = adapter.run(config)
    if not result.success:
        raise RuntimeError(f"discovery failed for {dialect}: {result.error}")
    return DiscoveryResult(**result.output)


def main():
    catalogs = {d: discover(d) for d in DIALECTS}
    for d, cat in catalogs.items():
        print(f"\n=== {d} catalog: {len(cat.object_catalog)} objects ===")
        for e in cat.object_catalog:
            print(f"  {e['object_type']:10s} {e['name']:30s} ddl={'yes' if e.get('definition') else 'NO'}")

    for source in DIALECTS:
        for target in DIALECTS:
            if source == target:
                continue
            print(f"\n{'=' * 70}\nPAIR {source} -> {target}\n{'=' * 70}")
            job_id = str(uuid.uuid4())
            with metadata_connection() as conn:
                upsert_migration_job(conn, job_id, source, target, "TRANSLATING")
            translation, low_conf = translate_schema(
                job_id, catalogs[source], source, target, target_connection=CONNECTIONS[target]
            )
            for obj in translation.translated_objects:
                conf = obj.get("confidence")
                conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "n/a"
                print(
                    f"  [{obj['status']:12s}] {obj['object_type']:10s} {obj['object_name']:28s} "
                    f"conf={conf_str} method={obj.get('method', '-')}"
                )
            print(f"  -> average_confidence={translation.average_confidence} low_confidence={low_conf}")


if __name__ == "__main__":
    main()
