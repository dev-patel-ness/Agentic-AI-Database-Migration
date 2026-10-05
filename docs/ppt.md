# Agentic AI-Powered Database Migration Platform — PowerPoint Outline

## Slide 1: Problem Statement

### Database & Objects
- **Scale**: Enterprise databases with hundreds to thousands of objects
  - Tables: 100-500+
  - Views: 50-200+
  - Stored Procedures: 50-300+
  - Functions: 50-200+
  - Triggers: 20-100+
  - Complex dependencies: Foreign keys, sequences, permissions

- **Complexity of Manual Migration**
  - Dialect translation: Oracle → PostgreSQL, MySQL → Oracle, etc.
  - DDL/schema conversion with syntax differences across vendors
  - Stored procedure and trigger logic adaptation
  - Data validation and reconciliation across databases
  - Risk assessment and dependency mapping

- **Current Challenges**
  - Manual migrations: 3-6 months for large projects
  - High error rates in manual SQL translation
  - Data integrity validation is tedious and error-prone
  - Knowledge silos: expertise required per database dialect
  - Difficult to parallelize and scale to multiple migrations

---

## Slide 2: Business Requirements & Value Proposition

### Key Objectives
- **Automation**: Reduce manual effort by 70-80%
  - Auto-translate schema (DDL, stored procedures, triggers)
  - Auto-generate validation & reconciliation queries
  - Auto-detect high-risk objects requiring human review

- **Cost Savings**
  - Reduced DBA/Engineer hours: ~1-2 FTE for 6-month project → 1-2 weeks of effort
  - Estimated manual cost: ~$200k-$500k per migration → Reduction to ~$20k-$50k
  - Repeatable platform amortizes R&D across multiple migrations

- **Risk Mitigation**
  - Human-in-the-loop approval gates before critical phases
  - Automated validation (checksums, row counts, referential integrity)
  - Comprehensive audit trail for compliance

- **Timeline Compression**
  - 6-month manual project → 2-3 weeks with platform
  - Parallel execution of migration phases
  - Rapid iteration on failed validations

---

## Slide 3: Architecture Overview

### High-Level System Design
```
┌─────────────────────────────────────────────────────────┐
│                    User Interface                        │
│  ┌──────────────────────────────────────────────────┐   │
│  │  Streamlit UI: Job Configuration & Review        │   │
│  │  - Job creation, status tracking                 │   │
│  │  - Human approval gates (Plan, Validation, Test) │   │
│  │  - DDL/report viewers                            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                    API Layer (FastAPI)                  │
│  - REST endpoints for job management                    │
│  - WebSocket/SSE for real-time progress                 │
│  - Authentication & authorization                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│            Orchestration (LangGraph)                     │
│  - Stateful state machine: Discover → Validate → Test   │
│  - Human-in-the-loop interrupts                         │
│  - Postgres-backed checkpoint persistence               │
│  - Bounded-retry policy (3 attempts per phase)          │
└─────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    Agent Layer                               │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────┐           │
│  │ Planner     │ │ Assessment   │ │ Schema      │           │
│  │ Agent       │ │ Agent        │ │ Agent       │  ...      │
│  └─────────────┘ └──────────────┘ └─────────────┘           │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                 Tool Adapters (Plugins)                      │
│  ┌──────────────────┐ ┌──────────────┐ ┌─────────────────┐  │
│  │ Schema Extractor │ │ CrackSQL     │ │ SeaTunnel       │  │
│  │ Adapter          │ │ Adapter      │ │ Adapter         │  │
│  └──────────────────┘ └──────────────┘ └─────────────────┘  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    Data & AI Services                        │
│  AWS Bedrock (Nova Pro LLM + Titan Embeddings)               │
│  PGVector Knowledge Base                                     │
│  Platform Metadata Database (PostgreSQL)                     │
└──────────────────────────────────────────────────────────────┘
```

### Key Design Principles
- **Plugin-first**: Dialects and tool adapters are swappable; no hard-coded logic
- **Stateful orchestration**: Full workflow state persisted at every checkpoint
- **Human-in-the-loop as first-class node**: Approval gates at critical phases
- **Deterministic validation**: LLM suggestions are always verified by automated tests

---

## Slide 4: End-to-End Workflow & State Machine

### Migration Phases
1. **Discovery & Assessment**
   - Extract schema (DDL export) from source database
   - Parse with SQL/DDL parser (sqlglot) → object catalog + dependency graph
   - Identify FK dependencies, sequences, custom types

