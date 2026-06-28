"""The WRC decisions spider.

Strategy (confirmed against the live site):

* The advanced search is reachable by a plain ``GET`` with query parameters —
  no ASP.NET ``__VIEWSTATE`` round-trip is needed to page through results::

      /en/search/?decisions=1&from=DD/MM/YYYY&to=DD/MM/YYYY&body=<id>&pageNumber=<n>

* We iterate the cartesian product of (body, date-partition). For each, page 1
  tells us the total result count, from which we fan out the remaining pages.
* Each listing row already exposes the identifier, date, description and the
  link to the document (an ``.html`` detail page for recent decisions, a
  ``.pdf`` for older ones). We fetch that document and hand the raw bytes to the
  persistence pipeline.

The spider stays free of storage concerns: hashing, deduplication and writes
all live in the pipeline; the "skip already-known" fast path lives in a
downloader middleware.
"""

from __future__ import annotations

import math
import re
import uuid
from datetime import date, datetime
from urllib.parse import urlencode

import scrapy
from scrapy.http import Response
from scrapy.spidermiddlewares.httperror import HttpError

from wrc_pipeline.config import get_settings
from wrc_pipeline.logging_config import get_logger
from wrc_pipeline.models import detect_document_type, normalize_identifier
from wrc_pipeline.partitioning import iter_partitions
from wrc_pipeline.scraper.accounting import RunAccounting
from wrc_pipeline.scraper.items import DecisionItem
from wrc_pipeline.sources import resolve_bodies

RESULTS_PER_PAGE = 10
_COUNT_RE = re.compile(r"of\s+([\d,]+)\s+results", re.IGNORECASE)


