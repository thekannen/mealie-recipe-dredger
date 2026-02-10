from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import random
import sys
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from .config import (
    DEFAULT_DEPTH,
    DEFAULT_SITES,
    DEFAULT_TARGET,
    DRY_RUN,
    IMPORT_WORKERS,
    MAX_RETRY_ATTEMPTS,
    MEALIE_API_TOKEN,
    MEALIE_ENABLED,
    SITE_IMPORT_FAILURE_THRESHOLD,
    __version__,
)
from .logging_utils import configure_logging
from .url_utils import canonicalize_url

if TYPE_CHECKING:
    from .storage import StorageManager

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

logger = logging.getLogger("dredger")


def validate_config() -> None:
    issues = []

    if not MEALIE_ENABLED and not DRY_RUN:
        issues.append("⚠️  Warning: Mealie is disabled. Nothing will be imported!")

    if MEALIE_ENABLED and MEALIE_API_TOKEN == "your-token":
        issues.append("⚠️  Warning: MEALIE_API_TOKEN not configured (still set to default)")

    for issue in issues:
        logger.warning(issue)


def print_summary(storage: StorageManager) -> None:
    logger.info("=" * 50)
    logger.info("📊 Session Summary:")
    logger.info(f"   Total Imported: {len(storage.imported)}")
    logger.info(f"   Total Rejected: {len(storage.rejects)}")
    logger.info(f"   In Retry Queue: {len(storage.retry_queue)}")
    logger.info(f"   Cached Sitemaps: {len(storage.sitemap_cache)}")
    logger.info("=" * 50)


def process_retry_queue(
    storage: Any,
    verifier: Any,
    importer: Any,
    rate_limiter: Any,
) -> None:
    if not storage.retry_queue:
        return

    pending = list(storage.retry_queue.items())
    logger.info(f"🔁 Processing Retry Queue: {len(pending)} URL(s)")

    for url, meta in pending:
        url_key = canonicalize_url(url) or url
        attempts = int(meta.get("attempts", 0))
        if attempts >= MAX_RETRY_ATTEMPTS:
            logger.warning(f"   ❌ Giving up after {attempts} attempts: {url}")
            storage.remove_retry(url_key)
            storage.add_reject(url_key)
            continue

        rate_limiter.wait_if_needed(url)
        is_recipe, _, verify_error, verify_transient = verifier.verify_recipe(url)

        if not is_recipe:
            if verify_transient:
                storage.add_retry(url_key, verify_error or "Transient verification failure", increment=True)
                queue_entry = storage.retry_queue.get(url_key, {})
                attempts_now = int(queue_entry.get("attempts", 0))
                if attempts_now >= MAX_RETRY_ATTEMPTS:
                    logger.warning(f"   ❌ Max retries reached [verify], rejecting: {url}")
                    storage.remove_retry(url_key)
                    storage.add_reject(url_key)
                else:
                    logger.warning(f"   ↻ Retry queued ({attempts_now}/{MAX_RETRY_ATTEMPTS}) [verify]: {url}")
            else:
                storage.remove_retry(url_key)
                storage.add_reject(url_key)
            continue

        imported, import_error, import_transient = importer.import_recipe(url)
        if imported:
            storage.add_imported(url_key)
            continue

        if import_transient:
            storage.add_retry(url_key, import_error or "Transient import failure", increment=True)
            queue_entry = storage.retry_queue.get(url_key, {})
            attempts_now = int(queue_entry.get("attempts", 0))
            if attempts_now >= MAX_RETRY_ATTEMPTS:
                logger.warning(f"   ❌ Max retries reached [import], rejecting: {url}")
                storage.remove_retry(url_key)
                storage.add_reject(url_key)
            else:
                logger.warning(f"   ↻ Retry queued ({attempts_now}/{MAX_RETRY_ATTEMPTS}) [import]: {url}")
        else:
            storage.remove_retry(url_key)
            storage.add_reject(url_key)


def _parse_sites_json(data) -> List[str]:
    if isinstance(data, list):
        return [s for s in data if isinstance(s, str) and s.startswith("http")]

    if isinstance(data, dict) and "sites" in data:
        sites = data["sites"]
        return [s for s in sites if isinstance(s, str) and s.startswith("http")]

    logger.error("Invalid sites.json format. Expected array or object with 'sites' key.")
    return []


