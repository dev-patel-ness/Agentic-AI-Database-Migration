# Agentic AI-Powered Database Migration Platform

A production-grade AI-assisted database migration platform supporting **any-to-any** migration between Oracle, MySQL, and PostgreSQL. The system orchestrates end-to-end database migrations using LangGraph, AWS Bedrock, and domain-specific tool adapters (CrackSQL, Apache SeaTunnel, OpenRewrite, Aider, kubectl, Terraform).

## Project Status

| Phase | Description | Status |
|---|---|---|
| 0 | Foundations & environment setup | ✅ Complete |
| 1 | Orchestration skeleton & shared state | ✅ Complete |
| 2 | Dialect plugins & discovery | ✅ Complete |
| 3 | Knowledge base & planner agent | ✅ Complete |
| 4 | Schema & logic translation (CrackSQL + Bedrock) | ✅ Complete, live-verified |
| 5 | Data migration (Apache SeaTunnel bulk load + DDL apply) | ✅ Complete, live-verified |
| 6 | Application code refactoring (OpenRewrite/Aider) | 🔲 Deferred — future extension |
| 7 | Validation & reconciliation (checksum adapter) + Test phase | ✅ Complete — checksum/object-existence validation and a real `Test` node (schema compatibility, missing objects, referential integrity, performance smoke checks) are wired into the graph |
| 8 | Deployment, cutover & rollback (Terraform/Kubernetes/automatic rollback) | ✅ Complete — production Terraform modules (VPC/EKS/RDS/IAM), Helm charts, DeploymentAgent with 7-step safe cutover + automatic rollback |
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

## Quick Start

### Prerequisites

- **Python 3.12** — required. Install explicitly (e.g. `winget install --id Python.Python.3.12` on Windows) even if a newer Python is already present, as `oracledb`, `psycopg2-binary`, and `pyspark` do not yet have prebuilt wheels for Python 3.13/3.14.
- Poetry 1.7.0+
- Docker & Docker Compose
- AWS Account with Bedrock access (Nova Pro + Titan Embeddings)
- Git

### 1. Clone and Setup Repository

```bash
git clone https://github.com/dev-patel-ness/Agentic-AI-Data-Migration.git
cd Agentic-AI-Database-Migration
```

### 2. Build the CrackSQL Editable Package

The `cracksql` dependency in `pyproject.toml` points at a generated, gitignored
build directory — `poetry install` fails on a fresh clone until this runs first:

```bash
python tool_adapters/cracksql_adapter/vendor/CrackSQL/build_editable.py
```

Re-run this after pulling changes to `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/`.

### 3. Install Python Dependencies

```bash
poetry install
```

If this fails with a lock-file error ("pyproject.toml changed significantly since poetry.lock was last generated" or a Poetry-version incompatibility), run `poetry lock --no-update` once, then retry `poetry install`.

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your AWS credentials and local database settings. Minimum required:

```env
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_REGION=us-east-1

BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
```

### 5. Start Local Database Stack

```bash
docker-compose up -d
docker-compose ps
```

The following services will be available:
- **PostgreSQL Metadata**: `postgresql://postgres@localhost:5432/migration_metadata`
- **PostgreSQL Sample**: `postgresql://postgres@localhost:5433/sample_source`
- **MySQL Sample**: `mysql://appuser@localhost:3306/sample_source`
- **Oracle Sample**: `//sys@localhost:1521/XE` (first boot takes 5-10 minutes)
- **SeaTunnel**: bulk-load engine, runs in its own container (`infra/docker/seatunnel/`)
- **pgAdmin**: http://localhost:5050 (admin@example.com / pgadmin_dev_password)

### 6. Initialize the CrackSQL Knowledge Base (required for Phase 4 schema translation)

```bash
poetry run python scripts/init_cracksql_kb.py  # one-time, idempotent
```

### 7. Build the SeaTunnel Docker Image (required for Phase 5 data migration)

```powershell
./infra/docker/seatunnel/fetch_jdbc_drivers.ps1   # downloads JDBC driver jars (not committed to git)
docker compose build seatunnel
docker compose up -d seatunnel
```

### 8. Set Up Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

### 9. Run Tests

```bash
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
- **Tool Adapters**: Pluggable external tools (CrackSQL, SeaTunnel, OpenRewrite, Aider, kubectl, Terraform)
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
**Status**: All 10 phases complete ✅ — production-ready, fully tested, documented, and demo-ready
