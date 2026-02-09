import json
import os
import re
from pathlib import Path
from typing import List

from dotenv import load_dotenv

from .version import __version__

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TARGET = int(os.getenv("TARGET_RECIPES_PER_SITE", 50))
DEFAULT_DEPTH = int(os.getenv("SCAN_DEPTH", 1000))
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

MEALIE_ENABLED = os.getenv("MEALIE_ENABLED", "true").lower() == "true"
MEALIE_URL = os.getenv("MEALIE_URL", "http://localhost:9000").rstrip("/")
MEALIE_API_TOKEN = os.getenv("MEALIE_API_TOKEN", "your-token")
MEALIE_IMPORT_TIMEOUT = int(os.getenv("MEALIE_IMPORT_TIMEOUT", 20))

DEFAULT_CRAWL_DELAY = float(os.getenv("CRAWL_DELAY", 2.0))
RESPECT_ROBOTS_TXT = os.getenv("RESPECT_ROBOTS_TXT", "true").lower() == "true"

CACHE_EXPIRY_DAYS = int(os.getenv("CACHE_EXPIRY_DAYS", 7))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", 3))


def _normalize_language(value: str) -> str:
    cleaned = value.strip().lower().replace("_", "-")
    if not cleaned:
        return ""
    return cleaned.split("-", 1)[0]


TARGET_LANGUAGE = _normalize_language(os.getenv("TARGET_LANGUAGE", "en"))
LANGUAGE_FILTER_ENABLED = os.getenv("LANGUAGE_FILTER_ENABLED", "true").lower() == "true"
LANGUAGE_DETECTION_STRICT = os.getenv("LANGUAGE_DETECTION_STRICT", "true").lower() == "true"
LANGUAGE_MIN_CONFIDENCE = float(os.getenv("LANGUAGE_MIN_CONFIDENCE", 0.70))
CLEANER_REMOVE_NON_TARGET_LANGUAGE = os.getenv("CLEANER_REMOVE_NON_TARGET_LANGUAGE", "true").lower() == "true"

REJECT_FILE = DATA_DIR / "rejects.json"
IMPORTED_FILE = DATA_DIR / "imported.json"
RETRY_FILE = DATA_DIR / "retry_queue.json"
STATS_FILE = DATA_DIR / "stats.json"
SITEMAP_CACHE_FILE = DATA_DIR / "sitemap_cache.json"

TRANSIENT_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}

NON_RECIPE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".ico",
    ".pdf",
    ".zip",
    ".mp4",
    ".webm",
    ".mov",
    ".avi",
    ".mkv",
)

NON_RECIPE_PATH_HINTS = (
    "/wp-content/uploads/",
    "/wp-json/",
    "/category/",
    "/tag/",
    "/author/",
    "/feed/",
)

LISTICLE_REGEX = re.compile(
    r"\b(top|best)\b.*\b(recipes|meals|dishes|ideas|desserts|appetizers|snacks|soups|salads|sides|cocktails|drinks)\b",
    re.IGNORECASE,
)

NUMBERED_COLLECTION_REGEX = re.compile(
    r"^\s*\d{1,3}\b.*\b(recipes|meals|dishes|ideas|desserts|appetizers|snacks|soups|salads|sides|cocktails|drinks)\b",
    re.IGNORECASE,
)

LISTICLE_TITLE_REGEX = re.compile(
    r"(\b(top|best)\b|\b\d{1,3}\b).*\b(recipes|meals|dishes|ideas|desserts|appetizers|snacks|soups|salads|sides|cocktails|drinks)\b",
    re.IGNORECASE,
)

HOW_TO_COOK_REGEX = re.compile(
    r"^how\s+to\s+(cook|make)\b",
    re.IGNORECASE,
)

BAD_KEYWORDS = [
    "roundup",
    "collection",
    "guide",
    "review",
    "giveaway",
    "shop",
    "store",
    "product",
]


def _parse_sites_data(data) -> List[str]:
    if isinstance(data, list):
        return [s for s in data if isinstance(s, str) and s.startswith("http")]

    if isinstance(data, dict) and "sites" in data:
        sites = data["sites"]
        return [s for s in sites if isinstance(s, str) and s.startswith("http")]

    return []


def _load_default_sites() -> List[str]:
    sites_file = ROOT_DIR / "sites.json"
    try:
        data = json.loads(sites_file.read_text(encoding="utf-8"))
        parsed = _parse_sites_data(data)
        if parsed:
            return parsed
    except OSError:
        pass
    except json.JSONDecodeError:
        pass

    return [
        "https://www.seriouseats.com",
        "https://www.wellplated.com",
        "https://www.recipetineats.com",
    ]


DEFAULT_SITES = _load_default_sites()
