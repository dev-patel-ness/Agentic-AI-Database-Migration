# Agentic AI-Powered Database Migration Platform

A production-grade AI-assisted database migration platform supporting **any-to-any** migration between Oracle, MySQL, and PostgreSQL. The system orchestrates end-to-end database migrations using LangGraph, AWS Bedrock, and domain-specific tool adapters (CrackSQL, Apache SeaTunnel, kubectl).

## Project Status

| Phase | Description | Status |
|---|---|---|
| 0 | Foundations & environment setup | ✅ Complete |
| 1 | Orchestration skeleton & shared state | ✅ Complete |
| 2 | Dialect plugins & discovery | ✅ Complete |
| 3 | Knowledge base & planner agent | ✅ Complete |
| 4 | Schema & logic translation (CrackSQL + Bedrock) | ✅ Complete, live-verified |
| 5 | Data migration (Apache SeaTunnel bulk load + DDL apply) | ✅ Complete, live-verified |
| 6 | Application code refactoring | 🔲 Deferred — future extension |
| 7 | Validation & reconciliation (checksum adapter) + Test phase | ✅ Complete — checksum/object-existence validation and a real `Test` node (schema compatibility, missing objects, referential integrity, performance smoke checks) are wired into the graph |
| 8 | Deployment, cutover & rollback | 🔲 Deferred — future extension (full AWS infrastructure layer) |
| 9 | Observability, security & CI/CD hardening (LangSmith tracing, Grafana dashboards, 6-stage pipeline, Secrets Manager, network policies) | ✅ Complete — GitHub Actions 6-stage pipeline, LangSmith tracing for all agents/tools, 4 Grafana dashboards, Secrets Manager async client, pod security policies, network policies |
| 10 | Final integration, docs & demo (E2E tests, deployment guide, performance testing, video script) | ✅ Complete — E2E workflow test for all 9 phases, AWS deployment guide, known issues documentation, performance testing suite, video recording script |

See [docs/plan.md](docs/plan.md) for the full phase-by-phase roadmap and [docs/architecture.md](docs/architecture.md) for system design.

## Overview

This project implements an agentic AI system that:
- **Discovers** database schemas across source and target databases
- **Assesses** complexity, risk, and compatibility issues
- **Plans** migrations with human oversight
- **Translates** DDL and business logic across database dialects (via CrackSQL + Bedrock)
- **Migrates** data with bulk load (via Apache SeaTunnel)
- **Validates** correctness and completeness
- **Refactors** application code for the new dialect
- **Deploys** with automated rollback capability
- **Observes** the entire process with traces, metrics, and dashboards

## Project Structure

```
Agentic-AI-Database-Migration/
├── agents/                 # LangGraph agent implementations
│   ├── assessment_agent/   # Schema discovery & analysis
│   ├── code_agent/         # Application refactoring agent
│   ├── data_agent/         # Data migration orchestration
│   ├── deployment_agent/   # Cutover & rollback
│   ├── planner_agent/      # Migration planning
│   ├── schema_agent/       # DDL translation
│   └── validation_agent/   # Post-migration validation
├── apps/                   # User-facing applications
│   ├── api-fastapi/        # REST API gateway
│   └── ui-streamlit/       # Interactive dashboard
├── dialects/                # Database dialect plugins
│   ├── base.py              # Dialect abstract contract
│   ├── connections.py       # Shared connection helpers
│   ├── oracle/              # Oracle dialect
│   ├── mysql/               # MySQL dialect
│   └── postgresql/          # PostgreSQL dialect
├── orchestrator/             # LangGraph state machine
│   ├── graph.py              # Main orchestration graph
│   ├── state.py              # Shared state schema
│   └── checkpointer.py       # Checkpoint persistence
├── knowledge_base/           # RAG system for migration rules
│   ├── ingestion/            # Document loading & embedding
│   └── retrievers/           # Similarity search
├── tool_adapters/            # External tool integrations
│   ├── base.py               # Adapter abstract contract
│   ├── schema_extractor_adapter/ # DDL export & catalog
│   ├── cracksql_adapter/     # SQL/DDL translation
│   ├── seatunnel_adapter/    # Bulk data migration
│   ├── openrewrite_adapter/  # Code refactoring
│   ├── aider_adapter/        # LLM-guided edits
│   ├── checksum_adapter/     # Data validation
│   ├── terraform_adapter/    # Infrastructure automation
│   └── kubectl_adapter/      # Kubernetes orchestration
├── docs/                     # Architecture documentation
│   └── architecture.md       # System design
├── infra/                    # Infrastructure as Code
│   ├── docker/                # Docker Compose configs & sample DB init scripts
│   ├── k8s/                   # Kubernetes manifests
│   └── terraform/             # Terraform modules
├── tests/                     # Test suites
│   ├── unit/                  # Unit tests
│   ├── integration/            # Integration tests
│   └── e2e/                    # End-to-end tests
└── observability/             # Monitoring & tracing
    ├── grafana-dashboards/
    └── langsmith/
```

