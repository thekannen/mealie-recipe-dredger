import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from requests.adapters import HTTPAdapter

from .config import (
    IMPORT_PRECHECK_DUPLICATES,
    MEALIE_API_TOKEN,
    MEALIE_ENABLED,
    MEALIE_IMPORT_TIMEOUT,
    MEALIE_URL,
    TRANSIENT_HTTP_CODES,
)
from .runtime import RateLimiter
from .storage import StorageManager
from .url_utils import canonicalize_url

logger = logging.getLogger("dredger")


class ImportManager:
    def __init__(
        self,
        session: requests.Session,
        storage: StorageManager,
        rate_limiter: RateLimiter,
        dry_run: bool,
    ):
        self.session = session
        self.import_session = requests.Session()
        self.import_session.headers.update(dict(self.session.headers))
        # Import requests should not be retried by urllib3 adapters; timeout
        # handling is managed explicitly by this class and retry_queue logic.
        self.import_session.mount("http://", HTTPAdapter(max_retries=0))
        self.import_session.mount("https://", HTTPAdapter(max_retries=0))
        self.storage = storage
        self.rate_limiter = rate_limiter
        self.dry_run = dry_run
        self._mealie_endpoint_candidates = [
            "/api/recipes/create/url",
            "/api/recipes/create-url",
        ]
        self._mealie_import_path: Optional[str] = None
        self._known_source_urls: Set[str] = set()
        self._source_index_loaded = False
        self._source_index_failed = False

    def _extract_source_url(self, recipe: Dict[str, Any]) -> str:
        for key in ["orgURL", "originalURL", "source"]:
            value = recipe.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _load_existing_sources(self, headers: Dict[str, str]) -> None:
        if self._source_index_loaded or self._source_index_failed:
            return

        source_urls: Set[str] = set()
        page = 1
        try:
            while True:
                response = self.import_session.get(
                    f"{MEALIE_URL}/api/recipes",
                    headers=headers,
                    params={"page": page, "perPage": 1000},
                    timeout=MEALIE_IMPORT_TIMEOUT,
                )
                if response.status_code != 200:
                    logger.warning(f"   [Mealie] Duplicate precheck disabled: recipe list HTTP {response.status_code}")
                    self._source_index_failed = True
                    return

                payload = response.json()
                if not isinstance(payload, dict):
                    self._source_index_failed = True
                    return

                items = payload.get("items", [])
                if not isinstance(items, list) or not items:
                    break

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    source_url = self._extract_source_url(item)
                    canonical_source = canonicalize_url(source_url)
                    if canonical_source:
                        source_urls.add(canonical_source)

                page += 1

            self._known_source_urls = source_urls
            self._source_index_loaded = True
            logger.info(f"   [Mealie] Duplicate precheck source index loaded: {len(source_urls)} entries")
        except Exception as exc:
            logger.warning(f"   [Mealie] Duplicate precheck unavailable: {exc}")
            self._source_index_failed = True

    def _precheck_duplicate_source(self, url: str, headers: Dict[str, str]) -> bool:
        if not IMPORT_PRECHECK_DUPLICATES:
            return False

        self._load_existing_sources(headers)
        if self._source_index_failed:
            return False

        canonical_source = canonicalize_url(url)
        if canonical_source and canonical_source in self._known_source_urls:
            logger.info(f"   ⚠️ [Mealie] Duplicate source URL detected, skipping import: {url}")
            return True
        return False

    def import_to_mealie(self, url: str) -> Tuple[bool, Optional[str], bool]:
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would import to Mealie: {url}")
            return True, None, False

        headers = {"Authorization": f"Bearer {MEALIE_API_TOKEN}"}
        try:
            if self._precheck_duplicate_source(url, headers):
                return True, None, False

            self.rate_limiter.wait_if_needed(MEALIE_URL)
            candidate_paths = list(self._mealie_endpoint_candidates)
            if self._mealie_import_path in candidate_paths:
                candidate_paths.remove(self._mealie_import_path)
                candidate_paths.insert(0, self._mealie_import_path)

            endpoint_error = None
            for path in candidate_paths:
                response = self.import_session.post(
                    f"{MEALIE_URL}{path}",
                    headers=headers,
                    json={"url": url},
                    timeout=MEALIE_IMPORT_TIMEOUT,
                )

                if response.status_code in [200, 201, 202]:
                    if self._mealie_import_path != path:
                        self._mealie_import_path = path
                        logger.info(f"   [Mealie] Using import endpoint: {path}")
                    canonical_source = canonicalize_url(url)
                    if canonical_source:
                        self._known_source_urls.add(canonical_source)
                    logger.info(f"   ✅ [Mealie] Imported: {url}")
                    return True, None, False

                if response.status_code == 409:
                    if self._mealie_import_path != path:
                        self._mealie_import_path = path
                        logger.info(f"   [Mealie] Using import endpoint: {path}")
                    canonical_source = canonicalize_url(url)
                    if canonical_source:
                        self._known_source_urls.add(canonical_source)
                    logger.info(f"   ⚠️ [Mealie] Duplicate: {url}")
                    return True, None, False

                if response.status_code in [404, 405]:
                    endpoint_error = f"HTTP {response.status_code}"
                    continue

                if response.status_code in TRANSIENT_HTTP_CODES:
                    return False, f"HTTP {response.status_code}", True

                body = response.text.strip().replace("\n", " ")
                if len(body) > 180:
                    body = f"{body[:177]}..."
                return False, f"HTTP {response.status_code}" + (f" - {body}" if body else ""), False

            return False, endpoint_error or "No compatible Mealie import endpoint found", False

        except requests.exceptions.Timeout as exc:
            return False, f"Timeout: {exc}", True
        except requests.exceptions.ConnectionError as exc:
            return False, f"Connection error: {exc}", True
        except requests.exceptions.RequestException as exc:
            return False, f"Request error: {exc}", True
        except Exception as exc:
            return False, str(exc), False

    def import_recipe(self, url: str) -> Tuple[bool, Optional[str], bool]:
        if not MEALIE_ENABLED:
            return False, "Mealie import is disabled", False

        return self.import_to_mealie(url)
