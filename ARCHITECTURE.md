# Architecture

A two-zone pipeline. **Ingestion** scrapes the Workplace Relations Commission
decisions database into a **Landing Zone** (raw bytes in object storage + metadata
in MongoDB). **Transformation** reads a slice of the landing zone, cleans HTML,
renames/re-hashes files and writes a **Curated Zone** (new bucket + new
collection). The landing zone is append-only and never mutated.

```
                 ┌─────────── Ingestion (Scrapy) ───────────┐
 search GET ──▶  listing parse ──▶ document fetch ──▶ persistence
 (body × month)     (metadata)        (html/pdf)      pipeline
                                                          │
                       ┌──────────────────────────────────┼───────────┐
                       ▼                                   ▼           ▼
                MongoDB landing_decisions          MinIO landing bucket
                       │                                   │
                 ┌─────┴──────── Transformation ───────────┘
                 ▼
   BeautifulSoup clean (HTML) / passthrough (PDF) ──▶ MinIO curated bucket
                 └──────────────────────────────────▶ MongoDB curated_decisions
```

Orchestrated by **Dagster** (`ingest` → `transform`, with a data dependency so
transform runs strictly after ingest). The crawl runs in a subprocess because
Twisted's reactor cannot be restarted inside a long-lived worker.

## Why monthly partitions
The scraper walks `(body × date-window)`. **Monthly** is the default because it
keeps each search query small (typically tens to a few hundred results, well
within the site's pageable range), produces a human-meaningful `partition_date`
(`2024-01`), and yields independent units of work that parallelise cleanly and
make reruns and back-fills granular. The window size is configurable
(`weekly`/`monthly`/`yearly`); dense bodies (WRC) can use weekly, sparse legacy
bodies (EAT) yearly — all without code changes.

## Retries & rate limiting
"Fastest without getting blocked" = concurrency with built-in restraint.
**AutoThrottle** adapts the delay to observed server latency (fast when healthy,
backing off under load), bounded by `CONCURRENT_REQUESTS` and `DOWNLOAD_DELAY`.
Transient failures (`408/429/5xx`) are retried by Scrapy's `RetryMiddleware`
(`RETRY_TIMES`, exponential by default). We send a descriptive User-Agent, obey
`robots.txt`, and disable cookies (the endpoints are stateless GETs). Permanent
failures are caught by per-request errbacks and recorded — never silently
dropped (see reconciliation below).

> **robots.txt note:** the site disallows the legacy capital-C `/en/Cases/` and
> `*_Import/` paths. Current decisions are served at lowercase `/en/cases/` and
> search at `/en/search/` — distinct, non-disallowed paths (robots paths are
> case-sensitive per RFC 9309). We obey robots and stay polite regardless.

## Deduplication / idempotency
Two independent levels:
1. **Record** — metadata is upserted by `identifier` (the Mongo `_id`), so
   reruns can never create duplicate records.
2. **Content** — every document is SHA-256 hashed. If the hash matches the stored
   value the bytes are *not* rewritten (no churn). If it differs, the new bytes
   are written under a hash-versioned key (`identifier__<hash>.ext`) so prior
   versions survive (append-only landing zone) and the metadata pointer + hash
   are updated.

The WRC HTML pages embed a per-request render-time comment
(`<!-- Elapsed time: ... -->`) that changes on every fetch. We strip that single
volatile marker before hashing/storing, otherwise every rerun would look
"changed". This keeps the hash a faithful signal of *real* content change while
preserving genuine idempotency (verified live: a second run reports all records
`unchanged` with zero new objects).

The source sends no `ETag`/`Last-Modified` and `Cache-Control: no-cache`, so HTTP
conditional requests can't short-circuit the fetch — hashing is the source of
truth for change detection, exactly as the brief specifies. For a pure
"no re-download" rerun, `WRC_RECHECK_EXISTING=false` skips already-known
identifiers entirely via a downloader middleware. **Reconciliation:** per
`(body, partition)` we log records *found* vs *new/changed/unchanged/skipped* vs
*failed* (with URL + reason), so every record is accounted for (N, or N−X with
each X explained).

## Scaling to 50+ sources
The site-specific parts are isolated: a `Spider`, a `sources.py` body map, and
listing selectors. The reusable spine — partitioning, hashing, idempotent
storage adapters, structured logging, the transform contract, and the Dagster
shape — is source-agnostic. To add sources I would:
- model each source as config + a small spider implementing a common contract
  (yield `DecisionItem` with raw bytes); keep one shared persistence pipeline;
- turn `(source × body × partition)` into **Dagster partitioned assets**, giving
  per-partition retries, backfills and observability for free;
- run ingestion as horizontally-scaled workers keyed by partition; move the
  synchronous Mongo/S3 writes behind batched/async writers (and per-source rate
  limits) since at 1000× volume the write path, not parsing, is the bottleneck;
- add a schema/validation layer and per-source dashboards off the existing JSON
  logs. MongoDB (flexible schema) and S3 (effectively unbounded) already suit a
  heterogeneous, high-volume corpus.