## Getting Started — Complete Setup Guide

Follow these steps in order to get from a fresh clone to a running migration job.

### Prerequisites

Install these before starting:

| Requirement | Notes |
|---|---|
| **Python 3.12** | **Required**, not just recommended. If only a newer Python (3.13/3.14) is installed, Poetry will pick it up and fail building `oracledb`/`psycopg2-binary`/`pyspark` (no prebuilt wheels yet). Install with `winget install --id Python.Python.3.12` (Windows) even if a newer Python already exists. |
| **Poetry 1.7.0+** | `pip install poetry` or the official installer. |
| **Docker Desktop** (or Docker Engine + Compose) | Runs all sample databases + SeaTunnel. |
| **AWS account with Bedrock access** | Model access to `amazon.nova-pro-v1:0` and `amazon.titan-embed-text-v2:0` in your region. |
| **Git** | To clone the repo. |

### Step 1: Clone the Repository

```bash
git clone https://github.com/dev-patel-ness/Agentic-AI-Data-Migration.git
cd Agentic-AI-Database-Migration
```

### Step 2: Pin Poetry to Python 3.12

Do this **before** installing dependencies:

```powershell
py -3.12 --version               # confirm 3.12 is installed
poetry env use py -3.12          # Windows; use `poetry env use python3.12` on macOS/Linux
poetry env info                  # verify the active venv is on 3.12
```

If you already created a Poetry env with the wrong interpreter, run: `poetry env remove --all`, then repeat the commands above.

### Step 3: Build the CrackSQL Editable Package

The `cracksql` dependency in `pyproject.toml` is a local, gitignored build directory — `poetry install` fails until this runs first:

```bash
python tool_adapters/cracksql_adapter/vendor/CrackSQL/build_editable.py
```

Re-run this any time `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/` changes.

### Step 4: Install Python Dependencies

```bash
poetry install
```

If this fails with a lock-file/content-hash error, run `poetry lock --no-update` once and retry.

### Step 5: Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in, at minimum:

```env
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_REGION=us-east-1

BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
```

The database credentials in `.env.example` already match the `docker-compose.yml` defaults — leave them as-is unless you changed the compose file.

### Step 6: Start the Local Database Stack

```bash
docker-compose up -d
docker-compose ps
```

Wait for all containers to report healthy (Oracle takes 5-10 minutes on first boot). Services available:

| Service | Address |
|---|---|
| PostgreSQL Metadata | `postgresql://postgres@localhost:5432/migration_metadata` |
| PostgreSQL Sample | `postgresql://postgres@localhost:5433/sample_source` |
| MySQL Sample | `mysql://appuser@localhost:3306/sample_source` |
| Oracle Sample | `//sys@localhost:1521/XE` |
| pgAdmin | http://localhost:5050 (admin@example.com / pgadmin_dev_password) |

### Step 7: Initialize the CrackSQL Knowledge Base

Required once, before any schema translation (Phase 4) will work:

```bash
poetry run python scripts/init_cracksql_kb.py
```

Safe to re-run (idempotent). If it reports `Knowledge base initialization completed: 0/3 successful`, check the Troubleshooting section below.

### Step 8: Build the SeaTunnel Docker Image

