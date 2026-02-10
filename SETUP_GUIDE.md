# Recipe Dredger Setup Guide (Fork)

This guide follows the standardized workflow used in `mealie-organizer`.

## 1. Clone and configure

```bash
git clone https://github.com/<your-user>/mealie-recipe-dredger.git
cd mealie-recipe-dredger
cp .env.example .env
```

Edit `.env` and set:
- `MEALIE_URL`
- `MEALIE_API_TOKEN`
- `DRY_RUN=false` when ready for live imports
- `TARGET_LANGUAGE=en` (or your preferred language code)

## 2. Optional site customization

Edit `sites.json` on host. It is mounted into the container at runtime:
- `./sites.json:/app/sites.json:ro`

## 3. Deploy/update

```bash
./scripts/docker/update.sh --branch main --service mealie-recipe-dredger
```

Check logs:

```bash
docker compose logs -f mealie-recipe-dredger
```

## 4. Run cleaner manually

Dry run first:

```bash
docker compose run --rm -e TASK=cleaner -e RUN_MODE=once mealie-recipe-dredger
```

If you want live deletion, set `DRY_RUN=false` in `.env` and rerun.

To keep salvageable entries and clean names instead of deleting them (for example `How to Cook ...`), keep `CLEANER_RENAME_SALVAGE=true` in `.env`.

To remove already-imported recipes that are not in your target language, keep these enabled in `.env` before running cleaner:
- `LANGUAGE_FILTER_ENABLED=true`
- `LANGUAGE_DETECTION_STRICT=true`
- `CLEANER_REMOVE_NON_TARGET_LANGUAGE=true`
- `TARGET_LANGUAGE=en`

Language detection is generalized (`langdetect`) so cleanup is not limited to a hardcoded language pair.

To prevent and clean true duplicates:
- `IMPORT_PRECHECK_DUPLICATES=true` (prevents re-import by canonical source URL)
- `CLEANER_DEDUPE_BY_SOURCE=true` (removes existing duplicates sharing canonical source URL)

To improve slow import throughput:
- `IMPORT_WORKERS=2` (increase to `3-4` if your Mealie host has headroom)
- `MEALIE_IMPORT_TIMEOUT=20` (increase if imports frequently timeout)

## 5. Runtime controls

Supported container env vars:
- `TASK=dredger|cleaner`
- `RUN_MODE=once|loop|schedule`
- `RUN_INTERVAL_SECONDS=<int>`
- `RUN_SCHEDULE_DAY=<1-7>` (`1=Mon`, `7=Sun`)
- `RUN_SCHEDULE_TIME=<HH:MM>` (24-hour)

Current compose default for `mealie-recipe-dredger`: Sunday `03:00`.

Example loop mode:

```bash
docker compose run --rm -e TASK=dredger -e RUN_MODE=loop -e RUN_INTERVAL_SECONDS=21600 mealie-recipe-dredger
```

Example weekly schedule (Sunday 03:00):

```bash
docker compose run --rm -e TASK=dredger -e RUN_MODE=schedule -e RUN_SCHEDULE_DAY=7 -e RUN_SCHEDULE_TIME=03:00 mealie-recipe-dredger
```

## Troubleshooting

### `Not a git repo` from update script
You deployed from tarball/curl. Re-clone as git repo, or run manual compose build/up commands.

### Import timeouts to Mealie
Increase `MEALIE_IMPORT_TIMEOUT`, verify Mealie host reachability, check Mealie server load, and tune `IMPORT_WORKERS` gradually.

### Too many rejects from transient outages
Check `data/retry_queue.json`; transient failures should queue and retry automatically.