2. **Planning**
   - Planner Agent analyzes discovery data with RAG
   - Risk-score objects (auto, medium, high)
   - Flag manual-review objects (complex triggers, unsupported syntax)
   - Generate migration plan with sequence and effort estimates
   - **Human Review Gate**: Approve, modify, or reject plan

3. **Schema Transformation**
   - Schema Agent translates DDL using CrackSQL (AST + LLM)
   - Convert views, stored procedures, triggers
   - Apply target dialect syntax & case conventions
   - Generate target DDL scripts

4. **Data Migration**
   - Data Agent orchestrates bulk load via SeaTunnel
   - Order tables by FK dependency
   - Bulk extract → Bulk load to target
   - Streaming CDC (future extension)

5. **Validation & Reconciliation**
   - Validation Agent runs checksums (row count, hash by table)
   - Compare source ↔ target databases
   - Generate reconciliation report
   - **Human Review Gate**: Approve or retry data migration

6. **Testing**
   - Test Runner verifies:
     - Schema compatibility (DDL syntax)
     - Missing objects (compare catalogs)
     - Referential integrity (FK orphan queries)
     - Performance smoke tests (query latency thresholds)
   - Route: PASS → Complete, FAIL → retry validation

7. **Completion**
   - Job marked COMPLETED
   - Audit trail persisted
   - Artifacts (DDL, validation reports) exported

### State Machine with Retries
- Every phase with LLM/tool invocation: **max 3 automatic retries** on failure
- Backoff strategy: exponential delays between retries
- After 3 failures: **HumanReviewFailure interrupt** with error context
- Reviewer can: Retry (resets counter), Abort (marks job ABORTED)
- State persisted at checkpoints → resume after crash/restart

---

## Slide 5: Docker Images & Deployment

### Container Architecture
```
┌──────────────────────────────────┐
│   Docker Compose (Local Dev)     │
├──────────────────────────────────┤
│ ┌─ Migration Platform Service  │
│ │  - Python 3.10+ (FastAPI)     │
│ │  - LangGraph orchestrator      │
│ │  - Agents & tool adapters      │
│ │  - Port: 8000                  │
│ └──────────────────────────────  │
│                                  │
│ ┌─ Streamlit UI                 │
│ │  - Python 3.10+               │
│ │  - Port: 8501                 │
│ └──────────────────────────────  │
│                                  │
│ ┌─ PostgreSQL (Metadata DB)     │
│ │  - PGVector extension          │
│ │  - Knowledge base & checkpoints│
│ │  - Port: 5432                 │
│ └──────────────────────────────  │
│                                  │
│ ┌─ Prometheus (Metrics)         │
│ │  - Port: 9090                 │
│ └──────────────────────────────  │
│                                  │
│ ┌─ Grafana (Dashboards)         │
│ │  - Port: 3000                 │
│ └──────────────────────────────  │
└──────────────────────────────────┘
```

### Build & Push
- **Base image**: `python:3.10-slim` (lightweight)
- **Dependencies**: `pyproject.toml` with pinned versions
- **ECR Registry**: AWS ECR for production deployments
- **Kubernetes Deployment**: Helm charts for scaling

### Local Setup
```bash
docker-compose up -d
# Starts all services with pre-configured networks
```

---

## Slide 6: Agent Catalog & Descriptions

### Five Core Agents

| # | Agent | Responsibility | Key Features |
|---|-------|-----------------|-------------|
| **1** | **Planner Agent** | Build migration plan: sequence, priorities, risk levels, effort estimates | RAG-backed, Bedrock Nova Pro, deterministic heuristic scoring |
| **2** | **Assessment Agent** | Discovery & schema analysis, dependency graph | Per-dialect DDL export, sqlglot parser, FK mapping |
| **3** | **Schema Agent** | DDL/stored procedure/trigger/view translation | CrackSQL hybrid AST+LLM, confidence scores, idempotent re-apply |
| **4** | **Data Agent** | Bulk historical data load (phase 5 main action) | SeaTunnel orchestration, FK-dependency ordering, resumable |
| **5** | **Validation Agent** | Row counts, checksums, referential integrity | Pandas/PySpark hashing, per-table reconciliation, Prometheus metrics |

