"""Tests for the transformation step's per-record logic (with in-memory fakes)."""

from wrc_pipeline.hashing import sha256_hex
from wrc_pipeline.transform.html_cleaner import clean_html
from wrc_pipeline.transform.transformer import _process_record

HTML_PAGE = b"""
<html><body>
  <nav>NAVIGATION</nav><header>HEADER</header>
  <div class="content"><h1>ADJ-1</h1><p>The decision text.</p></div>
  <footer>FOOTER</footer>
</body></html>
"""
PDF_BYTES = b"%PDF-1.7 binary decision content"


class FakeStore:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    def get_bytes(self, key):
        return self.objects[key]

    def put_bytes(self, key, data, content_type=None):
        self.objects[key] = data


class FakeRepo:
    def __init__(self):
        self.docs = {}

    def get(self, _id):
        return self.docs.get(_id)

    def upsert(self, rec):
        self.docs[rec["_id"]] = rec


def _stats():
    return {"processed": 0, "transformed_html": 0, "copied_asis": 0,
            "unchanged": 0, "failed": 0, "failures": []}


def _record(identifier, doc_type, url, storage_path):
    return {
        "_id": identifier, "identifier": identifier, "document_type": doc_type,
        "document_url": url, "storage_path": storage_path, "file_hash": "old",
        "body_key": "labour_court", "partition_date": "2024-01",
        "decision_date": None, "title": "t", "description": "d",
        "body_name": "LC", "body_id": 3, "source_url": url,
    }


def test_html_is_cleaned_renamed_rehashed():
    src = FakeStore({"labour_court/2024-01/ADJ-1.html": HTML_PAGE})
    dst_repo, dst_store, stats = FakeRepo(), FakeStore(), _stats()
    rec = _record("ADJ-1", "html", "http://x/adj-1.html", "labour_court/2024-01/ADJ-1.html")

    _process_record(rec, src, dst_repo, dst_store, stats)

    assert stats == {"processed": 1, "transformed_html": 1, "copied_asis": 0,
                     "unchanged": 0, "failed": 0, "failures": []}
    # Renamed to identifier.ext in the curated bucket.
    assert "ADJ-1.html" in dst_store.objects
    cleaned = dst_store.objects["ADJ-1.html"].decode()
    assert "decision text" in cleaned and "NAVIGATION" not in cleaned
    # New hash recorded, provenance preserved.
    curated = dst_repo.docs["ADJ-1"]
    assert curated["file_hash"] == sha256_hex(clean_html(HTML_PAGE, title="ADJ-1"))
    assert curated["original_file_hash"] == "old"
    assert curated["original_storage_path"] == "labour_court/2024-01/ADJ-1.html"


def test_pdf_is_copied_as_is():
    src = FakeStore({"eat/2011-12/UD-1.pdf": PDF_BYTES})
    dst_repo, dst_store, stats = FakeRepo(), FakeStore(), _stats()
    rec = _record("UD-1", "pdf", "http://x/ud-1.pdf", "eat/2011-12/UD-1.pdf")

    _process_record(rec, src, dst_repo, dst_store, stats)

    assert stats["copied_asis"] == 1 and stats["transformed_html"] == 0
    assert dst_store.objects["UD-1.pdf"] == PDF_BYTES  # byte-for-byte
    assert dst_repo.docs["UD-1"]["file_hash"] == sha256_hex(PDF_BYTES)


def test_idempotent_when_curated_hash_matches():
    src = FakeStore({"eat/2011-12/UD-1.pdf": PDF_BYTES})
    dst_repo, dst_store, stats = FakeRepo(), FakeStore(), _stats()
    dst_repo.docs["UD-1"] = {"_id": "UD-1", "file_hash": sha256_hex(PDF_BYTES)}
    rec = _record("UD-1", "pdf", "http://x/ud-1.pdf", "eat/2011-12/UD-1.pdf")

    _process_record(rec, src, dst_repo, dst_store, stats)

    assert stats["unchanged"] == 1 and stats["processed"] == 1
    assert dst_store.objects == {}  # nothing rewritten


def test_missing_landing_file_is_recorded_as_failure():
    dst_repo, dst_store, stats = FakeRepo(), FakeStore(), _stats()
    rec = _record("ADJ-2", "html", "http://x/adj-2.html", "missing/key.html")

    _process_record(rec, FakeStore(), dst_repo, dst_store, stats)

    assert stats["failed"] == 1
    assert stats["failures"][0]["identifier"] == "ADJ-2"
