import concurrent.futures
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

from .config import (
    CLEANER_DEDUPE_BY_SOURCE,
    CLEANER_REMOVE_NON_TARGET_LANGUAGE,
    DATA_DIR,
    HOW_TO_COOK_REGEX,
    LANGUAGE_DETECTION_STRICT,
    LANGUAGE_FILTER_ENABLED,
    LANGUAGE_MIN_CONFIDENCE,
    LISTICLE_REGEX,
    LISTICLE_TITLE_REGEX,
    MEALIE_API_TOKEN,
    MEALIE_ENABLED,
    MEALIE_IMPORT_TIMEOUT,
    MEALIE_URL,
    NON_RECIPE_DIGEST_REGEX,
    NUMBERED_COLLECTION_REGEX,
    TARGET_LANGUAGE,
)
from .language import detect_language_from_recipe_payload
from .logging_utils import configure_logging
from .url_utils import canonicalize_url, has_numeric_suffix, numeric_suffix_value, strip_numeric_suffix

DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 2))
CLEANER_RENAME_SALVAGE = os.getenv("CLEANER_RENAME_SALVAGE", "true").lower() == "true"
CLEANER_API_TIMEOUT = max(5, int(os.getenv("CLEANER_API_TIMEOUT", str(MEALIE_IMPORT_TIMEOUT))))
CLEANER_API_RETRIES = max(1, int(os.getenv("CLEANER_API_RETRIES", "3")))
CLEANER_RECIPES_PER_PAGE = max(50, int(os.getenv("CLEANER_RECIPES_PER_PAGE", "250")))
CLEANER_PAGE_RETRY_DELAY = max(0.0, float(os.getenv("CLEANER_PAGE_RETRY_DELAY", "1.5")))
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
    "we tried",
    "clear winner",
    "taste test",
    "detox water",
    "lose weight",
]

INSTRUCTION_PLACEHOLDERS = (
    "could not detect instructions",
    "could not detect instruction",
    "instructions unavailable",
    "instruction unavailable",
    "no instructions",
)

logger = logging.getLogger("cleaner")
IntegrityResult = Tuple[str, str, str, Optional[str]]
CleanerAction = Literal["keep", "rename", "delete"]


def _as_optional_str(value: object) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_optional_recipe_id(value: object) -> Optional[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, int):
        return str(value)
    return None


def _extract_recipe_id(recipe: Dict[str, Any]) -> Optional[str]:
    return _as_optional_recipe_id(recipe.get("id")) or _as_optional_recipe_id(recipe.get("recipeId"))


def _recipe_identity(recipe: Dict[str, Any]) -> str:
    recipe_id = _extract_recipe_id(recipe)
    if recipe_id:
        return f"id:{recipe_id}"
    slug = _as_optional_str(recipe.get("slug"))
    if slug:
        return f"slug:{slug}"
    return f"obj:{id(recipe)}"


def _build_recipe_resource_urls(slug: Optional[str], recipe_id: Optional[str]) -> List[str]:
    urls: List[str] = []
    seen: Set[str] = set()

    for identifier in (recipe_id, slug):
        if not identifier:
            continue
        if identifier in seen:
            continue
        seen.add(identifier)
        urls.append(f"{MEALIE_URL}/api/recipes/{identifier}")

    return urls


