# Development Guide

This guide provides detailed instructions for setting up a local development environment for the Agentic AI Database Migration Platform.

## System Requirements

### Minimum
- **OS**: Windows 10/11, macOS 11+, or Linux (Ubuntu 20.04+)
- **CPU**: 4 cores
- **RAM**: 8 GB (16 GB recommended)
- **Disk**: 50 GB free space

### Required Software
- **Python**: 3.11+ (3.12 recommended)
- **Docker**: 20.10+ and Docker Compose 2.0+
- **Git**: 2.30+
- **Poetry**: 1.7.0+ (for dependency management)

### AWS Requirements (Phase 1+)
- AWS account with Bedrock access
- IAM user with Bedrock permissions
- AWS credentials configured locally

## Installation Steps

### 1. Clone Repository

```bash
git clone https://github.com/your-org/Agentic-AI-Data-Migration.git
cd Agentic-AI-Data-Migration
```

### 2. Python Environment Setup

#### Option A: Using Poetry (Recommended)

```bash
# Install Poetry (if not already installed)
curl -sSL https://install.python-poetry.org | python3 -

# Verify installation
poetry --version

# Create virtual environment and install dependencies
poetry install

# Activate virtual environment
poetry shell

# Or use `poetry run` to run commands in the environment
poetry run python --version
```

#### Option B: Using pip

```bash
# Create virtual environment
python3.11 -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Docker Setup

#### Install Docker Desktop

- **Windows/macOS**: Download from https://www.docker.com/products/docker-desktop
- **Linux**: Follow https://docs.docker.com/engine/install/

#### Start Docker Daemon

```bash
# Windows/macOS: Start Docker Desktop application
# Linux: Ensure Docker service is running
sudo systemctl start docker
```

#### Verify Installation

```bash
docker --version
docker-compose --version
docker run hello-world
```

### 4. Environment Configuration

```bash
# Copy template
cp .env.example .env

# Edit with your settings
# On Windows:
code .env  # or use your preferred editor

# On macOS/Linux:
nano .env
```

**Minimum required settings:**

```env
# AWS (required for agent functionality)
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_REGION=us-east-1

# Bedrock (optional, defaults provided)
BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0

# Local database URLs (auto-configured by docker-compose)
# These match the docker-compose.yml defaults
POSTGRES_METADATA_HOST=localhost
POSTGRES_METADATA_PORT=5432
POSTGRES_METADATA_PASSWORD=postgres_dev_password
```

### 5. Start Local Services

```bash
# Start all databases and services
docker-compose up -d

# Wait for services to become healthy (30-60 seconds)
docker-compose ps

# Example output:
# NAME                  STATUS
# postgres-metadata     Up (healthy)
# postgres-sample       Up (healthy)
# mysql-sample          Up (healthy)
# oracle-sample         Up (healthy, but may take 5-10 min on first run)
# pgadmin               Up
```

#### Test Database Connections

```bash
# PostgreSQL metadata
poetry run python -c "
import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres_dev_password@localhost:5432/migration_metadata')
print('✓ PostgreSQL metadata connected')
conn.close()
"

# MySQL sample
poetry run python -c "
import mysql.connector
conn = mysql.connector.connect(host='localhost', user='appuser', password='mysql_dev_password', database='sample_source')
print('✓ MySQL sample connected')
conn.close()
"

# Oracle sample (if available)
poetry run python -c "
import cx_Oracle
conn = cx_Oracle.connect('sys/oracle_dev_password@localhost:1521/XE')
print('✓ Oracle sample connected')
conn.close()
"
```

### 6. Set Up Pre-commit Hooks

```bash
# Install git hooks
pre-commit install

# Test hooks (will run on every commit)
pre-commit run --all-files

# Check installation
cat .git/hooks/pre-commit
```

### 7. Verify Installation

```bash
# Run tests
poetry run pytest tests/unit/ -v

# Run linting
poetry run black --check .
poetry run isort --check-only .
poetry run flake8 .

# Run type checking
poetry run mypy . --ignore-missing-imports
```

## IDE Configuration

### Visual Studio Code

1. **Install Extensions**:
   - Python
   - Pylance
   - Black Formatter
   - isort
   - Flake8
   - MyPy Type Checker

2. **Configure `.vscode/settings.json`**:

```json
{
  "[python]": {
    "editor.defaultFormatter": "ms-python.python",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    }
  },
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.linting.flake8Args": [
    "--max-line-length=100"
  ],
  "mypy.overrides": [
    {
      "file": "tool_adapters/**",
      "mypy_path": "/path/to/repo"
    }
  ],
  "isort.args": [
    "--profile",
    "black"
  ]
}
```

### PyCharm

1. **Configure Python Interpreter**:
   - Settings → Project → Python Interpreter
   - Click gear icon → Add → Select Poetry venv
   - Or: `poetry shell` then use that path

2. **Configure Code Style**:
   - Settings → Project → Code Style → Python
   - Set line length to 100
   - Enable isort integration

3. **Enable Type Checking**:
   - Settings → Languages & Frameworks → Python → Type Checker
   - Select "MyPy"

## Common Development Tasks

### Running the API Server

```bash
cd apps/api-fastapi

# Start with auto-reload (development)
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, test the API
curl http://localhost:8000/health
```

**API Documentation**: http://localhost:8000/docs

### Running the Streamlit UI

```bash
cd apps/ui-streamlit

# Start the app
poetry run streamlit run app.py

# App opens at http://localhost:8501
```

**Config file**: `~/.streamlit/config.toml`

### Running Tests

```bash
# All unit tests
poetry run pytest tests/unit/ -v

# Specific test file
poetry run pytest tests/unit/test_adapter.py -v

