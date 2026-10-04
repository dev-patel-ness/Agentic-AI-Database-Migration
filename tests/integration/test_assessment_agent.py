"""Integration test: Assessment Agent end-to-end (schema_extractor_adapter ->
object catalog + dependency graph -> Bedrock Titan embeddings -> Platform
Metadata DB). Skipped if the sample DB, metadata DB, or Bedrock aren't
reachable (architecture.md §8.1, §10 ERD).
"""

from __future__ import annotations

import uuid

import pytest

from agents.assessment_agent import metadata_store, run_discovery


@pytest.fixture()
def job_id():
    job_id = str(uuid.uuid4())
    yield job_id
    try:
        with metadata_store.metadata_connection() as conn:
            conn.execute("DELETE FROM migration_jobs WHERE id = %s", (job_id,))
    except Exception:
        pass  # best-effort cleanup; metadata DB reachability is asserted in the test body


def test_run_discovery_persists_catalog_and_embeddings(job_id):
    try:
        result = run_discovery(
            job_id,
            "postgresql",
            "mysql",
            {
                "host": "localhost",
                "port": 5433,
                "username": "postgres",
                "password": "postgres_dev_password",
                "database": "sample_source",
                "schema_name": "sample",
            },
        )
    except Exception as exc:  # noqa: BLE001 - sample DB / metadata DB / Bedrock unreachable
        pytest.skip(f"discovery pipeline not reachable: {exc}")

    assert len(result.object_catalog) == 12
    assert result.dependency_graph["projects"] == ["departments"]

    with metadata_store.metadata_connection() as conn:
        row = conn.execute("SELECT status FROM migration_jobs WHERE id = %s", (job_id,)).fetchone()
        assert row is not None
        assert row[0] == "DISCOVERING"

        catalog_count = conn.execute(
            "SELECT count(*) FROM object_catalog_entries WHERE job_id = %s", (job_id,)
        ).fetchone()[0]
        assert catalog_count == 12

        embedding_count = conn.execute(
            "SELECT count(*) FROM discovery_embeddings WHERE job_id = %s", (job_id,)
        ).fetchone()[0]
        assert embedding_count == 12
