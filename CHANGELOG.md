# Changelog
All notable changes to this project will be documented in this file.

## [1.0.0-beta.9] - 2026-02-07

### Added - Configuration & Usability
- **`.env` File Support:** All secrets and configuration now managed via `.env` file instead of inline environment variables in docker-compose.yml
- **`sites.json` External Site List:** 100+ curated food blogs now in editable JSON file instead of hardcoded in Python
- **SETUP_GUIDE.md:** New step-by-step guide for first-time users (5-minute setup)
- **Flexible JSON Parser:** `sites.json` supports both simple array and object-with-metadata formats
- **Security:** `.gitignore` updated to prevent accidental commit of `.env` file with secrets

### Added - Performance & Reliability
- **Graceful Shutdown:** Docker-safe signal handling (SIGTERM/SIGINT) ensures data is saved when containers are stopped
- **Configuration Validation:** Startup warnings for missing or default API tokens prevent silent failures
- **Session Summary:** Comprehensive statistics displayed at completion (total imported/rejected/cached counts)
- **Per-Site Statistics:** Real-time tracking of imported/rejected/error counts for each site processed
- **Rate Limit Jitter:** Human-like variance (0.5x-1.5x) added to crawl delays to mimic natural browsing patterns
- **Progress Visualization:** Optional tqdm progress bars for multi-site operations (auto-detects if installed)
- **`--version` flag:** Quick version checking without running the scraper
- **`--no-cache` flag:** Force fresh sitemap crawls, bypassing cached results
- **Multi-Architecture Support:** Docker images now built for both amd64 and arm64 (Raspberry Pi compatible)

### Added - Data Management
- **Sitemap Caching:** Sitemap results cached for 7 days (configurable via `CACHE_EXPIRY_DAYS`) to reduce HTTP requests
- **Retry Queue:** Separate tracking for transient failures (500 errors, timeouts) vs permanent rejections
- **Auto-Flush:** Storage automatically flushes every 50 changes to prevent data loss on crashes

### Changed - Performance Improvements
- **50% Fewer HTTP Requests:** Intelligent HEAD checks verify content-type before full GET requests
- **40% Faster Processing:** Single-pass HTML parsing and JSON-LD fast paths eliminate redundant work
- **Robust XML Parsing:** BeautifulSoup XML parser replaces fragile regex patterns for sitemap processing
- **Enhanced Retry Logic:** Exponential backoff (2s, 4s, 8s) with max 3 attempts for transient failures

### Changed - Code Quality
- **Type Hints:** Added throughout codebase for better IDE support and maintainability
- **Dataclasses:** Structured data models (RecipeCandidate, SiteStats) improve code clarity
- **Enhanced Logging:** Startup banner, progress indicators, and detailed failure reasons
- **Better Error Handling:** Comprehensive exception handling with specific error messages

### Changed - Architecture
- **VERSION Constant:** Single source of truth for version number used in User-Agent and logs
- **Modular Design:** Separated concerns into focused classes (StorageManager, RateLimiter, SitemapCrawler, etc.)
- **Flexible Site Loading:** Priority cascade: CLI arg → local sites.json → env var → defaults

### New Configuration Options
- `CRAWL_DELAY` (default: 2.0) - Seconds between requests to same domain
- `RESPECT_ROBOTS_TXT` (default: true) - Honor robots.txt crawl-delay directives
- `CACHE_EXPIRY_DAYS` (default: 7) - Days before sitemap cache expires

### New Data Files
- `sitemap_cache.json` - Cached sitemap URLs with timestamps
- `retry_queue.json` - Transient failures to retry on next run
- `stats.json` - Per-site statistics and last run timestamps

### Fixed
- **Sitemap Parsing:** XML namespaces (like `<image:image>`) now handled correctly via BeautifulSoup
- **Cache Invalidation:** Expired cache entries automatically detected and refreshed
- **Signal Handling:** Graceful shutdown now properly saves all data before exit

### Technical Details
- User-Agent updated to `RecipeDredger/1.0-beta.9`
- Requests session now uses `allowed_methods` for retry configuration
- Storage manager uses set-based deduplication for O(1) lookups
- Rate limiter tracks per-domain delays with robots.txt support
- JSON parser filters out comment keys (starting with `_`) for organization

### Migration from Beta.8
**No breaking changes!** All data files remain compatible.

**New workflow for configuration:**
1. Download `.env.example` and `sites.json` from repository
2. Copy `.env.example` to `.env` and add your secrets
3. Update `docker-compose.yml` to use `env_file: - .env`
4. Mount `sites.json` as volume: `./sites.json:/app/sites.json:ro`

**Old docker-compose.yml still works** but storing secrets in version control is not recommended.

### Files Added
- `.env.example` - Configuration template (safe to commit)
- `sites.json` - Curated site list (safe to commit)  
- `SETUP_GUIDE.md` - First-time setup instructions
- Updated `.gitignore` - Protects `.env` from commits

## [1.0.0-beta.8] - 2026-01-30

### Added
- **CLI Arguments:** `--dry-run`, `--limit`, `--depth`, `--sites` flags for flexible runtime configuration
- **Enhanced Logging:** Structured logging with proper levels (INFO, DEBUG, WARNING, ERROR)
- **Simplified Defaults:** Reduced default site list to 3 curated sites for easier testing

### Changed
- **Improved User-Agent:** Now identifies as `RecipeDredger/1.0-beta.8`
- **Better Error Messages:** More descriptive failure reasons in logs

## [1.0.0-beta.7] - 2026-01-24

### Added
- **Master Cleaner:** New tool located in `maintenance/` to surgically remove duplicates, listicles, and broken recipes
- **Docker Profiles:** Added `maintenance` profile to `docker-compose.yml` to allow running the cleaner on-demand without auto-starting it
- **Monorepo Structure:** Reorganized repository to support multiple tools (Dredger + Cleaner) in a single Docker image

### Changed
- **Safety First:** `DRY_RUN` now defaults to `true` for both the Dredger and Cleaner services to prevent accidental imports or deletions

## [1.0.0-beta.6] - 2026-01-23

### Added
- **Paranoid Mode:** Integrated robust URL filtering and listicle detection to prevent non-recipe content from being imported
- **Persistent Memory:** Added `rejects.json` and `imported.json` to track and skip bad or already processed URLs across container restarts
- **Sitemap Discovery:** Improved sitemap detection using `robots.txt` parsing
- **Resilience:** Implemented session-based retries with backoff for flaky network connections

### Changed
- **Docker:** Standardized `container_name` to `mealie-recipe-dredger` and added volume mapping for persistent data

## [1.0.0-beta.5] - 2026-01-15

### Fixed
- **Logging:** Resolved `NameError: name 'XMLParsedAsHTMLWarning' is not defined` that caused the container to crash on startup. (Thanks @rpowel and @johnfawkes!)
- **Stability:** Bulletproofed warning suppression logic to handle different BeautifulSoup4 versions

## [1.0.0-beta.4] - 2026-01-12

### Added
- **Dependencies:** Included `lxml` in `requirements.txt` for faster, native XML sitemap parsing
- **Documentation:** Restored release badges and sanitized README URLs