def _is_no_result_error(status_code: int, body: str) -> bool:
    if status_code not in [404, 500]:
        return False
    lowered = (body or "").lower()
    return "noresultfound" in lowered or "no result found" in lowered


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
    terminated_due_error = False
    logger.info(f"Scanning Mealie library at {MEALIE_URL}...")
    while True:
        payload: Optional[Dict[str, Any]] = None
        request_error: Optional[str] = None

        for attempt in range(1, CLEANER_API_RETRIES + 1):
            try:
                response = requests.get(
                    f"{MEALIE_URL}/api/recipes?page={page}&perPage={CLEANER_RECIPES_PER_PAGE}",
                    headers=headers,
                    timeout=CLEANER_API_TIMEOUT,
                )
            except Exception as exc:
                request_error = str(exc)
                if attempt < CLEANER_API_RETRIES:
                    logger.warning(
                        f"Error fetching Mealie page {page} "
                        f"(attempt {attempt}/{CLEANER_API_RETRIES}): {exc}"
                    )
                    time.sleep(CLEANER_PAGE_RETRY_DELAY)
                    continue
                break

            if response.status_code != 200:
                request_error = f"HTTP {response.status_code}"
                if response.status_code >= 500 and attempt < CLEANER_API_RETRIES:
                    logger.warning(
                        f"Transient error fetching Mealie page {page} "
                        f"(attempt {attempt}/{CLEANER_API_RETRIES}): {request_error}"
                    )
                    time.sleep(CLEANER_PAGE_RETRY_DELAY)
                    continue
                break

            raw_payload = response.json()
            if not isinstance(raw_payload, dict):
                request_error = "Invalid JSON payload"
                break

            payload = raw_payload
            break

        if payload is None:
            if request_error:
                logger.error(f"Error fetching Mealie recipes page {page}: {request_error}")
                terminated_due_error = True
            break

        raw_items = payload.get("items", [])
        if not isinstance(raw_items, list):
            terminated_due_error = True
            logger.error(f"Malformed Mealie payload for page {page}: 'items' is not a list")
            break

        items = [item for item in raw_items if isinstance(item, dict)]
        if not items:
            break

        recipes.extend(items)
        page += 1
        if page % 5 == 0:
            logger.debug(f"Fetched page {page - 1}...")

    if terminated_due_error:
        logger.warning(
            f"Mealie scan ended early at page {page}; cleaner will run on partial inventory ({len(recipes)} recipes)."
        )

    logger.info(f"Total Mealie recipes found: {len(recipes)}")
    return recipes


def delete_mealie_recipe(
    slug: str,
    name: str,
    reason: str,
    rejects: Set[str],
    verified: Set[str],
    url: Optional[str] = None,
    recipe_id: Optional[str] = None,
) -> None:
    if DRY_RUN:
        logger.info(f" [DRY RUN] Would delete from Mealie: '{name}' (Reason: {reason})")
        return

    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    logger.info(f"🗑️ Deleting from Mealie: '{name}' (Reason: {reason})")
    targets = _build_recipe_resource_urls(slug, recipe_id)
    deleted = False

    for target in targets:
        for attempt in range(CLEANER_API_RETRIES):
            try:
                response = requests.delete(target, headers=headers, timeout=CLEANER_API_TIMEOUT)
                if response.status_code == 200:
                    deleted = True
                    break
                if response.status_code in [404, 405] or _is_no_result_error(response.status_code, response.text):
                    break
                time.sleep(1)
            except Exception as exc:
                logger.warning(f"Error deleting {slug} (Attempt {attempt + 1}): {exc}")
                time.sleep(1)
        if deleted:
            break

    if not deleted:
        logger.warning(f"Delete failed for '{name}' ({slug})")

    if url:
        rejects.add(url)
    if slug in verified:
        verified.remove(slug)


def _slug_fallback(url: Optional[str], slug: Optional[str]) -> str:
    slug_text = (slug or "").strip().lower()
    if slug_text:
        return slug_text

    if url:
        try:
            return urlparse(url).path.strip("/").split("/")[-1].lower()
        except Exception:
            return ""

    return ""


def _recipe_source_url(recipe: Dict[str, Any]) -> Optional[str]:
    return (
        _as_optional_str(recipe.get("orgURL"))
        or _as_optional_str(recipe.get("originalURL"))
        or _as_optional_str(recipe.get("source"))
    )


def _dedupe_keeper_sort_key(recipe: Dict[str, Any]) -> Tuple[int, int, int, int]:
    name = _as_optional_str(recipe.get("name")) or ""
    stripped_name = strip_numeric_suffix(name)
    return (
        1 if has_numeric_suffix(name) else 0,
        numeric_suffix_value(name),
        len(stripped_name),
        len(_as_optional_str(recipe.get("slug")) or ""),
    )