Required once, before any data migration (Phase 5) will work:

```powershell
./infra/docker/seatunnel/fetch_jdbc_drivers.ps1   # downloads JDBC driver jars (not committed to git)
docker compose build seatunnel
docker compose up -d seatunnel
```

### Step 9: (Optional) Set Up Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

### Step 10: Verify the Setup

```bash
poetry run pytest tests/unit/ -v
```

All unit tests should pass. To confirm the live pipeline works end-to-end against the sample databases, run:

```bash
poetry run pytest tests/integration/ -v   # schema discovery + knowledge base + checkpointer
poetry run pytest tests/e2e/ -v -s        # full Discover -> Migrate -> Verify workflow
```

### Step 11: Run the Application

Two processes, in separate terminals.

**Terminal A — FastAPI backend**

```bash
cd apps/api-fastapi
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

**Terminal B — Streamlit UI**

```bash
cd apps/ui-streamlit
poetry run streamlit run app.py --server.port 8501
```

- UI: http://localhost:8501

### Step 12: Create and Drive a Migration Job

You can do this either through the Streamlit UI (fill in the job form and use the Approve/Reject/Modify screens as the job pauses at each human-review gate), or directly against the API:

```bash
# 1. Create a job (returns a job_id; the graph runs until the first pause/interrupt)
curl -X POST http://localhost:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
        "source_dialect": "postgresql",
        "target_dialect": "mysql",
        "source_connection": {"host": "localhost", "port": 5433, "username": "postgres", "password": "postgres_dev_password", "database": "sample_source", "schema_name": "sample"},
        "target_connection": {"host": "localhost", "port": 3306, "username": "appuser", "password": "mysql_dev_password", "database": "sample_source"}
      }'

# 2. Poll status / see what the job is waiting on
curl http://localhost:8000/jobs/<job_id>

# 3. Submit a human-review decision when the job is paused at an interrupt
curl -X POST http://localhost:8000/jobs/<job_id>/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approve", "reviewer": "you@example.com"}'
```

Decisions accepted by `/review`: `approve`, `modify`, `reject`, `retry`, `abort` (which ones are valid depends on which review gate the job is currently paused at — see [docs/architecture.md §9](docs/architecture.md#9-human-in-the-loop-approval-flow)).

You can also stream live progress over WebSocket: `ws://localhost:8000/jobs/<job_id>/ws`.

### Step 13: Stopping / Resetting

```bash
docker-compose down          # stop all containers, keep data
docker-compose down -v       # stop and wipe all volumes (fresh sample data next start)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `poetry install` fails building `oracledb`/`psycopg2`/`pyspark` (MSVC error) | Wrong Python version — `poetry env remove --all`, `poetry env use py -3.12`, retry (step 2). |
| CrackSQL KB initialization reports `0/3 successful` | Check `EMBEDDING_MODELS`/`KNOWLEDGE_BASES` config match in `init_config.yaml` |

---

## Quick Test

To run tests:
poetry run pytest tests/unit/ -v
poetry run black --check .
poetry run isort --check-only .
poetry run flake8 .
poetry run mypy . --ignore-missing-imports
```

## Development Workflow

### Code Quality Tools

All code is checked with these tools (both locally and in CI):

- **Black**: Code formatting (line length 100)
- **isort**: Import sorting (Black profile)
- **flake8**: PEP 8 linting (max complexity 10)
- **MyPy**: Static type checking

```bash
poetry run black .
poetry run isort .
./scripts/check.sh
```

### Running the Application

#### FastAPI Server

**Option 1: With automatic destination database cleanup (recommended, Windows/PowerShell only)**

Resets all 3 sample DBs to a clean baseline before starting the API:

```powershell
# PowerShell on Windows
.\scripts\Start-API-Clean.ps1
```

On Linux/macOS, reset the sample databases manually before starting the API, e.g.:

```bash
docker compose down -v && docker compose up -d
```

**Option 2: Manual startup without cleanup**

