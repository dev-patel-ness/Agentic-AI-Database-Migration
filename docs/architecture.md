# Agentic AI-Powered Database Migration Platform — Architecture

> **Migration matrix**: any of Oracle, MySQL, PostgreSQL can act as source or target. A single `DialectPair` in `MigrationState` (see [§7](#7-shared-state-schema)) determines direction at job-creation time; agents and adapters are direction-agnostic — they read `dialects.source` / `dialects.target` and dispatch to the matching plugin pair.

> Status: Design baseline (v1.0), derived from `Capstone_Proposal.md` (agentic/API/UI framework) and the concrete migration tooling choices below.
> Supported migrations: **any-to-any interconversion between Oracle, MySQL, and PostgreSQL** (e.g. Oracle→PostgreSQL, MySQL→Oracle, PostgreSQL→MySQL, etc). Each dialect is a symmetric plugin usable as either source or target — SQL Server is not in scope.

## Table of Contents

1. [Guiding Principles](#1-guiding-principles)
2. [System Context](#2-system-context)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Repository Structure](#4-repository-structure)
5. [Agent Catalog & Tool Mapping](#5-agent-catalog--tool-mapping)
6. [Orchestration: LangGraph State Machine](#6-orchestration-langgraph-state-machine)
7. [Shared State Schema](#7-shared-state-schema)
8. [Phase-by-Phase Sequence Diagrams](#8-phase-by-phase-sequence-diagrams)
9. [Human-in-the-Loop Approval Flow](#9-human-in-the-loop-approval-flow)
10. [Data & Knowledge Stores](#10-data--knowledge-stores)
11. [Deployment Architecture](#11-deployment-architecture)
12. [CI/CD Pipeline](#12-cicd-pipeline)
13. [Observability](#13-observability)
14. [Security Considerations](#14-security-considerations)
15. [Extensibility: Adding New Features](#15-extensibility-adding-new-features)
16. [Open Questions / Future Work](#16-open-questions--future-work)
17. [Implementation Status](#17-implementation-status)

---

## 1. Guiding Principles

- **Plugin-first**: every source dialect, target dialect, and migration tool is a swappable adapter behind a stable interface — never hard-coded into agent logic.
- **Stateful orchestration, not scripts**: LangGraph owns the end-to-end workflow state so any phase can pause, resume, replay, or be re-entered after human review.
- **Human-in-the-loop is a first-class node**, not an afterthought — high-risk transitions always route through an interrupt.
- **Bounded automatic recovery, not infinite loops**: any LLM call or tool-adapter invocation retries automatically on failure, capped at **3 attempts**, before escalating to a human review interrupt (see [§6.1](#61-failure-handling--retry-policy)).
- **Deterministic validation over LLM trust**: schema/code translation may use LLM reasoning, but data correctness is always confirmed by deterministic checksum/reconciliation code.
- **Everything observable**: every agent call, tool invocation, and state transition is traced (LangSmith) and every infra/runtime metric is scraped (Prometheus/Grafana).
- **Infra as code, deploy as code**: Terraform provisions cloud resources; Kubernetes manifests/Helm charts describe runtime; nothing is clicked manually.

---

## 2. System Context

```mermaid
flowchart TB
    subgraph Users
        Eng[Migration Engineer / DBA]
        Approver[Approver / Reviewer]
    end

    subgraph Platform["Agentic Migration Platform"]
        UI[Streamlit UI]
        API[FastAPI Backend]
        Orchestrator[LangGraph Orchestrator]
    end

    SrcDB[(Source DB\nOracle / MySQL / PostgreSQL - any)]
    TgtDB[(Target DB\nOracle / MySQL / PostgreSQL - any)]
    Bedrock[AWS Bedrock\nNova Pro + Titan Embeddings]
    KB[(PGVector Knowledge Base)]
    K8s[Kubernetes Cluster]
    Obs[Observability Stack\nLangSmith / Prometheus / Grafana]

    Eng -->|Configure migration job| UI
    Approver -->|Approve / Reject / Modify| UI
    UI --> API
    API --> Orchestrator
    Orchestrator -->|Discover / Read| SrcDB
    Orchestrator -->|Write / Validate| TgtDB
    Orchestrator -->|Reasoning, translation| Bedrock
    Orchestrator -->|RAG retrieval| KB
    Orchestrator -->|Rolling update / rollback| K8s
    Orchestrator -.->|traces & metrics| Obs
    API -.->|traces & metrics| Obs
```

---

## 3. High-Level Architecture

```mermaid
flowchart TB
    subgraph Client Layer
        ST[Streamlit UI]
    end

    subgraph API Layer
        FA[FastAPI Gateway]
        Auth[AuthN/AuthZ Middleware]
        WS[WebSocket / SSE Progress Stream]
    end

    subgraph Orchestration Layer
        LG[LangGraph Runtime]
        Ckpt[(LangGraph Checkpointer\nPostgres)]
        HITL[Human-in-the-Loop Interrupt Handler]
    end

    subgraph Agent Layer
        A1[Assessment Agent]
        A2[Schema Agent]
        A3[Data Agent]
        A4[Code Agent]
        A5[Validation Agent]
        A6[Deployment Agent]
        A7[Planner Agent]
    end

    subgraph Tool Adapter Layer["Tool Adapters (plugin interface)"]
        T1[Schema Extractor / DDL Parser Adapter]
        T2[CrackSQL Adapter]
        T3[SeaTunnel Zeta Adapter]
        T4[OpenRewrite Adapter]
        T5[Aider Adapter]
        T6[Checksum/Reconciliation Adapter]
        T7[kubectl / Helm Adapter]
        T8[Terraform Adapter]
    end

    subgraph AI Services
        Bedrock[AWS Bedrock: Nova Pro LLM]
        Embed[AWS Bedrock: Titan Embeddings]
    end

    subgraph Data Layer
        KBV[(PGVector Knowledge Base)]
        MetaDB[(Platform Metadata DB\nPostgres)]
        SrcDB[(Source DB)]
        TgtDB[(Target DB)]
    end

    subgraph Infra Layer
        TF[Terraform: VPC/EKS/RDS/Aurora]
        K8s[EKS Cluster: App Pods, Old + New]
    end

    subgraph Observability Layer
        LF[LangSmith Tracing]
        Prom[Prometheus]
        Graf[Grafana Dashboards]
    end

    ST --> FA --> Auth --> LG
    FA --> WS
    LG --> Ckpt
    LG --> HITL --> ST

    LG --> A7 --> LG
    LG --> A1 --> T1 --> SrcDB
    LG --> A2 --> T2
    LG --> A3 --> T3
    LG --> A4 --> T4
    LG --> A4 --> T5
    LG --> A5 --> T6
    LG --> A6 --> T7 --> K8s
    A6 --> T8 --> TF --> K8s

    A2 --> Bedrock
    A4 --> Bedrock
    A7 --> Bedrock
    A1 --> Embed --> KBV
    A2 --> KBV
    A7 --> KBV

    T3 --> SrcDB
    T3 --> TgtDB
    T6 --> SrcDB
    T6 --> TgtDB

    LG --> MetaDB
    LG -.-> LF
    FA -.-> LF
    K8s -.-> Prom --> Graf
    FA -.-> Prom
```

---

## 4. Repository Structure

Monorepo, modular per agent, with plugin adapters isolated so new dialects/tools slot in without touching orchestration code.

```
migration-platform/
├── apps/
│   ├── ui-streamlit/              # Human review + job configuration UI
│   └── api-fastapi/               # REST/WebSocket gateway, auth, job queue
├── orchestrator/
│   ├── graph.py                   # LangGraph StateGraph definition (nodes/edges)
│   ├── state.py                   # Shared Pydantic state schema
│   └── checkpointer.py            # Postgres-backed checkpoint store
├── agents/
│   ├── assessment_agent/
│   ├── schema_agent/
│   ├── data_agent/
│   ├── code_agent/
│   ├── validation_agent/
│   ├── deployment_agent/
│   └── planner_agent/
├── tool_adapters/                 # Plugin interface: BaseToolAdapter
│   ├── base.py                    # Abstract adapter contract (run/status/rollback)
│   ├── schema_extractor_adapter/  # generates schema.sql per dialect, parses via SQL/DDL parser
│   ├── cracksql_adapter/
│   ├── seatunnel_adapter/
│   ├── openrewrite_adapter/
│   ├── aider_adapter/
│   ├── checksum_adapter/
│   ├── kubectl_adapter/
│   └── terraform_adapter/
├── dialects/                      # Source/target dialect plugins
│   ├── base.py                    # Abstract Dialect contract (type map, SQL grammar hooks)
│   ├── oracle/                # symmetric: usable as source or target
│   ├── mysql/                 # symmetric: usable as source or target
│   └── postgresql/            # symmetric: usable as source or target
├── knowledge_base/
│   ├── ingestion/                 # Loads mapping rules, best practices into PGVector
│   └── retrievers/
├── infra/
│   ├── terraform/                 # VPC, EKS, RDS/Aurora, IAM modules
│   ├── k8s/                       # Helm charts / manifests per app
│   └── github-actions/            # CI/CD workflows
├── observability/
│   ├── langsmith/                 # Tracing config
│   └── grafana-dashboards/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── docs/
    └── architecture.md            # this file
```

**Extension contract:** a new source dialect = new folder under `dialects/` implementing `base.py`; a new migration tool = new folder under `tool_adapters/` implementing `BaseToolAdapter`; neither requires editing `orchestrator/graph.py`.

---

## 5. Agent Catalog & Tool Mapping

| # | Agent | Responsibility (Capstone) | Tool | Adapter |
|---|-------|---------------------------|--------------------|---------|
| 1 | **Planner Agent** | Builds migration plan: sequence, priorities, risk levels, effort, manual-review flags | LLM reasoning + RAG over knowledge base | — (no external tool, pure LangGraph node) |
| 2 | **Assessment Agent** | Discovery & schema analysis, dependency graph | Code-generated `schema.sql` (native per-dialect DDL export) + SQL/DDL parser (e.g. sqlglot) | `schema_extractor_adapter` |
| 3 | **Schema Agent** | DDL / stored procedure / trigger / view translation, source→target dialect | CrackSQL (hybrid AST + LLM) | `cracksql_adapter` |
| 4 | **Data Agent** | Bulk historical load + streaming CDC | Apache SeaTunnel (Zeta engine) | `seatunnel_adapter` |
| 5 | **Code Agent** | Application refactor: ORM/JDBC swap (Java/Spring), raw SQL/SQLAlchemy rewrite (C++/Python) | OpenRewrite (AST) + Aider (LLM CLI) | `openrewrite_adapter`, `aider_adapter` |
| 6 | **Validation Agent** | Row counts, checksums, referential integrity, aggregate comparisons | Custom Python (Pandas/PySpark hashing) | `checksum_adapter` |
| 7 | **Deployment Agent** | Cutover rollout + automatic rollback on failure | kubectl (rolling update, `rollout undo`), Terraform (infra provisioning) | `kubectl_adapter`, `terraform_adapter` |

Each adapter implements the same contract so agents call adapters generically:

```mermaid
classDiagram
    class BaseToolAdapter {
        <<interface>>
        +prepare(config) AdapterConfig
        +run(input) ToolResult
        +status(job_id) JobStatus
        +rollback(job_id) RollbackResult
    }
    class SchemaExtractorAdapter
    class CrackSQLAdapter
    class SeaTunnelAdapter
    class OpenRewriteAdapter
    class AiderAdapter
    class ChecksumAdapter
    class KubectlAdapter
    class TerraformAdapter

    BaseToolAdapter <|.. SchemaExtractorAdapter
    BaseToolAdapter <|.. CrackSQLAdapter
    BaseToolAdapter <|.. SeaTunnelAdapter
    BaseToolAdapter <|.. OpenRewriteAdapter
    BaseToolAdapter <|.. AiderAdapter
    BaseToolAdapter <|.. ChecksumAdapter
    BaseToolAdapter <|.. KubectlAdapter
    BaseToolAdapter <|.. TerraformAdapter
```

---

## 6. Orchestration: LangGraph State Machine

LangGraph drives the full workflow: **Discover → Analyse → Plan → Transform → Generate → Validate → Test → Approve → Migrate → Verify**. Every human-approval point is a graph **interrupt**; on resume, the graph re-enters exactly where it paused (via the Postgres checkpointer).

```mermaid
stateDiagram-v2
    [*] --> Discover
    Discover --> Analyse: schema.sql generation + DDL parse -> dependency graph
    Analyse --> Plan: Planner Agent (RAG + LLM)
    Plan --> HumanReviewPlan

    HumanReviewPlan --> Transform: Approve
    HumanReviewPlan --> Plan: Modify
    HumanReviewPlan --> [*]: Reject

    Transform --> Generate: CrackSQL DDL/SP/Trigger translation
    Generate --> CodeRefactor: OpenRewrite / Aider
    CodeRefactor --> DataMigrate: SeaTunnel bulk load + CDC

    DataMigrate --> Validate: Checksum reconciliation
    Validate --> HumanReviewValidation: report generated

    HumanReviewValidation --> Test: Approve
    HumanReviewValidation --> DataMigrate: Modify / retry
    HumanReviewValidation --> [*]: Reject

    Test --> HumanReviewCutover: test report PASS
    Test --> Validate: test report FAIL

    HumanReviewCutover --> Cutover: Approve
    HumanReviewCutover --> [*]: Reject

    Cutover --> Verify: kubectl rollout (new pods)
    Verify --> Done: health checks pass
    Verify --> Rollback: health checks fail / connection errors

    Rollback --> [*]: kubectl rollout undo
    Done --> [*]
```

Graph nodes map 1:1 to LangGraph `StateGraph` nodes; conditional edges are implemented as router functions reading `state.status` / `state.validation_result`.

### 6.1 Failure Handling & Retry Policy

Every phase that invokes an LLM (Bedrock) or an external tool adapter is wrapped by the same bounded-retry policy inside its LangGraph node — the state diagram above shows the happy path; this is the failure path underneath each of those nodes:

```mermaid
flowchart TD
    Call[Agent invokes LLM / Tool Adapter] --> Result{Success?}
    Result -->|Yes| Continue[Advance to next phase]
    Result -->|"No: exception, timeout,\nmalformed output, tool error"| Count{attempt < 3?}
    Count -->|Yes| Backoff["Increment retry_count\nexponential backoff"] --> Call
    Count -->|"No: 3 attempts failed"| Escalate["HumanReviewFailure interrupt\nerror + last attempt context surfaced"]
    Escalate --> Decision{Reviewer Decision}
    Decision -->|Retry| Reset[Reset retry_count = 0] --> Call
    Decision -->|Abort| Abort[Job marked ABORTED, audit logged]
```

- **Retry limit: 3 automatic attempts** per phase (Transform/Generate translation calls, CodeRefactor LLM calls, DataMigrate/SeaTunnel job errors, Test execution) before the graph stops looping and raises a `HumanReviewFailure` interrupt.
- `MigrationState.retry_count` (per-phase) is persisted at every checkpoint, so a resumed job does not reset its attempt count after a crash/restart.
- On `HumanReviewFailure`, the reviewer sees the captured error/exception and can **Retry** (resets `retry_count` to 0 and re-invokes the same phase) or **Abort** (job marked `ABORTED`, same as other reject paths).
- Applies uniformly to LLM-backed steps (Bedrock calls in Schema/Code/Planner Agents) and deterministic tool calls (SeaTunnel, checksum, kubectl) — only the definition of "failure" differs (LLM: malformed/low-confidence output or API error; tool: non-zero exit code or exception).
- The `Test --> Validate: test report FAIL` edge in §6 is a **business-logic** retry (validation legitimately didn't pass) — distinct from this **infrastructure/LLM-call** retry, which caps a test *run's own execution* failures (e.g. runner crash, timeout) at 3 attempts before escalating.

---

## 7. Shared State Schema

Single Pydantic model threaded through the entire graph and persisted at every checkpoint — this is what makes replay, audit, and mid-flight resumption possible.

```mermaid
classDiagram
    class MigrationState {
        +str job_id
        +DialectPair dialects
        +DiscoveryResult discovery
        +MigrationPlan plan
        +ApprovalRecord[] approvals
        +TranslationResult schema_translation
        +CodeRefactorResult code_refactor
        +DataMigrationResult data_migration
        +ValidationReport validation
        +TestReport test_report
        +DeploymentStatus deployment
        +str current_phase
        +str status
        +int retry_count
        +int max_retries = 3
    }
    class DialectPair {
        +str source
        +str target
    }
    class MigrationPlan {
        +int tables
        +int views
        +int procedures
        +int functions
        +int triggers
        +ObjectRisk[] risk_register
        +str[] manual_review_objects
    }
    class ApprovalRecord {
        +str phase
        +str decision
        +str reviewer
        +datetime timestamp
        +str comment
    }
    class ValidationReport {
        +ChecksumResult[] table_checksums
        +int mismatches
        +str overall_status
    }
    MigrationState --> DialectPair
    MigrationState --> MigrationPlan
    MigrationState --> ApprovalRecord
    MigrationState --> ValidationReport
```

---

## 8. Phase-by-Phase Sequence Diagrams

### 8.1 Discovery & Assessment

```mermaid
sequenceDiagram
    participant O as Orchestrator (LangGraph)
    participant AA as Assessment Agent
    participant SE as Schema Extractor / DDL Parser Adapter
    participant SDB as Source DB
    participant KB as Knowledge Base

    O->>AA: start(job_id, dialect_pair)
    AA->>SE: run(connection_config)
    SE->>SDB: execute per-dialect DDL export (e.g. pg_dump --schema-only, DBMS_METADATA.GET_DDL, mysqldump --no-data)
    SDB-->>SE: raw schema.sql
    SE->>SE: parse schema.sql with SQL/DDL parser (e.g. sqlglot) -> object catalog + dependency graph
    SE-->>AA: catalog + dependency graph
    AA->>KB: store discovery embeddings
    AA-->>O: DiscoveryResult
```

### 8.2 Schema & Logic Translation

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant SA as Schema Agent
    participant CS as CrackSQL Adapter
    participant Bedrock as AWS Bedrock (Nova Pro)
    participant KB as Knowledge Base

    O->>SA: translate(discovery, plan)
    SA->>KB: retrieve type-mapping & conversion rules
    KB-->>SA: relevant rules (RAG)
    SA->>CS: run(ddl, rules)
    CS->>CS: AST-based deterministic translation
    CS->>Bedrock: resolve ambiguous constructs (LLM)
    Bedrock-->>CS: suggested translation
    CS-->>SA: TranslationResult (DDL/SP/Trigger, confidence scores)
    SA-->>O: schema_translation
```

### 8.3 Data Migration

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant DA as Data Agent
    participant ST as SeaTunnel Adapter
    participant SDB as Source DB
    participant TDB as Target DB

    O->>DA: migrate_data(plan, translated_schema)
    DA->>ST: generate config (batch + CDC)
    ST->>SDB: bulk extract (historical)
    ST->>TDB: bulk load
    ST->>SDB: stream CDC (ongoing changes)
    ST->>TDB: apply CDC stream
    ST-->>DA: DataMigrationResult (rows moved, lag metrics)
    DA-->>O: data_migration
```

### 8.4 Application Code Refactoring

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant CA as Code Agent
    participant OR as OpenRewrite Adapter
    participant AI as Aider Adapter
    participant Repo as App Source Repo

    O->>CA: refactor(target_dialect, app_stack)
    alt Java/Spring backend
        CA->>OR: run(recipe: swap ORM dialect + JDBC driver)
        OR->>Repo: AST-based rewrite
        OR-->>CA: OpenRewriteResult (diff, files changed)
    else C++ / Python microservice
        CA->>AI: run(prompt: translate raw SQL / SQLAlchemy config)
        AI->>Repo: LLM-guided code edits
        AI-->>CA: AiderResult (diff, files changed)
    end
    CA-->>O: code_refactor
```

### 8.5 Validation & Reconciliation

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant VA as Validation Agent
    participant CK as Checksum Adapter
    participant SDB as Source DB
    participant TDB as Target DB

    O->>VA: validate(job_id)
    VA->>CK: run(batch_config)
    loop per table batch
        CK->>SDB: fetch rows
        CK->>TDB: fetch rows
        CK->>CK: hash (Pandas/PySpark) + compare
    end
    CK-->>VA: ValidationReport (mismatches, per-table status)
    VA-->>O: validation
    O->>O: route: PASS -> Test, FAIL -> retry DataMigrate
```

### 8.6 Cutover & Rollback

```mermaid
sequenceDiagram
    participant O as Orchestrator
    participant DG as Deployment Agent
    participant KC as kubectl Adapter
    participant K8s as EKS Cluster
    participant VA as Validation Agent

    O->>DG: cutover(job_id)
    DG->>KC: rollout new pods (new DB driver/endpoint)
    KC->>K8s: kubectl set env / update ConfigMap
    K8s-->>KC: new pods healthy
    KC-->>DG: DeploymentStatus(new pods live)
    DG->>K8s: terminate legacy pods
    DG-->>O: deployment=SUCCESS

    alt connection errors detected
        VA-->>O: post-cutover anomaly
        O->>DG: rollback(job_id)
        DG->>KC: kubectl rollout undo
        KC->>K8s: revert to legacy pods
        DG-->>O: deployment=ROLLED_BACK
    end
```

---

## 9. Human-in-the-Loop Approval Flow

```mermaid
flowchart TD
    Plan[Migration Plan Generated] --> Summary["Summary:\nTables 125, Views 42, Procedures 86,\nFunctions 53, Triggers 31\nAuto: 278  Review: 59  High-risk: 12"]
    Summary --> UI[Streamlit Review Screen]
    UI --> Decision{Reviewer Decision}
    Decision -->|Approve| Proceed[LangGraph resumes: Transform phase]
    Decision -->|Modify| Adjust[Planner Agent regenerates plan section]
    Decision -->|Reject| Abort[Job marked ABORTED, audit logged]
    Adjust --> Summary

    subgraph Additional Gates
        G1[Post-Validation Gate]
        G2[Pre-Cutover Gate]
    end
    Proceed --> G1 --> G2
```

Each gate persists an `ApprovalRecord` (reviewer, decision, timestamp, comment) into the metadata DB for full audit trail.

---

## 10. Data & Knowledge Stores

```mermaid
erDiagram
    MIGRATION_JOB ||--o{ APPROVAL_RECORD : has
    MIGRATION_JOB ||--o{ OBJECT_CATALOG_ENTRY : contains
    MIGRATION_JOB ||--o{ VALIDATION_RESULT : produces
    MIGRATION_JOB ||--o{ CHECKPOINT : "checkpointed by"
    OBJECT_CATALOG_ENTRY ||--o{ TRANSLATION_RESULT : "translated to"
    KNOWLEDGE_DOC ||--o{ KNOWLEDGE_EMBEDDING : "chunked into"

    MIGRATION_JOB {
        uuid id PK
        string source_dialect
        string target_dialect
        string status
        timestamp created_at
    }
    APPROVAL_RECORD {
        uuid id PK
        uuid job_id FK
        string phase
        string decision
        string reviewer
        timestamp decided_at
    }
    OBJECT_CATALOG_ENTRY {
        uuid id PK
        uuid job_id FK
        string object_type
        string object_name
        string risk_level
    }
    TRANSLATION_RESULT {
        uuid id PK
        uuid catalog_entry_id FK
        text source_ddl
        text target_ddl
        float confidence
    }
    VALIDATION_RESULT {
        uuid id PK
        uuid job_id FK
        string table_name
        string status
        string checksum_source
        string checksum_target
    }
    CHECKPOINT {
        uuid id PK
        uuid job_id FK
        string node_name
        jsonb state_snapshot
        timestamp created_at
    }
    KNOWLEDGE_DOC {
        uuid id PK
        string title
        string category
    }
    KNOWLEDGE_EMBEDDING {
        uuid id PK
        uuid doc_id FK
        vector embedding
        text chunk_text
    }
```

- **Platform Metadata DB** (Postgres): jobs, approvals, catalog, checkpoints — operational state.
- **PGVector Knowledge Base**: type-mapping rules, vendor syntax quirks, known incompatibilities, historical issues — embedded with Titan Embeddings, retrieved via RAG by Planner/Schema Agents.

---

## 11. Deployment Architecture

Terraform provisions cloud infrastructure; Kubernetes (EKS) runs the platform and the migrated application; both are treated as production-grade from day one per requirements.

```mermaid
flowchart TB
    subgraph AWSAccount["AWS Account"]
        subgraph VPCNet["VPC"]
            subgraph EKSCluster["EKS Cluster"]
                subgraph ns-platform["namespace: migration-platform"]
                    UIpod[Streamlit Pod]
                    APIpod[FastAPI Pod x N]
                    Orchpod[LangGraph Worker Pod x N]
                end
                subgraph ns-app["namespace: target-application"]
                    OldPods[App Pods - legacy DB config]
                    NewPods[App Pods - new DB config]
                end
                subgraph ns-observability["namespace: observability"]
                    PromPod[Prometheus]
                    GrafPod[Grafana]
                    LFPod[LangSmith]
                end
            end
            RDS_A[(RDS/Managed DB: Dialect A\nOracle, MySQL, or PostgreSQL)]
            RDS_B[(RDS/Managed DB: Dialect B\nOracle, MySQL, or PostgreSQL)]
            MetaPG[(RDS Postgres:\nPlatform Metadata + PGVector)]
        end
        Bedrock[AWS Bedrock]
        ECR[ECR: container images]
        S3[S3: Terraform state, artifacts, reports]
    end

    Terraform[Terraform Modules] -->|provisions| VPCNet
    Terraform -->|provisions| EKSCluster
    Terraform -->|provisions| RDS_A
    Terraform -->|provisions| RDS_B
    Terraform -->|provisions| MetaPG
    Terraform -->|state| S3

    APIpod --> Bedrock
    Orchpod --> Bedrock
    Orchpod --> MetaPG
    Orchpod --> RDS_A
    Orchpod --> RDS_B
    Orchpod -->|kubectl / helm| ns-app
    NewPods --> RDS_B
    OldPods --> RDS_A
    PromPod --> APIpod
    PromPod --> ns-app
    LFPod --> Orchpod
```

Dialect assignment to `RDS_A`/`RDS_B` is per-job, driven by the `DialectPair` in `MigrationState` — the same Terraform module (`rds-instance`) is parameterized by engine type rather than having fixed "source" and "target" modules.

- Terraform modules: `network`, `eks`, `rds-instance` (parameterized: oracle/mysql/postgres), `metadata-db`, `iam`.
- Helm charts per app under `infra/k8s/`; the Deployment Agent calls `kubectl`/`helm` scoped to `ns-app` only (least privilege — cannot touch `ns-platform`).

---

## 12. CI/CD Pipeline

```mermaid
flowchart LR
    Dev[Developer Push / PR] --> GH[GitHub Actions]
    GH --> Lint[Lint + Type Check]
    Lint --> Unit[Unit Tests]
    Unit --> Build[Build Container Images]
    Build --> Scan[Image Vulnerability Scan]
    Scan --> Push[Push to ECR]
    Push --> IntegrationEnv[Deploy to Staging Namespace]
    IntegrationEnv --> E2E[E2E Migration Test\n small sample DB]
    E2E --> Approval{Manual Approval Gate}
    Approval -->|Approve| Prod[Terraform Apply + Helm Upgrade: Prod]
    Approval -->|Reject| Stop[Pipeline Halted]
```

---

## 13. Observability

```mermaid
flowchart LR
    subgraph Traces
        Orchpod[LangGraph Agents] -->|spans per node/tool call| LangSmith
    end
    subgraph Metrics
        APIpod[FastAPI] -->|/metrics| Prometheus
        K8s[K8s cAdvisor/kube-state-metrics] --> Prometheus
        SeaTunnelJob[SeaTunnel Job Metrics] --> Prometheus
    end
    Prometheus --> Grafana
    LangSmith --> Grafana
    Grafana --> Dashboards["Dashboards:\nAgent latency & cost, Tool success rate,\nMigration throughput, Validation pass rate,\nPod health / rollout status"]
```

Every LLM call (Bedrock Nova Pro / Titan) is wrapped with a LangSmith trace capturing prompt, tokens, latency, and cost — enabling per-job cost attribution and prompt regression detection.

---

## 14. Security Considerations

- **Least privilege**: Deployment Agent's Kubernetes service account is scoped via RBAC to only the `target-application` namespace; it cannot modify `migration-platform` or `observability` namespaces.
- **Secrets management**: DB credentials and Bedrock IAM roles are never stored in state or logs — sourced from AWS Secrets Manager / IRSA (IAM Roles for Service Accounts), injected at runtime.
- **Input validation boundary**: FastAPI validates all job configuration (connection strings, dialect names) against an allow-list before any adapter executes — prevents injection into generated SQL/kubectl commands.
- **SQL/command injection**: CrackSQL and checksum adapters use parameterized queries; `kubectl`/`terraform` adapters build commands from typed config objects, never raw string interpolation.
- **Audit trail**: every approval, rejection, and rollback is immutably logged (`APPROVAL_RECORD`, checkpoint history) for compliance review.
- **Network isolation**: source and target DBs live in private subnets; only the orchestrator pods have security-group access.
- **LLM output as untrusted input**: LLM-suggested DDL/code diffs are never auto-applied — they pass through the human approval gate (or, at minimum, automated test/validation) before merge/execution.

---

## 15. Extensibility: Adding New Features

| To add... | Do this | Touch orchestrator? |
|---|---|---|
| New dialect (e.g. DB2, SQL Server) | Implement `dialects/<name>/` against `dialects/base.py` (type map, grammar hooks); immediately usable as both source and target since the contract is symmetric | No |
| New migration tool (replace SeaTunnel) | Implement `tool_adapters/<tool>_adapter/` against `BaseToolAdapter` | No |
| New agent (e.g. Performance-Tuning Agent) | Add module under `agents/`, register as a LangGraph node + edge in `orchestrator/graph.py` | Yes (one node + edges) |
| New approval gate | Add `HumanReview*` node + interrupt in the state graph | Yes (one node) |
| New observability signal | Add exporter in `observability/` and a Grafana dashboard JSON | No |

The rule of thumb: **agents change when workflow phases change; adapters change when tools change; dialects change when database vendors change** — these three concerns never overlap in the same file.

---

## 16. Open Questions / Future Work

- Multi-tenant isolation model if the platform serves multiple migration projects concurrently.
- Cost controls/guardrails for Bedrock usage during large-schema translation (batching, caching CrackSQL LLM fallbacks).
- Formal risk-scoring rubric for the Planner Agent's "High Risk Objects" classification (currently rule-based + LLM judgment — needs calibration against historical migrations).
- Disaster-recovery plan for the platform's own metadata DB (checkpoints) independent of the migration's source/target DBs.

---

## 17. Implementation Status

This section tracks which parts of the design above are real, working code vs. still a stub/placeholder, as of 2026-10-01. Kept up to date so this doc stays trustworthy rather than purely aspirational.

### ✅ Implemented

| Area | Notes |
|---|---|
| Orchestration (LangGraph `StateGraph`, Postgres checkpointer, bounded retry) | Full graph topology + pause/resume works; `orchestrator/graph.py`, `orchestrator/checkpointer.py`, `orchestrator/retry.py` |
| FastAPI gateway + Streamlit UI | Job create/status/review endpoints; review screens; DDL viewer; progress polling |
| Assessment Agent + `schema_extractor_adapter` | Real DDL export + sqlglot parse → object catalog + FK dependency graph, for Oracle/MySQL/PostgreSQL |
| Planner Agent (`risk.py` + `llm.py`) | Deterministic heuristic risk scoring + Bedrock Nova Pro refinement for medium/high objects, RAG-backed |
| Schema Agent + `cracksql_adapter` | Hybrid AST+LLM translation with confidence scores, idempotent DDL re-apply, schema/case/escape sanitization |
| Knowledge Base (ingestion + retrieval) | PGVector + Titan Embeddings v2, dialect-pair-aware retrieval, 21 seed documents |
| Data Agent + `seatunnel_adapter` | Bulk (batch) load only, FK-dependency-ordered table load, idempotent re-run (`DROP_DATA`) |
| Validation Agent + `checksum_adapter` | Row-count/checksum reconciliation, `ValidationReport`, Prometheus metrics |
| Human-in-the-loop gates | `HumanReviewPlan` and `HumanReviewValidation` are real interrupts with persisted `ApprovalRecord`s |
| Test phase | Generated/executed schema compatibility, referential integrity checks (FK orphan queries), and performance smoke tests (timed `COUNT(*)`) wired into graph with `Test → Done/Validate` routing per validation result |
| **Deployment Agent + `kubectl_adapter` + `terraform_adapter`** | Real rolling update, health-check gating, automatic `kubectl rollout undo` on pod/health/traffic failure; async subprocess wrappers with JSON output parsing |
| **Infra as code (Terraform)** | 5 modules (VPC, EKS, RDS, IAM/IRSA, outputs) + 330 lines of variables/locals/data sources; VPC 3-tier (public/private/database subnets), EKS 1.28 with 2 node groups (platform/app), RDS multi-AZ (PostgreSQL/MySQL/Oracle), IRSA for pods |
| **Kubernetes Helm charts** | `capstone-platform` (2 replicas, HPA 2-5, network policies, RBAC, PDB) and `capstone-app` (3 replicas, HPA 3-10, pod anti-affinity, network policies, RBAC, PDB) with liveness/readiness probes, resource limits, and rolling update strategy |
| CI | Lint (black/isort/flake8/mypy) + unit tests on push/PR (`.github/workflows/ci.yml`); unit tests for terraform_adapter, kubectl_adapter, deployment_agent workflows |
| Prometheus metrics definitions | `observability/metrics.py` – validation, retry, throughput, and deployment (rollout success/duration) metrics emitted |

### 🔮 Future Extension (designed, not yet built)

These are explicitly scoped in this document and in `plan.md`, but currently exist only as empty interfaces, `.gitkeep` placeholders, or no-op stub nodes that just advance `current_phase`:

| Area | Current state | What's missing |
|---|---|---|
| **CDC streaming** (Data Agent) | Bulk/batch load only | Streaming change-data-capture after initial bulk load |
| **Code Agent** (`openrewrite_adapter`, `aider_adapter`) | Empty `__init__.py` stubs; `CodeRefactor` graph node is a no-op passthrough | ORM/JDBC dialect swap (OpenRewrite) + LLM-guided raw-SQL/SQLAlchemy edits (Aider) |
| **LangSmith tracing** | `observability/langsmith/` empty | Per-call tracing (prompt/tokens/latency/cost) for every Bedrock call and tool invocation (currently Phase 4 only) |
| **Grafana dashboards** | `observability/grafana-dashboards/` empty; metrics already emitted to Prometheus | Dashboard JSON for agent latency/cost, tool success rate, pod health, deployment/rollout status |
| **Full CI/CD pipeline** | Lint + unit test only | Build images, vuln scan, push ECR, staging deploy, E2E sample migration test, manual gate, Terraform/Helm prod deploy |
| **Secrets management** (Secrets Manager/IRSA runtime injection) | Local dev uses `.env`; Terraform/Helm already provision IRSA roles + Secrets Manager secrets | Runtime secret injection via AWS Secrets Manager / IRSA in deployed containers (no plaintext credentials in env) |
| **Multi-tenant isolation**, **DR plan for metadata DB** | Not started | See [§16 Open Questions](#16-open-questions--future-work) |
| **Secrets management** (Secrets Manager/IRSA) | Local dev uses `.env` | Runtime secret injection via AWS Secrets Manager / IRSA, no plaintext credentials |
| **Multi-tenant isolation**, **DR plan for metadata DB** | Not started | See [§16 Open Questions](#16-open-questions--future-work) |

No stubbed area was judged not worth keeping — all map directly to a Capstone-required capability ([Capstone_Proposal.md](./Capstone_Proposal.md)), so each is retained here as a scoped future extension rather than removed.
