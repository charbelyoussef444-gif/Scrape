"""Storage adapters: MongoDB (metadata) and S3/MinIO (objects)."""

from wrc_pipeline.storage.mongo import MongoRepository
from wrc_pipeline.storage.object_store import ObjectStore

__all__ = ["MongoRepository", "ObjectStore"]
