# Risk Assessment & Dependency Graph Architecture

## Overview
The platform generates a **per-object risk drill-down** (12 objects in your example) and builds a **dependency graph** entirely through **deterministic code analysis + optional LLM refinement**, NOT static data. This document explains the data flow, decision logic, and how it appears in the Streamlit UI.

---

## Data Flow: Risk Assessment Pipeline

```
DiscoveryResult (from SchemaExtractorAdapter)
    ↓
    └─→ [Phase 1] Deterministic Risk Heuristic (risk.py)
            ├─ Object type → default risk level
            ├─ Vendor-specific column types → elevate to "high"
            └─ Generate list of ObjectRisk records
                ↓
                └─→ [Phase 2] LLM Refinement (llm.py)
                        ├─ Filter: only "medium" & "high" risk objects (max 30)
                        ├─ Retrieve KB context (RAG): "migrating {source} to {target}: type mapping, syntax incompatibilities"
                        ├─ Call Bedrock Nova Pro with system prompt + list of risky objects
                        ├─ LLM responds with refined risk levels + reasons
                        └─ Merge back into risk_register
                            ↓
                            └─→ MigrationPlan (returned to Streamlit UI)
                                    ├─ risk_register (list of ObjectRisk)
                                    ├─ manual_review_objects (high-risk names)
                                    └─ risk_counts (low/medium/high breakdown)
```

---

## Phase 1: Deterministic Risk Heuristic

**File**: [agents/planner_agent/risk.py](../agents/planner_agent/risk.py)

### Default Risk by Object Type

```python
_DEFAULT_RISK_BY_TYPE = {
    "table": "low",
    "view": "medium",
    "procedure": "high",
    "function": "high",
    "trigger": "high",
    "foreign_key": "medium",
}
```

**Rationale**:
- **Tables**: Passive schema (mostly just columns + constraints); straightforward to translate
- **Views**: Moderately risky (SQL syntax often differs between dialects; functions/operators may not exist)
- **Procedures/Functions/Triggers**: High risk (PL/SQL/T-SQL/PL/pgSQL syntax differs significantly; dialect-specific built-ins)
- **Foreign Keys**: Medium risk (constraint syntax needs adjustment; reference resolution sensitive to schema/namespace)

### Column-Type Risk Elevation

For tables, function `_table_risk()` inspects all columns and escalates to **"high"** if any use vendor-specific types:

```python
_RISKY_COLUMN_TYPES = {
    "oracle": {"CLOB", "BLOB", "LONG", "LONG RAW", "RAW", "XMLTYPE", "ROWID", "UROWID", "BFILE"},
    "mysql": {"ENUM", "SET", "YEAR", "TINYBLOB", "MEDIUMBLOB", "LONGBLOB", "GEOMETRY", "POINT"},
    "postgresql": {"JSONB", "JSON", "ARRAY", "HSTORE", "TSVECTOR", "XML", "CIDR", "INET", "MACADDR"},
}
```

**Example**: `PROJECTS` table uses Oracle `CLOB` → escalated to **"high"** risk, reason: `"columns use vendor-specific type(s) with no direct equivalent: CLOB"`.

### Score Function Output

```python
def score_object(entry: dict[str, Any], source_dialect: str) -> ObjectRisk:
    """Returns: ObjectRisk(object_name, object_type, risk_level, reason)"""
    # For tables, check columns; for others, use defaults
    return ObjectRisk(
        object_name=entry["name"],
        object_type=entry["object_type"],
        risk_level=risk_level,
        reason=reason,  # Optional; e.g., "columns use vendor-specific type(s): CLOB"
    )
```

---

## Phase 2: LLM Refinement via Bedrock

**File**: [agents/planner_agent/llm.py](../agents/planner_agent/llm.py) + [agents/planner_agent/__init__.py](../agents/planner_agent/__init__.py)

### When LLM is Used

1. **Filter**: Extract only objects with risk_level `"medium"` or `"high"` (up to 30 to bound cost/latency)
2. **Retrieve Knowledge Base**: Ask embeddings API to find top-5 relevant KB docs matching:
   ```
   "migrating {source} to {target}: type mapping, syntax incompatibilities, known migration issues"
   ```
3. **Call Bedrock Nova Pro**: System + user prompts with object list + KB context

### System Prompt

```
You are a database migration risk assessor. You are given a list of database 
objects flagged by a heuristic as medium or high risk, plus relevant migration 
knowledge-base notes. Reply with ONLY a JSON object of this exact shape, no other 
text: {"objects": [{"name": "<object name exactly as given>", "risk_level": 
"low"|"medium"|"high", "reason": "<one short sentence>"}]}. Include every object 
you were given, exactly once, using its exact given name.
```

### User Prompt Template

