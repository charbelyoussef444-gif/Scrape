"""Persistence pipeline: hash, deduplicate, store bytes, upsert metadata.

This is where idempotency is enforced for every scraped document:

* **Record level** — metadata is upserted by ``identifier`` (the Mongo ``_id``),
  so reruns never create duplicate records.
* **Content level** — we sha256 the bytes and compare against the stored hash:
    - unchanged  -> nothing is rewritten (no duplicate object, no churn)
    - changed    -> the new bytes are written under a hash-versioned key so the
                    landing zone stays append-only, and the metadata pointer +
                    hash are updated
    - new        -> bytes written, metadata inserted
"""

from __future__ import annotations

from scrapy.exceptions import DropItem

from wrc_pipeline.config import get_settings
from wrc_pipeline.factories import landing_repo, landing_store
from wrc_pipeline.hashing import sha256_hex, short_hash
from wrc_pipeline.logging_config import get_logger
from wrc_pipeline.models import (
    build_record,
    canonicalize_for_storage,
    document_extension,
    landing_key,
)
from wrc_pipeline.scraper.accounting import RunAccounting
from wrc_pipeline.storage.object_store import content_type_for


class PersistencePipeline:
    def __init__(self, crawler) -> None:
        self.crawler = crawler
        settings = get_settings()
        self._repo = landing_repo(settings)
        self._store = landing_store(settings)
        self._run_id = "unknown"
        self.log = get_logger("wrc.pipeline")

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self):
        # Ensure infrastructure is ready before the first write.
        self._repo.ensure_indexes()
        self._store.ensure_bucket()
        self._run_id = getattr(self.crawler.spider, "run_id", "unknown")
        self.log = self.log.bind(run_id=self._run_id)

    def close_spider(self):
        self._repo.close()

    def process_item(self, item):
        accounting = self.crawler.spider.accounting
        record = dict(item)
        # Canonicalise before hashing/storing so per-request volatile markup
        # (e.g. the server's render-time comment) doesn't defeat idempotency.
        data: bytes = canonicalize_for_storage(record["document_type"], record.pop("document_bytes"))
        identifier = record["identifier"]
        key = RunAccounting.key(record["body_key"], record["partition_date"])

        # A 200 with an empty body is a failed download, not a valid document —
        # record it with a reason instead of storing a 0-byte file.
        if not data:
            accounting.add_failure(key, record["document_url"], "empty document body")
            self.log.error("empty_document", identifier=identifier, url=record["document_url"])
            raise DropItem(f"empty document for {identifier}")

        try:
            outcome = self._persist(record, data, identifier)
        except Exception as exc:  # noqa: BLE001 - we want to account for any failure
            accounting.add_failure(key, record["document_url"], f"persist: {exc}")
            self.log.error("persist_failed", identifier=identifier, error=str(exc))
            raise DropItem(f"persist failed for {identifier}: {exc}") from exc

        accounting.mark(key, outcome)
        return item

    # -- core logic -----------------------------------------------------------

    def _persist(self, record: dict, data: bytes, identifier: str) -> str:
        file_hash = sha256_hex(data)
        ext = document_extension(record["document_url"], record["document_type"])
        existing = self._repo.get(identifier)

        if existing and existing.get("file_hash") == file_hash:
            # Unchanged: leave the immutable landing object and record as-is.
            self.log.info("document_unchanged", identifier=identifier, file_hash=file_hash)
            return "unchanged"

        version = short_hash(file_hash) if existing else None
        key = landing_key(
            record["body_key"], record["partition_date"], identifier, ext, version=version
        )
        self._store.put_if_absent(key, data, content_type_for(record["document_type"]))

        mongo_doc = build_record(
            identifier=identifier,
            title=record["title"],
            description=record["description"],
            decision_date=record["decision_date"],
            body_key=record["body_key"],
            body_name=record["body_name"],
            body_id=record["body_id"],
            partition_date=record["partition_date"],
            source_url=record["source_url"],
            document_url=record["document_url"],
            document_type=record["document_type"],
            storage_path=key,
            file_hash=file_hash,
            content_length=len(data),
            run_id=self._run_id,
        )
        self._repo.upsert(mongo_doc)

        outcome = "changed" if existing else "new"
        self.log.info(
            "document_stored",
            identifier=identifier,
            outcome=outcome,
            document_type=record["document_type"],
            storage_path=key,
            file_hash=file_hash,
            bytes=len(data),
        )
        return outcome
