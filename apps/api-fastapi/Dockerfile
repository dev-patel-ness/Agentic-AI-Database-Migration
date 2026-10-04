# Build context MUST be the repo root (not this directory): main.py imports
# agents/dialects/knowledge_base/orchestrator/tool_adapters as top-level
# packages installed editable via the root pyproject.toml.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir "poetry==1.8.3"

WORKDIR /app

# Install third-party deps first (cached layer). The cracksql dependency is a
# local editable path, so its source must already be present at this point.
COPY pyproject.toml poetry.lock ./
COPY tool_adapters/cracksql_adapter/vendor/CrackSQL/_package_build tool_adapters/cracksql_adapter/vendor/CrackSQL/_package_build
RUN poetry install --only main --no-root --no-ansi

# Now bring in the rest of the monorepo and install the root project itself
# (editable), which is what makes `import orchestrator` etc. work.
COPY . .
RUN poetry install --only main --no-ansi \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/apps/api-fastapi
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