```
Source dialect: oracle
Target dialect: postgresql

Knowledge base context:
- Oracle to PostgreSQL: Type Mapping: CLOB → text, BLOB → bytea, XMLTYPE → XML, ...
- Oracle to PostgreSQL: Constraint Syntax: Oracle's ENABLE/DISABLE syntax differs from PG's CHECK expressions...
- Oracle to PostgreSQL: Stored Procedures: PL/SQL packages and package bodies must be converted to PL/pgSQL functions...

Objects to assess:
- table PROJECTS (heuristic risk: high)
- function GET_EMPLOYEE_COUNT (heuristic risk: high)
- trigger TRG_NORMALIZE_EMPLOYEE_EMAIL (heuristic risk: high)
```

### LLM Response & Merge

LLM returns:
```json
{
  "objects": [
    {
      "name": "PROJECTS",
      "risk_level": "high",
      "reason": "Complex table structure may not translate directly to PostgreSQL."
    },
    {
      "name": "GET_EMPLOYEE_COUNT",
      "risk_level": "high",
      "reason": "Function may use Oracle-specific features not available in PostgreSQL."
    },
    ...
  ]
}
```

Code merges LLM refinements back: for each object the LLM returned, override the heuristic risk level + reason.

### LLM Failure Handling

If KB retrieval or Bedrock call fails:
```python
except Exception:
    logger.exception("Planner Agent: LLM risk refinement failed, keeping heuristic scores")
    return risk_register  # Return original heuristic scores, never block on LLM
```

**Philosophy**: LLM refinement is **best-effort**, not blocking. If it fails, users see the deterministic heuristic scores.

---

## Building the Dependency Graph

**File**: [tool_adapters/schema_extractor_adapter/__init__.py](../../tool_adapters/schema_extractor_adapter/__init__.py)

### Graph Construction

The dependency graph is built **purely from foreign key metadata** (not LLM-inferred):

```python
def _build_dependency_graph(self, fk_rows: list[tuple]) -> dict[str, list[str]]:
    """FK-based graph: table_name → [referenced_table_names]"""
    graph: dict[str, list[str]] = {}
    for _constraint_name, table_name, _column_name, ref_table_name, _ref_column_name in fk_rows:
        graph.setdefault(table_name, [])
        if ref_table_name not in graph[table_name]:
            graph[table_name].append(ref_table_name)
    return graph
```

### Example Graph Output

For your sample schema:
```python
{
    "PROJECT_ASSIGNMENTS": ["EMPLOYEES", "PROJECTS"],  # Foreign keys to EMPLOYEES and PROJECTS
    "PROJECTS": ["DEPARTMENTS"],                         # Foreign key to DEPARTMENTS
    "EMPLOYEES": ["DEPARTMENTS"],                        # Foreign key to DEPARTMENTS
    "DEPARTMENTS": []                                    # No outgoing FKs
}
```

**Note**: This is **not** used for risk assessment directly (risk is per-object). The graph is exposed in the `DiscoveryResult` struct but the planner's risk ranking doesn't currently traverse it. It's available for **future features** like:
- Topological sort to determine migration order
- Impact analysis ("if this table fails, which others are blocked?")
- Circular dependency detection

---

## Streamlit UI Rendering

**File**: [apps/ui-streamlit/app.py](../../apps/ui-streamlit/app.py)

### Plan Summary View

```python
def _render_plan_summary(plan: dict[str, Any]) -> None:
    # 1. Show object counts
    cols = st.columns(5)
    for col, key in zip(cols, ["tables", "views", "procedures", "functions", "triggers"]):
        col.metric(key.capitalize(), plan.get(key, 0))
    
    # 2. Show risk breakdown
    risk_register = plan.get("risk_register") or []
    risk_counts = Counter(r["risk_level"] for r in risk_register)
    st.write(f"**Risk breakdown:** {risk_counts['low']} low / {risk_counts['medium']} medium / {risk_counts['high']} high")
    
    # 3. Show manual review list
    manual_review = plan.get("manual_review_objects") or []
    if manual_review:
        st.warning(f"{len(manual_review)} object(s) flagged for manual review: " + ", ".join(manual_review))
    
    # 4. Per-object drill-down (expandable table)
    if risk_register:
        with st.expander(f"Per-object risk drill-down ({len(risk_register)} objects)"):
            st.dataframe([
                {
                    "object": r["object_name"],
                    "type": r["object_type"],
                    "risk": r["risk_level"],
                    "reason": r.get("reason") or "",
                }
                for r in risk_register
            ], use_container_width=True, hide_index=True)
```

### Example Rendering (Your Data)

| Object | Type | Risk | Reason |
|--------|------|------|--------|
| DEPARTMENTS | table | low | (none) |
| EMPLOYEES | table | low | (none) |
| PROJECTS | table | high | Complex table structure may not translate directly to PostgreSQL. |
| PROJECT_ASSIGNMENTS | table | low | (none) |
| ACTIVE_EMPLOYEES | view | medium | View may require adjustments for PostgreSQL syntax and functions. |
| GET_EMPLOYEE_COUNT | function | high | Function may use Oracle-specific features not available in PostgreSQL. |
| TRG_NORMALIZE_EMPLOYEE_EMAIL | trigger | high | Trigger may use Oracle-specific features or PL/SQL which needs conversion. |
| FK_DEPARTMENTS_MANAGER | foreign_key | medium | Foreign key constraints may need syntax adjustments for PostgreSQL. |
| SYS_C008227 | foreign_key | medium | Foreign key constraints may need syntax adjustments for PostgreSQL. |
| SYS_C008233 | foreign_key | medium | Foreign key constraints may need syntax adjustments for PostgreSQL. |

