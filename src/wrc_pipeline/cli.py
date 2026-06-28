"""Command-line entrypoints.

    wrc-scrape    --start 2024-01-01 --end 2024-04-01 [--partition monthly]
                  [--bodies workplace_relations_commission,labour_court]
    wrc-transform --start 2024-01-01 --end 2024-04-01

Both also work without arguments, falling back to the dates configured via
environment (WRC_START_DATE / WRC_END_DATE).
"""

from __future__ import annotations

import argparse
from datetime import date, datetime

from wrc_pipeline.config import get_settings
from wrc_pipeline.logging_config import configure_logging


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _add_window_args(parser: argparse.ArgumentParser) -> None:
    settings = get_settings()
    parser.add_argument("--start", type=_parse_date, default=settings.start_date,
                        help="Start date YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", type=_parse_date, default=settings.end_date,
                        help="End date YYYY-MM-DD (exclusive)")


def scrape_main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="wrc-scrape", description="Scrape WRC decisions.")
    _add_window_args(parser)
    parser.add_argument("--partition", default=settings.partition_size,
                        choices=["monthly", "weekly", "yearly"])
    parser.add_argument("--bodies", default=settings.bodies,
                        help="Comma-separated body keys (default: all)")
    args = parser.parse_args(argv)

    # Imported here so non-scrape commands don't pay Scrapy's import cost.
    from wrc_pipeline.scraper.runner import crawl

    bodies = [b.strip() for b in args.bodies.split(",") if b.strip()]
    crawl(
        start_date=args.start,
        end_date=args.end,
        partition_size=args.partition,
        bodies=bodies or None,
    )


def transform_main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    parser = argparse.ArgumentParser(prog="wrc-transform", description="Transform landing data.")
    _add_window_args(parser)
    args = parser.parse_args(argv)

    from wrc_pipeline.transform import run_transform

    run_transform(start_date=args.start, end_date=args.end, settings=settings)


if __name__ == "__main__":  # pragma: no cover
    scrape_main()
