"""Integration test: knowledge-base ingestion -> Bedrock Titan embeddings ->
pgvector similarity retrieval (architecture.md §5, §10 ERD). Skipped if the
metadata DB or Bedrock aren't reachable.
"""

from __future__ import annotations

import pytest

from knowledge_base.ingestion.ingest import ingest_documents
from knowledge_base.retrievers.similarity import retrieve


@pytest.fixture(scope="module")
def seeded_kb():
    try:
        count = ingest_documents()
    except Exception as exc:  # noqa: BLE001 - metadata DB / Bedrock unreachable
        pytest.skip(f"knowledge-base ingestion not reachable: {exc}")
    assert count > 0
    return count


def test_retrieve_returns_pair_specific_docs_ranked_by_similarity(seeded_kb):
    results = retrieve(
        "how do I migrate PL/SQL packages and CLOB columns to PostgreSQL?",
        source_dialect="oracle",
        target_dialect="postgresql",
        top_k=5,
    )
    assert results
    assert any(r["source_dialect"] == "oracle" for r in results)
    # results are ordered most-to-least similar
    similarities = [r["similarity"] for r in results]
    assert similarities == sorted(similarities, reverse=True)


def test_retrieve_excludes_mismatched_pair_specific_docs(seeded_kb):
    results = retrieve(
        "type mapping",
        source_dialect="oracle",
        target_dialect="postgresql",
        top_k=50,
    )
    for r in results:
        assert r["source_dialect"] in (None, "oracle")
        assert r["target_dialect"] in (None, "postgresql")
