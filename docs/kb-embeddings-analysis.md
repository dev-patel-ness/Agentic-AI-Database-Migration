# Knowledge Base Embeddings Analysis - 2026-10-01

## Issues Found

### 🔴 CRITICAL: Knowledge Base Not Ingested
**Status:** EMPTY  
**Evidence:** `knowledge_base_entries` table has 0 documents  
**Impact:** CrackSQL cannot retrieve knowledge base documents for translation guidance

**Root Cause:** 
- The `ingest_documents()` function in `knowledge_base/ingestion/ingest.py` was never executed
- Or if run, it failed silently

**Fix Required:**
```bash
poetry run python -m knowledge_base.ingestion.ingest
```

---

### 🟡 ISSUE: CrackSQL KB Embedding Model Mismatch
**File:** `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/config/init_config.yaml`  
**Problem:** Knowledge base embedding model misconfiguration

```yaml
EMBEDDING_MODELS:
  - name: "amazon.titan-embed-text-v2:0"  # Only this is configured ✓
    # ... other settings ...

KNOWLEDGE_BASES:
  - kb_name: "mysql_knowledge"
    embedding_model: "text-embedding-ada-002"  # This is NOT configured ✗
  - kb_name: "postgresql_knowledge"
    embedding_model: "text-embedding-ada-002"  # This is NOT configured ✗
  - kb_name: "oracle_knowledge"
    embedding_model: "text-embedding-ada-002"  # This is NOT configured ✗
```

**Fix:**
Change all KB embedding model references to match the configured model:
```yaml
KNOWLEDGE_BASES:
  - kb_name: "mysql_knowledge"
    embedding_model: "amazon.titan-embed-text-v2:0"  # Use configured model
  - kb_name: "postgresql_knowledge"
    embedding_model: "amazon.titan-embed-text-v2:0"
  - kb_name: "oracle_knowledge"
    embedding_model: "amazon.titan-embed-text-v2:0"
```

---

### 🟠 DESIGN ISSUE: CrackSQL Only Uses Target KB for Retrieval
**File:** `tool_adapters/cracksql_adapter/vendor/CrackSQL/_package_build/cracksql/translate.py`  
**Method:** `Translator.get_document_description()` (line ~540)

**Current Behavior:**
```python
# Source SQL segment analysis (lines 490-520)
src_key = [str(piece['Keyword'])]
src_detail = [{"Description": piece['Description'], ...}]

# Then retrieve ONLY from target KB (lines 540-555)
topk_result = [ite for ite in
               self.vector_db.search(self.tgt_kb_name, query_embedding.tolist(),  # ← ONLY TARGET!
                                     content_type=detail['Type'], top_k=self.top_k)]
results.extend(topk_result)
```

**Problem:**
- `self.src_kb_name` is populated but NEVER used
- Source dialect-specific rules/patterns are completely ignored
- Example: Oracle-specific quirks (ROWNUM, implicit NULL handling, etc.) won't help guide translation

**Impact:**
- Lower translation quality for source-specific constructs
- Missed opportunities to flag incompatibilities early
- No contextual understanding of source dialect idioms

**Recommended Fix:**
Should retrieve from BOTH source and target KBs:
```python
# Understand source construct
src_results = self.vector_db.search(self.src_kb_name, query_embedding.tolist(),
                                     content_type=detail['Type'], top_k=self.top_k)

# Find target equivalent
tgt_results = self.vector_db.search(self.tgt_kb_name, query_embedding.tolist(),
                                     content_type=detail['Type'], top_k=self.top_k)

# Combine insights
results.extend(src_results + tgt_results)
```

---

## Verification & Recommendations

### Step 1: Ingest Knowledge Base Documents
```bash
cd c:\Users\user\Downloads\Capstone\Agentic-AI-Database-Migration
poetry run python -m knowledge_base.ingestion.ingest
```

Expected output:
```
INFO:__main__:Ingested N knowledge-base documents
```

### Step 2: Fix CrackSQL Embedding Model Configuration
Edit: `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/config/init_config.yaml`

Change all `embedding_model: "text-embedding-ada-002"` to `embedding_model: "amazon.titan-embed-text-v2:0"`

### Step 3: (Optional) Enhance CrackSQL Retrieval Logic
Consider updating `translate.py` to use both source and target KBs for richer context during translation.

---

## How Embeddings Currently Work (When Properly Configured)

### Our Implementation (knowledge_base/)
✅ **Properly Designed:**
- Embeddings stored in PostgreSQL with pgvector
- Dialect-aware retrieval via `similarity.retrieve(source_dialect, target_dialect)`
- Supports NULL dialects for pair-agnostic documents
- Uses AWS Bedrock Titan Embeddings v2 (1024 dimensions)

### CrackSQL Integration
⚠️ **Partially Integrated:**
- Receives `vector_config` with `src_kb_name` and `tgt_kb_name`
- Uses them to initialize `ChromaStore()` vector DB
- BUT: Only `tgt_kb_name` is used during retrieval
- Fallback: Uses local "all-MiniLM-L6-v2" model if KB retrieval fails

---

## Summary

| Aspect | Status | Action Required |
|--------|--------|-----------------|
| KB Ingestion | ❌ NOT DONE | Run ingest script |
| KB Schema | ✅ CORRECT | None |
| Retrieval Logic | ⚠️ PARTIAL | Optimize to use both source/target |
| Embedding Model Config | ⚠️ MISMATCH | Update init_config.yaml |
| Dialect Filtering | ✅ PROPER | None |

**Priority:** 
1. **HIGH**: Ingest knowledge base documents
2. **MEDIUM**: Fix embedding model configuration in init_config.yaml
3. **LOW**: Enhance retrieval to use both source and target KBs (performance improvement)

