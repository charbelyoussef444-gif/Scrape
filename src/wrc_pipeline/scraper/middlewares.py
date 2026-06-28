"""Downloader middleware implementing the "skip already-known" fast path.

When ``recheck_existing`` is disabled, a rerun should not even re-download
documents it already has. This middleware short-circuits document requests whose
identifier is already present in MongoDB, turning a rerun into a cheap listing
walk with zero document downloads.

When ``recheck_existing`` is enabled (the default), this middleware does
nothing: every document is fetched so the pipeline can detect content changes
via the file hash.
"""

from __future__ import annotations

from scrapy import signals
from scrapy.exceptions import IgnoreRequest

from wrc_pipeline.config import get_settings
from wrc_pipeline.factories import landing_repo
from wrc_pipeline.logging_config import get_logger
from wrc_pipeline.scraper.accounting import RunAccounting


class SkipKnownDocumentsMiddleware:
    def __init__(self, crawler) -> None:
        self.crawler = crawler
        settings = get_settings()
        self.recheck_existing = settings.recheck_existing
        self._repo = landing_repo(settings) if not self.recheck_existing else None
        self.log = get_logger("wrc.middleware")

    @classmethod
    def from_crawler(cls, crawler):
        mw = cls(crawler)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    def process_request(self, request):
        if self.recheck_existing or not request.meta.get("wrc_document"):
            return None  # fetch normally

        record = request.meta["wrc_record"]
        identifier = record["identifier"]
        if self._repo and self._repo.exists(identifier):
            key = RunAccounting.key(record["body_key"], record["partition_date"])
            self.crawler.spider.accounting.mark(key, "skipped")
            self.log.info("document_skipped", identifier=identifier, reason="already_ingested")
            raise IgnoreRequest(f"{identifier} already ingested")
        return None

    def spider_closed(self):
        if self._repo:
            self._repo.close()
