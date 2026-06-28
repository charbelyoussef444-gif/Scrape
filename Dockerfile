# Application image: runs the scraper, transform, or Dagster.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DAGSTER_HOME=/opt/dagster/home

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[orchestration]"

# Dagster instance config (explicit, so `dagster dev` doesn't warn / default).
RUN mkdir -p /opt/dagster/home
COPY dagster.yaml /opt/dagster/home/dagster.yaml

# Default to showing CLI help; compose overrides the command for Dagster.
CMD ["wrc-scrape", "--help"]
