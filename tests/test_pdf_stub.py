"""Test detection of legacy 'download PDF' stub pages vs real HTML decisions."""

from scrapy.http import HtmlResponse, Request

from wrc_pipeline.scraper.spiders.wrc import WrcSpider

BASE = "https://www.workplacerelations.ie/en/cases/2011/december/rp2093_2010.html"

# Real stub layout: empty div.content, real file behind a.download in a sibling.
STUB = b"""
<html><body>
  <nav>menu</nav>
  <h1>MN746/2010</h1>
  <div class="content"></div>
  <div class="related-items related-file">
    <a class="download" href="/en/eat_import/2011/12/abc-123.pdf">Download</a>
  </div>
  <footer>foot</footer>
</body></html>
"""

# Real HTML decision: substantial content. Even with a download button present,
# it must NOT be followed (we keep the HTML).
REAL = (
    b"<html><body><div class=\"content\"><h1>LCR22904</h1><p>"
    + b"Full decision text. " * 30
    + b"</p></div>"
    + b"<a class=\"download\" href=\"/en/x.pdf\">Download</a></body></html>"
)


def _resp(body: bytes) -> HtmlResponse:
    return HtmlResponse(url=BASE, body=body, request=Request(BASE), encoding="utf-8")


def test_stub_download_link_detected():
    assert (
        WrcSpider._decision_download_link(_resp(STUB))
        == "/en/eat_import/2011/12/abc-123.pdf"
    )


def test_real_page_has_no_download_link():
    assert WrcSpider._decision_download_link(_resp(REAL)) is None


def test_parse_document_follows_stub_to_pdf():
    spider = WrcSpider()
    record = {
        "identifier": "RP2093/2010", "title": "x", "description": "y",
        "published_date": None, "body_key": "employment_appeals_tribunal",
        "body_name": "EAT", "body_id": 2, "partition_date": "2011-12",
        "source_url": BASE, "document_url": BASE, "document_type": "html",
    }
    resp = _resp(STUB)
    resp.meta["wrc_record"] = record
    out = list(spider.parse_document(resp))
    assert len(out) == 1
    req = out[0]
    # It yields a follow-up request for the PDF, classified as a pdf document.
    assert req.url.endswith("/en/eat_import/2011/12/abc-123.pdf")
    assert req.meta["wrc_record"]["document_type"] == "pdf"
    assert req.meta["wrc_record"]["source_url"] == BASE


def test_parse_document_yields_item_for_real_html():
    spider = WrcSpider()
    record = {
        "identifier": "LCR22904", "title": "x", "description": "y",
        "published_date": None, "body_key": "labour_court", "body_name": "LC",
        "body_id": 3, "partition_date": "2024-02",
        "source_url": BASE, "document_url": BASE, "document_type": "html",
    }
    resp = _resp(REAL)
    resp.meta["wrc_record"] = record
    out = list(spider.parse_document(resp))
    assert len(out) == 1
    assert dict(out[0])["document_type"] == "html"  # stored as HTML, not followed