# Tests matching pattern
poetry run pytest tests/unit/ -k "adapter" -v

# With coverage
poetry run pytest tests/unit/ --cov=. --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Code Quality Checks

```bash
# Format code
poetry run black .

# Sort imports
poetry run isort .

# Check without formatting
poetry run black --check .

# Run all linting at once
./scripts/check.sh  # if available
```

### Inspecting Databases

#### PostgreSQL

```bash
# Using psql
poetry run psql -h localhost -U postgres -d migration_metadata

# List tables
\dt

# Run query
SELECT * FROM migration_jobs;

# Quit
\q
```

#### MySQL

```bash
# Using mysql CLI
poetry run mysql -h localhost -u appuser -pmysql_dev_password sample_source

# List tables
SHOW TABLES;

# Run query
SELECT * FROM employees;

# Quit
exit
```

#### Oracle

```bash
# Using sqlplus
poetry run sqlplus sys/oracle_dev_password@localhost:1521/XE

# List tables
SELECT * FROM tab;

# Run query
SELECT * FROM employees;

# Quit
exit
```

### Using pgAdmin (Web UI)

1. Navigate to http://localhost:5050
2. Login: `admin@example.com` / `pgadmin_dev_password`
3. Register PostgreSQL servers:
   - Metadata DB: `localhost:5432`
   - Sample DB: `localhost:5433`
4. Explore schemas and run queries in browser

## Docker-Compose Workflows

### Restart All Services

```bash
docker-compose restart
```

### View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f postgres-metadata

# Last N lines
docker-compose logs postgres-metadata --tail=50
```

### Clean Up

```bash
# Stop services (keep volumes)
docker-compose down

# Stop and remove volumes (WARNING: deletes data)
docker-compose down -v

# Remove all stopped containers
docker container prune

# Clean up unused images
docker image prune
```

### Rebuild Images

```bash
# Rebuild all images
docker-compose up -d --build

# Rebuild specific service
docker-compose up -d --build postgres-metadata
```

## Troubleshooting

### "Module not found" errors

```bash
# Reinstall dependencies
poetry install --no-cache

# Activate shell
poetry shell

# Or explicitly run with poetry
poetry run python your_script.py
```

### Database connection failures

```bash
# Check service status
docker-compose ps

# Restart database
docker-compose restart postgres-metadata

# Check logs
docker-compose logs postgres-metadata

# Verify connectivity
docker-compose exec postgres-metadata psql -U postgres -c "SELECT 1"
```

### Port conflicts

If ports are already in use, modify `docker-compose.yml`:

```yaml
postgres-metadata:
  ports:
    - "5432:5432"  # Change first number (e.g., "15432:5432")
```

Then update `.env`:

```env
POSTGRES_METADATA_PORT=15432  # Match the changed port
```

### Poetry issues

```bash
# Clear Poetry cache
poetry cache clear . --all

# Reinstall
poetry install

# Update lock file
poetry lock --no-update
```

### Git hooks not running

```bash
# Reinstall hooks
pre-commit install

# Run manually
pre-commit run --all-files

# Debug issues
pre-commit run --all-files --verbose
```

## Architecture Learning Path

1. **Start with** `docs/architecture.md` - Understand the system design
2. **Review** `orchestrator/state.py` - Understand shared state
3. **Study** `tool_adapters/base.py` - Tool adapter contract
4. **Read** `dialects/base.py` - Dialect plugin contract
5. **Explore** `agents/` folder - Agent implementations
6. **Check** `docs/adr/` - Architecture decision records

## Contributing Code

### Branch Naming

```bash
# Feature
git checkout -b feature/add-oracle-dialect

# Bug fix
git checkout -b bugfix/connection-timeout

# Docs
git checkout -b docs/update-setup-guide
```

### Commit Messages

```
# Good
commit -m "Add type annotations to tool_adapters/base.py"

# Also good
commit -m "Implement Oracle dialect

- Add type_map for Oracle types
- Implement export_ddl_command
- Add quote_identifier for Oracle names"

# Avoid
commit -m "stuff"
commit -m "Fix"
```

### Pull Request Checklist

- [ ] Branch created from `develop`
- [ ] Tests pass: `poetry run pytest tests/unit/`
- [ ] Code formatted: `poetry run black .`
- [ ] Imports sorted: `poetry run isort .`
- [ ] Types checked: `poetry run mypy . --ignore-missing-imports`
- [ ] No lint errors: `poetry run flake8 .`
- [ ] Docstrings added for new functions/classes
- [ ] Related GitHub issues linked

## Performance Tips

### IDE Performance

- Disable unnecessary extensions in VSCode/PyCharm
- Exclude `__pycache__` from file indexing
- Use "Pylance" over "PyLance" for better performance

### Testing Performance

```bash
# Run only fast tests
poetry run pytest tests/unit/ -m "not slow"

# Run in parallel
poetry run pytest -n auto tests/unit/

# Stop after first failure
poetry run pytest -x tests/unit/
```

### Docker Performance

```bash
# Remove unused images/volumes
docker system prune -a

# Limit resource usage (edit docker-compose.yml)
services:
  postgres-metadata:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
```

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Poetry Documentation](https://python-poetry.org/docs/)
- [Docker Documentation](https://docs.docker.com/)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)

## Getting Help

1. Check [README.md](README.md) for quick start
2. Review [docs/architecture.md](docs/architecture.md) for design
3. Search GitHub Issues for similar problems
4. Create detailed issue with:
   - Error messages and logs
   - Steps to reproduce
   - Environment info (OS, Python version, etc.)
   - Output of `poetry show --tree`

---

**Last Updated**: 2026-09-29
