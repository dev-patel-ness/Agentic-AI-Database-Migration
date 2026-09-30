import os
import re
import json
import hashlib
from typing import List, Dict, Optional

import psycopg2
from pgvector.utils import to_db

from config.logging_config import logger

# NOTE: despite the module/class name (kept for import-site compatibility --
# see api/services/knowledge.py, init_knowledge_base.py, task/task.py,
# translate.py), this is NOT backed by ChromaDB. On Windows, chromadb pulls in
# chroma-hnswlib, which ships no prebuilt wheel and requires MSVC build tools
# to compile from source. This project already runs a Postgres+pgvector
# metadata DB (docker-compose's postgres-metadata service) for its own
# knowledge base (see knowledge_base/retrievers/similarity.py) -- reusing it
# here avoids a second vector-store technology and the Windows build issue
# entirely. Embedding dimension is fixed at 1024 to match the Titan Embed v2
# model configured for this deployment (see config/init_config.yaml).
_EMBEDDING_DIM = 1024
_TABLE = "cracksql_knowledge_vectors"


def convert_distance_to_score(distance: float) -> float:
    """
    Convert a cosine distance (pgvector's `<=>`, range [0,2]) to a 0-100
    similarity score. distance = 0 means identical, 2 means opposite.
    """
    if distance is None:
        return 0
    score = (1 - distance / 2) * 100
    score = round(score, 2)
    return max(0, min(100, score))


def generate_collection_id(kb_name: str, content_type: str) -> str:
    """Generate collection ID
    Args:
        kb_name: Knowledge base name
        content_type: Content type

    Returns:
        str: Valid table name
    """
    # Use MD5 to hash Chinese names, ensuring table name uniqueness
    name_hash = hashlib.md5(kb_name.encode('utf-8')).hexdigest()[:8]
    # Remove all non-alphanumeric characters, convert to lowercase
    safe_name = re.sub(r'[^a-zA-Z0-9]', '_', kb_name.encode('ascii', 'ignore').decode('ascii').lower())
    # Combine table name: prefix + safe_name + hash
    return f"vector_store_{safe_name}_{name_hash}_{content_type}"


def _db_dsn() -> str:
    host = os.getenv("POSTGRES_METADATA_HOST", "localhost")
    port = os.getenv("POSTGRES_METADATA_PORT", "5432")
    database = os.getenv("POSTGRES_METADATA_DATABASE", "migration_metadata")
    user = os.getenv("POSTGRES_METADATA_USER", "postgres")
    password = os.getenv("POSTGRES_METADATA_PASSWORD", "postgres_dev_password")
    return f"host={host} port={port} dbname={database} user={user} password={password}"


class ChromaStore:
    """Postgres+pgvector-backed vector store (see module docstring above)."""

    def __init__(self, persist_directory: str = "./instance/chroma"):
        # persist_directory kept for constructor-signature compatibility with
        # call sites; unused now that storage is Postgres, not a local dir.
        self._dsn = _db_dsn()
        self._ensure_schema()

    def _connect(self):
        return psycopg2.connect(self._dsn)

    def _ensure_schema(self) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cur.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {_TABLE} (
                        id TEXT PRIMARY KEY,
                        collection_id TEXT NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB,
                        embedding VECTOR({_EMBEDDING_DIM})
                    )
                    """
                )
                cur.execute(
                    f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_collection "
                    f"ON {_TABLE} (collection_id)"
                )
            conn.commit()
        finally:
            conn.close()

    def _validate_inputs(self, texts: List[str], embeddings: List[List[float]], ids: Optional[List[str]] = None):
        """Validate input data consistency"""
        if len(texts) != len(embeddings):
            raise ValueError("Number of texts does not match number of vectors")
        if ids and len(ids) != len(texts):
            raise ValueError("Number of IDs does not match number of texts")

    def add_texts(
            self,
            kb_name: str,
            content_type: str,
            texts: List[str],
            embeddings: List[List[float]],
            metadatas: Optional[List[Dict]] = None,
            ids: Optional[List[str]] = None,
            batch_size: int = 100
    ):
        """Add texts to vector database"""
        self._validate_inputs(texts, embeddings, ids)
        collection_id = generate_collection_id(kb_name, content_type)

        if not ids:
            ids = [f"{collection_id}_{i}" for i in range(len(texts))]

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for i in range(0, len(texts), batch_size):
                    end_idx = min(i + batch_size, len(texts))
                    for j in range(i, end_idx):
                        meta = metadatas[j] if metadatas else {}
                        cur.execute(
                            f"""
                            INSERT INTO {_TABLE} (id, collection_id, content, metadata, embedding)
                            VALUES (%s, %s, %s, %s, %s::vector)
                            ON CONFLICT (id) DO UPDATE SET
                                content = EXCLUDED.content,
                                metadata = EXCLUDED.metadata,
                                embedding = EXCLUDED.embedding
                            """,
                            (ids[j], collection_id, texts[j], json.dumps(meta), to_db(embeddings[j])),
                        )
            conn.commit()
        finally:
            conn.close()

    def search(
            self,
            kb_name: str,
            query_embedding: List[float],
            content_type: str = None,
            top_k: int = 5,
            where: Optional[Dict] = None,
            where_document: Optional[Dict] = None,
            **kwargs
    ) -> List[Dict]:
        """Search by knowledge base name and content type"""
        if where or where_document:
            logger.warning("ChromaStore.search: 'where'/'where_document' filters are not "
                           "supported by the Postgres-backed store and will be ignored")

        if content_type:
            collection_ids = [generate_collection_id(kb_name, content_type)]
        else:
            collection_ids = [generate_collection_id(kb_name, ct)
                              for ct in ('function', 'keyword', 'type', 'operator')]

        embedding_literal = to_db(query_embedding)
        results_all: List[Dict] = []
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for collection_id in collection_ids:
                    try:
                        cur.execute(
                            f"""
                            SELECT id, content, metadata, embedding <=> %s::vector AS distance
                            FROM {_TABLE}
                            WHERE collection_id = %s
                            ORDER BY embedding <=> %s::vector
                            LIMIT %s
                            """,
                            (embedding_literal, collection_id, embedding_literal, top_k),
                        )
                        rows = cur.fetchall()
                    except Exception as e:
                        logger.error(f"Search failed: {str(e)}")
                        raise
                    for row_id, content, metadata, distance in rows:
                        results_all.append({
                            'content': content,
                            'metadata': metadata if metadata else {},
                            'score': convert_distance_to_score(distance),
                            'id': row_id,
                        })
        finally:
            conn.close()

        results_all.sort(key=lambda x: x['score'], reverse=True)
        return results_all

    def delete_by_ids(self, kb_name: str, content_type: str, ids: List[str]):
        """Delete vectors by ID"""
        collection_id = generate_collection_id(kb_name, content_type)
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {_TABLE} WHERE collection_id = %s AND id = ANY(%s)",
                    (collection_id, ids),
                )
            conn.commit()
        finally:
            conn.close()

    def delete_collection(self, kb_name: str):
        """Delete collection"""
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                for content_type in ('function', 'keyword', 'type', 'operator'):
                    cur.execute(
                        f"DELETE FROM {_TABLE} WHERE collection_id = %s",
                        (generate_collection_id(kb_name, content_type),),
                    )
            conn.commit()
        finally:
            conn.close()
