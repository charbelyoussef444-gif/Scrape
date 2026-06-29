"""Typed, environment-driven configuration.

Every operational value (connection strings, bucket names, partition size,
politeness knobs) is defined here and sourced from environment variables or a
local ``.env`` file. Nothing is hardcoded in the business logic, which keeps
the same image runnable locally, in Docker, and in CI by only changing env.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object, populated from ``WRC_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="WRC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- MongoDB ---
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "wrc"
    landing_collection: str = "landing_decisions"
    curated_collection: str = "curated_decisions"

    # --- Object storage (MinIO / S3) ---
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_region: str = "us-east-1"
    landing_bucket: str = "landing"
    curated_bucket: str = "curated"

    # --- Target site ---
    base_url: str = "https://www.workplacerelations.ie"
    search_path: str = "/en/search/"

    # --- Scraping window & partitioning ---
    start_date: date = date(2024, 1, 1)
    end_date: date = date(2024, 4, 1)
    partition_size: str = Field(default="monthly", pattern="^(monthly|weekly|yearly)$")
    # Comma-separated body keys; empty = scrape every known body. Stored as a
    # plain string (not list[str]) so env values like "a,b" aren't JSON-parsed.
    bodies: str = ""

    # --- Politeness / anti-block tuning ---
    user_agent: str = "wrc-research-bot/0.1 (+contact: you@example.com)"
    concurrent_requests: int = 8
    download_delay: float = 0.25
    autothrottle_enabled: bool = True
    download_timeout: int = 60
    retry_times: int = 3
    # robots.txt disallows the legacy capital-C /en/Cases/ import paths; the
    # live decision pages live at lowercase /en/cases/ (a distinct, allowed
    # path). We obey robots by default and stay polite regardless.
    robotstxt_obey: bool = True
    log_level: str = "INFO"

    # --- Idempotency ---
    # Published decisions are immutable, so by default a rerun skips
    # already-ingested identifiers entirely: no duplicate records and no
    # re-download of unchanged files. Set to true to re-fetch known documents and
    # use the file hash to detect changes between runs (for corrected/republished
    # decisions).
    recheck_existing: bool = False

    def body_keys(self) -> list[str]:
        """Parse the comma-separated ``bodies`` string into a list of keys."""
        return [item.strip() for item in self.bodies.split(",") if item.strip()]

    @property
    def search_url(self) -> str:
        """Fully-qualified search endpoint."""
        return f"{self.base_url}{self.search_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance (read env/.env exactly once)."""
    return Settings()
