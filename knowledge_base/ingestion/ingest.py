"""Embeds `SEED_DOCUMENTS` (Titan Text Embeddings v2) and upserts them into
`knowledge_base_entries` (architecture.md §5 knowledge_base/ingestion, §10 ERD).

Run standalone to (re-)seed the knowledge base:
    poetry run python -m knowledge_base.ingestion.ingest
"""

from __future__ import annotations

import logging

from agents.assessment_agent.embeddings import embed_text
from agents.assessment_agent.metadata_store import metadata_connection
from knowledge_base.ingestion.documents import SEED_DOCUMENTS

logger = logging.getLogger(__name__)


def ingest_documents() -> int:
    """(Re-)seed `knowledge_base_entries` from `SEED_DOCUMENTS`. Idempotent: clears
    existing rows first, so re-running after editing the seed content is safe."""
    count = 0
    with metadata_connection() as conn:
        conn.execute("DELETE FROM knowledge_base_entries")
        for doc in SEED_DOCUMENTS:
            embedding = embed_text(doc["content"])
            conn.execute(
                """
                INSERT INTO knowledge_base_entries
                    (title, category, source_dialect, target_dialect, content, embedding)
                VALUES
                    (%(title)s, %(category)s, %(source_dialect)s, %(target_dialect)s,
                     %(content)s, %(embedding)s)
                """,
                {**doc, "embedding": embedding},
            )
            count += 1
    return count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ingested = ingest_documents()
    logger.info("Ingested %d knowledge-base documents", ingested)
