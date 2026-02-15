# Changelog
All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **Repeatable Site Alignment Feature:** Added reusable `site_alignment` module and `mealie-align-sites` CLI command for domain-policy reconciliation.
- **Dredger Diff Alignment Mode:** Optional pre-crawl alignment step (`ALIGN_RECIPES_WITH_SITES`) now prunes only removed domains (baseline -> current), preserving manual/external recipes outside diff scope.
- **Docker Alignment Task:** Added `TASK=align-sites` support in container entrypoint for env-file-backed alignment runs without host Python tooling.

### Changed
- **One-Off Cleanup Script Reused:** `scripts/oneoff/prune_by_sites.py` is now a compatibility wrapper around the shared site-alignment implementation.
- **Safer Live Alignment Apply:** `--apply` now prompts for `y/n` confirmation after preview by default; `--yes` / `ALIGN_SITES_ASSUME_YES=true` allow non-interactive automation.
- **Diff Logic Enforcement:** `mealie-align-sites` now requires `--baseline-sites-file` by default and only prunes baseline→current domain diffs; broad "outside current sites" pruning requires explicit unsafe opt-in.
- **Docker Baseline Seeding:** `scripts/docker/update.sh` now seeds `data/sites.baseline.json` once from repo `sites.json` for easier diff runs.
- **Alignment Candidate Audit Output:** Optional `ALIGN_SITES_AUDIT_FILE` / `--audit-file` now writes full candidate lists for recovery/audit before apply.
- **Pre-Delete Backup Option:** Alignment apply mode now offers optional Mealie API backup (`POST /api/admin/backups`) and supports forced backup via `--backup-before-apply` / `ALIGN_SITES_BACKUP_BEFORE_APPLY=true`.

## [1.0.0-beta.14] - 2026-02-10

### Added
- **Parallel Import Workers:** Added `IMPORT_WORKERS` to allow concurrent Mealie import requests for better throughput on slow `/api/recipes/create/url` responses.
- **One-Off Domain Cleanup Tool:** Added `scripts/oneoff/prune_by_sites.py` to prune existing imports by source-domain policy, including baseline-diff mode (`--baseline-sites-file`) to remove only domains removed from your sites list.

### Changed
- **Import Precheck Thread Safety:** Protected duplicate source-url precheck state with a lock to safely support concurrent imports.
- **Mealie Import Throttling:** Removed crawler-domain delay throttling from Mealie API import calls; crawl delay remains for scraped sites.
- **Fail-Fast Site Aborts:** Added `SITE_IMPORT_FAILURE_THRESHOLD` so repeated Mealie HTTP 5xx import failures abort a bad site early instead of burning an entire site quota.
- **Retry Queue Finalization:** Retry queue entries that hit max attempts are now rejected immediately in the same run (instead of waiting for another cycle).
- **Runtime Sites Persistence:** Docker runtime now prefers `SITES=/app/data/sites.json` when present, preventing update pulls from overwriting active site customizations.
- **Docker Build Robustness:** Image build no longer hard-requires a repo `sites.json` file.
- **Runtime Sites Fallback:** If no runtime sites file exists, entrypoint now falls back cleanly to built-in defaults instead of producing empty targets.
- **First-Deploy Sites Seeding:** `scripts/docker/update.sh` now seeds `data/sites.json` once from repo `sites.json` when missing.
- **Docs:** Updated README and setup guide with current runtime-sites behavior, performance tuning, and one-off cleanup workflow.

## [1.0.0-beta.13] - 2026-02-09

### Added
- **Import Duplicate Precheck:** Added `IMPORT_PRECHECK_DUPLICATES=true` to precheck Mealie library by canonical source URL before posting imports.
- **Cleaner Source Dedupe Phase:** Added `CLEANER_DEDUPE_BY_SOURCE=true` and a new cleaner Phase 0 that removes duplicate recipes sharing the same canonical source URL.
- **Canonical URL Utilities:** Added shared canonicalization helpers for URL normalization and numeric title suffix handling in `url_utils.py`.
- **Duplicate Test Coverage:** Added tests for canonical URL normalization, import precheck duplicate short-circuiting, and cleaner source-dedupe behavior.

### Changed
- **Generalized Language Detection:** Replaced fixed-language/script heuristics with generalized `langdetect`-based detection for all non-target languages.
- **Language Cleanup Coverage:** Cleaner now re-checks previously verified recipes when language cleanup is enabled, so older records are not skipped.
- **Runtime URL Keying:** Import/reject/retry state now uses canonicalized URL keys to avoid treating tracking-query variants as separate entries.
- **Cleaner API Robustness:** Rename/delete/detail lookups now fall back to recipe `id` when slug-based API calls return `NoResultFound`.
- **Documentation & Env Template:** Updated README, setup guide, and `.env.example` with new duplicate/language controls.

## [1.0.0-beta.12] - 2026-02-08

### Changed
- **Structural Refactor:** Split the old monolithic `dredger.py` into a standardized package layout under `src/mealie_recipe_dredger/`.
- **Python Project Standardization:** Added `pyproject.toml`, `VERSION`, package entrypoints, and a `tests/` directory.
- **Docker Runtime Standardization:** Added `scripts/docker/entrypoint.sh` with `TASK`/`RUN_MODE` controls to mirror `mealie-organizer` conventions.
- **Fork Documentation Refresh:** README/Setup guide rewritten to explicitly identify this repository as a fork and credit the original author (@D0rk4ce).
- **Scheduled Runtime Mode:** Added `RUN_MODE=schedule` with weekly day/time controls and set compose defaults to Sunday at 03:00.
- **Cleaner Salvage Renaming:** Cleaner can now keep salvageable `how-to` recipes and normalize names (instead of deleting them) when `CLEANER_RENAME_SALVAGE=true`.

### Fixed
- **Entrypoint Cleanup:** Removed legacy root wrappers and now run exclusively via package entrypoints (`mealie-dredger`, `mealie-cleaner`) and Docker `TASK` routing.

## [1.0.0-beta.11] - 2026-02-08

### Fixed
- **Transient Failure Handling:** Timeouts, connection errors, and transient HTTP responses now enter `retry_queue.json` instead of being permanently rejected.
- **Sitemap URL Quality:** XML parsing now only reads direct `<url><loc>` entries, preventing `<image:loc>` media URLs from being treated as recipe candidates.
- **Mealie Timeout Behavior:** Request retries for `POST` imports were removed at the HTTP adapter level to prevent repeated long timeout cycles against Mealie import endpoints.

### Changed
- **Mealie-Only Scope:** Removed Tandoor import support from the dredger and cleaner workflows.
- **Runtime Site Editability Restored:** Docker Compose now mounts `./sites.json:/app/sites.json:ro` again for live host-side edits without image rebuilds.
- **Deploy Workflow:** Docker Compose now uses local repo build context (`context: .`) to match `mealie-organizer` style update flows.
- **Versioning:** Runtime version string updated to `1.0.0-beta.11`.

## [1.0.0-beta.10] - 2026-02-08

### Fixed
- **Mealie Import API Compatibility:** Added endpoint fallback support for both `/api/recipes/create/url` (current) and `/api/recipes/create-url` (legacy), fixing `405 Method Not Allowed` failures on newer Mealie versions.
- **Sitemap Discovery Reliability:** Standard sitemap probes now follow redirects and gracefully fall back to `GET` when sites reject `HEAD` requests.

### Changed
- **Cleaner Debug Output:** Suppressed noisy charset detection debug logs from dependency libraries to keep DEBUG output focused on actionable network/import events.
- **Versioning:** Runtime version string updated to `1.0.0-beta.10`.

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
