"""Content hashing helpers.

A single, well-defined hash function is used everywhere (download dedup,
change detection between runs, and the transformation step's re-hash) so the
values are directly comparable across the pipeline.
"""

from __future__ import annotations

import hashlib

HASH_ALGORITHM = "sha256"


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def short_hash(digest_hex: str, length: int = 12) -> str:
    """Short prefix of a hex digest, used to version changed objects on disk."""
    return digest_hex[:length]
