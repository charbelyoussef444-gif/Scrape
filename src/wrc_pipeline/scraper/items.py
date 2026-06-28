"""The item produced by the spider and consumed by the persistence pipeline.

It carries the listing metadata plus the raw document bytes; the pipeline is
responsible for hashing, storing the bytes and upserting the metadata record.
"""

from __future__ import annotations

import scrapy


class DecisionItem(scrapy.Item):
    # --- Metadata scraped from the search listing ---
    identifier = scrapy.Field()
    title = scrapy.Field()
    description = scrapy.Field()
    decision_date = scrapy.Field()  # datetime.date | None

    # --- Provenance / partitioning ---
    body_key = scrapy.Field()
    body_name = scrapy.Field()
    body_id = scrapy.Field()
    partition_date = scrapy.Field()
    source_url = scrapy.Field()
    document_url = scrapy.Field()
    document_type = scrapy.Field()  # "html" | "pdf" | "doc"

    # --- Payload (consumed and dropped by the pipeline, never stored in Mongo) ---
    document_bytes = scrapy.Field()
