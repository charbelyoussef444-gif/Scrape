"""Tests for listing parsing: metadata extraction, pagination, reconciliation."""

from scrapy.http import HtmlResponse, Request

from wrc_pipeline.scraper.spiders.wrc import WrcSpider

SEARCH = "https://www.workplacerelations.ie/en/search/?decisions=1&from=01/01/2024&to=31/01/2024&body=15376&pageNumber=1"

# Two valid rows + one unparsable row (no link); "of 25 results" -> 3 pages.
LISTING = b"""
<html><body>
  <div class="searchhead">Shows 1 to 10 of 25 results</div>
  <div class="item-list search-list"><ul>
    <li class="each-item clearfix">
      <div class="row"><div class="col-sm-9">
        <h2 class="title" title="ADJ-1"><a href="/en/cases/2024/january/adj-00047352.html" title="ADJ-1">ADJ-1</a></h2>
      </div><div class="col-sm-3"><span class="date">31/01/2024</span></div></div>
      <p class="description" title="Car Valet V Motor Garage">Car Valet V Motor Garage</p>
      <div class="row bottom-ref"><div class="col-sm-9 ref"><span class="refNO">ADJ-1</span></div></div>
    </li>
    <li class="each-item clearfix">
      <div class="row"><div class="col-sm-9">
        <h2 class="title" title="IR-SC-1"><a href="/en/cases/2024/january/ir-sc-00001785.html">IR - SC - 1</a></h2>
      </div><div class="col-sm-3"><span class="date">15/01/2024</span></div></div>
      <p class="description" title="A Worker V A Company">A Worker V A Company</p>
    </li>
    <li class="each-item clearfix"><h2 class="title">BROKEN ROW NO LINK</h2></li>
  </ul></div>
</body></html>
"""


def _listing_response():
    req = Request(SEARCH, meta={
        "body_key": "workplace_relations_commission", "body_id": 15376,
        "body_name": "Workplace Relations Commission",
        "partition_label": "2024-01", "page": 1,
    })
    return HtmlResponse(url=SEARCH, body=LISTING, request=req, encoding="utf-8")


def test_listing_extracts_metadata_pagination_and_reconciles():
    spider = WrcSpider()
    out = list(spider.parse_listing(_listing_response()))
    doc_reqs = [r for r in out if r.meta.get("wrc_document")]
    page_reqs = [r for r in out if not r.meta.get("wrc_document")]

    # 25 results -> ceil(25/10)=3 pages -> 2 fan-out requests (pages 2,3).
    assert len(page_reqs) == 2
    assert {r.meta["page"] for r in page_reqs} == {2, 3}

    # Two valid rows -> two document requests, identifiers from the URL slug.
    ids = [r.meta["wrc_record"]["identifier"] for r in doc_reqs]
    assert ids == ["ADJ-00047352", "IR-SC-00001785"]

    rec = doc_reqs[0].meta["wrc_record"]
    assert rec["description"] == "Car Valet V Motor Garage"
    assert rec["decision_date"].isoformat() == "2024-01-31"
    assert rec["document_type"] == "html"
    assert rec["partition_date"] == "2024-01"

    summary = spider.accounting.summary()
    # found counted once from the result total.
    assert summary["partitions"]["workplace_relations_commission/2024-01"]["found"] == 25
    # The unparsable row is reconciled as a failure with a reason.
    assert summary["totals"]["failed"] == 1
    failure = summary["partitions"]["workplace_relations_commission/2024-01"]["failures"][0]
    assert "unparsable" in failure["reason"]


def test_result_count_unparsed_falls_back_to_row_count():
    spider = WrcSpider()
    body = b'<html><body><div class="item-list"><ul>' \
           b'<li class="each-item"><h2 class="title"><a href="/en/cases/2024/january/adj-9.html">ADJ-9</a></h2></li>' \
           b"</ul></div></body></html>"
    req = Request(SEARCH, meta={"body_key": "wrc", "body_id": 1, "body_name": "WRC",
                                "partition_label": "2024-01", "page": 1})
    resp = HtmlResponse(url=SEARCH, body=body, request=req, encoding="utf-8")
    out = list(spider.parse_listing(resp))
    # No "of N results" text -> no fan-out, found falls back to rows on page.
    assert [r for r in out if not r.meta.get("wrc_document")] == []
    assert spider.accounting.summary()["partitions"]["wrc/2024-01"]["found"] == 1
