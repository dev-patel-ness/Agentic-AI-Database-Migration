"""Assessment Agent: discovery, schema analysis, and dependency-graph construction.

Per architecture.md §8.1: schema_extractor_adapter -> object catalog +
dependency graph -> discovery embeddings stored in PGVector -> DiscoveryResult.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.assessment_agent import metadata_store
from agents.assessment_agent.embeddings import embed_text
from orchestrator.state import DiscoveryResult
from tool_adapters.schema_extractor_adapter import SchemaExtractorAdapter

logger = logging.getLogger(__name__)


def _summarize_object(entry: dict[str, Any]) -> str:
    columns = ", ".join(c["name"] for c in entry.get("columns", []))
    parts = [f"{entry['object_type']} {entry['schema']}.{entry['name']}"]
    if columns:
        parts.append(f"columns: {columns}")
    return " | ".join(parts)


def run_discovery(
    job_id: str, source_dialect: str, target_dialect: str, connection_config: dict[str, Any]
) -> DiscoveryResult:
    """Discover a source database's schema and persist the catalog + embeddings."""
    adapter = SchemaExtractorAdapter()
    config = adapter.prepare({"dialect": source_dialect, "connection": connection_config})
    result = adapter.run(config)
    if not result.success:
        raise RuntimeError(f"schema discovery failed: {result.error}")

    catalog: list[dict[str, Any]] = result.output["object_catalog"]
    dependency_graph: dict[str, list[str]] = result.output["dependency_graph"]

    with metadata_store.metadata_connection() as conn:
        metadata_store.upsert_migration_job(
            conn, job_id, source_dialect, target_dialect, "DISCOVERING"
        )
        metadata_store.save_object_catalog(conn, job_id, catalog, dependency_graph)

        for entry in catalog:
            try:
                embedding = embed_text(_summarize_object(entry))
                metadata_store.save_discovery_embedding(
                    conn, job_id, entry["object_type"], entry["name"], embedding
                )
            except Exception:
                # Embeddings power later RAG retrieval (Phase 3) but must never
                # block discovery itself from completing.
                logger.exception(
                    "job=%s: failed to embed/store %s %s (non-fatal)",
                    job_id,
                    entry["object_type"],
                    entry["name"],
                )

    return DiscoveryResult(object_catalog=catalog, dependency_graph=dependency_graph)