def dedupe_duplicate_source_recipes(
    recipes: List[Dict[str, Any]],
    rejects: Set[str],
    verified: Set[str],
) -> Tuple[List[Dict[str, Any]], int, int]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for recipe in recipes:
        source_url = _recipe_source_url(recipe)
        canonical_source = canonicalize_url(source_url)
        if not canonical_source:
            continue
        groups.setdefault(canonical_source, []).append(recipe)

    duplicate_groups = {source: group for source, group in groups.items() if len(group) > 1}
    if not duplicate_groups:
        return recipes, 0, 0

    to_remove: Set[str] = set()
    deleted_count = 0
    for canonical_source, group in duplicate_groups.items():
        sorted_group = sorted(group, key=_dedupe_keeper_sort_key)
        keeper = sorted_group[0]
        keeper_name = _as_optional_str(keeper.get("name")) or "Unknown"
        logger.info(
            f"🔁 Duplicate source detected ({len(group)}): keeping '{keeper_name}' from {canonical_source}"
        )

        for duplicate in sorted_group[1:]:
            duplicate_slug = _as_optional_str(duplicate.get("slug"))
            duplicate_name = _as_optional_str(duplicate.get("name")) or "Unknown"
            duplicate_id = _extract_recipe_id(duplicate)
            duplicate_url = _recipe_source_url(duplicate)
            if not duplicate_slug:
                continue

            delete_mealie_recipe(
                duplicate_slug,
                duplicate_name,
                f"Duplicate source URL: {canonical_source}",
                rejects,
                verified,
                duplicate_url,
                recipe_id=duplicate_id,
            )
            to_remove.add(_recipe_identity(duplicate))
            deleted_count += 1

    filtered = [recipe for recipe in recipes if _recipe_identity(recipe) not in to_remove]
    return filtered, len(duplicate_groups), deleted_count


def normalize_recipe_name(candidate: str) -> str:
    text = re.sub(r"[-_]+", " ", candidate or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"^(recipe for)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(how to)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(cook|make)\s+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(recipe)\b$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+", " ", text)
    return text.title()


def suggest_salvage_name(name: str, slug: Optional[str]) -> Optional[str]:
    original = (name or "").strip()
    if not original:
        return None

    cleaned_from_name = normalize_recipe_name(original)
    if cleaned_from_name and cleaned_from_name.lower() != original.lower():
        return cleaned_from_name

    # Only infer rename from slug when the title itself is explicitly a how-to.
    if not HOW_TO_COOK_REGEX.search(original.lower()):
        return None

    slug_text = _slug_fallback(None, slug)
    if slug_text:
        cleaned_from_slug = normalize_recipe_name(slug_text)
        if cleaned_from_slug and cleaned_from_slug.lower() != original.lower():
            return cleaned_from_slug

    return None


def classify_recipe_action(name: str, url: Optional[str], slug: Optional[str] = None) -> Tuple[CleanerAction, str, Optional[str]]:
    name_l = (name or "").lower()
    slug_text = _slug_fallback(url, slug)
    normalized_slug = re.sub(r"[-_]+", " ", slug_text).strip()
    slug_has_how_to = bool(HOW_TO_COOK_REGEX.search(normalized_slug))
    name_has_how_to = bool(HOW_TO_COOK_REGEX.search(name_l))

    if slug_has_how_to or name_has_how_to:
        if CLEANER_RENAME_SALVAGE:
            new_name = suggest_salvage_name(name, slug_text or None)
            if new_name:
                return "rename", "How-to naming cleanup", new_name
        if slug_has_how_to and not name_has_how_to:
            return "keep", "How-to slug only with clean recipe title", None
        return "delete", "How-to article", None

    if NON_RECIPE_DIGEST_REGEX.search(normalized_slug) or NON_RECIPE_DIGEST_REGEX.search(name_l):
        return "delete", "Digest/non-recipe post", None

    for keyword in HIGH_RISK_KEYWORDS:
        if keyword in normalized_slug or keyword in name_l:
            return "delete", f"High-risk keyword: {keyword}", None

    if (
        LISTICLE_REGEX.search(normalized_slug)
        or NUMBERED_COLLECTION_REGEX.search(normalized_slug)
        or LISTICLE_REGEX.search(name_l)
        or NUMBERED_COLLECTION_REGEX.search(name_l)
        or LISTICLE_TITLE_REGEX.search(normalized_slug)
        or LISTICLE_TITLE_REGEX.search(name_l)
    ):
        return "delete", "Listicle/roundup", None

    if url and any(x in url.lower() for x in ["privacy-policy", "contact", "about-us", "login", "cart"]):
        return "delete", "Utility/non-recipe page", None

    return "keep", "", None


