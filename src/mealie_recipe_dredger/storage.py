import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

from .config import (
    CACHE_EXPIRY_DAYS,
    IMPORTED_FILE,
    REJECT_FILE,
    RETRY_FILE,
    SITEMAP_CACHE_FILE,
    STATS_FILE,
)
from .models import SiteStats
from .url_utils import canonicalize_url

logger = logging.getLogger("dredger")


class StorageManager:
    def __init__(self):
        self.rejects: Set[str] = self._load_json_set(REJECT_FILE)
        self.imported: Set[str] = self._load_json_set(IMPORTED_FILE)
        self.retry_queue: Dict[str, dict] = self._canonicalize_retry_queue(self._load_json_dict(RETRY_FILE))
        self.stats: Dict[str, dict] = self._load_json_dict(STATS_FILE)
        self.sitemap_cache: Dict[str, dict] = self._load_json_dict(SITEMAP_CACHE_FILE)

        self._changes_since_flush = 0
        self._flush_threshold = 50

    def _load_json_set(self, filename: Path) -> Set[str]:
        if filename.exists():
            try:
                raw = json.loads(filename.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    normalized = set()
                    for entry in raw:
                        if not isinstance(entry, str):
                            continue
                        normalized_entry = self._normalize_url_key(entry)
                        if normalized_entry:
                            normalized.add(normalized_entry)
                    return normalized
            except Exception as exc:
                logger.warning(f"Error loading {filename}: {exc}")
        return set()

    def _load_json_dict(self, filename: Path) -> dict:
        if filename.exists():
            try:
                return json.loads(filename.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning(f"Error loading {filename}: {exc}")
        return {}

    def _save_json_set(self, filename: Path, data_set: Set[str]):
        filename.write_text(json.dumps(list(data_set), indent=2), encoding="utf-8")

    def _save_json_dict(self, filename: Path, data_dict: dict):
        filename.write_text(json.dumps(data_dict, indent=2), encoding="utf-8")

    def _normalize_url_key(self, url: str) -> str:
        normalized = canonicalize_url(url)
        return normalized or url.strip().lower()

    def _canonicalize_retry_queue(self, queue: dict) -> Dict[str, dict]:
        if not isinstance(queue, dict):
            return {}

        normalized: Dict[str, dict] = {}
        for key, value in queue.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            normalized_key = self._normalize_url_key(key)
            if normalized_key in normalized:
                existing_attempts = int(normalized[normalized_key].get("attempts", 0))
                incoming_attempts = int(value.get("attempts", 0))
                if incoming_attempts > existing_attempts:
                    normalized[normalized_key] = value
                continue
            normalized[normalized_key] = value
        return normalized

    def add_imported(self, url: str):
        url_key = self._normalize_url_key(url)
        self.imported.add(url_key)
        if url_key in self.retry_queue:
            self.retry_queue.pop(url_key, None)
        self._changes_since_flush += 1
        self._auto_flush()

    def add_reject(self, url: str):
        url_key = self._normalize_url_key(url)
        self.rejects.add(url_key)
        if url_key in self.retry_queue:
            self.retry_queue.pop(url_key, None)
        self._changes_since_flush += 1
        self._auto_flush()

    def add_retry(self, url: str, reason: str, increment: bool = False):
        url_key = self._normalize_url_key(url)
        existing = self.retry_queue.get(url_key, {})
        attempts = int(existing.get("attempts", 0))
        if increment:
            attempts += 1

        self.retry_queue[url_key] = {
            "reason": reason,
            "attempts": attempts,
            "last_attempt": datetime.now().isoformat(),
        }
        self._changes_since_flush += 1
        self._auto_flush()

    def remove_retry(self, url: str):
        url_key = self._normalize_url_key(url)
        if url_key in self.retry_queue:
            self.retry_queue.pop(url_key, None)
            self._changes_since_flush += 1
            self._auto_flush()

    def update_stats(self, site_url: str, stats: SiteStats):
        self.stats[site_url] = stats.to_dict()
        self._changes_since_flush += 1
        self._auto_flush()

    def get_cached_sitemap(self, site_url: str) -> Optional[dict]:
        if site_url not in self.sitemap_cache:
            return None

        cache_entry = self.sitemap_cache[site_url]
        cached_time = datetime.fromisoformat(cache_entry["timestamp"])

        if datetime.now() - cached_time > timedelta(days=CACHE_EXPIRY_DAYS):
            return None

        return cache_entry

    def cache_sitemap(self, site_url: str, sitemap_url: str, urls: List[str]):
        self.sitemap_cache[site_url] = {
            "sitemap_url": sitemap_url,
            "urls": urls,
            "timestamp": datetime.now().isoformat(),
        }
        self._changes_since_flush += 1
        self._auto_flush()

    def _auto_flush(self):
        if self._changes_since_flush >= self._flush_threshold:
            self.flush_all()

    def flush_all(self):
        self._save_json_set(REJECT_FILE, self.rejects)
        self._save_json_set(IMPORTED_FILE, self.imported)
        self._save_json_dict(RETRY_FILE, self.retry_queue)
        self._save_json_dict(STATS_FILE, self.stats)
        self._save_json_dict(SITEMAP_CACHE_FILE, self.sitemap_cache)
        self._changes_since_flush = 0
