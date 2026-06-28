"""Per-run accounting so every record is reconciled.

The assignment requires that for a date range containing N records we either
scrape N, or scrape N-X with every one of the X failures logged with a reason.
This tracks, per ``(body, partition)``: how many records the listing reported,
how many were newly stored / changed / unchanged / skipped, and the full list
of failures with URL and error reason.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class PartitionStats:
    found: int = 0          # records the listing said exist
    new: int = 0            # first-time downloads stored
    changed: int = 0        # content changed since a previous run
    unchanged: int = 0      # already stored, identical hash
    skipped: int = 0        # known identifier skipped (recheck disabled)
    failures: list[dict] = field(default_factory=list)

    @property
    def scraped(self) -> int:
        """Records accounted for as successfully handled this run."""
        return self.new + self.changed + self.unchanged + self.skipped

    @property
    def missing(self) -> int:
        """found - scraped - failed; should be 0 when fully reconciled."""
        return max(self.found - self.scraped - len(self.failures), 0)


class RunAccounting:
    """Aggregates :class:`PartitionStats` keyed by ``"{body}/{partition}"``."""

    def __init__(self) -> None:
        self._stats: dict[str, PartitionStats] = defaultdict(PartitionStats)

    @staticmethod
    def key(body_key: str, partition_label: str) -> str:
        return f"{body_key}/{partition_label}"

    def add_found(self, key: str, count: int) -> None:
        self._stats[key].found += count

    def mark(self, key: str, outcome: str) -> None:
        """Increment one of new/changed/unchanged/skipped for ``key``."""
        setattr(self._stats[key], outcome, getattr(self._stats[key], outcome) + 1)

    def add_failure(self, key: str, url: str, reason: str, status: int | None = None) -> None:
        self._stats[key].failures.append({"url": url, "reason": reason, "status": status})

    def summary(self) -> dict:
        """A JSON-serialisable end-of-run summary."""
        totals = {"found": 0, "scraped": 0, "new": 0, "changed": 0,
                  "unchanged": 0, "skipped": 0, "failed": 0, "missing": 0}
        partitions = {}
        for key, st in sorted(self._stats.items()):
            partitions[key] = {
                "found": st.found, "scraped": st.scraped, "new": st.new,
                "changed": st.changed, "unchanged": st.unchanged,
                "skipped": st.skipped, "failed": len(st.failures),
                "missing": st.missing, "failures": st.failures,
            }
            totals["found"] += st.found
            totals["scraped"] += st.scraped
            totals["new"] += st.new
            totals["changed"] += st.changed
            totals["unchanged"] += st.unchanged
            totals["skipped"] += st.skipped
            totals["failed"] += len(st.failures)
            totals["missing"] += st.missing
        return {"totals": totals, "partitions": partitions}
