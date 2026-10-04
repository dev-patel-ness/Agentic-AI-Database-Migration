# Getting Started — Step-by-Step Setup & Run Guide

This guide takes you from a fresh clone to a running migration job, in order. For a condensed version see [README.md](README.md#quick-start); for system design see [docs/architecture.md](docs/architecture.md).

---

## 0. Prerequisites

Install these before starting:

| Requirement | Notes |
|---|---|
| **Python 3.12** | Required, not just recommended. If only a newer Python (3.13/3.14) is installed, Poetry will pick it up and fail building `oracledb`/`psycopg2-binary`/`pyspark` (no prebuilt wheels yet). Install with `winget install --id Python.Python.3.12` (Windows) even if a newer Python already exists. |
| **Poetry 1.7.0+** | `pip install poetry` or the official installer. |
| **Docker Desktop** (or Docker Engine + Compose) | Runs all sample databases + SeaTunnel. |
| **AWS account with Bedrock access** | Model access to `amazon.nova-pro-v1:0` and `amazon.titan-embed-text-v2:0` in your region. |
| **Git** | To clone the repo. |

---

## 1. Clone the Repository

```bash
git clone https://github.com/your-org/Agentic-AI-Data-Migration.git
cd Agentic-AI-Data-Migration
```

## 2. Pin Poetry to Python 3.12

Do this **before** installing dependencies:

```powershell
py -3.12 --version               # confirm 3.12 is installed
poetry env use py -3.12          # Windows; use `poetry env use python3.12` on macOS/Linux
poetry env info                  # verify the active venv is on 3.12
```

If you already created a Poetry env with the wrong interpreter: `poetry env remove --all`, then repeat the two commands above.

## 3. Build the CrackSQL Editable Package

The `cracksql` dependency in `pyproject.toml` is a local, gitignored build directory — `poetry install` fails until this runs first:

```bash
python tool_adapters/cracksql_adapter/vendor/CrackSQL/build_editable.py
```

Re-run this any time `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/` changes.

## 4. Install Python Dependencies

```bash
poetry install
```

If this fails with a lock-file/content-hash error, run `poetry lock --no-update` once and retry.

## 5. Configure Environment Variables

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

## 6. Start the Local Database Stack

```bash
docker-compose up -d
docker-compose ps
```

Wait for all containers to report healthy (Oracle takes 5-10 minutes on first boot). Services:

| Service | Address |
|---|---|
| PostgreSQL Metadata | `postgresql://postgres@localhost:5432/migration_metadata` |
| PostgreSQL Sample | `postgresql://postgres@localhost:5433/sample_source` |
| MySQL Sample | `mysql://appuser@localhost:3306/sample_source` |
| Oracle Sample | `//sys@localhost:1521/XE` |
| pgAdmin | http://localhost:5050 (admin@example.com / pgadmin_dev_password) |

## 7. Initialize the CrackSQL Knowledge Base

Required once, before any schema translation (Phase 4) will work:

```bash
poetry run python scripts/init_cracksql_kb.py
```

Safe to re-run (idempotent). If it reports `Knowledge base initialization completed: 0/3 successful`, see the Troubleshooting table below (`EMBEDDING_MODELS`/`KNOWLEDGE_BASES` config mismatch in `init_config.yaml`).

## 8. Build the SeaTunnel Docker Image

Required once, before any data migration (Phase 5) will work:

```powershell
./infra/docker/seatunnel/fetch_jdbc_drivers.ps1   # downloads JDBC driver jars (not committed to git)
docker compose build seatunnel
docker compose up -d seatunnel
```

## 9. (Optional) Set Up Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

## 10. Verify the Setup

```bash
poetry run pytest tests/unit/ -v
```

All unit tests should pass. If you also want to confirm the live pipeline works end-to-end against the sample databases, run:

```bash
poetry run pytest tests/integration/ -v   # schema discovery + knowledge base + checkpointer
poetry run pytest tests/e2e/ -v -s        # full Discover -> Migrate -> Verify workflow
```

---

## 11. Run the Application

Two processes, in separate terminals.

### Terminal A — FastAPI backend

```bash
cd apps/api-fastapi
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs

### Terminal B — Streamlit UI

```bash
cd apps/ui-streamlit
poetry run streamlit run app.py --server.port 8501
```

- UI: http://localhost:8501

## 12. Create and Drive a Migration Job

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

## 13. Stopping / Resetting

```bash
docker-compose down          # stop all containers, keep data
docker-compose down -v       # stop and wipe all volumes (fresh sample data next start)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `poetry install` fails building `oracledb`/`psycopg2`/`pyspark` (MSVC error) | Wrong Python version — `poetry env remove --all`, `poetry env use py -3.12`, retry (step 2). |
| `poetry install` fails with a "directory does not exist" error for `cracksql` | Run step 3 (`build_editable.py`) first. |
| `poetry install` fails with a lock-file/content-hash error | `poetry lock --no-update`, then retry. |
| `scripts/init_cracksql_kb.py` reports `0/3 successful`, or hybrid translation (Phase 4) logs embedding `Missing credentials`/`Could not connect to the endpoint URL` | Stale CrackSQL config/DB. In `tool_adapters/cracksql_adapter/vendor/CrackSQL/backend/config/init_config.yaml`, the `EMBEDDING_MODELS` entry's `deployment_type` must be `"bedrock"` (not `"cloud"`) with `api_base` set to a real AWS region, and every `KNOWLEDGE_BASES[*].embedding_model` must match the Bedrock model name (`amazon.titan-embed-text-v2:0`, not `text-embedding-ada-002`). Delete `tool_adapters/cracksql_adapter/instance/info.db` and re-run step 7. |
| Oracle container never becomes healthy | Normal on first run (5-10 min). Check `docker-compose logs oracle-sample`. |
| SeaTunnel job can't reach a sample DB container | Job configs run inside the SeaTunnel container, so `localhost` there isn't the host — already configured to use `host.docker.internal` via `extra_hosts` in `docker-compose.yml`. |
| `AUTH_API_KEY` warning at API startup | Expected in local dev (auth disabled). Set `AUTH_API_KEY` in `.env` before exposing the API beyond localhost. |

For more detail, see [README.md](README.md#troubleshooting) and [docs/architecture.md](docs/architecture.md).
