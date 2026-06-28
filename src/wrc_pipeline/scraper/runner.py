"""Programmatic entrypoint for running the spider.

Used by the CLI. Builds a Scrapy ``CrawlerProcess`` from our settings module and
installs our JSON logging handler (disabling Scrapy's own root handler so all
output is uniform structured JSON).

Note: Twisted's reactor cannot be restarted within a process, so an orchestrator
that runs ingestion and transformation in sequence should invoke the crawl in a
*subprocess* (the Dagster job and CLI both do this).
"""

from __future__ import annotations

import uuid
from datetime import date

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings

from wrc_pipeline.config import get_settings
from wrc_pipeline.logging_config import configure_logging


def crawl(
    start_date: date | None = None,
    end_date: date | None = None,
    partition_size: str | None = None,
    bodies: list[str] | None = None,
    run_id: str | None = None,
) -> str:
    """Run a full crawl for the given window. Returns the run_id."""
    app_settings = get_settings()
    configure_logging(app_settings.log_level)
    run_id = run_id or uuid.uuid4().hex

    scrapy_settings = Settings()
    scrapy_settings.setmodule("wrc_pipeline.scraper.settings", priority="project")

    process = CrawlerProcess(settings=scrapy_settings, install_root_handler=False)
    process.crawl(
        "wrc",
        start_date=start_date.isoformat() if start_date else None,
        end_date=end_date.isoformat() if end_date else None,
        partition_size=partition_size,
        bodies=",".join(bodies) if bodies else None,
        run_id=run_id,
    )
    process.start()  # blocks until the crawl finishes
    return run_id