---

## Answering Your Questions

### Q: "Is LLM used to generate the dependency graph?"

**A: No.** The dependency graph is built **deterministically from foreign key metadata** in `_build_dependency_graph()`. LLM is only used for **risk refinement** (Phase 2), not graph construction.

### Q: "How is the dependency graph made?"

**A: Via SQL introspection + dictionary aggregation**:

1. **Discovery Phase**: SchemaExtractorAdapter connects to source DB and queries the native catalog (e.g., Oracle's `ALL_CONSTRAINTS`, MySQL's `INFORMATION_SCHEMA.KEY_COLUMN_USAGE`)
2. **FK Extraction**: SQL query returns tuples of `(constraint_name, table, column, ref_table, ref_column)` for every FK
3. **Graph Aggregation**: Loop through FK tuples and build a dict mapping `table_name → [referenced_table_names]`
4. **Return**: Included in `DiscoveryResult.dependency_graph`

### Q: "How is risk assessment made?"

**A: Two-phase deterministic + LLM process**:

1. **Phase 1 (Deterministic heuristic)**: 
   - Look up object type in `_DEFAULT_RISK_BY_TYPE` (tables=low, views=medium, functions=high, etc.)
   - For tables, inspect columns and escalate to "high" if any use vendor-specific types (CLOB, ENUM, JSON, etc.)
   
2. **Phase 2 (LLM refinement, best-effort)**:
   - Filter to only "medium"/"high" risk objects (≤30)
   - Retrieve 5 relevant KB docs matching "migrating X to Y: type mapping, syntax issues"
   - Call Bedrock Nova Pro with object list + KB context
   - LLM refines risk levels + reasons based on domain knowledge
   - If LLM fails, fall back to Phase 1 scores

**No LLM is required for risk; the heuristic alone produces valid results. LLM is optional refinement.**

---

## Code References

### Risk Scoring
- [agents/planner_agent/risk.py](../agents/planner_agent/risk.py) — Deterministic heuristic
- [agents/planner_agent/llm.py](../agents/planner_agent/llm.py) — Bedrock Nova Pro integration
- [agents/planner_agent/__init__.py](../agents/planner_agent/__init__.py) — Two-phase pipeline

### Dependency Graph
- [tool_adapters/schema_extractor_adapter/__init__.py](../../tool_adapters/schema_extractor_adapter/__init__.py) — `_build_dependency_graph()`
- [dialects/base.py](../dialects/base.py) — `Dialect.get_foreign_keys_query()`

### UI Rendering
- [apps/ui-streamlit/app.py](../../apps/ui-streamlit/app.py) — `_render_plan_summary()`

### State Model
- [orchestrator/state.py](../orchestrator/state.py) — `ObjectRisk`, `DiscoveryResult`, `MigrationPlan` dataclasses

---

## Knowledge Base Context

The Planner Agent's LLM step queries the knowledge base for documents matching:
```
"migrating {source_dialect} to {target_dialect}: type mapping, syntax incompatibilities, known migration issues"
```

Documents are ingested from [knowledge_base/ingestion/documents.py](../knowledge_base/ingestion/documents.py) and embedded with Bedrock Titan. Top-5 matches are included in the LLM prompt as context for risk refinement.

**Example KB docs**:
- "Oracle to PostgreSQL: Type Mapping" (CLOB → text, BLOB → bytea, etc.)
- "Oracle Stored Procedures → PostgreSQL Functions" (PL/SQL syntax differences)
- "Foreign Key Constraints: Oracle vs PostgreSQL" (ENABLE/DISABLE syntax, reference resolution)

---

## Summary

| Component | Type | LLM-Based? | Output |
|-----------|------|-----------|--------|
| **Risk Scoring** | Heuristic + LLM refinement | Partial (optional) | `ObjectRisk[]` (risk_level + reason per object) |
| **Dependency Graph** | FK SQL metadata aggregation | No | `dict[str, list[str]]` (table → referenced tables) |
| **Plan Summary** | Aggregation of above | No | `MigrationPlan` (counts, risk breakdown, manual review flags) |
| **Per-Object Drill-Down** | Streamlit dataframe rendering | No | UI table (12 objects in your case) |

**The dependency graph is 100% deterministic code analysis; LLM is used only for risk refinement.**

---

**Document**: Risk Assessment & Dependency Graph Architecture  
**Last Updated**: 2026-10-01  
**Related**: [architecture.md](./architecture.md) §5 (Planner Agent), [plan.md](../plan.md) (Phase 3 DoD)
