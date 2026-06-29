# Architecture

A two-zone pipeline. **Ingestion** (Scrapy) scrapes the WRC decisions database
into a **Landing Zone** — raw bytes in object storage (MinIO) + metadata in
MongoDB. **Transformation** reads a date slice of the landing zone, cleans HTML,
renames/re-hashes files, and writes a **Curated Zone** (new bucket + collection).
The landing zone is append-only and never mutated.

```
 search GET (body × month) ─▶ listing parse ─▶ document fetch ─▶ persistence
                                (metadata)       (html/pdf)        pipeline
                                                                      │
        MongoDB landing_decisions  ◀──────────────┬──────────────────┘
        MinIO  landing bucket      ◀──────────────┘
                       │
        Transformation: BeautifulSoup clean (HTML) / passthrough (PDF)
                       └─▶ MinIO curated bucket + MongoDB curated_decisions
```

Orchestrated by **Dagster** (`ingest → transform`, a data dependency so transform
runs strictly after ingest). The crawl runs in a subprocess — Twisted's reactor
cannot be restarted inside a long-lived worker.

## Why monthly partitions
The scraper walks `(body × date-window)`. **Monthly** keeps each query small
(tens–hundreds of results, within the site's pageable range), gives a meaningful
`partition_date` (`2024-01`), and yields independent units that parallelise and
make reruns/back-fills granular. Size is configurable (`weekly`/`monthly`/
`yearly`) — dense bodies can go weekly, sparse legacy bodies yearly, no code
changes.

## Retries & rate limiting
"Fastest without getting blocked" = concurrency with restraint. **AutoThrottle**
adapts the delay to server latency, bounded by `CONCURRENT_REQUESTS` /
`DOWNLOAD_DELAY`; transient `408/429/5xx` are retried by Scrapy's
`RetryMiddleware`. We send a descriptive User-Agent, obey `robots.txt`, and
disable cookies (stateless GETs). Permanent failures hit per-request errbacks and
are recorded, never silently dropped. *(robots.txt disallows the legacy
capital-C `/en/Cases/` and `*_Import/` paths; live decisions are at lowercase
`/en/cases/` — distinct, allowed paths, robots being case-sensitive per RFC 9309.)*

## Deduplication / idempotency
1. **Record** — upserted by `identifier` (Mongo `_id`), so reruns never duplicate.
   The identifier is the decision's unique **URL slug** (`ADJ-00047352`), not the
   listing "Ref no", which is *not* unique (one ref → several documents).
2. **Content** — every document is SHA-256 hashed and the hash is stored. Matching
   hash ⇒ bytes not rewritten; differing hash ⇒ written under a versioned key
   (`identifier__<hash>.ext`) so prior versions survive, and the metadata pointer
   updates.

Published decisions are **immutable**, so the default rerun **skips
already-ingested identifiers** via a downloader middleware — no duplicate records
and **no re-download of unchanged files** (verified: a second run reports every
record `skipped`, zero fetches). The file hash is the integrity/dedup key; because
the source sends no `ETag`/`Last-Modified`, detecting a change requires a fetch, so
`WRC_RECHECK_EXISTING=true` re-fetches known documents and uses the hash to catch
the rare corrected/republished decision. (WRC HTML embeds a per-request
`<!-- Elapsed time -->` comment; we strip that one volatile marker before hashing
so a re-fetch isn't a false "changed".) **Reconciliation:** per `(body, partition)`
we log *found* vs *new/changed/unchanged/skipped* vs *failed* (URL + reason), so
every record is accounted for.

## Scaling to 50+ sources
Site-specific code is isolated (a spider, the `sources.py` body map, selectors);
the spine — partitioning, hashing, idempotent storage adapters, JSON logging, the
transform contract, the Dagster shape — is source-agnostic. I would: model each
source as config + a small spider on a shared `DecisionItem` contract and one
persistence pipeline; turn `(source × body × partition)` into **Dagster
partitioned assets** for free per-partition retries/back-fills/observability;
scale ingestion as workers keyed by partition and move the synchronous Mongo/S3
writes behind batched/async writers (at 1000× the write path, not parsing, is the
bottleneck); add schema validation and per-source dashboards off the JSON logs.
MongoDB (flexible schema) and S3 (unbounded) already fit a heterogeneous corpus.
