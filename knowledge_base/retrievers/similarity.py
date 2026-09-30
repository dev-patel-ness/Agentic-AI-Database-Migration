"""Cosine-similarity retrieval over `knowledge_base_entries` (architecture.md
§5 Planner/Schema Agents, §10 Data Stores). Used for RAG lookups of
type-mapping rules, vendor syntax quirks, and known incompatibilities.
"""

from __future__ import annotations

from typing import Any, Optional

from pgvector.utils import to_db

from agents.assessment_agent.embeddings import embed_text
from agents.assessment_agent.metadata_store import metadata_connection

_COLUMNS = ("title", "category", "source_dialect", "target_dialect", "content", "similarity")


def retrieve(
    query: str,
    source_dialect: Optional[str] = None,
    target_dialect: Optional[str] = None,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """Return the top-k KB docs most similar to ``query``.

    A doc matches if its ``source_dialect``/``target_dialect`` are NULL
    (pair-agnostic) or equal to the given dialects -- pair-specific docs
    naturally rank higher for a pair-specific query via cosine similarity.
    """
    # register_vector() only dumps numpy.ndarray -> vector, not plain list, so a
    # bare list param here would go over the wire as a float8[] array literal
    # ("{1,2}", not pgvector's "[1,2]" text format) and <=> would fail to
    # resolve an operator against it. to_db() renders the literal pgvector
    # expects; the ::vector cast then binds it to the right type explicitly.
    embedding_literal = to_db(embed_text(query))
    sql = """
        SELECT title, category, source_dialect, target_dialect, content,
               1 - (embedding <=> %(embedding)s::vector) AS similarity
        FROM knowledge_base_entries
        WHERE (source_dialect IS NULL OR source_dialect = %(source_dialect)s)
          AND (target_dialect IS NULL OR target_dialect = %(target_dialect)s)
        ORDER BY embedding <=> %(embedding)s::vector
        LIMIT %(top_k)s
    """
    with metadata_connection() as conn:
        rows = conn.execute(
            sql,
            {
                "embedding": embedding_literal,
                "source_dialect": source_dialect,
                "target_dialect": target_dialect,
                "top_k": top_k,
            },
        ).fetchall()
    return [dict(zip(_COLUMNS, row)) for row in rows]