def is_junk_content(name: str, url: Optional[str], slug: Optional[str] = None) -> bool:
    action, _, _ = classify_recipe_action(name, url, slug)
    return action == "delete"


def rename_mealie_recipe(slug: str, old_name: str, new_name: str, recipe_id: Optional[str] = None) -> bool:
    if not new_name or old_name.strip().lower() == new_name.strip().lower():
        return True

    if DRY_RUN:
        logger.info(f" [DRY RUN] Would rename in Mealie: '{old_name}' -> '{new_name}'")
        return True

    headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
    payload = {"name": new_name}
    targets = _build_recipe_resource_urls(slug, recipe_id)
    last_error: Optional[str] = None

    for target in targets:
        for method in ("patch", "put"):
            for attempt in range(CLEANER_API_RETRIES):
                try:
                    if method == "patch":
                        response = requests.patch(target, headers=headers, json=payload, timeout=CLEANER_API_TIMEOUT)
                    else:
                        response = requests.put(target, headers=headers, json=payload, timeout=CLEANER_API_TIMEOUT)

                    if response.status_code in [200, 201]:
                        logger.info(f"✏️ Renamed in Mealie: '{old_name}' -> '{new_name}'")
                        return True

                    if response.status_code in [404, 405] or _is_no_result_error(response.status_code, response.text):
                        break

                    last_error = f"HTTP {response.status_code} {response.text[:180]}"
                    time.sleep(1)
                except Exception as exc:
                    last_error = str(exc)
                    time.sleep(1)

    if last_error:
        logger.warning(f"Rename failed for '{old_name}' ({slug}): {last_error}")
    else:
        logger.warning(f"Rename failed for '{old_name}' ({slug}): Not found")

    return False


def validate_instructions(inst: Any) -> bool:
    def _has_valid_instruction_text(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text).strip().lower()
        if not normalized:
            return False
        return not any(marker in normalized for marker in INSTRUCTION_PLACEHOLDERS)

    if not inst:
        return False

    if isinstance(inst, str):
        return _has_valid_instruction_text(inst)

    if isinstance(inst, list):
        for step in inst:
            if validate_instructions(step):
                return True
        return False

    if isinstance(inst, dict):
        text = inst.get("text")
        if isinstance(text, str) and _has_valid_instruction_text(text):
            return True
        nested = inst.get("itemListElement")
        if nested is not None:
            return validate_instructions(nested)
        return False

    return False


def language_issue_for_payload(payload: dict[str, Any]) -> Optional[str]:
    if not LANGUAGE_FILTER_ENABLED or not CLEANER_REMOVE_NON_TARGET_LANGUAGE or not TARGET_LANGUAGE:
        return None

    detected_language, _source, _confidence = detect_language_from_recipe_payload(
        payload,
        min_confidence=LANGUAGE_MIN_CONFIDENCE,
    )
    if detected_language and detected_language != TARGET_LANGUAGE:
        return f"Language mismatch: {detected_language}"

    if LANGUAGE_DETECTION_STRICT and not detected_language:
        return "Language unknown"

    return None


def _should_skip_verified(slug: str, verified: Set[str]) -> bool:
    # When language cleanup is enabled, always re-check previously verified recipes.
    if LANGUAGE_FILTER_ENABLED and CLEANER_REMOVE_NON_TARGET_LANGUAGE and TARGET_LANGUAGE:
        return False
    return slug in verified


