"""Errback accounting: intentional skips are not counted as failures."""

from scrapy import Request
from scrapy.exceptions import IgnoreRequest
from twisted.python.failure import Failure

from wrc_pipeline.scraper.spiders.wrc import WrcSpider

META = {
    "wrc_record": {
        "identifier": "ADJ-1", "body_key": "labour_court",
        "partition_date": "2024-01", "document_url": "http://x/doc",
    }
}


def test_ignore_request_is_not_a_failure():
    spider = WrcSpider()
    failure = Failure(IgnoreRequest("already ingested"))
    failure.request = Request("http://x/doc", meta=META)
    spider.handle_document_error(failure)
    assert spider.accounting.summary()["totals"]["failed"] == 0


def test_real_error_is_recorded_with_reason():
    spider = WrcSpider()
    failure = Failure(ValueError("boom"))
    failure.request = Request("http://x/doc", meta=META)
    spider.handle_document_error(failure)
    summary = spider.accounting.summary()
    assert summary["totals"]["failed"] == 1
    part = summary["partitions"]["labour_court/2024-01"]
    assert part["failures"][0]["url"] == "http://x/doc"
    assert "boom" in part["failures"][0]["reason"]
