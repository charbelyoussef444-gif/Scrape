"""Canonical data model and storage-key helpers.

A single source of truth for: how we classify a document (HTML vs PDF/DOC), how
we name objects in the landing and curated buckets, and how a metadata record is
shaped in MongoDB. Keeping these here avoids drift between the spider, the
pipeline and the transformation step.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlparse

# Identifier normalisation ----------------------------------------------------

_WS_AROUND_HYPHEN = re.compile(r"\s*-\s*")
_WHITESPACE = re.compile(r"\s+")


# WRC HTML pages embed a per-request render-time comment, e.g.
# "<!-- Elapsed time: 0.0156026 -->", which changes on every fetch. Left in, it
# would make the file hash differ on each run and break landing-zone idempotency.
# We strip it so the stored bytes (and their hash) are stable, while genuine
# content changes are still detected.
_VOLATILE_HTML = re.compile(rb"<!--\s*Elapsed time:.*?-->", re.IGNORECASE | re.DOTALL)


def canonicalize_for_storage(document_type: str, data: bytes) -> bytes:
    """Remove per-request volatile markers so identical documents hash equally."""
    if document_type == "html":
        return _VOLATILE_HTML.sub(b"", data)
    return data


def normalize_identifier(raw: str) -> str:
    """Canonicalise a decision reference.

    The listing renders some references with spaces around the hyphens
    (e.g. ``"IR - SC - 00001785"``) while the URL slug uses the compact form
    (``ir-sc-00001785``). We collapse spaces around hyphens and uppercase, so the
    same decision always yields one stable identifier (used as the Mongo ``_id``
    and the curated filename).
    """
    collapsed = _WS_AROUND_HYPHEN.sub("-", raw.strip())
    collapsed = _WHITESPACE.sub(" ", collapsed)
    return collapsed.upper()


def identifier_from_url(url: str) -> str:
    """Derive the canonical identifier from a decision's detail-page URL slug.

    The slug is the authoritative unique key: the listing's "Ref no" is *not*
    unique (one ref can map to several documents), whereas each decision has a
    distinct detail URL, e.g. ``/en/cases/2011/december/ud1301_2010.html`` ->
    ``UD1301_2010``. For recent WRC/Labour Court decisions this equals the
    displayed reference (``adj-00047352`` -> ``ADJ-00047352``).
    """
    slug = os.path.splitext(os.path.basename(urlparse(url).path))[0]
    return normalize_identifier(slug.strip("_-. "))


# Document classification -----------------------------------------------------

PDF_EXTS = {".pdf"}
DOC_EXTS = {".doc", ".docx", ".rtf"}
HTML_EXTS = {".html", ".htm"}


def detect_document_type(url: str) -> str:
    """Classify a document URL as ``"pdf"``, ``"doc"`` or ``"html"``.

    The WRC listing links recent decisions to ``*.html`` detail pages and older
    (EAT / Equality Tribunal) decisions to ``*.pdf`` files. Anything without a
    recognised binary extension is treated as an HTML page to be scraped.
    """
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOC_EXTS:
        return "doc"
    return "html"


def document_extension(url: str, document_type: str) -> str:
    """Return the on-disk file extension (with leading dot) for a document."""
    if document_type == "html":
        return ".html"
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    return ext or (".pdf" if document_type == "pdf" else ".bin")


# Object-storage key layout ---------------------------------------------------


def landing_key(
    body_key: str,
    partition_label: str,
    identifier: str,
    ext: str,
    version: str | None = None,
) -> str:
    """Build the landing-bucket object key.

    Layout: ``{body}/{partition}/{identifier}{__version}{ext}``. The optional
    version suffix (a short hash) is only used when a document's content changes
    between runs, so prior bytes are never overwritten (the landing zone is
    append-only / immutable).
    """
    suffix = f"__{version}" if version else ""
    return f"{body_key}/{partition_label}/{identifier}{suffix}{ext}"


def curated_key(identifier: str, ext: str) -> str:
    """Build the curated-bucket key: files are renamed to ``identifier.ext``."""
    return f"{identifier}{ext}"


# Metadata record -------------------------------------------------------------


def build_record(
    *,
    identifier: str,
    title: str,
    description: str,
    decision_date: date | None,
    body_key: str,
    body_name: str,
    body_id: int,
    partition_date: str,
    source_url: str,
    document_url: str,
    document_type: str,
    storage_path: str,
    file_hash: str,
    content_length: int,
    run_id: str,
) -> dict[str, Any]:
    """Assemble a MongoDB metadata document.

    ``_id`` is the identifier, which gives us free record-level idempotency:
    re-scraping the same decision upserts the same document instead of creating
    a duplicate.
    """
    now = datetime.now(UTC)
    return {
        "_id": identifier,
        "identifier": identifier,
        "title": title,
        "description": description,
        # store as datetime for range queries in the transform step
        "decision_date": _to_datetime(decision_date),
        "body_key": body_key,
        "body_name": body_name,
        "body_id": body_id,
        "partition_date": partition_date,
        "source_url": source_url,
        "document_url": document_url,
        "document_type": document_type,
        "storage_path": storage_path,
        "file_hash": file_hash,
        "content_length": content_length,
        "scraped_at": now,
        "last_run_id": run_id,
    }


def _to_datetime(value: date | None) -> datetime | None:
    if value is None:
        return None
    return datetime(value.year, value.month, value.day, tzinfo=UTC)
