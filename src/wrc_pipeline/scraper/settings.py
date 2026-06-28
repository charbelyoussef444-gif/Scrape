"""Scrapy settings, derived from the project's typed configuration.

Scrapy reads module-level UPPERCASE names. We translate our ``Settings`` object
into those names here so there is exactly one source of truth for tunables.
"""

from wrc_pipeline.config import get_settings

_s = get_settings()

BOT_NAME = "wrc"
SPIDER_MODULES = ["wrc_pipeline.scraper.spiders"]
NEWSPIDER_MODULE = "wrc_pipeline.scraper.spiders"

# --- Identity & politeness ---------------------------------------------------
USER_AGENT = _s.user_agent
ROBOTSTXT_OBEY = _s.robotstxt_obey
COOKIES_ENABLED = False  # search/detail pages are stateless GETs

# --- Throughput vs. being a good citizen ------------------------------------
# AutoThrottle adapts the delay to the server's latency: fast when the site is
# responsive, backing off automatically under load. This is the "fastest way to
# scrape without getting blocked" — concurrency with built-in restraint.
CONCURRENT_REQUESTS = _s.concurrent_requests
CONCURRENT_REQUESTS_PER_DOMAIN = _s.concurrent_requests
DOWNLOAD_DELAY = _s.download_delay
DOWNLOAD_TIMEOUT = _s.download_timeout

AUTOTHROTTLE_ENABLED = _s.autothrottle_enabled
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 10.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 4.0

# --- Resilience --------------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = _s.retry_times
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504, 522, 524]

# --- Components --------------------------------------------------------------
DOWNLOADER_MIDDLEWARES = {
    "wrc_pipeline.scraper.middlewares.SkipKnownDocumentsMiddleware": 543,
}
ITEM_PIPELINES = {
    "wrc_pipeline.scraper.pipelines.PersistencePipeline": 300,
}

# --- Logging -----------------------------------------------------------------
# We render logs ourselves (structlog JSON). The runner installs the handler and
# disables Scrapy's own root handler so all output is uniform JSON.
LOG_LEVEL = _s.log_level
TELNETCONSOLE_ENABLED = False

# Forward-compatible Scrapy defaults.
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
