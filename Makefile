# Convenience targets. On Windows without `make`, run the underlying commands
# shown in each recipe directly (see README).

.PHONY: install up down logs scrape transform dagster test lint fmt clean

install:        ## Install the package with dev + orchestration extras
	pip install -e ".[dev,orchestration]"

up:             ## Start storage containers (mongo + minio + bucket init)
	docker compose up -d mongo minio createbuckets

down:           ## Stop and remove containers
	docker compose down

logs:           ## Tail container logs
	docker compose logs -f

scrape:         ## Run the crawl (override DATES, e.g. make scrape START=2024-01-01 END=2024-02-01)
	wrc-scrape --start $(or $(START),2024-01-01) --end $(or $(END),2024-04-01)

transform:      ## Run the transformation step over the same window
	wrc-transform --start $(or $(START),2024-01-01) --end $(or $(END),2024-04-01)

dagster:        ## Launch the Dagster UI locally on http://localhost:3000
	dagster dev -m wrc_pipeline.orchestration.definitions

test:           ## Run unit tests
	pytest

lint:           ## Lint with ruff
	ruff check src tests

fmt:            ## Auto-format with ruff
	ruff format src tests

clean:          ## Remove caches
	rm -rf .pytest_cache .ruff_cache **/__pycache__
