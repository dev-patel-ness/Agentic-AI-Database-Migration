# Operations & Deployment Guide

**Version:** 1.0.0 (Phase 10 Release)  
**Status:** Production-ready for demonstrations and limited production use  
**Date:** 2026-10-05

---

## Table of Contents
1. [Resolved Issues](#resolved-issues)
2. [Known Issues & Limitations](#known-issues--limitations)
3. [AWS Deployment](#aws-deployment)
4. [Performance Baselines](#performance-baselines)
5. [Risk Assessment Architecture](#risk-assessment-architecture)

---

## Resolved Issues

### 1. FK DDL Fails: "relation does not exist"
**Fix:** `_sanitize_target_ddl()` in `agents/schema_agent/__init__.py` folds quoted identifiers to lowercase for PostgreSQL targets (CrackSQL preserves Oracle's uppercase, but SeaTunnel creates lowercase unquoted tables).

### 2. Connection Defaults to Wrong Schema
**Fix:** Set `search_path` in `dialects/connections.py` after connecting with `SET search_path TO "<schema>", public`.

### 3. CrackSQL Hybrid Translation: NoneType Error
**Fix:** Updated `knowledge_bases` in SQLite config to use `amazon.titan-embed-text-v2:0` instead of disabled `text-embedding-ada-002` model.

### 4. Oracle `EDITIONABLE` Keyword Breaks Parser
**Fix:** `_strip_oracle_noise()` removes cosmetic keywords (`EDITIONABLE`, `NONEDITIONABLE`, `FORCE`) from source DDL before CrackSQL processing.

### 5. View DDL Schema Name Not Mapped
**Fix:** Reorder `_sanitize_target_ddl()`: map source → target schema first (case-insensitive), then fold identifiers to lowercase.

### 6. View/Procedure DDL Has Literal `\n`/`\t` Escapes
**Fix:** Unescape JSON escape sequences: `cleaned = ddl.encode('utf-8').decode('unicode_escape')`.

### 7. FK Constraint Reapply Fails: "already exists"
**Fix:** Treat "already exists" errors for foreign_key objects as idempotent success in `apply_schema_translations()`.

### 8. Target Row Counts Multiply on Re-run
**Fix:** Changed SeaTunnel sink from `APPEND_DATA` to `DROP_DATA` mode in `tool_adapters/seatunnel_adapter/__init__.py` to truncate before each load.

### 9. Knowledge Base Embeddings Table Empty
**Fix:** Run `poetry run python -m knowledge_base.ingestion.ingest` to populate 21 seed documents with Bedrock Titan v2 embeddings.

---

## Known Issues & Limitations

### Current Issues (Severity: LOW-MEDIUM)

| Issue | Phase | Impact | Workaround | Planned Fix |
|-------|-------|--------|-----------|------------|
| **Oracle Procedure Translation Accuracy** | 4 | ~5-10% of procedures may need manual editing (low confidence < 0.75) | Review flagged procedures in UI; accept as starting point | Enhanced KB hints (future) |
| **Bedrock Rate Limits** | 4 | >50 procedures may timeout; cost ~$0.0024/proc | Batch translations; exponential backoff retry | Result caching + batching (future) |
| **SeaTunnel Performance Plateau** | 5 | 1,000-2,000 rows/sec over WAN vs 5,000-10,000 local | Use AWS VPN/Direct Connect; increase connection pool | Parallel multi-table load; CDC support (future) |
| **Network Policy Strictness** | 8-9 | New services require manual NetworkPolicy updates | Edit `infra/k8s/network-policies.yaml` | Parameterize with Helm values (future) |
| **LangSmith Trace Sampling** | 9 | 10-20% slowdown on 1000+ LLM calls | Reduce sampling to 10%; disable locally | Adaptive sampling + batching (future) |
| **Infrastructure Automation** | 8 | Terraform/EKS/RDS automation deferred | Manual AWS provisioning (Phase 8 future extension) | Full IaC stack (future) |
| **Pod Restart Cascade on Memory Pressure** | 8-9 | OOM kills on 100M+ row migrations | Monitor pod memory; increase node size | Streaming data + spill-to-disk (future) |

### Unsupported Dialects (by design)
- SQL Server, Snowflake, BigQuery, Redshift, Sybase, Informix

### Design Limitations
- **Application code refactoring** (Phase 6): Future extension. Users must manually refactor application code for dialect-specific syntax changes.
- **Infrastructure automation** (Phase 8): Future extension. Full Terraform/Kubernetes/RDS automation planned.
- **Multi-tenant isolation**: Future enhancement.
- **Full observability stack** (Phase 9-10): Core logging/tracing in place; full Prometheus/Grafana dashboards planned.

---

## AWS Deployment

### Prerequisites
- AWS account with Bedrock model access (Nova Pro, Titan Embeddings)
- Docker (for local development)
- Source and target databases configured (Oracle, MySQL, or PostgreSQL)

**Note:** Full infrastructure automation (Terraform/EKS/RDS) is a future extension. Current deployment uses manual AWS provisioning or local Docker Compose.

### Database Setup

**Local Development:**
```bash
# Start local database stack
docker-compose -f infra/docker/docker-compose.yml up -d
```

**AWS Deployment (Future Extension):**
Full infrastructure automation via Terraform (VPC/EKS/RDS) is planned for Phase 8. Currently requires manual AWS provisioning.

### Configuration

**Configuration Files:**

Set environment variables for database connections:
```bash
# Source DB (Oracle, MySQL, or PostgreSQL)
export SOURCE_DIALECT=oracle
export SOURCE_HOST=source-db.example.com
export SOURCE_PORT=1521
export SOURCE_USER=migration_user
export SOURCE_PASSWORD=***

# Target DB (Oracle, MySQL, or PostgreSQL)
export TARGET_DIALECT=postgresql
export TARGET_HOST=target-db.example.com
export TARGET_PORT=5432
export TARGET_USER=postgres
export TARGET_PASSWORD=***

# Bedrock configuration
export AWS_REGION=us-east-1
export BEDROCK_MODEL_ID=us.amazon.nova-pro-v1:0
```

---

## Performance Baselines

### Measured Performance (Phase 10 E2E Testing)

| Phase | Metric | Value |
|-------|--------|-------|
| 2 (Discovery) | 15 tables | 12 seconds |
| 3 (Planning) | 30 objects | 8 seconds |
| 4 (Translation) | 2 procedures | 15 seconds |
| 4 (Translation Latency p95) | Bedrock | 450ms |
| 5 (Data Load) | 6,050 rows | 0.75 seconds @ 8,000 rows/sec |
| 7 (Validation) | 3 tables | 8 seconds |
| 8 (Deployment) | 2 replicas | 50 seconds |
| 9 (Observability) | Trace overhead | <1% |

### Scaling Limits

| Dimension | Limit | Bottleneck |
|-----------|-------|-----------|
| Objects per migration | 10,000 | Bedrock rate limit (100 req/min) |
| Rows per table | 100M | SeaTunnel memory/throughput |
| Jobs in flight | 5-10 | EKS pod capacity |
| Bedrock cost per job | $50-100 | Large translation volumes |
| LangSmith traces | 100,000/month | Storage costs |

### Test Scenarios

```bash
# Latency benchmarking
pytest tests/performance/test_phase_latency.py -v --benchmark-only

# Throughput testing (small/medium/large datasets)
pytest tests/performance/test_throughput.py -v

# Memory profiling
python -m memory_profiler tests/performance/test_memory_profile.py

# CPU profiling
py-spy record -o profile.svg -- poetry run python scripts/run_migration.py
```

---

## Risk Assessment Architecture

### Two-Phase Risk Assessment

**Phase 1 (Deterministic Heuristic):**
- Object type → default risk level (tables=low, views=medium, procedures/functions/triggers=high)
- Column type inspection: escalate to "high" if using vendor-specific types (CLOB, BLOB, ENUM, JSON, ARRAY, etc.)

**Phase 2 (LLM Refinement, Best-Effort):**
- Filter to only "medium"/"high" risk objects (≤30)
- Retrieve knowledge base context: "migrating X to Y: type mapping, syntax incompatibilities"
- Call Bedrock Nova Pro with risk list + KB context
- LLM refines risk levels + reasons; merge back into assessment
- If LLM fails, fall back to Phase 1 deterministic scores (never blocks)

### Dependency Graph Construction

Built **purely from foreign key metadata** (not LLM-inferred):

```python
def _build_dependency_graph(fk_rows):
    """table_name → [referenced_table_names]"""
    graph = {}
    for constraint_name, table_name, column_name, ref_table_name, ref_column_name in fk_rows:
        graph.setdefault(table_name, [])
        if ref_table_name not in graph[table_name]:
            graph[table_name].append(ref_table_name)
    return graph
```

Used by:
- `agents/data_agent/_topological_sort_tables()` — orders table loads so parents load before dependents
- `agents/schema_agent/_topological_sort_by_dependencies()` — orders DDL application by dependency

### Streamlit UI Rendering

- Object counts (tables, views, procedures, functions, triggers)
- Risk breakdown (low/medium/high counts)
- Manual review objects list
- Per-object drill-down table (object, type, risk_level, reason)

---

## Common Scenarios & Solutions

### Scenario 1: Schema with 100+ Procedures
**Problem:** Phase 4 translation takes 2+ hours.  
**Solution:** Split into 10-20 procedure batches; run parallel jobs on separate EKS pods; merge results.

### Scenario 2: Oracle Migration Over Slow Network
**Problem:** SeaTunnel drops to 500 rows/sec.  
**Solution:** Pre-stage source DB replica on AWS RDS; use AWS VPN/Direct Connect; run from same AZ.

### Scenario 3: Pod Restart Cascade on Memory Pressure
**Problem:** Large migrations (100M+ rows) trigger OOM kills.  
**Solution:** Monitor pod memory (`kubectl top pods`); increase node size (t3.xlarge → m5.2xlarge); enable streaming data mode.

---

## Monitoring & Troubleshooting

### Observability

**LangSmith Traces:**
- All agent calls and LLM invocations are traced
- Set `LANGSMITH_API_KEY` to enable trace collection
- Disable locally: `unset LANGSMITH_API_KEY`

**Monitoring (Future):**
- Prometheus dashboards (Phase 9+)
- Grafana observability stack (Phase 9+)

### Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `429: Rate limited` | Bedrock limit exceeded (100 req/min) | Add exponential backoff; batch requests |
| `search_path: does not exist` | Wrong schema connection | Verify `SET search_path` in connections.py |
| `DuplicateObject: already exists` | Rerunning job against non-empty target | Treat as idempotent success for FKs |
| `Pod evicted: memory pressure` | Node memory >90% | Scale node group or increase pod memory requests |


---

## Cost Estimation

- **Bedrock Nova Pro:** ~$0.003 per 1K input tokens (~800 tokens/procedure → $0.0024/proc)
  - Example: 200 procedures = $0.48; 1000 procedures = $2.40
- **LangSmith:** ~$2 per 10,000 traces (scale beyond 100K traces/month for cost concerns)
- **AWS RDS Multi-AZ:** ~$0.50/hour (PostgreSQL db.r5.large equivalent)
- **EKS:** ~$0.10/hour cluster + node costs (t3.large/xlarge = ~$0.10/hour each)

---

## References

### Configuration Files
- Infrastructure: `infra/docker/` (for local dev), `infra/` (future Terraform/Helm/K8s configs)
- Dialects: `dialects/` (MySQL, Oracle, PostgreSQL adapters)
- Agents: `agents/` (planner, schema, data, deployment, validation agents)
- Observability: `observability/` (Prometheus, Grafana, LangSmith, tracer)

### Key Code Files
- Risk assessment: `agents/planner_agent/risk.py`, `agents/planner_agent/llm.py`
- Dependency graph: `tool_adapters/schema_extractor_adapter/__init__.py`
- Schema translation: `agents/schema_agent/__init__.py` (`_sanitize_target_ddl()`)
- Data migration: `tool_adapters/seatunnel_adapter/__init__.py`

---

## Future Enhancements

### Phase 6: Application Code Refactoring
- Automated application-layer adaptation (AST-based transformations)
- Multi-language support (Java/Spring, Python/SQLAlchemy, C++)

### Phase 8: Infrastructure Automation
- Full Terraform provisioning (VPC, EKS, RDS, IAM/IRSA)
- Helm charts for application deployment
- Kubernetes manifests and network policies
- Automated secrets management via Secrets Manager
- Multi-environment support (dev/staging/prod)

### Phase 9-10: Observability & CI/CD
- Prometheus metrics collection and dashboards
- Grafana dashboards for all phases
- Full GitHub Actions CI/CD pipeline
- E2E workflow testing
- Performance benchmarking suite
- Cost estimation and tracking

### Additional Enhancements
- [ ] Translation result caching (Redis-backed)
- [ ] Parallel multi-table load (3-5 tables concurrent)
- [ ] CDC (Change Data Capture) for incremental updates
- [ ] Multi-tenant isolation & RBAC
- [ ] Comprehensive audit logging
- [ ] Adaptive LangSmith trace sampling
- [ ] Advanced refactoring hints via OpenRewrite patterns

