"""S3-compatible object storage (MinIO) wrapper.

Used for both the landing bucket (raw downloads) and the curated bucket
(transformed output). Path-style addressing is forced so the same code talks to
MinIO locally and to real S3 in production by changing only the endpoint URL.
"""

from __future__ import annotations

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

# Map our document types to sensible Content-Type values.
CONTENT_TYPES = {
    "html": "text/html; charset=utf-8",
    "pdf": "application/pdf",
    "doc": "application/msword",
}


class ObjectStore:
    """Wrapper around one S3/MinIO bucket."""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
        bucket: str,
    ) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    @property
    def bucket(self) -> str:
        return self._bucket

    def ensure_bucket(self) -> None:
        """Create the bucket if it does not already exist."""
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, **extra)

    def put_if_absent(self, key: str, data: bytes, content_type: str | None = None) -> bool:
        """Write ``data`` only if ``key`` does not exist. Returns True if written.

        This keeps the landing zone append-only: identical content at the same
        key is never rewritten, which is the object-storage half of idempotency.
        """
        if self.exists(key):
            return False
        self.put_bytes(key, data, content_type)
        return True

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()


def content_type_for(document_type: str) -> str:
    return CONTENT_TYPES.get(document_type, "application/octet-stream")
