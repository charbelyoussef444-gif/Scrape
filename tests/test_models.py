"""Tests for document classification and storage-key helpers."""

from datetime import date

from wrc_pipeline.hashing import sha256_hex
from wrc_pipeline.models import (
    build_record,
    canonicalize_for_storage,
    curated_key,
    detect_document_type,
    document_extension,
    landing_key,
    normalize_identifier,
)


def test_canonicalize_strips_volatile_render_time():
    a = b"<html><body>Decision text</body></html><!-- Elapsed time: 0.0156026 -->"
    b = b"<html><body>Decision text</body></html><!-- Elapsed time: 0.0312594 -->"
    # Same document fetched twice -> identical canonical bytes & hash (idempotent).
    assert canonicalize_for_storage("html", a) == canonicalize_for_storage("html", b)
    assert sha256_hex(canonicalize_for_storage("html", a)) == sha256_hex(
        canonicalize_for_storage("html", b)
    )
    # A genuine content change is still detected.
    c = b"<html><body>DIFFERENT text</body></html><!-- Elapsed time: 0.01 -->"
    assert canonicalize_for_storage("html", a) != canonicalize_for_storage("html", c)


def test_canonicalize_leaves_binary_untouched():
    pdf = b"%PDF-1.7\x00\x01 binary <!-- Elapsed time: 1 -->"
    assert canonicalize_for_storage("pdf", pdf) == pdf


def test_normalize_identifier():
    # Spaces around hyphens (as some listing rows render) are collapsed.
    assert normalize_identifier("IR - SC - 00001785") == "IR-SC-00001785"
    assert normalize_identifier("adj-00047352") == "ADJ-00047352"
    assert normalize_identifier("  DEC-E2024-001  ") == "DEC-E2024-001"


def test_detect_document_type():
    assert detect_document_type("/en/cases/2024/january/adj-1.html") == "html"
    assert detect_document_type("https://x/y/decision.PDF") == "pdf"
    assert detect_document_type("https://x/y/decision.docx") == "doc"
    assert detect_document_type("https://x/y/decision") == "html"  # no extension


def test_document_extension():
    assert document_extension("/a/b.html", "html") == ".html"
    assert document_extension("/a/b.pdf", "pdf") == ".pdf"
    assert document_extension("/a/b.docx", "doc") == ".docx"


def test_landing_key_layout_and_versioning():
    base = landing_key("labour_court", "2024-01", "LCR-1", ".html")
    assert base == "labour_court/2024-01/LCR-1.html"
    versioned = landing_key("labour_court", "2024-01", "LCR-1", ".html", version="abc123")
    assert versioned == "labour_court/2024-01/LCR-1__abc123.html"


def test_curated_key_renames_to_identifier():
    assert curated_key("ADJ-00047352", ".html") == "ADJ-00047352.html"


def test_build_record_uses_identifier_as_id():
    rec = build_record(
        identifier="ADJ-1", title="ADJ-1", description="A v B",
        decision_date=date(2024, 1, 31), body_key="wrc", body_name="WRC", body_id=15376,
        partition_date="2024-01", source_url="http://x", document_url="http://x",
        document_type="html", storage_path="wrc/2024-01/ADJ-1.html",
        file_hash="deadbeef", content_length=10, run_id="run1",
    )
    assert rec["_id"] == "ADJ-1"
    assert rec["decision_date"].year == 2024
    assert rec["file_hash"] == "deadbeef"
    assert "document_bytes" not in rec
