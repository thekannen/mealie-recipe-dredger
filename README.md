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

3. Optional: set your runtime sites file on host:

```bash
cp custom_sites.json data/sites.json
# or edit data/sites.json directly
```

If `data/sites.json` exists, Docker runtime uses it via `SITES=/app/data/sites.json`.
Because it lives under `data/`, git updates do not overwrite it.
If you skip this step, `./scripts/docker/update.sh` seeds `data/sites.json` once from repo `sites.json` when missing.

4. Deploy/update:

```bash
./scripts/docker/update.sh --branch main --service mealie-recipe-dredger
docker compose logs -f mealie-recipe-dredger
```

## Runtime model

Docker entrypoint supports:
- `TASK=dredger` (default service behavior)
- `TASK=cleaner`
- `TASK=align-sites`
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

# run site alignment once (dry run by default)
docker compose run --rm -e TASK=align-sites -e RUN_MODE=once mealie-recipe-dredger
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

# diff-based site alignment (dry run)
mealie-align-sites --sites-file data/sites.json --baseline-sites-file sites.json
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
- `CLEANER_RENAME_SALVAGE`
- `IMPORT_PRECHECK_DUPLICATES`
- `CLEANER_DEDUPE_BY_SOURCE`
- `TARGET_LANGUAGE` (default `en`)
- `LANGUAGE_FILTER_ENABLED`
- `LANGUAGE_DETECTION_STRICT`
- `LANGUAGE_MIN_CONFIDENCE`
- `CLEANER_REMOVE_NON_TARGET_LANGUAGE`
- `TARGET_RECIPES_PER_SITE`
- `SCAN_DEPTH`
- `CRAWL_DELAY`
- `CACHE_EXPIRY_DAYS`
- `MEALIE_IMPORT_TIMEOUT`
- `IMPORT_WORKERS`
- `SITE_IMPORT_FAILURE_THRESHOLD`
- `MAX_RETRY_ATTEMPTS`
- `ALIGN_RECIPES_WITH_SITES`
- `ALIGN_SITES_BASELINE_FILE`
- `ALIGN_SITES_STATE_FILE`
- `ALIGN_SITES_INCLUDE_MISSING_SOURCE`

### Language filtering and post-hoc cleanup

- New imports are filtered by `TARGET_LANGUAGE` in verifier (default `en`).
- Detection is generalized via `langdetect` (not limited to a fixed set like English/Spanish/Hindi).
- Unknown-language pages are rejected by default via `LANGUAGE_DETECTION_STRICT=true`.
- Existing imported recipes can be cleaned after the fact by running cleaner with:
- `CLEANER_REMOVE_NON_TARGET_LANGUAGE=true`
- `LANGUAGE_FILTER_ENABLED=true`

Example cleanup run:

```bash
docker compose run --rm -e TASK=cleaner -e RUN_MODE=once -e DRY_RUN=false mealie-recipe-dredger
```

### Duplicate prevention and cleanup

- Import-time: `IMPORT_PRECHECK_DUPLICATES=true` checks Mealie for canonical source URL duplicates before posting import.
- Cleaner: `CLEANER_DEDUPE_BY_SOURCE=true` removes duplicate recipes that share the same canonical source URL.
- Name collisions from different sites are not auto-deleted solely by title; source URL is used as the safe dedupe key.

### Repeatable site alignment (diff mode)

Enable `ALIGN_RECIPES_WITH_SITES=true` to run alignment before each `mealie-dredger` cycle.

- Alignment uses domain diff scope (baseline -> current), not "delete everything outside current sites".
- This preserves manual/external recipes unless their host is explicitly in removed-domain scope.
- Baseline source priority for dredger alignment:
1. CLI `--align-sites-baseline` or env `ALIGN_SITES_BASELINE_FILE`
2. rolling snapshot `data/site_alignment_hosts.json` (`ALIGN_SITES_STATE_FILE`), auto-initialized/updated on live runs

Manual dry run:

```bash
mealie-align-sites --sites-file data/sites.json --baseline-sites-file sites.json
```

Manual apply:

```bash
mealie-align-sites --sites-file data/sites.json --baseline-sites-file sites.json --apply
```

Backward-compatible wrapper:

```bash
python3 scripts/oneoff/prune_by_sites.py --sites-file data/sites.json --baseline-sites-file sites.json --apply
```

Docker-native run (uses env_file and runtime `SITES` automatically):

```bash
docker compose run --rm -e TASK=align-sites -e RUN_MODE=once mealie-recipe-dredger
docker compose run --rm -e TASK=align-sites -e RUN_MODE=once -e ALIGN_SITES_BASELINE_FILE=/app/data/site_alignment_hosts.json -e ALIGN_SITES_APPLY=true mealie-recipe-dredger
```

For destructive apply in Docker task mode, set `ALIGN_SITES_BASELINE_FILE` so pruning stays diff-scoped.

### Performance tuning

- Import throughput is usually bounded by Mealie's `/api/recipes/create/url` latency.
- Increase `IMPORT_WORKERS` (start at `2`, then test `3-4`) to overlap slow Mealie imports.
- Increase `MEALIE_IMPORT_TIMEOUT` if you see frequent timeout retries under load.
- Keep `SITE_IMPORT_FAILURE_THRESHOLD` at a low value (for example `3`) to skip sites that repeatedly return Mealie HTTP 5xx import errors.

Site source priority:
1. CLI `--sites`
2. `SITES` env override (path or comma-separated URLs)
3. local `sites.json`
4. built-in defaults

Docker note:
- The entrypoint prefers `/app/data/sites.json` when present.

## Notes

- `retry_queue.json` tracks transient failures and retries them in later runs.

## License

MIT (same as upstream).