### Agent Capabilities
- **Planner**: Risk scoring, manual review flagging, effort estimation
- **Assessment**: Table/view/procedure inventory, FK dependency graph, custom type detection
- **Schema**: AST-based translation for 80% of DDL, LLM fallback for ambiguous constructs
- **Data**: Parallel table load, CDC readiness (placeholder), resumable on failure
- **Validation**: Hash-based checksums, aggregate comparisons, orphan FK detection

---

## Slide 7: Agent-to-Agent Communication & State Management

### Unified State Machine (Pydantic Model)
```python
class MigrationState:
    job_id: str                        # Unique identifier
    dialects: DialectPair              # Source & target database
    discovery: DiscoveryResult         # Schema catalog + dependency graph
    plan: MigrationPlan                # Sequenced object list + risk levels
    schema_translation: TranslationResult  # Translated DDL
    data_migration: DataMigrationResult    # Rows moved, CDC status
    validation: ValidationReport       # Checksums, mismatches
    test_report: TestReport            # Test results (PASS/FAIL)
    current_phase: str                 # Which phase are we in?
    status: str                        # RUNNING, PAUSED, COMPLETED, ABORTED
    retry_count: int                   # Retries in current phase (max 3)
    approvals: List[ApprovalRecord]    # Human decisions, timestamps, audit trail
```

### State Flow
1. **Discover** → Sets `discovery`
2. **Analyse** → Sets `plan` (Planner Agent decision)
3. **HumanReviewPlan** → Records `approvals[0]` (first approval)
4. **Transform** → Sets `schema_translation`
5. **DataMigrate** → Sets `data_migration`
6. **Validate** → Sets `validation`
7. **HumanReviewValidation** → Records `approvals[1]` (second approval)
8. **Test** → Sets `test_report`
9. **Checkpoint persisted after every node** (Postgres)

### Agent Communication Pattern
```
LangGraph Node (Agent)
  ↓ (reads state, calls agent logic)
Agent (with RAG / LLM / Tool Adapter)
  ↓ (updates specific state fields)
LangGraph persists updated state → next edge decision
  ↓ (router function: checks status/validation_result)
Next Node (Agent or Human Gate)
```

### Key State Transitions
- **Router: Plan → PASS**: `status == 'PLAN_COMPLETE'` → HumanReviewPlan interrupt
- **Router: Validation → PASS/FAIL**: `validation.overall_status == 'PASS'` → Test; `'FAIL'` → DataMigrate retry
- **Retry Loop**: On tool/LLM failure, increment `retry_count`; if `retry_count >= 3`, raise `HumanReviewFailure` interrupt

---

## Slide 8: Retrieval-Augmented Generation (RAG) Implementation

### Knowledge Base Architecture
```
┌───────────────────────────────────────────────┐
│       Knowledge Ingestion Pipeline            │
├───────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────┐   │
│ │ Source Docs (Markdown, SQL docs, etc.)  │   │
│ │ - Type mapping rules (Oracle ↔ MySQL)   │   │
│ │ - Vendor syntax quirks & incompatibilities
│ │ - Historical migration patterns         │   │
│ │ - Known issues & workarounds            │   │
│ │ - Performance tuning tips               │   │
│ │ - Security best practices               │   │
│ └─────────────────────────────────────────┘   │
│            ↓ (chunking & embedding)           │
│ ┌─────────────────────────────────────────┐   │
│ │ Text Splitter: 512-char chunks          │   │
│ └─────────────────────────────────────────┘   │
│            ↓ (AWS Bedrock Titan Embeddings)   │
│ ┌─────────────────────────────────────────┐   │
│ │ PGVector Store (PostgreSQL)             │   │
│ │ - 1536-dim vectors (Titan v2)           │   │
│ │ - 21 seed documents ingested            │   │
│ │ - ~800 chunks indexed                   │   │
│ └─────────────────────────────────────────┘   │
└───────────────────────────────────────────────┘
```

### Retrieval at Runtime

**Planner Agent RAG Flow**:
1. Query: "What are best practices for Oracle → PostgreSQL migration?"
2. Embed query with Titan Embeddings (same model as corpus)
3. PGVector similarity search (cosine distance, top-5 chunks)
4. Re-rank by dialect pair match (Oracle source + PostgreSQL target)
5. Inject top-3 chunks into Bedrock Nova Pro system prompt
6. LLM reasons over retrieved examples + discovery data
7. Output: Risk scores + manual review flags

