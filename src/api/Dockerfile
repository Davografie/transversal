# Transversal API Dockerfile

# SEC-9: pinned by digest so every build resolves the same base. Bump this
# deliberately (that is the point) — `docker build --pull` will not move it.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.lock .
COPY src/ src/
COPY tests/ tests/

# SEC-9: install from the committed lock, so a build cannot silently drift to a
# new major the way `pip install -e ".[dev]"` against `>=` floors could. The lock
# is generated with --all-extras, so the dev tooling (pytest/ruff) stays in this
# image on purpose — the documented test recipe runs pytest inside it. Splitting
# dev extras into a separate stage is a follow-up that has to move that recipe
# with it.
RUN pip install --no-cache-dir -r requirements.lock \
    && pip install --no-cache-dir -e . --no-deps

EXPOSE 8080

# Default: single worker with reload (dev). Set UVICORN_WORKERS (e.g. 4) to run
# multiple workers (no reload — uvicorn's reloader is single-worker only).
# Multi-worker requires Redis (see docker-compose) for cross-worker SSE/sessions.
CMD ["sh", "-c", "if [ -n \"$UVICORN_WORKERS\" ] && [ \"$UVICORN_WORKERS\" != \"1\" ]; then exec uvicorn transversal.main:app --host 0.0.0.0 --port 8080 --workers ${UVICORN_WORKERS}; else exec uvicorn transversal.main:app --host 0.0.0.0 --port 8080 --reload; fi"]
