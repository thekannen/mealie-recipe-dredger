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

## 5. Runtime controls

Supported container env vars:
- `TASK=dredger|cleaner`
- `RUN_MODE=once|loop`
- `RUN_INTERVAL_SECONDS=<int>`

Example loop mode:

```bash
docker compose run --rm -e TASK=dredger -e RUN_MODE=loop -e RUN_INTERVAL_SECONDS=21600 mealie-recipe-dredger
```

## Troubleshooting

### `Not a git repo` from update script
You deployed from tarball/curl. Re-clone as git repo, or run manual compose build/up commands.

### Import timeouts to Mealie
Increase `MEALIE_IMPORT_TIMEOUT`, verify Mealie host reachability, and check Mealie server load.

### Too many rejects from transient outages
Check `data/retry_queue.json`; transient failures should queue and retry automatically.