**Schema Agent RAG Flow**:
1. Query: "How to translate Oracle ROWTYPE to PostgreSQL?"
2. Retrieve type-mapping rules from knowledge base
3. Pass to CrackSQL for deterministic AST translation
4. On ambiguity (e.g., custom package types), use retrieved rules to LLM prompt
5. Output: Translated DDL with confidence score

### Knowledge Base Contents
- **Dialect-pair compatibility**: Oracle ↔ MySQL, Oracle ↔ PostgreSQL, MySQL ↔ PostgreSQL
- **Type mappings**: NUMBER/INTEGER/VARCHAR translations per dialect
- **Function/procedure equivalents**: Vendor-specific built-ins
- **Performance patterns**: Indexing, partitioning strategies per dialect
- **Security models**: Row-level security, encryption, audit trail patterns

---

## Slide 9: Future Extensions

### Planned Enhancements (Phase 2+)

#### 1. **CDC (Change Data Capture) Streaming**
   - **Current state**: Bulk batch load only (after discovery, schema, validation)
   - **Future**: Real-time streaming after bulk load
   - **Implementation**: Debezium + Kafka + SeaTunnel streaming engine
   - **Benefit**: Minimal downtime, continuous sync before cutover

#### 2. **Application Deployment & Cutover Orchestration**
   - **Current state**: Migration completes; humans manually update app connection strings
   - **Future**: Automated rolling deployment
   - **Implementation**:
     - kubectl adapter for canary/rolling updates
     - Helm charts for blue/green deployment
     - Health checks + automatic rollback on test failure
   - **Benefit**: Zero-downtime cutover, automated rollout validation

#### 3. **Infrastructure Automation (Terraform)**
   - **Current state**: Databases pre-provisioned; platform runs in docker-compose/manual K8s
   - **Future**: Full IaC (Infrastructure as Code)
   - **Implementation**:
     - Terraform modules: VPC, EKS, RDS/Aurora multi-AZ, networking, IAM
     - CloudFormation stacks as alternative
     - Automated disaster recovery provisioning
   - **Benefit**: Repeatable, auditable infrastructure; cost optimization

#### 4. **Advanced Validation & Drift Detection**
   - **Current state**: Row count + checksum validation at job completion
   - **Future**: Continuous drift detection post-migration
   - **Implementation**: Background job to periodically validate schema/data consistency
   - **Benefit**: Early detection of schema drift, unauthorized changes

#### 5. **Multi-Tenancy & Cost Controls**
   - **Current state**: Single-tenant per deployment
   - **Future**: Multi-tenant isolation + cost guardrails
   - **Implementation**:
     - RBAC per tenant
     - Bedrock usage quotas & rate limiting
     - Cost attribution per migration job
   - **Benefit**: SaaS-ready platform, budget predictability

#### 6. **Advanced Performance Tuning**
   - **Current state**: Smoke tests (query latency thresholds)
   - **Future**: Automated query optimization + index recommendation
   - **Implementation**: Query explain plan analysis, workload replay on target DB
   - **Benefit**: Confidence in query performance parity

---

## Slide 10: Demo & Walkthrough

### Demo Scenario
- **Source DB**: Oracle 19c (Capstone demo database)
  - 5 tables, 2 views, 1 procedure, 1 function, 1 trigger
  - ~50k rows

- **Target DB**: PostgreSQL 14
  - Empty initially

### Live Demo Steps

#### Step 1: Job Creation (Streamlit UI)
- [ ] Show UI at `http://localhost:8501`
- [ ] Walk through job form:
  - Source dialect: Oracle
  - Target dialect: PostgreSQL
  - Source connection: [pre-configured]
  - Target connection: [pre-configured]
  - Submit → Job ID assigned, status = CREATED

#### Step 2: Discovery & Assessment
- [ ] **Expected duration**: ~2 min
- [ ] Show LangGraph orchestrator running (FastAPI logs)
- [ ] Refresh UI → status = ASSESSING
- [ ] After assessment:
  - Object catalog displayed
  - FK dependency graph shown
  - Highlighted: procedure with PL/SQL → needs CrackSQL

#### Step 3: Planning
- [ ] **Expected duration**: ~1 min
- [ ] LangGraph calls Planner Agent
- [ ] Planner queries RAG ("Oracle → PostgreSQL best practices")
- [ ] Risk scores computed:
  - Trigger: MEDIUM (PL/SQL → pl/pgsql, requires review)
  - Others: AUTO
