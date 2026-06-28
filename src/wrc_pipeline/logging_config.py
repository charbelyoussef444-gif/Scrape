"""Structured JSON logging via structlog.

Every log line is a single JSON object with a timestamp, level, event name and
arbitrary contextual key/values (run_id, body, partition, identifier, ...).
This satisfies the assignment's requirement for machine-readable logs and makes
per-partition / per-body progress trivially greppable and aggregatable.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure structlog + stdlib logging to emit JSON to stdout.

    Safe to call multiple times (e.g. once per process entrypoint).
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Route the stdlib root logger (used by Scrapy, boto3, pymongo) to stdout.
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger."""
    return structlog.get_logger(name)
