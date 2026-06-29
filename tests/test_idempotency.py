"""Tests for the hash-based idempotency logic in the persistence pipeline.

These exercise ``PersistencePipeline._persist`` directly with in-memory fakes,
so no MongoDB or MinIO is required.
"""

from datetime import date

import pytest
from scrapy.exceptions import DropItem

from wrc_pipeline.logging_config import get_logger
from wrc_pipeline.scraper.accounting import RunAccounting
from wrc_pipeline.scraper.items import DecisionItem
from wrc_pipeline.scraper.pipelines import PersistencePipeline


class FakeRepo:
    def __init__(self):
        self.docs = {}

    def get(self, _id):
        return self.docs.get(_id)

    def upsert(self, rec):
        self.docs[rec["_id"]] = rec


class FakeStore:
    def __init__(self):
        self.objects = {}

    def exists(self, key):
        return key in self.objects

    def put_if_absent(self, key, data, content_type=None):
        if key in self.objects:
            return False
        self.objects[key] = data
        return True

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data


def make_pipeline():
    pipe = PersistencePipeline.__new__(PersistencePipeline)
    pipe._repo = FakeRepo()
    pipe._store = FakeStore()
    pipe._run_id = "test-run"
    pipe.log = get_logger("test")
    return pipe


def make_record():
    return {
        "identifier": "ADJ-1",
        "title": "ADJ-1",
        "description": "A v B",
        "published_date": date(2024, 1, 31),
        "body_key": "workplace_relations_commission",
        "body_name": "Workplace Relations Commission",
        "body_id": 15376,
        "partition_date": "2024-01",
        "source_url": "https://x/en/cases/2024/january/adj-1.html",
        "document_url": "https://x/en/cases/2024/january/adj-1.html",
        "document_type": "html",
    }


def test_new_then_unchanged_then_changed():
    pipe = make_pipeline()
    record = make_record()

    # 1) First run: brand new.
    assert pipe._persist(record, b"<html>v1</html>", "ADJ-1") == "new"
    assert "ADJ-1" in pipe._repo.docs
    assert len(pipe._store.objects) == 1

    # 2) Rerun with identical content: unchanged, nothing rewritten.
    assert pipe._persist(record, b"<html>v1</html>", "ADJ-1") == "unchanged"
    assert len(pipe._store.objects) == 1

    # 3) Content changed: new versioned object, metadata pointer updated.
    assert pipe._persist(record, b"<html>v2 CHANGED</html>", "ADJ-1") == "changed"
    assert len(pipe._store.objects) == 2  # landing zone stays append-only
    assert "__" in pipe._repo.docs["ADJ-1"]["storage_path"]  # versioned key


def test_no_duplicate_records_on_rerun():
    pipe = make_pipeline()
    record = make_record()
    for _ in range(3):
        pipe._persist(record, b"same bytes", "ADJ-1")
    assert list(pipe._repo.docs.keys()) == ["ADJ-1"]


def test_hash_is_stored_for_change_detection():
    pipe = make_pipeline()
    pipe._persist(make_record(), b"abc", "ADJ-1")
    stored = pipe._repo.docs["ADJ-1"]
    # sha256("abc")
    assert stored["file_hash"] == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize("doc_type,url,expected_ext", [
    ("html", "https://x/a.html", ".html"),
    ("pdf", "https://x/a.pdf", ".pdf"),
])
def test_extension_drives_storage_key(doc_type, url, expected_ext):
    pipe = make_pipeline()
    record = make_record()
    record["document_type"] = doc_type
    record["document_url"] = url
    pipe._persist(record, b"data", "ADJ-1")
    assert pipe._repo.docs["ADJ-1"]["storage_path"].endswith(expected_ext)


class _FakeSpider:
    def __init__(self):
        self.accounting = RunAccounting()


class _FakeCrawler:
    def __init__(self, spider):
        self.spider = spider


def test_empty_document_body_is_recorded_as_failure():
    spider = _FakeSpider()
    pipe = PersistencePipeline.__new__(PersistencePipeline)
    pipe.crawler = _FakeCrawler(spider)
    pipe.log = get_logger("test")

    item = DecisionItem(**make_record())
    item["document_bytes"] = b""  # empty download

    with pytest.raises(DropItem):
        pipe.process_item(item)

    summary = spider.accounting.summary()
    assert summary["totals"]["failed"] == 1
    reason = summary["partitions"]["workplace_relations_commission/2024-01"]["failures"][0]["reason"]
    assert "empty" in reason
