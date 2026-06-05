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

CMD ["uvicorn", "transversal.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]
