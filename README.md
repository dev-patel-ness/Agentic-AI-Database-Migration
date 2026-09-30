# Agentic AI-Powered Database Migration Platform

A production-grade AI-assisted database migration platform supporting Oracle, MySQL, and PostgreSQL. This system orchestrates end-to-end database migrations using LangGraph, Bedrock AI, and domain-specific tool adapters.

## Overview

This project implements an agentic AI system that:
- **Discovers** database schemas across source and target databases
- **Assesses** complexity, risk, and compatibility issues
- **Plans** migrations with human oversight
- **Translates** DDL and business logic across database dialects
- **Migrates** data with CDC support
- **Validates** correctness and completeness
- **Tests** migrated applications
- **Deploys** with automated rollback capability
- **Observes** the entire process with traces, metrics, and dashboards

## Project Structure

```
Agentic-AI-Data-Migration/
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
├── dialects/               # Database dialect plugins
│   ├── base.py            # Dialect abstract contract
│   ├── oracle/            # Oracle dialect
│   ├── mysql/             # MySQL dialect
│   └── postgresql/        # PostgreSQL dialect
├── orchestrator/           # LangGraph state machine
│   ├── graph.py           # Main orchestration graph
│   ├── state.py           # Shared state schema
│   └── checkpointer.py    # Checkpoint persistence
├── knowledge_base/         # RAG system for migration rules
│   ├── ingestion/         # Document loading & embedding
│   └── retrievers/        # Similarity search
├── tool_adapters/          # External tool integrations
│   ├── base.py            # Adapter abstract contract
│   ├── cracksql_adapter/  # SQL translation
│   ├── openrewrite_adapter/ # Code refactoring
│   ├── aider_adapter/     # LLM-guided edits
│   ├── seatunnel_adapter/ # Data migration engine
│   ├── terraform_adapter/ # Infrastructure automation
│   ├── kubectl_adapter/   # Kubernetes orchestration
│   └── ...
├── docs/                   # Architecture & decision records
│   ├── architecture.md    # System design
│   └── adr/              # Architecture Decision Records
├── infra/                  # Infrastructure as Code
│   ├── docker/            # Docker Compose configs
│   ├── kubernetes/        # K8s manifests
│   └── terraform/         # Terraform modules
├── tests/                  # Test suites
│   ├── unit/             # Unit tests
│   ├── integration/       # Integration tests
│   └── e2e/              # End-to-end tests
└── observability/          # Monitoring & tracing
    ├── grafana-dashboards/
    └── langsmith/
```

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (or pip)
- Docker & Docker Compose
- AWS Account with Bedrock access
- Git

### 1. Clone and Setup Repository

```bash
git clone https://github.com/your-org/Agentic-AI-Data-Migration.git
cd Agentic-AI-Data-Migration
```

### 2. Install Python Dependencies

```bash
# Using Poetry
poetry install

# Or using pip
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy the example env file
cp .env.example .env

# Edit .env with your AWS credentials and local database settings
# Required AWS credentials:
#   - AWS_ACCESS_KEY_ID
#   - AWS_SECRET_ACCESS_KEY
#   - AWS_REGION
#   - BEDROCK_MODEL_ID (default: amazon.nova-pro-v1:0)
```

### 4. Start Local Database Stack

```bash
# Start all local databases (PostgreSQL, MySQL, Oracle)
docker-compose up -d

# Verify services are running
docker-compose ps

# Check database connectivity
docker-compose exec postgres-metadata psql -U postgres -d migration_metadata -c "SELECT version();"
```

The following services will be available:
- **PostgreSQL Metadata**: `postgresql://postgres@localhost:5432/migration_metadata`
- **PostgreSQL Sample**: `postgresql://postgres@localhost:5433/sample_source`
- **MySQL Sample**: `mysql://appuser@localhost:3306/sample_source`
- **Oracle Sample**: `//sys@localhost:1521/XE`
- **pgAdmin**: http://localhost:5050 (admin@example.com / pgadmin_dev_password)

### 5. Set Up Pre-commit Hooks

```bash
# Install pre-commit hooks (automatic linting/formatting on commit)
pre-commit install

# Run hooks manually (optional)
pre-commit run --all-files
```

### 6. Run Tests

```bash
# Unit tests
poetry run pytest tests/unit/ -v

# Lint and type checking
poetry run black --check .
poetry run isort --check-only .
poetry run flake8 .
poetry run mypy . --ignore-missing-imports
```

## Development Workflow

### Code Quality Tools

All code is checked with these tools (both locally and in CI):

- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: PEP 8 linting
- **MyPy**: Static type checking

Run all checks locally:

```bash
# Format code
poetry run black .

# Sort imports
poetry run isort .

# Run linting & type checking
./scripts/lint.sh  # Or run manually (see scripts directory)
```

### Running the Application

#### FastAPI Server

```bash
cd apps/api-fastapi
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API will be available at: http://localhost:8000
API docs: http://localhost:8000/docs

#### Streamlit UI

```bash
cd apps/ui-streamlit
poetry run streamlit run app.py --server.port 8501
```

UI will be available at: http://localhost:8501

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

## Architecture Highlights

- **LangGraph State Machine**: Orchestrates migration phases with deterministic state management
- **Human-in-the-Loop**: Approval gates at critical points with audit trails
- **Dialect Symmetry**: Source and target DBs use the same dialect interface
- **Tool Adapters**: Pluggable external tools (CrackSQL, SeaTunnel, OpenRewrite, etc.)
- **Knowledge Base**: RAG-powered migration rules and patterns with PGVector
- **Observability**: Full tracing with LangSmith, metrics with Prometheus, dashboards in Grafana
- **Checkpointing**: Pause/resume capability across restarts

See [docs/architecture.md](docs/architecture.md) for detailed system design.

## CI/CD Pipeline

GitHub Actions runs on every push and pull request:

1. **Lint**: Black, isort, flake8 formatting and style checks
2. **Type Check**: MyPy static type analysis
3. **Unit Tests**: pytest with coverage reporting
4. **Security Scan**: Bandit security vulnerability scanning

View workflow: [.github/workflows/ci.yml](.github/workflows/ci.yml)

## Common Tasks

### Stop Local Databases

```bash
docker-compose down
```

### Clean Up Everything (including volumes)

```bash
docker-compose down -v
```

### View Database Logs

```bash
docker-compose logs postgres-metadata
docker-compose logs mysql-sample
docker-compose logs oracle-sample
```

### Reset a Specific Database

```bash
docker-compose down postgres-metadata
docker-compose up -d postgres-metadata
```

## Troubleshooting

### Docker Compose won't start

Ensure Docker daemon is running and you have sufficient disk space:

```bash
docker system prune -a  # Clean up unused images/containers
docker-compose up -d    # Try again
```

### Oracle container stuck initializing

Oracle XE takes 5-10 minutes on first run. Check logs:

```bash
docker-compose logs oracle-sample
```

### PostgreSQL connection refused

Ensure the service is healthy:

```bash
docker-compose ps postgres-metadata
docker-compose logs postgres-metadata
```

### Python import errors

Ensure dependencies are installed:

```bash
poetry install
poetry run python -c "import langgraph; print(langgraph.__version__)"
```

## Environment Variables

See [.env.example](.env.example) for all configurable options:

- **AWS**: Region, credentials, Bedrock model IDs
- **Databases**: Host, port, credentials for source/target DBs
- **API**: FastAPI host/port, debug settings
- **Observability**: LangSmith API keys
- **Deployment**: Kubernetes, namespace, environment

## Documentation

- [Architecture & Design](docs/architecture.md) - System overview and design decisions
- [ADRs](docs/adr/README.md) - Architectural Decision Records
- [Development Guide](DEVELOPMENT.md) - Detailed development setup
- [Implementation Plan](plan.md) - Phase-by-phase roadmap
- [Capstone Proposal](Capstone_Proposal.md) - Project proposal & scope

## Security

- Store credentials in `.env` files (never commit)
- Use AWS Secrets Manager for production
- Follow [security checklist](docs/architecture.md#14-security-considerations)
- Enable IAM role-based access (IRSA) for Kubernetes
- All database connections use SSL/TLS where available

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Install pre-commit hooks: `pre-commit install`
3. Make your changes and commit (hooks will auto-run)
4. Push and create a pull request
5. All CI checks must pass before merge

## License

MIT License - see LICENSE file for details

## Support

- 📖 See [docs/](docs/) for documentation
- 🐛 Report issues on GitHub
- 💬 Check existing discussions in GitHub Issues

## Roadmap

See [plan.md](plan.md) for the 10-week implementation roadmap:
- Phase 0: Foundations (current)
- Phase 1: Orchestration skeleton
- Phase 2-3: Dialect plugins & knowledge base
- Phase 4-6: Translation & refactoring
- Phase 7-8: Validation & deployment
- Phase 9-10: Observability & integration

---

**Last Updated**: 2026-09-29  
**Status**: Phase 0 - Foundations Complete ✅
