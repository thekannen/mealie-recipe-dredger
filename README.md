# Mealie Recipe Dredger (Fork)

This repository is a **forked and modernized** version of the original project by **@D0rk4ce**:
- Original: https://github.com/D0rk4ce/mealie-recipe-dredger

Credit to the original author for creating the project and curated site list foundation.

## What this fork changes

- Refactors the monolithic `dredger.py` into a standard Python package under `src/`.
- Focuses the app on **Mealie only**.
- Adds transient-failure retry queue handling (timeouts/429/5xx are retried, not instantly rejected).
- Fixes sitemap parsing to avoid ingesting image URLs from `<image:loc>` entries.
- Standardizes Docker runtime with `TASK` and `RUN_MODE` entrypoint controls.
- Aligns deploy/update workflow with `mealie-organizer` (`scripts/docker/update.sh`).

## Project layout

```text
.
├── src/mealie_recipe_dredger/
│   ├── app.py
│   ├── cleaner.py
│   ├── config.py
│   ├── crawler.py
│   ├── importer.py
│   ├── logging_utils.py
│   ├── models.py
│   ├── runtime.py
│   ├── storage.py
│   └── verifier.py
├── scripts/
│   └── docker/
│       ├── entrypoint.sh
│       └── update.sh
├── tests/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── requirements.txt
└── VERSION
```

## Quick start (Docker)

1. Clone your fork and enter it:

```bash
git clone https://github.com/thekannen/mealie-recipe-dredger.git
cd mealie-recipe-dredger
```

2. Configure environment:

```bash
cp .env.example .env
# edit .env with MEALIE_URL + MEALIE_API_TOKEN
```

3. Optional: edit `sites.json` on host (runtime-mounted read-only into container).

4. Deploy/update:

```bash
./scripts/docker/update.sh --branch main --service mealie-recipe-dredger
docker compose logs -f mealie-recipe-dredger
```

## Runtime model

Docker entrypoint supports:
- `TASK=dredger` (default service behavior)
- `TASK=cleaner`
- `RUN_MODE=once` (entrypoint fallback if unset)
- `RUN_MODE=loop` with `RUN_INTERVAL_SECONDS=<int>`
- `RUN_MODE=schedule` with:
- `RUN_SCHEDULE_DAY=<1-7>` (`1=Mon`, `7=Sun`)
- `RUN_SCHEDULE_TIME=<HH:MM>` (24-hour)
- Compose default for `mealie-recipe-dredger`: Sunday `03:00` (`RUN_MODE=schedule`, `RUN_SCHEDULE_DAY=7`, `RUN_SCHEDULE_TIME=03:00`)

Examples:

```bash
# run dredger once
docker compose run --rm -e TASK=dredger -e RUN_MODE=once mealie-recipe-dredger

# run dredger in loop every 6 hours
docker compose run --rm -e TASK=dredger -e RUN_MODE=loop -e RUN_INTERVAL_SECONDS=21600 mealie-recipe-dredger

# run dredger every Sunday at 03:00
docker compose run --rm -e TASK=dredger -e RUN_MODE=schedule -e RUN_SCHEDULE_DAY=7 -e RUN_SCHEDULE_TIME=03:00 mealie-recipe-dredger

# run cleaner once
docker compose run --rm -e TASK=cleaner -e RUN_MODE=once mealie-recipe-dredger
```

## Update and redeploy

Preferred:

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

## Local development

1. Create and activate venv:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies and package:

```bash
pip install -r requirements.txt
pip install -e .
```

3. Run tools:

```bash
# dredger
mealie-dredger --dry-run --limit 10

# cleaner
mealie-cleaner
```

4. Run tests:

```bash
pytest
```

## Configuration highlights

Primary required values in `.env`:
- `MEALIE_URL`
- `MEALIE_API_TOKEN`

Useful tuning values:
- `DRY_RUN`
- `TARGET_RECIPES_PER_SITE`
- `SCAN_DEPTH`
- `CRAWL_DELAY`
- `CACHE_EXPIRY_DAYS`
- `MEALIE_IMPORT_TIMEOUT`
- `MAX_RETRY_ATTEMPTS`

Site source priority:
1. CLI `--sites`
2. `SITES` env override (path or comma-separated URLs)
3. local `sites.json`
4. built-in defaults

## Notes

- `retry_queue.json` tracks transient failures and retries them in later runs.

## License

MIT (same as upstream).