class WrcSpider(scrapy.Spider):
    name = "wrc"

    def __init__(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        partition_size: str | None = None,
        bodies: str | None = None,
        run_id: str | None = None,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        settings = get_settings()
        self.settings_obj = settings

        # Window/partitioning: kwargs override config defaults.
        self.start_date: date = _parse_iso(start_date) or settings.start_date
        self.end_date: date = _parse_iso(end_date) or settings.end_date
        self.partition_size: str = partition_size or settings.partition_size
        self.body_keys: list[str] = (
            [b.strip() for b in bodies.split(",") if b.strip()] if bodies else settings.body_keys()
        )

        self.run_id: str = run_id or uuid.uuid4().hex
        self.accounting = RunAccounting()
        self.log = get_logger("wrc.spider").bind(run_id=self.run_id)

    # -- request generation ---------------------------------------------------

    def start_requests(self):
        partitions = iter_partitions(self.start_date, self.end_date, self.partition_size)
        bodies = resolve_bodies(self.body_keys)
        self.log.info(
            "run_start",
            start_date=self.start_date.isoformat(),
            end_date=self.end_date.isoformat(),
            partition_size=self.partition_size,
            bodies=[b.key for b in bodies],
            partitions=[p.label for p in partitions],
        )
        for body in bodies:
            for part in partitions:
                yield self._listing_request(body.key, body.site_id, body.display_name, part, page=1)

    def _listing_request(self, body_key, body_id, body_name, partition, page):
        query = {
            "decisions": 1,
            "from": partition.from_param,
            "to": partition.to_param,
            "body": body_id,
            "pageNumber": page,
        }
        url = f"{self.settings_obj.search_url}?{urlencode(query)}"
        return scrapy.Request(
            url,
            callback=self.parse_listing,
            errback=self.handle_listing_error,
            meta={
                "body_key": body_key,
                "body_id": body_id,
                "body_name": body_name,
                "partition_label": partition.label,
                "page": page,
            },
            dont_filter=True,  # same URL never re-issued, but be explicit
        )

    # -- listing page ---------------------------------------------------------

    def parse_listing(self, response: Response):
        m = response.meta
        key = RunAccounting.key(m["body_key"], m["partition_label"])

        if m["page"] == 1:
            total = self._extract_total(response)
            self.accounting.add_found(key, total)
            self.log.info(
                "partition_listing",
                body=m["body_key"],
                partition=m["partition_label"],
                found=total,
            )
            # Fan out the remaining pages now that we know the total.
            total_pages = math.ceil(total / RESULTS_PER_PAGE)
            for page in range(2, total_pages + 1):
                yield self._listing_request(
                    m["body_key"], m["body_id"], m["body_name"],
                    _PartitionView(m["partition_label"], response), page,
                )

        for row in response.css("li.each-item"):
            yield from self._row_to_request(row, response)

    def _row_to_request(self, row, response: Response):
        m = response.meta
        identifier = (row.css("span.refNO::text").get() or row.css("h2.title a::attr(title)").get())
        href = row.css("h2.title a::attr(href)").get() or row.css("a.btn::attr(href)").get()
        if not identifier or not href:
            self.log.warning("row_unparsable", body=m["body_key"], partition=m["partition_label"])
            return

        identifier = normalize_identifier(identifier)
        document_url = response.urljoin(href)
        record = {
            "identifier": identifier,
            "title": (row.css("h2.title a::text").get() or identifier).strip(),
            "description": (
                row.css("p.description::attr(title)").get()
                or row.css("p.description::text").get()
                or ""
            ).strip(),
            "decision_date": _parse_site_date(row.css("span.date::text").get()),
            "body_key": m["body_key"],
            "body_name": m["body_name"],
            "body_id": m["body_id"],
            "partition_date": m["partition_label"],
            "source_url": document_url,
            "document_url": document_url,
            "document_type": detect_document_type(document_url),
        }
        yield scrapy.Request(
            document_url,
            callback=self.parse_document,
            errback=self.handle_document_error,
            meta={"wrc_record": record, "wrc_document": True},
        )

    # -- document page --------------------------------------------------------

    def parse_document(self, response: Response):
        record = response.meta["wrc_record"]
        item = DecisionItem(**record)
        item["document_bytes"] = response.body
        yield item

    # -- error handling -------------------------------------------------------

    def handle_document_error(self, failure):
        record = failure.request.meta.get("wrc_record", {})
        key = RunAccounting.key(record.get("body_key", "?"), record.get("partition_date", "?"))
        status = failure.value.response.status if failure.check(HttpError) else None
        reason = self._failure_reason(failure)
        self.accounting.add_failure(key, failure.request.url, reason, status)
        self.log.error(
            "document_failed",
            identifier=record.get("identifier"),
            url=failure.request.url,
            status=status,
            reason=reason,
        )

    def handle_listing_error(self, failure):
        m = failure.request.meta
        key = RunAccounting.key(m.get("body_key", "?"), m.get("partition_label", "?"))
        status = failure.value.response.status if failure.check(HttpError) else None
        reason = self._failure_reason(failure)
        self.accounting.add_failure(key, failure.request.url, f"listing: {reason}", status)
        self.log.error("listing_failed", url=failure.request.url, status=status, reason=reason)

    @staticmethod
    def _failure_reason(failure) -> str:
        if failure.check(HttpError):
            return f"HTTP {failure.value.response.status}"
        return failure.getErrorMessage() or failure.type.__name__

    # -- lifecycle ------------------------------------------------------------

    def closed(self, reason: str):
        summary = self.accounting.summary()
        self.log.info("run_summary", reason=reason, **summary)

    @staticmethod
    def _extract_total(response: Response) -> int:
        match = _COUNT_RE.search(response.text)
        return int(match.group(1).replace(",", "")) if match else 0


class _PartitionView:
    """Adapter exposing from_param/to_param for pagination follow-ups.

    The pagination links on the page already carry the from/to dates, so for
    pages 2..N we reuse them straight from the response URL rather than
    recomputing, keeping the request identical to what the site expects.
    """

    def __init__(self, label: str, response: Response) -> None:
        self.label = label
        self._from = _query_param(response.url, "from")
        self._to = _query_param(response.url, "to")

    @property
    def from_param(self) -> str:
        return self._from

    @property
    def to_param(self) -> str:
        return self._to


# -- small helpers ------------------------------------------------------------


def _parse_iso(value: str | None) -> date | None:
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _parse_site_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _query_param(url: str, name: str) -> str:
    from urllib.parse import parse_qs, urlparse

    values = parse_qs(urlparse(url).query).get(name)
    return values[0] if values else ""