def check_integrity(recipe: Dict[str, Any], verified: Set[str]) -> Optional[IntegrityResult]:
    slug = _as_optional_str(recipe.get("slug"))
    if not slug:
        return None

    recipe_id = _extract_recipe_id(recipe)

    if _should_skip_verified(slug, verified):
        return None

    name = _as_optional_str(recipe.get("name")) or "Unknown"
    url = (
        _as_optional_str(recipe.get("orgURL"))
        or _as_optional_str(recipe.get("originalURL"))
        or _as_optional_str(recipe.get("source"))
    )

    try:
        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        payload: Dict[str, Any] = {}
        for target in _build_recipe_resource_urls(slug, recipe_id):
            for attempt in range(CLEANER_API_RETRIES):
                response = requests.get(target, headers=headers, timeout=CLEANER_API_TIMEOUT)
                if response.status_code == 200:
                    raw_payload = response.json()
                    if isinstance(raw_payload, dict):
                        payload = raw_payload
                    break
                if response.status_code in [404, 405] or _is_no_result_error(response.status_code, response.text):
                    break
                if attempt + 1 < CLEANER_API_RETRIES:
                    time.sleep(1)
            if payload:
                break

        inst = payload.get("recipeInstructions")

        if not validate_instructions(inst):
            return slug, name, "Empty/Broken Instructions", url

        language_issue = language_issue_for_payload(payload)
        if language_issue:
            return slug, name, language_issue, url

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
    if LANGUAGE_FILTER_ENABLED and CLEANER_REMOVE_NON_TARGET_LANGUAGE and TARGET_LANGUAGE:
        logger.info("Language cleanup enabled: re-checking previously verified recipes.")
    logger.info("=" * 40)

    tasks = get_mealie_recipes()
    if not tasks:
        logger.info("No recipes found to scan.")
        return 0

    if CLEANER_DEDUPE_BY_SOURCE:
        logger.info("--- Phase 0: Duplicate Source Scan ---")
        tasks, duplicate_groups, duplicate_deletes = dedupe_duplicate_source_recipes(tasks, rejects, verified)
        logger.info(f"Duplicate source groups: {duplicate_groups}, removed: {duplicate_deletes}")

    logger.info("--- Phase 1: Surgical Filter Scan ---")
    clean_tasks: List[Dict[str, Any]] = []
    phase1_deleted = 0
    phase1_rename_succeeded = 0
    phase1_rename_failed = 0
    for recipe in tasks:
        name = _as_optional_str(recipe.get("name")) or "Unknown"
        url = (
            _as_optional_str(recipe.get("orgURL"))
            or _as_optional_str(recipe.get("originalURL"))
            or _as_optional_str(recipe.get("source"))
        )
        slug = _as_optional_str(recipe.get("slug"))
        recipe_id = _extract_recipe_id(recipe)

        if not slug:
            logger.debug(f"Skipping recipe with missing slug: {name}")
            continue

        action, reason, new_name = classify_recipe_action(name, url, slug)
        if action == "delete":
            phase1_deleted += 1
            delete_mealie_recipe(
                slug,
                name,
                reason or "JUNK CONTENT",
                rejects,
                verified,
                url,
                recipe_id=recipe_id,
            )
            continue

        if action == "rename" and new_name:
            if rename_mealie_recipe(slug, name, new_name, recipe_id=recipe_id):
                phase1_rename_succeeded += 1
            else:
                phase1_rename_failed += 1

        clean_tasks.append(recipe)

    logger.info(
        "Phase 1 summary: "
        f"deleted={phase1_deleted}, "
        f"renamed={phase1_rename_succeeded}, "
        f"rename_failed={phase1_rename_failed}, "
        f"passed_to_phase2={len(clean_tasks)}"
    )

    logger.info(f"--- Phase 2: Deep Integrity Scan (Checking {len(clean_tasks)} recipes) ---")
    phase2_deleted = 0
    phase2_verified = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(check_integrity, recipe, verified) for recipe in clean_tasks]
        future_recipe_id = {future: _extract_recipe_id(recipe) for future, recipe in zip(futures, clean_tasks)}

        for index, future in enumerate(concurrent.futures.as_completed(futures)):
            result = future.result()
            if result:
                slug, marker, reason, url = result
                if marker == "VERIFIED":
                    phase2_verified += 1
                    verified.add(slug)
                else:
                    phase2_deleted += 1
                    delete_mealie_recipe(
                        slug,
                        marker,
                        reason,
                        rejects,
                        verified,
                        url,
                        recipe_id=future_recipe_id.get(future),
                    )

            if index % 10 == 0:
                logger.debug(f"Progress: {index}/{len(clean_tasks)}")

    logger.info(
        "Phase 2 summary: "
        f"verified={phase2_verified}, "
        f"deleted={phase2_deleted}"
    )

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
