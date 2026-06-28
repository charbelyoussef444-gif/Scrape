"""Dagster job: ingest -> transform with explicit dependency handling.

Run with::

    dagster dev -m wrc_pipeline.orchestration.definitions

The two stages are separate ops. ``ingest`` runs the Scrapy crawl in a
subprocess (Twisted's reactor cannot be restarted within a long-lived Dagster
worker), then passes the date window to ``transform``, which runs in-process.
The data dependency makes Dagster schedule transform strictly after ingest.
"""

import subprocess
import sys
from datetime import date, datetime

# NB: do *not* add `from __future__ import annotations` here — Dagster resolves
# op config/IO types from real (non-stringized) annotations at import time.

from dagster import Config, Definitions, OpExecutionContext, job, op


class WindowConfig(Config):
    """Run configuration shared by the pipeline (supplied via the Dagster UI)."""

    start_date: str = "2024-01-01"  # inclusive, YYYY-MM-DD
    end_date: str = "2024-04-01"    # exclusive, YYYY-MM-DD
    partition_size: str = "monthly"
    bodies: str = ""                # comma-separated keys; empty = all bodies


@op
def ingest(context: OpExecutionContext, config: WindowConfig) -> dict:
    """Run the Scrapy crawl in a subprocess and return the processed window."""
    cmd = [
        sys.executable, "-m", "wrc_pipeline.cli",
        "--start", config.start_date,
        "--end", config.end_date,
        "--partition", config.partition_size,
    ]
    if config.bodies:
        cmd += ["--bodies", config.bodies]

    context.log.info(f"Starting crawl: {' '.join(cmd)}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Crawl subprocess failed (exit {result.returncode})")
    return {"start_date": config.start_date, "end_date": config.end_date}


@op
def transform(context: OpExecutionContext, window: dict) -> None:
    """Transform the freshly ingested window into the curated zone."""
    from wrc_pipeline.transform import run_transform

    summary = run_transform(_to_date(window["start_date"]), _to_date(window["end_date"]))
    context.log.info(
        f"Transform complete: {summary['processed']} processed, "
        f"{summary['failed']} failed"
    )


@job
def wrc_ingestion_pipeline():
    transform(ingest())


defs = Definitions(jobs=[wrc_ingestion_pipeline])


def _to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
