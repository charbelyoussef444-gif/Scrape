"""Date-range partitioning.

The scraper walks a ``[start_date, end_date)`` interval (end exclusive, matching
the assignment's "monthly partitions between 01-01-2024 and 01-01-2025" example)
and splits it into contiguous windows. Each window becomes one logical unit of
work per body and is stamped onto every record as ``partition_date``.

Partitioning the request space this way keeps each search query small (the site
caps usefully-pageable results), makes progress observable, and lets a rerun or
a 50-source fan-out parallelise cleanly along (body, partition) keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

# Date format expected by the WRC search endpoint's from/to parameters.
SITE_DATE_FORMAT = "%d/%m/%Y"


@dataclass(frozen=True)
class Partition:
    """A single contiguous date window (both ends inclusive for querying)."""

    label: str   # e.g. "2024-01" — stored as partition_date on every record
    start: date  # first day in the window (inclusive)
    end: date    # last day in the window (inclusive)

    @property
    def from_param(self) -> str:
        return self.start.strftime(SITE_DATE_FORMAT)

    @property
    def to_param(self) -> str:
        return self.end.strftime(SITE_DATE_FORMAT)


def _step(size: str) -> relativedelta:
    if size == "monthly":
        return relativedelta(months=1)
    if size == "weekly":
        return relativedelta(weeks=1)
    if size == "yearly":
        return relativedelta(years=1)
    raise ValueError(f"Unsupported partition size: {size!r}")


def _label(size: str, window_start: date) -> str:
    if size == "monthly":
        return window_start.strftime("%Y-%m")
    if size == "weekly":
        return window_start.strftime("%G-W%V")  # ISO year + ISO week
    return window_start.strftime("%Y")


def _aligned_start(size: str, day: date) -> date:
    """Snap a date to the natural period boundary so windows tile cleanly."""
    if size == "monthly":
        return day.replace(day=1)
    if size == "weekly":
        return day - timedelta(days=day.weekday())  # Monday of that week
    return day.replace(month=1, day=1)


def iter_partitions(start_date: date, end_date: date, size: str = "monthly") -> list[Partition]:
    """Split ``[start_date, end_date)`` into inclusive windows of ``size``.

    Windows are aligned to natural boundaries (calendar months/weeks/years) and
    clamped to the requested interval, so the first and last windows may be
    partial. Raises ``ValueError`` if the range is empty or inverted.
    """
    if end_date <= start_date:
        raise ValueError(f"end_date ({end_date}) must be after start_date ({start_date})")

    step = _step(size)
    last_day = end_date - timedelta(days=1)  # end is exclusive

    partitions: list[Partition] = []
    cursor = _aligned_start(size, start_date)
    while cursor <= last_day:
        window_end = (cursor + step) - timedelta(days=1)  # last day of this period
        clamped_start = max(cursor, start_date)
        clamped_end = min(window_end, last_day)
        partitions.append(
            Partition(label=_label(size, cursor), start=clamped_start, end=clamped_end)
        )
        cursor += step
    return partitions
