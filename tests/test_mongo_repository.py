"""Tests for MongoRepository using mongomock (no real MongoDB needed)."""

from datetime import UTC, datetime

import mongomock
import pytest

from wrc_pipeline.storage.mongo import MongoRepository


@pytest.fixture
def repo(monkeypatch):
    monkeypatch.setattr("wrc_pipeline.storage.mongo.MongoClient", mongomock.MongoClient)
    return MongoRepository("mongodb://fake", "wrc", "landing")


def _record(identifier: str, day: int) -> dict:
    return {
        "_id": identifier,
        "identifier": identifier,
        "published_date": datetime(2024, 1, day, tzinfo=UTC),
        "body_key": "labour_court",
        "partition_date": "2024-01",
        "file_hash": "h",
    }


def test_upsert_is_idempotent(repo):
    rec = _record("ID-1", 15)
    repo.upsert(rec)
    repo.upsert(rec)  # second time must not duplicate
    assert repo.collection.count_documents({}) == 1
    assert repo.exists("ID-1")
    assert not repo.exists("MISSING")


def test_find_by_date_range_is_half_open(repo):
    repo.upsert(_record("A", 10))
    repo.upsert(_record("B", 20))
    repo.upsert(_record("C", 31))

    found = repo.find_by_date_range(datetime(2024, 1, 10).date(), datetime(2024, 1, 31).date())
    ids = {r["_id"] for r in found}
    assert ids == {"A", "B"}  # 31st excluded (end is exclusive)