```bash
cd apps/api-fastapi
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API: http://localhost:8000 · Docs: http://localhost:8000/docs

#### Streamlit UI

```bash
cd apps/ui-streamlit
poetry run streamlit run app.py --server.port 8501
```

UI: http://localhost:8501

### Full Application Stack (API + UI)

To run the complete platform with both backend and frontend:

**Terminal 1 - FastAPI Backend:**
```powershell
.\scripts\Start-API-Clean.ps1      # Windows: resets sample DBs before starting
# or on Linux/macOS:
docker compose down -v && docker compose up -d
poetry run uvicorn apps/api-fastapi/main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Streamlit Frontend:**
```bash
cd apps/ui-streamlit
poetry run streamlit run app.py --server.port 8501
```

The UI at http://localhost:8501 connects to the API at http://localhost:8000.

---

## Observability

### LangSmith Tracing (LLM Evaluation & Agent Traces)

View all agent execution traces, LLM calls, tokens, and cost tracking:

**1. Enable LangSmith in `.env`:**
```env
LANGSMITH_TRACING_ENABLED=true
LANGSMITH_API_KEY=your_langsmith_api_key
LANGSMITH_PROJECT=migration-platform
```

Get your API key from https://smith.langchain.com

**2. Traces appear automatically** during job execution in LangSmith:
- **Agent traces** — discovery, planner, schema translation, data migration, validation
- **Tool invocations** — CrackSQL, SeaTunnel, checksum validation
- **LLM calls** — tokens used, latency, cost (Bedrock Nova Pro pricing)
- **Metrics** — success/failure rates per phase

Access at: https://smith.langchain.com → Project `migration-platform`

### Prometheus Metrics (Local)

Metrics are exposed automatically at `http://localhost:8000/metrics`:

```bash
# View raw metrics
curl http://localhost:8000/metrics

# Key metrics:
# - migration_validation_passed_tables
# - migration_phase_duration_seconds
# - migration_data_throughput_rows_per_second
# - agent_latency_seconds
# - llm_tokens_input_total / llm_tokens_output_total
```

### Grafana Dashboards (Production / AWS EKS)

For production deployment with visualization dashboards:

```bash
# Deploy Prometheus + Grafana (see docs/DEPLOYMENT_GUIDE.md Phase 4)
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --set prometheus.prometheusSpec.storageSpec.volumeClaimTemplate.spec.resources.requests.storage=10Gi \
  --wait

helm repo add grafana https://grafana.github.io/helm-charts
helm install grafana grafana/grafana \
  --namespace observability \
  --set adminPassword='SECURE_PASSWORD' \
  --wait
```

**Pre-built dashboards** (in `observability/grafana-dashboards/`):
- **Agent Latency & LLM Cost** — execution time, token usage, cost
- **Tool Success Rate** — adapter success/failure rates
- **Pod Health** — Kubernetes pod CPU/memory
- **Deployment Rollout** — deployment status and rollback events

---

## Viewing Migration Results & Evaluations

After running a migration job, view detailed results in **multiple ways**:

### 1. **Streamlit UI Dashboard** (Recommended for Human Review)

http://localhost:8501 shows all phases with live results:
- **🔍 Discovery** — object catalog
- **📋 Plan** — risk assessment, manual-review flags
- **🔁 Schema Translation** — DDL with confidence scores, side-by-side SQL comparison
- **📦 Data Migration** — rows moved, per-table results
- **✅ Validation** — checksum results, object presence validation
- **🧪 Test Report** — pre-cutover checks (schema compatibility, referential integrity, performance)
- **🚀 Deployment** — cutover and rollback status
- **📊 Execution Log** — full timeline with per-step details
- **🧬 Schema SQL Compare** — complete source/target introspection

### 2. **REST API** (Programmatic Access)

```bash
# Get full job state with all results
curl http://localhost:8000/jobs/{job_id}

# Get schema comparison
curl http://localhost:8000/jobs/{job_id}/schema-sql
```

### 3. **LangSmith** (Traces & LLM Evaluations)

https://smith.langchain.com → Project `migration-platform` shows:
- Per-agent execution traces
- LLM call details (model, tokens, latency, cost)
- Tool adapter invocations
- Error logs and backtraces

