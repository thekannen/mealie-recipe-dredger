# 🍲 Recipe Dredger (Mealie & Tandoor)

A bulk-import automation tool to populate your self-hosted recipe managers with high-quality recipes.

> **⚠️ Note regarding Tandoor:** This script was built and tested specifically for **Mealie**. Tandoor support was added via community request and is currently **untested** by the author. If you use Tandoor, please report your results in the Issues tab!

![Release](https://img.shields.io/github/v/release/D0rk4ce/mealie-recipe-dredger?include_prereleases&style=flat-square)

This script automates the process of finding **new** recipes. It scans a curated list of high-quality food blogs, detects new posts via sitemaps, checks if you already have them in your library, and imports them automatically.

## 🚀 Features

* **Multi-Platform:** Supports importing to **Mealie** (Primary) and **Tandoor** (Experimental).
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

## 📊 What's New in v1.0-beta.9

### Configuration & Security Improvements
- **`.env` file support** for secure secrets management (no more tokens in docker-compose.yml!)
- **`sites.json` external site list** - edit 100+ curated food blogs without touching code
- **SETUP_GUIDE.md** added for first-time users (5-minute setup)
- **Security:** `.gitignore` protects your `.env` file from accidental commits

### Performance Improvements
- **50% fewer HTTP requests** through intelligent HEAD checks and sitemap caching
- **40% faster processing** via single-pass HTML parsing and JSON-LD fast paths
- **Robust XML parsing** using BeautifulSoup instead of fragile regex patterns

### Reliability Enhancements
- **Graceful shutdown handling** for Docker containers (SIGTERM/SIGINT support)
- **Configuration validation** warns about missing API tokens before starting
- **Rate limit jitter** (0.5x-1.5x variance) mimics human browsing patterns
- **Session summary** displays total imported/rejected/cached counts at completion

### New Features
- **`--version` flag** to check current version
- **`--no-cache` flag** to force fresh sitemap crawls
- **Per-site statistics** show results after each site is processed
- **Multi-architecture Docker images** with ARM64 support (Raspberry Pi compatible)

### Developer Experience
- **Type hints throughout** for better IDE support
- **Dataclasses** for structured data management
- **Enhanced logging** with startup banner and progress indicators
- **Comprehensive error handling** with detailed failure reasons

## 🐳 Quick Start (Docker)

The most efficient way to run the Dredger is using Docker with a `.env` file for configuration.

### First-Time Setup

1. **Download the required files:**
   ```bash
   # Get docker-compose.yml, .env.example, and sites.json
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/docker-compose.yml
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/.env.example
   wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/sites.json
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

4. **(Optional) Customize `sites.json`:**
   - Edit to add/remove food blogs
   - Default includes 100+ curated sites
   - Organized by cuisine (Asian, Latin American, etc.)

5. **Run the dredger:**
   ```bash
   # Test run (dry mode - won't import anything)
   docker compose up
   
   # Check the output, then set DRY_RUN=false in .env for live import
   docker compose up
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

### Command-Line Options (New in beta.9)

```bash
# Check version
docker run --rm ghcr.io/d0rk4ce/mealie-recipe-dredger:latest python dredger.py --version

# Dry run with custom limits
docker run --rm ghcr.io/d0rk4ce/mealie-recipe-dredger:latest python dredger.py --dry-run --limit 10

# Force fresh sitemap crawl (ignore cache)
docker run --rm ghcr.io/d0rk4ce/mealie-recipe-dredger:latest python dredger.py --no-cache

# Use custom site list
docker run --rm -v $(pwd)/my_sites.json:/app/my_sites.json \
  ghcr.io/d0rk4ce/mealie-recipe-dredger:latest \
  python dredger.py --sites /app/my_sites.json
```

### Scheduling (Cron)

To run this weekly (e.g., Sundays at 3am), add an entry to your host's crontab:

```bash
0 3 * * 0 cd /path/to/docker-compose-folder && docker compose up
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
| `TANDOOR_ENABLED` | `false` | Set to `true` to enable Tandoor imports. |
| `TANDOOR_URL` | N/A | Your local Tandoor URL. |
| `TANDOOR_API_KEY` | N/A | Your Tandoor API key. |

### Scraper Behavior

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DRY_RUN` | `true` | **Dredger:** Scan without importing. **Cleaner:** Scan without deleting. |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for verbose logs (shows metadata and skip reasons). |
| `TARGET_RECIPES_PER_SITE` | `50` | Stops scanning a specific site after importing this many recipes. |
| `SCAN_DEPTH` | `1000` | Maximum number of sitemap links to check per site before giving up. |

### Performance & Rate Limiting (New in beta.9)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `CRAWL_DELAY` | `2.0` | Seconds to wait between requests to the same domain. |
| `RESPECT_ROBOTS_TXT` | `true` | Honor robots.txt crawl-delay directives. |
| `CACHE_EXPIRY_DAYS` | `7` | Days before sitemap cache expires. |

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

| File | Purpose | Commit to Git? |
| :--- | :--- | :--- |
| `.env` | **Your secrets and settings** (API tokens, URLs, behavior) | ❌ NO - Contains secrets! |
| `.env.example` | Template showing all available settings | ✅ YES - Safe template |
| `sites.json` | **100+ curated food blogs** organized by cuisine | ✅ YES - Just URLs, no secrets |
| `docker-compose.yml` | Container configuration | ✅ YES |

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
**Solution:** v1.0-beta.9 includes graceful shutdown handling. Check logs for `🛑 Received signal` messages. Your data is automatically saved before exit.

## 📊 Understanding the Output

### Startup Banner
```
🍲 Recipe Dredger Started (v1.0-beta.9)
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
   docker compose pull
   docker compose up
   ```

**Old configuration still works** but is not recommended (secrets in docker-compose.yml is a security risk).

**New features automatically available:**
- Graceful shutdown (works immediately in Docker)
- Configuration validation (warnings will appear if tokens not set)
- Session summary (shows automatically at end)
- Sites from `sites.json` (falls back to hardcoded list if not found)

### From beta.7 or earlier

Same steps as above. All data files from beta.7+ are fully compatible.