def load_sites_from_source(source_path: Optional[str] = None) -> List[str]:
    """Load sites with priority: CLI > env override > local file > defaults."""

    if source_path:
        if os.path.exists(source_path):
            try:
                with open(source_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return _parse_sites_json(data)
            except Exception as exc:
                logger.error(f"Failed to load CLI sites file: {exc}")
                sys.exit(1)
        logger.error(f"File not found: {source_path}")
        sys.exit(1)

    if os.getenv("SITES"):
        sites_env = os.getenv("SITES", "").strip()

        if os.path.exists(sites_env):
            try:
                with open(sites_env, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
                return _parse_sites_json(data)
            except Exception as exc:
                logger.error(f"Failed to load sites file from SITES={sites_env}: {exc}")
                sys.exit(1)

        return [site.strip() for site in sites_env.split(",") if site.strip().startswith("http")]

    if os.path.exists("sites.json"):
        try:
            with open("sites.json", "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return _parse_sites_json(data)
        except Exception as exc:
            logger.warning(f"Failed to load sites.json: {exc}")

    return DEFAULT_SITES


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recipe Dredger: Intelligent Scraper")
    parser.add_argument("--dry-run", action="store_true", help="Scan without importing")
    parser.add_argument("--limit", type=int, default=DEFAULT_TARGET, help="Recipes to import per site")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH, help="URLs to scan per site")
    parser.add_argument("--sites", type=str, help="Path to JSON file containing site URLs")
    parser.add_argument("--no-cache", action="store_true", help="Force fresh crawl (ignore sitemap cache)")
    parser.add_argument("--version", action="version", version=f"Recipe Dredger {__version__}")
    return parser


def run(args: argparse.Namespace) -> int:
    from .crawler import SitemapCrawler
    from .importer import ImportManager
    from .runtime import GracefulKiller, RateLimiter, get_session
    from .storage import StorageManager
    from .verifier import RecipeVerifier

    dry_run_mode = args.dry_run or DRY_RUN
    target_count = args.limit
    scan_depth_count = args.depth
    force_refresh = args.no_cache

    validate_config()
    sites_list = load_sites_from_source(args.sites)

    logger.info(f"🍲 Recipe Dredger Started ({__version__})")
    logger.info(f"   Mode: {'DRY RUN' if dry_run_mode else 'LIVE IMPORT'}")
    logger.info(f"   Targets: {len(sites_list)} sites")
    logger.info(f"   Limit: {target_count} per site")
    logger.info(f"   Import Workers: {IMPORT_WORKERS}")
    if SITE_IMPORT_FAILURE_THRESHOLD > 0:
        logger.info(f"   Site Failure Threshold: {SITE_IMPORT_FAILURE_THRESHOLD} consecutive HTTP 5xx import errors")

    storage = StorageManager()
    killer = GracefulKiller()
    session = get_session()
    rate_limiter = RateLimiter()
    crawler = SitemapCrawler(session, storage)
    verifier = RecipeVerifier(session)
    importer = ImportManager(session, storage, rate_limiter, dry_run_mode)

    process_retry_queue(storage, verifier, importer, rate_limiter)
    def handle_import_result(
        url: str,
        url_key: str,
        imported: bool,
        import_error: Optional[str],
        import_transient: bool,
        site_stats: dict[str, int],
    ) -> bool:
        if imported:
            storage.add_imported(url_key)
            site_stats["imported"] += 1
            return True

        site_stats["errors"] += 1
        if import_transient:
            storage.add_retry(url_key, import_error or "Transient import failure", increment=True)
            if not TQDM_AVAILABLE:
                queue_entry = storage.retry_queue.get(url_key, {})
                logger.warning(
                    f"   ↻ Transient import failure queued for retry "
                    f"({queue_entry.get('attempts', 0)}/{MAX_RETRY_ATTEMPTS}): {url}"
                )
        else:
            storage.add_reject(url_key)
            if not TQDM_AVAILABLE:
                logger.error(f"   ❌ Import failed ({import_error}): {url}")

        return False

    import_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
    if IMPORT_WORKERS > 1 and not dry_run_mode:
        import_executor = concurrent.futures.ThreadPoolExecutor(max_workers=IMPORT_WORKERS)

    try:
        random.shuffle(sites_list)

        iterator = sites_list
        if TQDM_AVAILABLE and len(sites_list) > 1:
            iterator = tqdm(sites_list, desc="Processing Sites", unit="site")

        for site in iterator:
            if killer.kill_now:
                break

            if not TQDM_AVAILABLE:
                logger.info(f"🌍 Processing Site: {site}")

            site_stats = {"imported": 0, "rejected": 0, "errors": 0}

            raw_candidates = crawler.get_urls_for_site(site, force_refresh=force_refresh)
            if not raw_candidates:
                continue

            candidates = raw_candidates[:scan_depth_count]
            random.shuffle(candidates)

            imported_count = 0
            site_import_failure_streak = 0
            abort_site = False
            pending_imports: dict[concurrent.futures.Future[Tuple[bool, Optional[str], bool]], tuple[str, str]] = {}

            def drain_imports(block: bool = False) -> None:
                nonlocal imported_count, site_import_failure_streak, abort_site
                if not pending_imports:
                    return

                if block:
                    done, _ = concurrent.futures.wait(
                        pending_imports.keys(),
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )
                else:
                    done = {future for future in pending_imports if future.done()}

                for future in done:
                    url, url_key = pending_imports.pop(future)
                    try:
                        imported, import_error, import_transient = future.result()
                    except Exception as exc:
                        imported, import_error, import_transient = False, str(exc), False
                    if handle_import_result(url, url_key, imported, import_error, import_transient, site_stats):
                        imported_count += 1
                        site_import_failure_streak = 0
                        continue

                    if import_error and import_error.startswith("HTTP 5"):
                        site_import_failure_streak += 1
                        if SITE_IMPORT_FAILURE_THRESHOLD > 0 and site_import_failure_streak >= SITE_IMPORT_FAILURE_THRESHOLD:
                            if not abort_site:
                                logger.warning(
                                    f"   🚫 Aborting site due to repeated Mealie HTTP 5xx import failures "
                                    f"(streak={site_import_failure_streak}): {site}"
                                )
                            abort_site = True
                    else:
                        site_import_failure_streak = 0

            for candidate in candidates:
                if killer.kill_now:
                    break

                if abort_site:
                    break

                if imported_count >= target_count:
                    break

                url = candidate.url
                url_key = canonicalize_url(url) or url

                if url_key in storage.imported or url_key in storage.rejects or url_key in storage.retry_queue:
                    continue

                rate_limiter.wait_if_needed(url)

                is_recipe, _, error, is_transient = verifier.verify_recipe(url)

                if is_recipe:
                    if import_executor is None:
                        imported, import_error, import_transient = importer.import_recipe(url)
                        if handle_import_result(url, url_key, imported, import_error, import_transient, site_stats):
                            imported_count += 1
                            site_import_failure_streak = 0
                        else:
                            if import_error and import_error.startswith("HTTP 5"):
                                site_import_failure_streak += 1
                                if (
                                    SITE_IMPORT_FAILURE_THRESHOLD > 0
                                    and site_import_failure_streak >= SITE_IMPORT_FAILURE_THRESHOLD
                                ):
                                    logger.warning(
                                        f"   🚫 Aborting site due to repeated Mealie HTTP 5xx import failures "
                                        f"(streak={site_import_failure_streak}): {site}"
                                    )
                                    abort_site = True
                            else:
                                site_import_failure_streak = 0
                        continue

                    while pending_imports and imported_count + len(pending_imports) >= target_count:
                        drain_imports(block=True)
                        if killer.kill_now:
                            break
                    if killer.kill_now or imported_count >= target_count:
                        break

                    future = import_executor.submit(importer.import_recipe, url)
                    pending_imports[future] = (url, url_key)
                    drain_imports(block=False)
                else:
                    if is_transient:
                        storage.add_retry(url_key, error or "Transient verification failure", increment=True)
                        if not TQDM_AVAILABLE:
                            queue_entry = storage.retry_queue.get(url_key, {})
                            logger.warning(
                                f"   ↻ Transient verification failure queued for retry "
                                f"({queue_entry.get('attempts', 0)}/{MAX_RETRY_ATTEMPTS}): {url}"
                            )
                    else:
                        if not TQDM_AVAILABLE:
                            logger.debug(f"   Skipping ({error}): {url}")
                        storage.add_reject(url_key)
                        site_stats["rejected"] += 1

            while pending_imports and not killer.kill_now and imported_count < target_count and not abort_site:
                drain_imports(block=True)

            if pending_imports:
                for future in list(pending_imports):
                    future.cancel()
                    pending_imports.pop(future, None)

            if not TQDM_AVAILABLE:
                logger.info(
                    f"   Site Results: {site_stats['imported']} imported, "
                    f"{site_stats['rejected']} rejected, {site_stats['errors']} errors"
                )

            storage.flush_all()

    finally:
        if import_executor is not None:
            import_executor.shutdown(wait=False, cancel_futures=True)

    if not killer.kill_now:
        print_summary(storage)
    else:
        logger.info("⏸️  Gracefully stopped by signal")

    logger.info("🏁 Dredge Cycle Complete")
    return 0


def main() -> None:
    global logger
    logger = configure_logging("dredger")

    parser = build_arg_parser()
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
