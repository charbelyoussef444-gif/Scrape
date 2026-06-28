"""MongoDB metadata repository.

Wraps a single collection and exposes only the operations the pipeline needs.
Record-level idempotency comes from using the decision ``identifier`` as the
document ``_id`` and upserting, so a rerun can never create duplicates.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection


class MongoRepository:
    """Thin, intention-revealing wrapper around one MongoDB collection."""

    def __init__(self, uri: str, db_name: str, collection_name: str) -> None:
        self._client: MongoClient = MongoClient(uri, tz_aware=True)
        self._collection: Collection = self._client[db_name][collection_name]

    @property
    def collection(self) -> Collection:
        return self._collection

    def ensure_indexes(self) -> None:
        """Create the indexes that back our lookups (idempotent in Mongo)."""
        # _id (== identifier) is unique automatically. These speed up the
        # transform's range query and per-body/partition reporting.
        self._collection.create_index([("decision_date", ASCENDING)])
        self._collection.create_index([("body_key", ASCENDING)])
        self._collection.create_index([("partition_date", ASCENDING)])

    def get(self, identifier: str) -> dict[str, Any] | None:
        return self._collection.find_one({"_id": identifier})

    def exists(self, identifier: str) -> bool:
        return self._collection.count_documents({"_id": identifier}, limit=1) > 0

    def upsert(self, record: dict[str, Any]) -> None:
        """Insert or replace a record keyed by its ``_id`` (identifier)."""
        self._collection.replace_one({"_id": record["_id"]}, record, upsert=True)

    def find_by_date_range(self, start: date, end: date) -> list[dict[str, Any]]:
        """Return records whose ``decision_date`` falls in ``[start, end)``.

        Used by the transformation step to select a slice of the landing zone.
        """
        query = {
            "decision_date": {
                "$gte": _start_of_day(start),
                "$lt": _start_of_day(end),
            }
        }
        return list(self._collection.find(query))

    def close(self) -> None:
        self._client.close()


def _start_of_day(value: date) -> datetime:
    return datetime(value.year, value.month, value.day, tzinfo=UTC)
