# Recipe Dredger - Quick Setup Guide

## 📋 Prerequisites
- Docker and Docker Compose installed
- Mealie instance running
- API token from your recipe manager

## 🚀 First-Time Setup (5 Minutes)

### Step 1: Get the Files

**Option A: Download from GitHub**
```bash
wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/docker-compose.yml
wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/.env.example
wget https://raw.githubusercontent.com/D0rk4ce/mealie-recipe-dredger/main/sites.json
```

**Option B: Clone the Repository**
```bash
git clone https://github.com/D0rk4ce/mealie-recipe-dredger.git
cd mealie-recipe-dredger
```

### Step 2: Configure Secrets

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your settings:
   ```bash
   nano .env  # or vim, code, etc.
   ```

3. Update these critical values:
   ```bash
   MEALIE_URL=http://192.168.1.10:9000          # Your Mealie URL
   MEALIE_API_TOKEN=eyJhbGciOiJIUzI1NiIsInR5...  # Your API token
   DRY_RUN=false                                 # Set to false to import
   ```

   **Finding your API token:**
   - Mealie: Settings → User Profile → API Tokens → Create Token

### Step 3: Customize Sites (Optional)

The default `sites.json` includes 100+ curated food blogs. To customize:

1. Open `sites.json` in a text editor
2. Remove sites you don't want (delete entire lines)
3. Add your own sites to the appropriate section
4. Save the file

**Example: Remove a site**
```json
{
  "sites": [
    "_general_western",
    "https://www.seriouseats.com",
    "https://www.bonappetit.com"
    // Remove this line to skip: "https://www.foodandwine.com",
  ]
}
```

**Example: Add a site**
```json
{
  "sites": [
    "_general_western",
    "https://www.seriouseats.com",
    "https://www.myblog.com",  // Add your own blog here
  ]
}
```

### Step 4: Test Run (Dry Mode)

```bash
# This won't import anything, just shows what would be imported
docker compose up
```

Watch the output for:
- ✅ `[DRY RUN] Would import to Mealie: ...`
- ⚠️ Configuration warnings
- 📊 Session summary at the end

### Step 5: Live Import

Once you're happy with the test results:

1. Edit `.env` and set `DRY_RUN=false`
2. Run again:
   ```bash
   ./scripts/docker/update.sh --branch main --service mealie-recipe-dredger
   docker compose logs -f mealie-recipe-dredger
   ```

### Step 6: Schedule (Optional)

To run automatically every Sunday at 3am:

```bash
# Open crontab
crontab -e

# Add this line (adjust path to your docker-compose.yml location)
0 3 * * 0 cd /path/to/recipe-dredger && docker compose up
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

## 📁 Your Directory Structure

```
recipe-dredger/
├── .env                  # YOUR SECRETS (git ignored)
├── .env.example          # Template (safe to commit)
├── docker-compose.yml    # Container configuration
├── sites.json            # Site list (customizable)
└── data/                 # Created automatically
    ├── imported.json     # Successfully imported URLs
    ├── rejects.json      # Rejected URLs (non-recipes, listicles)
    ├── sitemap_cache.json # Cached sitemaps (expires after 7 days)
    ├── retry_queue.json  # Transient failures to retry
    └── stats.json        # Per-site statistics
```

## 🔐 Security Notes

- **Never commit `.env` to git** - It contains your API tokens!
- `.env.example` is safe to commit (no secrets)
- `sites.json` is safe to commit (just URLs)
- `data/` folder is git-ignored (contains your import history)

## 🎯 Common Configurations

### Minimal (Test Mode)
```bash
# In .env
DRY_RUN=true
TARGET_RECIPES_PER_SITE=5
SCAN_DEPTH=50
```

### Aggressive (Fast Import)
```bash
# In .env
DRY_RUN=false
TARGET_RECIPES_PER_SITE=100
SCAN_DEPTH=2000
CRAWL_DELAY=1.0
```

### Conservative (Polite Mode)
```bash
# In .env
DRY_RUN=false
TARGET_RECIPES_PER_SITE=25
SCAN_DEPTH=500
CRAWL_DELAY=5.0
```

## 🧹 Running the Cleaner

To remove duplicates and broken recipes:

```bash
# Dry run first (shows what would be deleted)
docker compose run --rm mealie-cleaner

# To actually delete (set DRY_RUN=false in .env first)
docker compose run --rm mealie-cleaner
```

## 🐛 Troubleshooting

### "API token errors"
- Check your token is correct in `.env`
- Regenerate token in Mealie if needed
- Ensure no trailing spaces in `.env` values

### "No recipes imported"
- Check `DRY_RUN=false` in `.env`
- Verify `MEALIE_ENABLED=true` in `.env`
- Check logs for `⚠️ Warning` messages

### "File not found: .env"
- Run `cp .env.example .env` first
- Ensure you're in the correct directory

### "Permission denied on sites.json"
- The `:ro` in docker-compose.yml makes it read-only
- Edit `sites.json` on your host, not in container

## 📚 More Help

- Full README: https://github.com/D0rk4ce/mealie-recipe-dredger
- Report Issues: https://github.com/D0rk4ce/mealie-recipe-dredger/issues
- Check version: `docker compose run --rm mealie-recipe-dredger python dredger.py --version`
