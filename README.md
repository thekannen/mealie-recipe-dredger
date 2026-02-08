# 🍲 Recipe Dredger (Mealie)

A bulk-import automation tool to populate your self-hosted Mealie instance with high-quality recipes.

![Release](https://img.shields.io/github/v/release/D0rk4ce/mealie-recipe-dredger?include_prereleases&style=flat-square)

This script automates the process of finding **new** recipes. It scans a curated list of high-quality food blogs, detects new posts via sitemaps, checks if you already have them in your library, and imports them automatically.

## 🚀 Features

* **Mealie-Focused:** Imports directly into Mealie with endpoint compatibility for current and legacy API paths.
* **Secure Configuration:** Secrets managed via `.env` file (never committed to git).
* **Editable Site List:** 100+ curated food blogs in `sites.json` - easily add/remove sites without editing code.
* **Smart Memory:** Uses local JSON files to remember rejected and successfully imported URLs.
* **Intelligent Caching:** Sitemap results are cached for 7 days to minimize repeat requests.
* **Smart Deduplication:** Checks your existing libraries first. It will never import a URL you already have.
* **Recipe Verification:** Scans pages for Schema.org JSON-LD or standard recipe CSS classes to ensure it only imports actual recipes.
* **Deep Sitemap Scanning:** Automatically parses XML sitemaps (including recursive indexes) and robots.txt to find the most recent posts.
* **Graceful Shutdown:** Docker-safe signal handling ensures data is saved when containers are stopped (SIGTERM/SIGINT).
* **Rate Limiting with Jitter:** Respects robots.txt crawl-delay directives and adds human-like variance to prevent detection.
* **Per-Site Statistics:** Tracks imported/rejected/error counts for each site processed.
* **Progress Visualization:** Optional tqdm progress bars for long-running operations.

## 📊 What's New in v1.0.0-beta.11

### Reliability & Import Flow
- **Transient failures now retry:** Timeouts, 429s, and 5xx responses are queued in `retry_queue.json` instead of being permanently rejected.
- **Mealie POST timeout behavior improved:** HTTP adapter retries no longer retry `POST` import calls, preventing long repeated timeout loops.
- **Mealie endpoint compatibility:** Automatically uses `/api/recipes/create/url` (current) with fallback to `/api/recipes/create-url` (legacy).

### Crawl Quality & Performance
- **Sitemap parsing fixed:** Only primary `<url><loc>` entries are consumed, which avoids crawling `<image:loc>` media links.
- **Runtime-editable site list:** `sites.json` is mounted from host (`./sites.json:/app/sites.json:ro`) so you can edit targets without rebuilding.

### Deployment Workflow
- **Local repo deployment pattern:** Compose now builds from local repo context (`context: .`) and includes `scripts/docker/update.sh` to match `mealie-organizer` update/redeploy flow.

## 🐳 Quick Start (Docker)

The most efficient way to run the Dredger is using Docker with a `.env` file for configuration.

### First-Time Setup

1. **Clone your fork to the Docker host:**
   ```bash
   git clone https://github.com/<your-user>/mealie-recipe-dredger.git
   cd mealie-recipe-dredger
   ```

2. **Configure your secrets:**
   ```bash
   # Copy the template
   cp .env.example .env
   
   # Edit with your settings
   nano .env  # or vim, code, etc.
   ```

3. **Update these critical values in `.env`:**
   ```bash
   MEALIE_URL=http://192.168.1.10:9000          # Your Mealie URL
   MEALIE_API_TOKEN=eyJhbGciOiJIUzI1NiIsInR5...  # Your API token
   DRY_RUN=false                                 # Set to false to import
   ```

4. **(Optional) Customize `sites.json` on host:**
   - Edit to add/remove food blogs
   - Default includes 100+ curated sites
   - Organized by cuisine (Asian, Latin American, etc.)

5. **Deploy or update using helper script (organizer-style):**
   ```bash
   ./scripts/docker/update.sh --branch main --service mealie-recipe-dredger
   docker compose logs -f mealie-recipe-dredger
   ```

### Your Directory Structure

After setup, you'll have:
```
recipe-dredger/
├── .env                  # YOUR SECRETS (git ignored)
├── .env.example          # Template (safe to share)
├── docker-compose.yml    # Container config
├── sites.json            # 100+ curated food blogs (customizable)
└── data/                 # Created automatically
    ├── imported.json
    ├── rejects.json
    ├── sitemap_cache.json
    └── stats.json
```

### Example .env File

```bash
# Mealie Configuration
MEALIE_ENABLED=true
MEALIE_URL=http://192.168.1.10:9000
MEALIE_API_TOKEN=your_token_here

# Scraper Behavior
DRY_RUN=true              # Set to false for live import
LOG_LEVEL=INFO
TARGET_RECIPES_PER_SITE=50

# Performance
CRAWL_DELAY=2.0
CACHE_EXPIRY_DAYS=7
```

**Security Note:** Never commit `.env` to git! It contains your API tokens. The `.env.example` file is safe to commit.

### Command-Line Options

```bash
# Check version
docker compose run --rm mealie-recipe-dredger python dredger.py --version

# Dry run with custom limits
docker compose run --rm mealie-recipe-dredger python dredger.py --dry-run --limit 10

# Force fresh sitemap crawl (ignore cache)
docker compose run --rm mealie-recipe-dredger python dredger.py --no-cache

# Use custom site list
docker compose run --rm mealie-recipe-dredger python dredger.py --sites /app/sites.json
```

### Scheduling (Cron)

To run this weekly (e.g., Sundays at 3am), add an entry to your host's crontab:

```bash
0 3 * * 0 cd /path/to/docker-compose-folder && docker compose up
```

## 🔄 Update and Redeploy

Use the helper script:

```bash
./scripts/docker/update.sh
```

Useful options:
- `--skip-git-pull`
- `--no-build`
- `--branch <name>`
- `--service <name>`
- `--prune`

Manual equivalent:

```bash
git pull --ff-only origin main
docker compose up -d --build --remove-orphans mealie-recipe-dredger
```

## 🧹 Maintenance Mode (Cleaner)

The image includes a `master_cleaner.py` script to purge duplicates, listicles, and broken recipes.

**To run the cleaner in isolation (Dry Run):**
```bash
docker compose run --rm mealie-cleaner
```

**To actually delete data:**
1. Edit `docker-compose.yml` and set `DRY_RUN=false` in the `mealie-cleaner` service.
2. Run the command above again.

## ⚙️ Configuration Variables

All configuration is managed via the `.env` file (copy from `.env.example`).

### Connection Settings

| Variable | Default | Description |
| :--- | :--- | :--- |
| `MEALIE_ENABLED` | `true` | Set to `false` to disable Mealie imports. |
| `MEALIE_URL` | N/A | Your local Mealie URL (e.g. `http://192.168.1.5:9000`). |
| `MEALIE_API_TOKEN` | N/A | Found in Mealie User Settings > Manage API Tokens. |
| `MEALIE_IMPORT_TIMEOUT` | `20` | Seconds to wait for Mealie import endpoint response before retry-queueing. |

### Scraper Behavior

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DRY_RUN` | `true` | **Dredger:** Scan without importing. **Cleaner:** Scan without deleting. |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose logs (shows metadata and skip reasons). |
| `TARGET_RECIPES_PER_SITE` | `50` | Stops scanning a specific site after importing this many recipes. |
| `SCAN_DEPTH` | `1000` | Maximum number of sitemap links to check per site before giving up. |

### Performance & Rate Limiting

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CRAWL_DELAY` | `2.0` | Seconds to wait between requests to the same domain. |
| `RESPECT_ROBOTS_TXT` | `true` | Honor robots.txt crawl-delay directives. |
| `CACHE_EXPIRY_DAYS` | `7` | Days before sitemap cache expires. |
| `MAX_RETRY_ATTEMPTS` | `3` | Max retry-queue attempts for transient failures before final rejection. |

### Site Sources

**Default:** The script uses `sites.json` which contains 100+ curated food blogs organized by cuisine.

**Custom sites.json:**
- Edit `sites.json` to add/remove blogs
- Format: `{"sites": ["url1", "url2", ...]}`
- Lines starting with `_` are treated as comments/section headers

**Environment override (not recommended for large lists):**
```bash
# In .env file
SITES=https://example.com,https://another-blog.com
```

This overrides `sites.json` entirely.

## 📁 Configuration & Data Files

### Configuration Files (Edit These)

| File | Purpose |
| :--- | :--- |
| `.env` | **Your secrets and settings** (API tokens, URLs, behavior) |
| `.env.example` | Template showing all available settings |
| `sites.json` | **100+ curated food blogs** organized by cuisine |
| `docker-compose.yml` | Container configuration |

### Runtime Data Files (Auto-Generated)

The script creates a `data/` directory to persist state between runs:

| File | Purpose |
| :--- | :--- |
| `imported.json` | URLs successfully imported to your library |
| `rejects.json` | URLs that failed recipe verification (listicles, non-recipes, etc.) |
| `sitemap_cache.json` | Cached sitemap URLs with timestamps (expires after `CACHE_EXPIRY_DAYS`) |
| `retry_queue.json` | Transient failures to retry on next run (500 errors, timeouts, etc.) |
| `stats.json` | Per-site statistics and last run timestamps |
| `verified.json` | (Cleaner only) Successfully verified recipes |

**The `data/` directory is git-ignored and should never be committed.**

## 🐍 Manual Usage (Python)

If you prefer to run the script manually without Docker:

1. **Clone the repository:**
    ```bash
    git clone https://github.com/d0rk4ce/mealie-recipe-dredger.git
    cd mealie-recipe-dredger
    ```

2. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3. **Configure:**
    Create a `.env` file in the project root (see `.env.example`) OR export environment variables in your terminal.

4. **Run:**
    ```bash
    # Check version
    python dredger.py --version
    
    # Dry run
    python dredger.py --dry-run
    
    # Full run with custom limits
    python dredger.py --limit 25 --depth 500
    
    # Force cache refresh
    python dredger.py --no-cache
    
    # Run cleaner
    python maintenance/master_cleaner.py
    ```

## 🚀 Performance Tips

### Aggressive Mode (Faster, More Recipes)
```yaml
- CRAWL_DELAY=1.0              # Minimum polite delay
- TARGET_RECIPES_PER_SITE=100  # Import more per site
- SCAN_DEPTH=2000              # Check more URLs
```

### Conservative Mode (Slower, More Polite)
```yaml
- CRAWL_DELAY=5.0              # Very polite delay
- TARGET_RECIPES_PER_SITE=25   # Import fewer per site
- SCAN_DEPTH=500               # Check fewer URLs
- CACHE_EXPIRY_DAYS=14         # Longer cache (fewer requests)
```

### Bandwidth-Conscious Mode
```yaml
- CACHE_EXPIRY_DAYS=30         # Very long cache
- SCAN_DEPTH=250               # Minimal scanning
- TARGET_RECIPES_PER_SITE=10   # Quick runs
```

## 🐛 Troubleshooting

### Issue: "No recipes being imported"
**Solution:** Check your `DRY_RUN` setting. It defaults to `true` for safety.

### Issue: "API token errors"
**Solution:** The script validates your configuration at startup. Look for warnings about default tokens (`your-token`).

### Issue: "Slow performance"
**Solution:** 
- Increase `CRAWL_DELAY` if you see rate limiting (429 errors)
- Decrease `SCAN_DEPTH` to process fewer URLs per site
- Check your `data/sitemap_cache.json` is being used (look for cache hits in logs with `LOG_LEVEL=DEBUG`)

### Issue: "Container stops unexpectedly"
**Solution:** v1.0.0-beta.11 includes graceful shutdown and persistent retry queue handling. Check logs for `🛑 Received signal` or `🔁 Processing Retry Queue` messages.

## 📊 Understanding the Output

### Startup Banner
```
🍲 Recipe Dredger Started (1.0.0-beta.11)
   Mode: DRY RUN
   Targets: 95 sites
   Limit: 50 per site
```

### Per-Site Results
```
🌍 Processing Site: https://www.seriouseats.com
   ✅ [Mealie] Imported: https://...
   ⚠️ [Mealie] Duplicate: https://...
   Site Results: 12 imported, 3 rejected, 0 errors
```

### Session Summary
```
==================================================
📊 Session Summary:
   Total Imported: 248
   Total Rejected: 89
   In Retry Queue: 12
   Cached Sitemaps: 95
==================================================
🏁 Dredge Cycle Complete
```

## 🤝 Contributors

* **@rpowel** and **@johnfawkes** - Stability and logging fixes in v1.0.0-beta.5.

## ⚠️ Disclaimer & Ethics

* This tool is intended for personal archiving and self-hosting purposes.
* **Be Polite:** The script includes delays and respects robots.txt to prevent overloading site servers. Do not circumvent these protections.
* **Respect Creators:** Please continue to visit the original blogs to support the content creators who make these recipes possible.
* **Rate Limiting:** The default `CRAWL_DELAY=2.0` with jitter is a reasonable balance. If a site seems slow or you encounter rate limiting (429 errors), increase this value.

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.

## 🔄 Upgrading from Previous Versions

### From beta.8 → beta.9

**Configuration changes (recommended):**

1. **Get new files:**
   ```bash
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/.env.example
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/sites.json
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/docker-compose.yml
   ```

2. **Migrate to .env file:**
   ```bash
   # Copy template
   cp .env.example .env
   
   # Transfer your settings from old docker-compose.yml to .env
   nano .env
   ```

3. **Your data directory works as-is** - No changes needed to `data/` folder

4. **Optional: Customize sites.json** - Add/remove food blogs as desired

5. **Run:**
   ```bash
   docker compose up -d --build --remove-orphans mealie-recipe-dredger
   ```

**Old configuration still works** but is not recommended (secrets in docker-compose.yml is a security risk).

**New features automatically available:**
- Graceful shutdown (works immediately in Docker)
- Configuration validation (warnings will appear if tokens not set)
- Session summary (shows automatically at end)
- Sites from `sites.json` (falls back to hardcoded list if not found)

### From beta.7 or earlier

Same steps as above. All data files from beta.7+ are fully compatible.
