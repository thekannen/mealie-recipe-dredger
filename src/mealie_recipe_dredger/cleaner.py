import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from .config import DATA_DIR, MEALIE_API_TOKEN, MEALIE_ENABLED, MEALIE_URL
from .logging_utils import configure_logging

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 2))
REJECT_FILE = DATA_DIR / "rejects.json"
VERIFIED_FILE = DATA_DIR / "verified.json"

HIGH_RISK_KEYWORDS = [
    "cleaning",
    "storing",
    "freezing",
    "pantry",
    "kitchen tools",
    "review",
    "giveaway",
    "shop",
    "store",
    "product",
    "gift",
    "unboxing",
    "news",
    "travel",
    "podcast",
    "interview",
    "night cream",
    "face mask",
    "skin care",
    "beauty",
    "diy",
    "weekly plan",
    "menu",
    "holiday guide",
    "foods to try",
    "things to eat",
    "detox water",
    "lose weight",
]

LISTICLE_REGEX = re.compile(
    r"^(\\d+)\\s+(best|top|must|favorite|easy|healthy|quick|ways|things)",
    re.IGNORECASE,
)

logger = logging.getLogger("cleaner")
IntegrityResult = Tuple[str, str, str, Optional[str]]


def _as_optional_str(value: object) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_json_set(filename: Path) -> Set[str]:
    if filename.exists():
        try:
            return set(json.loads(filename.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_json_set(filename: Path, data_set: Set[str]) -> None:
    filename.parent.mkdir(parents=True, exist_ok=True)
    filename.write_text(json.dumps(list(data_set)), encoding="utf-8")


def get_mealie_recipes() -> List[Dict[str, Any]]:
    if not MEALIE_ENABLED:
        return []

    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    recipes: List[Dict[str, Any]] = []
    page = 1
    logger.info(f"Scanning Mealie library at {MEALIE_URL}...")
    while True:
        try:
            response = requests.get(
                f"{MEALIE_URL}/api/recipes?page={page}&perPage=1000",
                headers=headers,
                timeout=10,
            )
            if response.status_code != 200:
                break
            payload = response.json()
            if not isinstance(payload, dict):
                break

            raw_items = payload.get("items", [])
            if not isinstance(raw_items, list):
                break

            items = [item for item in raw_items if isinstance(item, dict)]
            if not items:
                break
            recipes.extend(items)
            page += 1
            if page % 5 == 0:
                logger.debug(f"Fetched page {page - 1}...")
        except Exception as exc:
            logger.error(f"Error fetching Mealie recipes: {exc}")
            break

    logger.info(f"Total Mealie recipes found: {len(recipes)}")
    return recipes


def delete_mealie_recipe(
    slug: str,
    name: str,
    reason: str,
    rejects: Set[str],
    verified: Set[str],
    url: Optional[str] = None,
) -> None:
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would delete from Mealie: '{name}' (Reason: {reason})")
        return

    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    logger.info(f"🗑️ Deleting from Mealie: '{name}' (Reason: {reason})")

    for attempt in range(3):
        try:
            response = requests.delete(f"{MEALIE_URL}/api/recipes/{slug}", headers=headers, timeout=10)
            if response.status_code == 200:
                break
            time.sleep(1)
        except Exception as exc:
            logger.warning(f"Error deleting {slug} (Attempt {attempt + 1}): {exc}")
            time.sleep(1)

    if url:
        rejects.add(url)
    if slug in verified:
        verified.remove(slug)


def is_junk_content(name: str, url: Optional[str]) -> bool:
    if not url:
        return False

    try:
        slug = urlparse(url).path.strip("/").split("/")[-1].lower()
    except Exception:
        slug = ""

    name_l = (name or "").lower()

    for keyword in HIGH_RISK_KEYWORDS:
        if keyword.replace(" ", "-") in slug or keyword in name_l:
            return True

    if LISTICLE_REGEX.match(slug) or LISTICLE_REGEX.match(name_l):
        return True

    if any(x in url.lower() for x in ["privacy-policy", "contact", "about-us", "login", "cart"]):
        return True

    return False


def validate_instructions(inst: Any) -> bool:
    if not inst:
        return False

    if isinstance(inst, str):
        if len(inst.strip()) == 0:
            return False
        if "could not detect" in inst.lower():
            return False
        return True

    if isinstance(inst, list):
        if len(inst) == 0:
            return False
        for step in inst:
            text = step.get("text", "") if isinstance(step, dict) else str(step)
            if text and len(text.strip()) > 0:
                return True
        return False

    return True


def check_integrity(recipe: Dict[str, Any], verified: Set[str]) -> Optional[IntegrityResult]:
    slug = _as_optional_str(recipe.get("slug"))
    if not slug:
        return None

    if slug in verified:
        return None

    name = _as_optional_str(recipe.get("name")) or "Unknown"
    url = (
        _as_optional_str(recipe.get("orgURL"))
        or _as_optional_str(recipe.get("originalURL"))
        or _as_optional_str(recipe.get("source"))
    )

    try:
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        response = requests.get(f"{MEALIE_URL}/api/recipes/{slug}", headers=headers, timeout=10)
        inst = response.json().get("recipeInstructions") if response.status_code == 200 else None

        if not validate_instructions(inst):
            return slug, name, "Empty/Broken Instructions", url

        return slug, "VERIFIED", "", None
    except Exception:
        return None


def run_cleaner() -> int:
    rejects = load_json_set(REJECT_FILE)
    verified = load_json_set(VERIFIED_FILE)

    logger.info("=" * 40)
    logger.info("MASTER CLEANER STARTED")
    logger.info(f"Mode: {'DRY RUN (Safe)' if DRY_RUN else 'LIVE (Destructive)'}")
    logger.info(f"Workers: {MAX_WORKERS}")
    logger.info("=" * 40)

    tasks = get_mealie_recipes()
    if not tasks:
        logger.info("No recipes found to scan.")
        return 0

    logger.info("--- Phase 1: Surgical Filter Scan ---")
    clean_tasks: List[Dict[str, Any]] = []
    for recipe in tasks:
        name = _as_optional_str(recipe.get("name")) or "Unknown"
        url = (
            _as_optional_str(recipe.get("orgURL"))
            or _as_optional_str(recipe.get("originalURL"))
            or _as_optional_str(recipe.get("source"))
        )
        slug = _as_optional_str(recipe.get("slug"))

        if not slug:
            logger.debug(f"Skipping recipe with missing slug: {name}")
            continue

        if is_junk_content(name, url):
            delete_mealie_recipe(slug, name, "JUNK CONTENT", rejects, verified, url)
        else:
            clean_tasks.append(recipe)

    logger.info(f"--- Phase 2: Deep Integrity Scan (Checking {len(clean_tasks)} recipes) ---")
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_integrity, recipe, verified) for recipe in clean_tasks]

        for index, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            if result:
                slug, marker, reason, url = result
                if marker == "VERIFIED":
                    verified.add(slug)
                else:
                    delete_mealie_recipe(slug, marker, reason, rejects, verified, url)

            if index % 10 == 0:
                logger.debug(f"Progress: {index}/{len(clean_tasks)}")

    if not DRY_RUN:
        save_json_set(REJECT_FILE, rejects)
        save_json_set(VERIFIED_FILE, verified)
        logger.info("State saved.")
    else:
        logger.info("Dry Run: No state files updated.")

    logger.info("CLEANUP COMPLETE")
    return 0


def main() -> None:
    global logger
    logger = configure_logging("cleaner")

    if not MEALIE_ENABLED:
        logger.warning("Mealie is disabled; cleaner has nothing to do.")
        raise SystemExit(0)

    try:
        raise SystemExit(run_cleaner())
    except KeyboardInterrupt:
        logger.warning("Operation Interrupted.")
        raise SystemExit(0)


if __name__ == "__main__":
    main()
