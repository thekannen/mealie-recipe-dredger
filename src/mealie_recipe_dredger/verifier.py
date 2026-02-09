import re
from typing import Optional, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .config import (
    BAD_KEYWORDS,
    HOW_TO_COOK_REGEX,
    LANGUAGE_DETECTION_STRICT,
    LANGUAGE_FILTER_ENABLED,
    LANGUAGE_MIN_CONFIDENCE,
    LISTICLE_REGEX,
    LISTICLE_TITLE_REGEX,
    NUMBERED_COLLECTION_REGEX,
    NON_RECIPE_EXTENSIONS,
    NON_RECIPE_PATH_HINTS,
    TARGET_LANGUAGE,
    TRANSIENT_HTTP_CODES,
)
from .language import detect_language_from_html

RECIPE_CLASS_PATTERN = re.compile(r"(wp-recipe-maker|tasty-recipes|mv-create-card|recipe-card)")


class RecipeVerifier:
    def __init__(self, session: requests.Session):
        self.session = session

    def pre_filter_candidate(self, url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            path = parsed.path.lower()

            if path.endswith(NON_RECIPE_EXTENSIONS):
                return "Non-HTML media URL"

            if any(marker in path for marker in NON_RECIPE_PATH_HINTS):
                return "Non-recipe path"

            if path in ("/blog", "/blog/"):
                return "Blog index path"
        except Exception:
            pass

        return None

    def is_paranoid_skip(self, url: str, soup: Optional[BeautifulSoup] = None) -> Optional[str]:
        try:
            path = urlparse(url).path
            slug = path.strip("/").split("/")[-1].lower()
            normalized_slug = re.sub(r"[-_]+", " ", slug)

            if HOW_TO_COOK_REGEX.search(normalized_slug):
                return "How-to article"

            if LISTICLE_REGEX.search(normalized_slug) or NUMBERED_COLLECTION_REGEX.search(normalized_slug):
                return f"Listicle detected: {slug}"

            for keyword in BAD_KEYWORDS:
                if keyword in normalized_slug:
                    return f"Bad keyword: {keyword}"

            if soup:
                title = soup.title.string.lower() if soup.title and soup.title.string else ""
                if HOW_TO_COOK_REGEX.search(title):
                    return "How-to title"
                if (
                    LISTICLE_TITLE_REGEX.search(title)
                    or NUMBERED_COLLECTION_REGEX.search(title)
                    or "best recipes" in title
                    or "top 10" in title
                ):
                    return "Listicle title"

        except Exception:
            pass

        return None

    def verify_recipe(self, url: str) -> Tuple[bool, Optional[BeautifulSoup], Optional[str], bool]:
        pre_filtered_reason = self.pre_filter_candidate(url)
        if pre_filtered_reason:
            return False, None, pre_filtered_reason, False

        try:
            response = self.session.get(url, timeout=10)
            if response.status_code != 200:
                is_transient = response.status_code in TRANSIENT_HTTP_CODES
                return False, None, f"HTTP {response.status_code}", is_transient

            is_recipe = False
            soup = None

            if '"@type":"Recipe"' in response.text or '"@type": "Recipe"' in response.text:
                is_recipe = True

            if not is_recipe:
                soup = BeautifulSoup(response.content, "lxml")
                if soup.find(class_=RECIPE_CLASS_PATTERN):
                    is_recipe = True

            if not is_recipe:
                return False, soup, "No recipe detected", False

            if soup is None:
                soup = BeautifulSoup(response.content, "lxml")

            if LANGUAGE_FILTER_ENABLED and TARGET_LANGUAGE:
                detected_language, _source, _confidence = detect_language_from_html(
                    soup,
                    response_text=response.text,
                    min_confidence=LANGUAGE_MIN_CONFIDENCE,
                )
                if detected_language and detected_language != TARGET_LANGUAGE:
                    return False, soup, f"Language mismatch: {detected_language}", False
                if LANGUAGE_DETECTION_STRICT and not detected_language:
                    return False, soup, "Language unknown", False

            skip_reason = self.is_paranoid_skip(url, soup)
            if skip_reason:
                return False, soup, skip_reason, False

            return True, soup, None, False

        except requests.exceptions.Timeout as exc:
            return False, None, f"Timeout: {exc}", True
        except requests.exceptions.ConnectionError as exc:
            return False, None, f"Connection error: {exc}", True
        except requests.exceptions.RequestException as exc:
            return False, None, f"Request error: {exc}", True
        except Exception as exc:
            return False, None, f"Exception: {exc}", False