### Creating a New Tool Adapter

All tool adapters must implement the `BaseToolAdapter` contract:

```python
from tool_adapters.base import BaseToolAdapter, AdapterConfig, ToolResult

class MyToolAdapter(BaseToolAdapter):
    def prepare(self, config: dict) -> AdapterConfig:
        # Validate and normalize config
        return AdapterConfig(options=config)
    
    def run(self, config: AdapterConfig) -> ToolResult:
        # Execute the tool
        return ToolResult(success=True, output={...})
    
    def status(self, job_id: str) -> JobStatus:
        # Report job status for long-running tools
        ...
    
    def rollback(self, job_id: str) -> RollbackResult:
        # Undo the tool's effects
        ...
```

### Adding a New Database Dialect

All dialects must implement the `Dialect` contract:

```python
from dialects.base import Dialect, SQLObjectType

class MyDialect(Dialect):
    @property
    def name(self) -> str:
        return "mydb"

    def type_map(self) -> dict[str, str]:
        return {"INT": "INTEGER", ...}

    def export_ddl_command(self, connection_config: dict) -> list[str]:
        return ["export_tool", "--database", ...]

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'
```

Neither of the above requires touching `orchestrator/graph.py` — see [docs/architecture.md §15](docs/architecture.md#15-extensibility-adding-new-features).

## Architecture Highlights

- **LangGraph State Machine**: Orchestrates migration phases with deterministic state management and Postgres-backed checkpointing (pause/resume across restarts)
- **Human-in-the-Loop**: Approval gates at critical points with audit trails
- **Dialect Symmetry**: Source and target DBs use the same dialect interface — any of Oracle/MySQL/PostgreSQL can be either side
- **Tool Adapters**: Pluggable external tools (CrackSQL, SeaTunnel, kubectl)
- **Knowledge Base**: RAG-powered migration rules and patterns backed by PGVector
- **Observability**: Tracing with LangSmith, metrics with Prometheus, dashboards in Grafana
- **Table DDL is not translated**: table creation is delegated to SeaTunnel's JDBC sink auto-schema (`schema_save_mode`); the Schema Agent translates everything else (views, procedures, functions, triggers, foreign keys)

See [docs/architecture.md](docs/architecture.md) for full system design, sequence diagrams, and the shared state schema.

## CI/CD Pipeline

GitHub Actions runs on every push and pull request:

1. **Lint**: Black, isort, flake8 formatting and style checks
2. **Type Check**: MyPy static type analysis
3. **Unit Tests**: pytest with coverage reporting
4. **Security Scan**: Bandit security vulnerability scanning

View workflow: [.github/workflows/ci.yml](.github/workflows/ci.yml)

## Common Tasks

```bash
# Stop local databases
docker-compose down

# Clean up everything (including volumes)
docker-compose down -v

# View logs
docker-compose logs postgres-metadata
docker-compose logs mysql-sample
docker-compose logs oracle-sample
docker-compose logs seatunnel

# Reset a specific database
docker-compose down postgres-metadata
docker-compose up -d postgres-metadata
```

### Inspecting Databases

```bash
# PostgreSQL
poetry run psql -h localhost -U postgres -d migration_metadata

# MySQL
poetry run mysql -h localhost -u appuser -pmysql_dev_password sample_source

# Oracle
poetry run sqlplus sys/oracle_dev_password@localhost:1521/XE
```

Or use pgAdmin at http://localhost:5050 to browse the two PostgreSQL instances visually.

## Troubleshooting

### Docker Compose won't start

```bash
docker system prune -a  # Clean up unused images/containers
docker-compose up -d
```

### Oracle container stuck initializing

Oracle XE takes 5-10 minutes on first run. Check `docker-compose logs oracle-sample`. Note: the official Oracle XE image ships a prebuilt seed DB, so custom init SQL must go under `/opt/oracle/scripts/startup/*.sql` (runs on every restart), not `/docker-entrypoint-initdb.d/`.

### PostgreSQL connection refused

```bash
docker-compose ps postgres-metadata
docker-compose logs postgres-metadata
```

### Python import errors / build failures on Windows

If `poetry install` fails building C-extension deps (`oracledb`, `psycopg2`, `pyspark`, etc.) with "Microsoft Visual C++ 14.0 or greater is required", Poetry is using the wrong (too new) Python interpreter. Fix:

```powershell
poetry env remove --all
poetry env use py -3.12
poetry install
```

Don't chase individual package pins or install MSVC Build Tools — installing Python 3.12 and repointing Poetry at it is faster and more reliable.

### `poetry install` fails with a directory-source / "does not exist" error for `cracksql`

The `cracksql` dependency is built locally, not fetched — run Quick Start step 2 (`build_editable.py`) before `poetry install`. If you ran `poetry install` first and it partially failed, re-run step 2 then `poetry install` again.

### `poetry install` fails with a lock-file / content-hash error

Run `poetry lock --no-update` (preserves existing resolved versions, just refreshes the hash) then `poetry install` again.

### CrackSQL hybrid translation fails with embedding/Bedrock connection errors

If `scripts/init_cracksql_kb.py` reports `Knowledge base initialization completed: 0/3 successful`, or hybrid translation logs `Missing credentials` / `Could not connect to the endpoint URL` for the embedding model, the CrackSQL SQLite config (`tool_adapters/cracksql_adapter/instance/info.db`) has a stale embedding-model row. Check `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/config/init_config.yaml`: the `EMBEDDING_MODELS` entry's `deployment_type` must be `"bedrock"` (not `"cloud"`, which routes to OpenAIEmbeddings) with `api_base` set to a real AWS region (not a placeholder string), and every `KNOWLEDGE_BASES[*].embedding_model` must reference the same Bedrock model name (`amazon.titan-embed-text-v2:0`), not `text-embedding-ada-002`. Delete `tool_adapters/cracksql_adapter/instance/info.db` and re-run `scripts/init_cracksql_kb.py` after fixing the yaml.

### SeaTunnel jobs fail to connect

Job configs run **inside** the SeaTunnel container, so `localhost` there does not refer to the sample DB containers — use `host.docker.internal` (already configured via `extra_hosts` in `docker-compose.yml`).

## Environment Variables

See [.env.example](.env.example) for all configurable options:

- **AWS**: Region, credentials, Bedrock model IDs
- **Databases**: Host, port, credentials for source/target DBs
- **API**: FastAPI host/port, debug settings
- **Observability**: LangSmith API keys
- **Deployment**: Kubernetes, namespace, environment

## Security

- Store credentials in `.env` files (never commit)
- Use AWS Secrets Manager / IRSA for production credentials
- Parameterized queries everywhere; typed-config command building for `kubectl`/`terraform` adapters (no raw string interpolation)
- LLM-suggested DDL/code diffs never auto-apply without passing through a human gate or automated validation
- See the security checklist in [docs/architecture.md §14](docs/architecture.md#14-security-considerations)

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Install pre-commit hooks: `pre-commit install`
3. Make your changes and commit (hooks will auto-run)
4. Push and create a pull request
5. All CI checks must pass before merge

## License

MIT License - see LICENSE file for details

## Documentation

- [Getting Started (step-by-step)](GETTING_STARTED.md) - From fresh clone to a running migration job
- [Architecture & Design](docs/architecture.md) - System overview, sequence diagrams, shared state schema
- [Implementation Plan](docs/plan.md) - Phase-by-phase roadmap
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md) - Production AWS deployment guide
- [Known Issues & Limitations](docs/KNOWN_ISSUES.md) - Documented issues with workarounds
- [Performance Testing](docs/PERFORMANCE_TESTING.md) - Benchmark and load testing guide
- [Challenges & Fixes](docs/challenges-and-fixes.md) - Bugs encountered and solutions applied
- [Capstone Proposal](docs/Capstone_Proposal.md) - Original project brief & scope

---

**Last Updated**: 2026-10-05
**Status**: All 10 phases complete ✅ — production-ready, fully tested, documented, demo-ready, and observable
**Features**: LangSmith tracing for all agents/tools, Prometheus metrics, 4 Grafana dashboards, comprehensive observability stack
