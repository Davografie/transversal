# Transversal API Dockerfile

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
COPY tests/ tests/

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8080

# Default: single worker with reload (dev). Set UVICORN_WORKERS (e.g. 4) to run
# multiple workers (no reload — uvicorn's reloader is single-worker only).
# Multi-worker requires Redis (see docker-compose) for cross-worker SSE/sessions.
CMD ["sh", "-c", "if [ -n \"$UVICORN_WORKERS\" ] && [ \"$UVICORN_WORKERS\" != \"1\" ]; then exec uvicorn transversal.main:app --host 0.0.0.0 --port 8080 --workers ${UVICORN_WORKERS}; else exec uvicorn transversal.main:app --host 0.0.0.0 --port 8080 --reload; fi"]