- [ ] Show LangSmith trace: latency, token usage, cost

#### Step 4: Human Review Gate (Plan Approval)
- [ ] UI shows "AWAITING_APPROVAL" status
- [ ] Show plan summary on Streamlit
  - 5 tables (MEDIUM risk due to custom types)
  - 1 trigger (MEDIUM)
  - Effort: ~2 hours manual (automation saves ~80%)
- [ ] **Demonstrate**:
  - Approve → continue
  - OR Modify → modify plan, resubmit
- [ ] Approver clicks **APPROVE**
- [ ] `ApprovalRecord` logged with reviewer name, timestamp

#### Step 5: Schema Transformation
- [ ] **Expected duration**: ~2 min
- [ ] Schema Agent invokes CrackSQL adapter
- [ ] Show generated PostgreSQL DDL
  - Oracle NUMBER(10,2) → PostgreSQL NUMERIC(10,2)
  - PL/SQL procedure → pl/pgsql
  - Trigger syntax adjusted
- [ ] LangSmith trace: CrackSQL AST parsing, Bedrock fallback LLM call

#### Step 6: Data Migration
- [ ] **Expected duration**: ~3-5 min (depends on table size)
- [ ] Data Agent orchestrates SeaTunnel
- [ ] Show SeaTunnel logs: per-table row counts
- [ ] Prometheus metrics dashboard (open in browser):
  - "Migration Throughput" graph updating in real-time
  - Rows/sec metric

#### Step 7: Validation & Reconciliation
- [ ] **Expected duration**: ~2 min
- [ ] Validation Agent runs checksums
- [ ] Show ValidationReport:
  - Table row counts (source vs. target): ✓ MATCH
  - Table checksums: ✓ MATCH
  - FK orphan queries: ✓ PASS (no orphans)
  - Overall: PASS

#### Step 8: Human Review Gate (Validation Approval)
- [ ] UI shows "AWAITING_VALIDATION_APPROVAL"
- [ ] Show validation report summary
- [ ] Approver reviews checksums and clicks **APPROVE**
- [ ] Second `ApprovalRecord` logged

#### Step 9: Testing
- [ ] **Expected duration**: ~1 min
- [ ] Test Runner invokes 4 checks:
  1. Schema compatibility (from ValidationReport)
  2. Missing objects (compare catalogs)
  3. Referential integrity (FK orphan queries)
  4. Performance smoke tests (query latency)
- [ ] All tests PASS
- [ ] Test report generated

#### Step 10: Completion & Audit Trail
- [ ] Job status → COMPLETED
- [ ] Show final summary:
  - Migration time: ~12 min (vs. 2-3 days manual)
  - Cost saved: [calculated from Bedrock tokens + DBA hours]
- [ ] Audit log:
  - All approvals with timestamps
  - Checkpoints saved to Postgres
  - Full LangSmith trace accessible

### Supporting Artifacts
- **LangSmith trace viewer**: Show spans for each agent/tool call
- **Grafana dashboard**: Agent latency, tool success rate, migration throughput
- **Prometheus metrics**: Real-time query latencies, throughput
- **Generated reports**: DDL script, validation report (PDF export)

### Key Talking Points During Demo
1. **Speed**: Schema + data + validation + testing in ~12 min vs. 2-3 days manual
2. **Accuracy**: Automated checksums + referential integrity checks → high confidence
3. **Transparency**: Every decision (agent reasoning, LLM call, approval) is traced and auditable
4. **Extensibility**: New dialects/tools slot in without changing orchestrator
5. **Risk mitigation**: Human approval gates + deterministic validation before commitment

---

## Slide 11: Q&A & Thank You

### Key Takeaways
- Agentic AI dramatically compresses enterprise database migrations (70-80% automation)
- Stateful orchestration + human-in-the-loop = safe, auditable process
- RAG + LLM reasoning enables dialect-agnostic translations
- Plugin-first architecture makes it extensible to new databases/tools
- Observability (LangSmith, Prometheus, Grafana) provides full visibility

### Backup Slides (if time permits)
- Deep dive: CrackSQL hybrid AST+LLM translation approach
- Deep dive: Retry policy & failure handling
- Deep dive: Knowledge base ingestion & dialect-pair RAG retrieval
- Cost & effort analysis (ROI calculation)
- Security & compliance considerations