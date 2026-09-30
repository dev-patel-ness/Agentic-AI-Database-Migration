# Enterprise AI Engineering Capstone Assessment

## Capstone Assessment Objective

As the final assessment of the 8-week AI Engineer Bootcamp, participants will select one of five capstone topics and develop a production-oriented enterprise AI solution. Each option demonstrates skills including Generative AI, RAG, vector databases, FastAPI, AWS, LangChain, LangGraph, multi-agent systems, DevOps, observability, LLMOps, and enterprise architecture.

---

## Capstone Option: Agentic AI–Powered Database Migration Assistant

### Business Scenario

Enterprises frequently migrate databases to reduce licensing costs, improve scalability, adopt cloud solutions, enhance performance, or modernize infrastructure. Database migration is often manual and complex, involving analysis of schemas, data types, stored procedures, queries, indexes, constraints, and application dependencies. Vendor differences introduce compatibility issues, data loss risks, and significant testing requirements.

### Capstone Objective

Develop an Agentic AI–Powered Database Migration Platform that:
- Analyzes source databases and understands their schema and constructs
- Generates corresponding target database implementations
- Validates migrations and assists with remediation

**Supported Migrations (examples):**
- Oracle → PostgreSQL
- SQL Server → PostgreSQL
- MySQL → PostgreSQL

### Key Responsibilities

#### 1. Database Discovery
Identify and catalog all objects in the source database.

#### 2. Schema Analysis
Understand source schema and identify constructs requiring transformation.

**Type Mapping Example:**
| Source (Oracle) | Target (PostgreSQL) |
|---|---|
| NUMBER | NUMERIC |
| VARCHAR2 | VARCHAR |
| SEQUENCE | SEQUENCE / IDENTITY |

#### 3. SQL Conversion
Convert database-specific SQL and procedural code to target syntax:
- SQL queries
- Stored procedures, functions, triggers
- Views and sequences

#### 4. Data Migration
Execute data migration with:
- Data extraction, transformation, and type conversion
- Batch and incremental processing for large tables
- Error handling and migration checkpoints

#### 5. Validation
Verify functional and structural equivalence by checking:
- Row counts and null counts
- Primary/foreign keys and constraints
- Data types and quality
- Aggregated values and sample records

**Validation Example:**
```
Customer Records:   1,250,000 → 1,250,000 ✓
Order Records:      4,800,000 → 4,800,000 ✓
Status: PASS
```

#### 6. Testing
Generate and execute migration test cases to identify:
- Schema and SQL compatibility issues
- Data conversion errors
- Referential integrity problems
- Performance issues
- Missing objects

Produce a structured migration test report.

#### 7. Migration Planning
Coordinate the complete migration process by determining:
- Migration sequence and dependencies
- Object priorities and risk levels
- Estimated effort and validation strategy
- Objects requiring manual intervention

#### 8. Human Approval
Implement Human-in-the-Loop approval before high-impact operations.

**Example Approval Flow:**
```
Migration Plan
──────────────
Tables:                    125
Views:                      42
Procedures:                 86
Functions:                  53
Triggers:                   31

Automatically Migratable:  278
Requires Review:            59
High Risk Objects:          12

         ↓

   HUMAN REVIEW

   [Approve] [Reject] [Modify]
```

### Expected End-to-End Workflow

**Discover → Analyse → Plan → Transform → Generate → Validate → Test → Approve → Migrate → Verify**

### Core Demonstration Areas

- Tool calling and multi-agent orchestration
- Structured outputs and RAG-based retrieval
- LLM reasoning and deterministic validation
- Human-in-the-loop workflows and error handling
- Automated code generation, testing, and migration planning
- Migration reporting and observability

### Suggested Knowledge Base

Support RAG implementation with:
- Source-to-target data type mappings and SQL conversion rules
- Vendor-specific syntax and migration best practices
- Known incompatibilities and transformation rules
- Historical migration issues and performance recommendations
- Validation rules and strategies

---

## Suggested Technology Stack

### AI & Agentic AI
- Python
- AWS Bedrock
- LangChain / LangGraph
- Prompt Engineering & RAG

### Databases
**Source Options:** Oracle, SQL Server, MySQL  
**Target Options:** PostgreSQL, AWS Aurora PostgreSQL

### Application
- FastAPI
- Streamlit (UI)
- PostgreSQL / PGVector

### DevOps
- Docker, Kubernetes
- Terraform, GitHub Actions

### Observability & Monitoring
- LangSmith
- Prometheus, Grafana

---

## Expected Deliverables

### Core Components
- Source database discovery module
- Target database mapping engine
- Agentic migration workflow
- Schema and SQL/procedure conversion engines
- Data migration pipeline
- Automated validation and testing frameworks
- Human approval workflow
- RAG-based migration knowledge base

### Outputs & Documentation
- Migration risk and execution reports
- FastAPI APIs and architecture diagram
- Source code repository
- Docker/Kubernetes deployment configurations
- CI/CD pipeline
- Observability dashboard
- Final demonstration video

### Evaluation
- Working Database Migration Assistant
- End-to-end workflow implementation
- Production-ready solution quality
