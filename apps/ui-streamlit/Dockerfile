# Build context MUST be the repo root (not this directory): the Streamlit app
# is installed via the root pyproject.toml alongside its sibling packages.
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

COPY . .
RUN poetry install --only main --no-ansi \
    && useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

WORKDIR /app/apps/ui-streamlit
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
