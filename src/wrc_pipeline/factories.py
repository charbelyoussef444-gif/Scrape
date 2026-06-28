"""Construction helpers that wire :class:`Settings` to storage adapters.

Centralising this keeps connection details in one place and out of the spider,
pipeline, transform and CLI modules.
"""

from __future__ import annotations

from wrc_pipeline.config import Settings
from wrc_pipeline.storage import MongoRepository, ObjectStore


def landing_repo(settings: Settings) -> MongoRepository:
    return MongoRepository(settings.mongo_uri, settings.mongo_db, settings.landing_collection)


def curated_repo(settings: Settings) -> MongoRepository:
    return MongoRepository(settings.mongo_uri, settings.mongo_db, settings.curated_collection)


def landing_store(settings: Settings) -> ObjectStore:
    return _object_store(settings, settings.landing_bucket)


def curated_store(settings: Settings) -> ObjectStore:
    return _object_store(settings, settings.curated_bucket)


def _object_store(settings: Settings, bucket: str) -> ObjectStore:
    return ObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        bucket=bucket,
    )
