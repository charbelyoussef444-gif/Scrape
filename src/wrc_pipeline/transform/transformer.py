"""Run transformations over a slice of the landing zone.

Given a date range it:

1. fetches the matching metadata from the landing MongoDB collection,
2. pulls each file from the landing object store,
3. transforms it:
     * PDF / DOC  -> kept byte-for-byte (no transformation),
     * HTML       -> reduced to the relevant decision content (BeautifulSoup),
4. recomputes the file hash,
5. renames the file to ``identifier.ext`` and writes it to the curated bucket,
6. upserts the new metadata (new path + new hash) into the curated collection.

The landing zone is never modified. The step is idempotent: a curated object/
record whose hash already matches is left untouched.
"""

from __future__ import annotations

from datetime import date

from wrc_pipeline.config import Settings, get_settings
from wrc_pipeline.factories import curated_repo, curated_store, landing_repo, landing_store
from wrc_pipeline.hashing import sha256_hex
from wrc_pipeline.logging_config import get_logger
from wrc_pipeline.models import curated_key, document_extension
from wrc_pipeline.storage.object_store import content_type_for

log = get_logger("wrc.transform")


def run_transform(
    start_date: date,
    end_date: date,
    settings: Settings | None = None,
) -> dict:
    """Transform landing records in ``[start_date, end_date)``. Returns a summary."""
    settings = settings or get_settings()

    src_repo = landing_repo(settings)
    src_store = landing_store(settings)
    dst_repo = curated_repo(settings)
    dst_store = curated_store(settings)
    dst_store.ensure_bucket()
    dst_repo.ensure_indexes()

    stats = {
        "processed": 0, "transformed_html": 0, "copied_asis": 0,
        "unchanged": 0, "failed": 0, "failures": [],
    }

    try:
        records = src_repo.find_by_date_range(start_date, end_date)
        log.info(
            "transform_start",
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            candidates=len(records),
        )
        for record in records:
            _process_record(record, src_store, dst_repo, dst_store, stats)
    finally:
        src_repo.close()
        dst_repo.close()

    log.info("transform_summary", **stats)
    return stats


def _process_record(record, src_store, dst_repo, dst_store, stats) -> None:
    identifier = record["identifier"]
    try:
        raw = src_store.get_bytes(record["storage_path"])
        document_type = record["document_type"]

        if document_type == "html":
            from wrc_pipeline.transform.html_cleaner import clean_html

            output = clean_html(raw, title=identifier)
        else:
            output = raw  # PDF/DOC stored verbatim

        new_hash = sha256_hex(output)
        ext = document_extension(record["document_url"], document_type)
        new_key = curated_key(identifier, ext)

        existing = dst_repo.get(identifier)
        if existing and existing.get("file_hash") == new_hash:
            # Already transformed with identical result -> idempotent no-op.
            stats["unchanged"] += 1
            stats["processed"] += 1
            return

        dst_store.put_bytes(new_key, output, content_type_for(document_type))
        dst_repo.upsert(_curated_record(record, new_key, new_hash, len(output)))
        # Count outcomes mutually exclusively: transformed/copied are *writes*.
        stats["transformed_html" if document_type == "html" else "copied_asis"] += 1
        stats["processed"] += 1
        log.info(
            "record_transformed",
            identifier=identifier,
            document_type=document_type,
            curated_path=new_key,
            file_hash=new_hash,
        )
    except Exception as exc:  # noqa: BLE001 - account for every failure
        stats["failed"] += 1
        stats["failures"].append({"identifier": identifier, "reason": str(exc)})
        log.error("record_transform_failed", identifier=identifier, error=str(exc))


def _curated_record(record: dict, new_key: str, new_hash: str, size: int) -> dict:
    """Carry metadata forward, updating the path/hash and keeping provenance."""
    curated = dict(record)
    curated["original_storage_path"] = record["storage_path"]
    curated["original_file_hash"] = record["file_hash"]
    curated["storage_path"] = new_key
    curated["file_hash"] = new_hash
    curated["content_length"] = size
    return curated
