# WRC Decisions Scraping Pipeline

A Scrapy-based pipeline that scrapes legal decisions and metadata from the
[Workplace Relations Commission decisions database](https://www.workplacerelations.ie/en/search/),
stores raw documents in object storage and metadata in a NoSQL database
(the **Landing Zone**), then runs a transformation step into a **Curated Zone**.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design rationale (partitioning,
retries/rate-limiting, deduplication, scaling to 50+ sources).

## What it does

- Scrapes each **body** (Workplace Relations Commission, Labour Court, Equality
  Tribunal, Employment Appeals Tribunal), partitioning the date range into
  monthly windows and stamping every record with a `partition_date`.
- Extracts metadata (identifier, title, description, decision date, document
  link, partition) into **MongoDB**.
- Downloads documents into **MinIO** object storage: PDFs/DOCs stored as-is,
  HTML decision pages saved as `.html`. Legacy decisions (EAT / Equality
  Tribunal) render an HTML stub linking to the real PDF; the spider follows that
  one hop and stores the actual PDF.
- Stores each file's path and **SHA-256 hash** in its metadata record.
- Is **idempotent**: a rerun creates no duplicate records and, by default, does
  **not re-download** already-ingested decisions (they're immutable once
  published). The SHA-256 file hash is stored and is the change-detection key —
  set `WRC_RECHECK_EXISTING=true` to re-fetch known documents and detect the rare
  corrected/republished decision (changed files are versioned). See ARCHITECTURE.md.
- Emits **structured JSON logs** (per-partition progress, found vs scraped,
  failures with URL + reason, and an end-of-run summary).
- A **transformation** step cleans HTML to the relevant decision content
  (BeautifulSoup), renames files to `identifier.ext`, re-hashes, and writes a new
  bucket + collection — without modifying the landing zone.
- Orchestrated with **Dagster** (`ingest → transform`); CLI runs also supported.

## Prerequisites

- Python 3.11+ and Docker (with the Docker Compose plugin).

## Setup

```bash
# 1. Configuration — copy and adjust if needed (defaults work out of the box).
cp .env.example .env

# 2. Start storage (MongoDB + MinIO) and create the buckets.
docker compose up -d mongo minio createbuckets

# 3. Install the package (a virtualenv is recommended).
pip install -e ".[dev,orchestration]"
```

MinIO console: http://localhost:9001 (user/pass from `.env`, default
`minioadmin`/`minioadmin`). MongoDB: `mongodb://localhost:27017`.

### Windows (PowerShell)

The blocks above are bash; the PowerShell equivalents for setup are:

```powershell
Copy-Item .env.example .env
docker compose up -d mongo minio createbuckets
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev,orchestration]"
```

Once the venv is activated, the `wrc-scrape` / `wrc-transform` / `pytest` /
`dagster` commands below work identically. PowerShell-specific notes:
- Set an env var with `$env:NAME = "value"` (e.g. `$env:WRC_RECHECK_EXISTING = "false"`).
- Launch the Dagster UI with:
  `$env:DAGSTER_HOME = (Get-Location).Path; dagster dev -m wrc_pipeline.orchestration.definitions`
- **Long paths:** clone to a short directory (e.g. `C:\Scrape`) or enable Windows
  long-path support. Dagster ships some long filenames that can exceed the legacy
  260-char `MAX_PATH` limit if installed under a very deep directory.

## Run — command line

```bash
# Ingest: scrape all bodies, Jan–Mar 2024 (end date is exclusive), monthly.
wrc-scrape --start 2024-01-01 --end 2024-04-01 --partition monthly

# ...or a single body (and cap the number of docs, handy for a quick sample):
wrc-scrape --start 2024-01-01 --end 2024-02-01 --bodies labour_court --limit 20

# Transform the same window into the curated zone.
wrc-transform --start 2024-01-01 --end 2024-04-01
```

Re-running the same `wrc-scrape` command is safe: it will report records as
`unchanged` and won't duplicate anything.

## Run — Dagster (orchestrated)

```bash
# Local UI at http://localhost:3000 (DAGSTER_HOME uses the provided dagster.yaml)
DAGSTER_HOME=$(pwd) dagster dev -m wrc_pipeline.orchestration.definitions
```

In the UI, open the `wrc_ingestion_pipeline` job → **Launchpad**, set the run
config, and launch:

```yaml
ops:
  ingest:
    config:
      start_date: "2024-01-01"
      end_date: "2024-04-01"
      partition_size: "monthly"
      bodies: ""          # empty = all bodies
```

Or run the whole stack (storage + Dagster) in containers:

```bash
docker compose --profile orchestration up -d
```

## Inspecting results

```bash
# Metadata (landing + curated collections)
docker compose exec mongo mongosh wrc --eval 'db.landing_decisions.countDocuments()'
docker compose exec mongo mongosh wrc --eval 'db.landing_decisions.findOne()'

# Objects: browse buckets in the MinIO console (http://localhost:9001).
```

## Configuration

Everything is configured via environment variables (or `.env`) — there are no
hardcoded connection strings, paths, partition sizes or scraping parameters.
See [.env.example](.env.example) for the full list (Mongo, MinIO, date window,
partition size, bodies, politeness/retry knobs, idempotency mode).

## Development

```bash
pytest                  # unit tests (no services required — uses fakes + mongomock)
ruff check src tests    # lint
ruff format src tests   # format
```

## Project layout

```
src/wrc_pipeline/
├── config.py            # typed env-driven settings
├── logging_config.py    # structlog JSON logging
├── sources.py           # the four WRC bodies + their site IDs
├── partitioning.py      # date-window iterator (partition_date)
├── hashing.py           # SHA-256 helpers
├── models.py            # document classification + storage keys + record shape
├── factories.py         # wire settings -> storage adapters
├── storage/             # MongoRepository + ObjectStore (MinIO/S3)
├── scraper/             # Scrapy: spider, middleware, pipeline, accounting, runner
├── transform/           # BeautifulSoup cleaner + transformation runner
├── orchestration/       # Dagster ingest -> transform job
└── cli.py               # wrc-scrape / wrc-transform entrypoints
```
