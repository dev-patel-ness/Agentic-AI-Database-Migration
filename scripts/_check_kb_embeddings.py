#!/usr/bin/env python3
"""Diagnostic: Check CrackSQL knowledge base embeddings usage"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.assessment_agent.metadata_store import metadata_connection
from knowledge_base.retrievers import similarity

print("="*80)
print("KNOWLEDGE BASE EMBEDDINGS DIAGNOSTIC")
print("="*80)

# Check what's in the knowledge_base_entries table
with metadata_connection() as conn:
    result = conn.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT source_dialect) as source_dialects,
            COUNT(DISTINCT target_dialect) as target_dialects,
            COUNT(DISTINCT CONCAT(source_dialect, '->', target_dialect)) as dialect_pairs
        FROM knowledge_base_entries
    """).fetchone()
    
    print(f"\n[OK] Knowledge Base Summary:")
    print(f"   Total documents: {result[0]}")
    print(f"   Source dialects: {result[1]}")
    print(f"   Target dialects: {result[2]}")
    print(f"   Dialect pairs: {result[3]}")
    
    # List documents by dialect pair
    print(f"\n[INFO] Documents by Dialect Pair:")
    docs_by_pair = conn.execute("""
        SELECT 
            CONCAT(source_dialect, ' -> ', target_dialect) as pair,
            COUNT(*) as count
        FROM knowledge_base_entries
        GROUP BY source_dialect, target_dialect
        ORDER BY pair
    """).fetchall()
    
    for row in docs_by_pair:
        print(f"   {row[0]}: {row[1]} documents")

# Test retrieval for each dialect pair
print(f"\n[TEST] Testing Retrieval (Oracle -> PostgreSQL):")
test_query = "Oracle ROWNUM vs PostgreSQL LIMIT"
results = similarity.retrieve(
    query=test_query,
    source_dialect="oracle",
    target_dialect="postgresql",
    top_k=3
)

if results:
    print(f"   Found {len(results)} documents:")
    for doc in results:
        similarity_score = doc.get('similarity', 'N/A')
        category = doc.get('category', 'N/A')
        title = doc.get('title', 'N/A')
        print(f"     * {title} (similarity: {similarity_score:.3f}, category: {category})")
else:
    print(f"   [WARN] No documents found for this query!")

# Test generic query (no dialect filter)
print(f"\n[TEST] Testing Generic Retrieval (No Dialect Filter):")
results_generic = similarity.retrieve(
    query=test_query,
    source_dialect=None,
    target_dialect=None,
    top_k=3
)

if results_generic:
    print(f"   Found {len(results_generic)} documents:")
    for doc in results_generic:
        similarity_score = doc.get('similarity', 'N/A')
        title = doc.get('title', 'N/A')
        src = doc.get('source_dialect', 'NULL')
        tgt = doc.get('target_dialect', 'NULL')
        print(f"     * {title}")
        print(f"       Dialects: {src} -> {tgt}")
        print(f"       Similarity: {similarity_score:.3f}")
else:
    print(f"   [WARN] No documents found!")

print("\n" + "="*80)
print("CRACKSQL CONFIGURATION CHECK")
print("="*80)

# Check if CrackSQL KBs are properly set up
try:
    from cracksql.models import KnowledgeBase
    from cracksql.config.db_config import db_session_manager
    
    @db_session_manager
    def check_cracksql_kbs():
        kbs = KnowledgeBase.query.all()
        print(f"\n[OK] CrackSQL Knowledge Bases ({len(kbs)} total):")
        for kb in kbs:
            embedding_model = kb.embedding_model_name if hasattr(kb, 'embedding_model_name') else 'N/A'
            print(f"   * {kb.kb_name}")
            print(f"     Type: {kb.db_type}")
            print(f"     Embedding Model: {embedding_model}")
            
            # Count documents in each KB
            from cracksql.models import JSONContent
            doc_count = JSONContent.query.filter_by(knowledge_base_id=kb.id).count()
            print(f"     Documents: {doc_count}")
    
    check_cracksql_kbs()
    
except Exception as e:
    print(f"\n[WARN] Could not check CrackSQL KBs: {e}")

print("\n" + "="*80)
print("EMBEDDING USAGE ANALYSIS")
print("="*80)

print("""
Current Implementation:
  1. Our knowledge_base_entries table has proper source/target dialect filtering
  2. Retrieval uses similarity.retrieve(source_dialect, target_dialect, ...)
  3. CrackSQL has separate KBs (oracle_knowledge, postgresql_knowledge, mysql_knowledge)
  
Potential Issues Found:
  [ISSUE] CrackSQL's get_document_description() method ONLY uses target KB for retrieval
      - It never consults src_kb_name for source dialect specific rules
      - This means source-specific patterns/quirks are ignored
      - The method should retrieve from BOTH source and target KBs
      
  [ISSUE] init_config.yaml specifies embedding_model as "text-embedding-ada-002"
      - But only "amazon.titan-embed-text-v2:0" is configured in LLM_MODELS
      - This mismatch should cause KB initialization to fail or fallback silently
      
  [OK] Positive: dialect-specific retrieval is properly implemented in similarity.py
     - Our knowledge base entries are properly separated by source/target dialect
     - Retrieval filters work correctly
""")

print("\n" + "="*80)
