import json
import re
from typing import Any, Iterable, Optional, Tuple

from bs4 import BeautifulSoup

ENGLISH_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
    "you",
    "your",
    "recipe",
    "ingredients",
    "instructions",
    "minutes",
    "serve",
    "cook",
    "make",
    "easy",
}

SPANISH_STOPWORDS = {
    "a",
    "al",
    "con",
    "de",
    "del",
    "el",
    "en",
    "es",
    "esta",
    "la",
    "las",
    "lo",
    "los",
    "para",
    "por",
    "que",
    "se",
    "sin",
    "su",
    "una",
    "un",
    "y",
    "receta",
    "ingredientes",
    "instrucciones",
    "minutos",
    "cocinar",
    "hacer",
    "fácil",
}

LANGUAGE_TOKEN_RE = re.compile(r"[a-zA-ZáéíóúñüÁÉÍÓÚÑÜ]+")
WHITESPACE_RE = re.compile(r"\s+")
ACCENT_RE = re.compile(r"[áéíóúñü]")


def normalize_language_code(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None

    cleaned = value.strip().lower().replace("_", "-")
    if not cleaned or cleaned == "x-default":
        return None

    primary = cleaned.split("-", 1)[0]
    if len(primary) < 2:
        return None
    return primary


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _iter_strings(values: Iterable[object]) -> Iterable[str]:
    for value in values:
        text = _coerce_text(value).strip()
        if text:
            yield text


def detect_language_from_text(text: str, min_confidence: float = 0.70) -> Tuple[Optional[str], float]:
    tokens = [t.lower() for t in LANGUAGE_TOKEN_RE.findall(text)]
    if len(tokens) < 8:
        return None, 0.0

    english = sum(1 for token in tokens if token in ENGLISH_STOPWORDS)
    spanish = sum(1 for token in tokens if token in SPANISH_STOPWORDS)
    spanish += sum(1 for token in tokens if ACCENT_RE.search(token))

    total_signal = english + spanish
    if total_signal < 3:
        return None, 0.0

    if english == spanish:
        return None, 0.5

    language = "en" if english > spanish else "es"
    confidence = max(english, spanish) / total_signal
    if confidence < min_confidence:
        return None, confidence
    return language, confidence


def _extract_declared_language_from_jsonld(soup: BeautifulSoup) -> Optional[str]:
    def find_in_language(payload: Any) -> Optional[str]:
        if isinstance(payload, dict):
            if "inLanguage" in payload:
                value = payload["inLanguage"]
                if isinstance(value, list):
                    for item in value:
                        normalized = normalize_language_code(item)
                        if normalized:
                            return normalized
                else:
                    normalized = normalize_language_code(value)
                    if normalized:
                        return normalized

            for nested in payload.values():
                found = find_in_language(nested)
                if found:
                    return found

        if isinstance(payload, list):
            for nested in payload:
                found = find_in_language(nested)
                if found:
                    return found

        return None

    for script in soup.find_all("script", type=lambda v: isinstance(v, str) and "ld+json" in v):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        found = find_in_language(data)
        if found:
            return found
    return None


def _extract_declared_language_from_soup(soup: BeautifulSoup) -> Optional[str]:
    html_tag = soup.find("html")
    if html_tag:
        lang_attr = html_tag.attrs.get("lang")
        normalized = normalize_language_code(lang_attr)
        if normalized:
            return normalized

    for selector in [
        {"name": "meta", "attrs": {"http-equiv": re.compile(r"content-language", re.IGNORECASE)}},
        {"name": "meta", "attrs": {"name": re.compile(r"language", re.IGNORECASE)}},
        {"name": "meta", "attrs": {"property": re.compile(r"og:locale", re.IGNORECASE)}},
    ]:
        tag = soup.find(selector["name"], attrs=selector["attrs"])
        if tag:
            normalized = normalize_language_code(tag.attrs.get("content"))
            if normalized:
                return normalized

    return _extract_declared_language_from_jsonld(soup)


def _extract_text_from_soup(soup: BeautifulSoup) -> str:
    parts = []
    if soup.title and soup.title.string:
        parts.append(soup.title.string)

    description = soup.find("meta", attrs={"name": re.compile(r"description", re.IGNORECASE)})
    if description and description.attrs.get("content"):
        parts.append(_coerce_text(description.attrs.get("content")))

    for tag in soup.find_all(["h1", "h2", "p"], limit=25):
        text = tag.get_text(" ", strip=True)
        if text:
            parts.append(text)

    return WHITESPACE_RE.sub(" ", " ".join(parts)).strip()


def detect_language_from_html(
    soup: BeautifulSoup,
    response_text: str = "",
    min_confidence: float = 0.70,
) -> Tuple[Optional[str], str, float]:
    declared = _extract_declared_language_from_soup(soup)
    if declared:
        return declared, "declared", 1.0

    merged_text = " ".join(filter(None, [_extract_text_from_soup(soup), _coerce_text(response_text)[:5000]]))
    detected, confidence = detect_language_from_text(merged_text, min_confidence=min_confidence)
    if detected:
        return detected, "text", confidence

    return None, "unknown", confidence


def detect_language_from_recipe_payload(
    payload: dict[str, Any],
    min_confidence: float = 0.70,
) -> Tuple[Optional[str], str, float]:
    for key in ["language", "recipeLanguage", "inLanguage", "orgLanguage", "originalLanguage"]:
        normalized = normalize_language_code(payload.get(key))
        if normalized:
            return normalized, f"field:{key}", 1.0

    text_chunks = []
    text_chunks.extend(
        _iter_strings(
            [
                payload.get("name"),
                payload.get("description"),
                payload.get("subtitle"),
                payload.get("recipeYield"),
            ]
        )
    )

    ingredients = payload.get("recipeIngredient")
    if isinstance(ingredients, list):
        for ingredient in ingredients[:80]:
            if isinstance(ingredient, dict):
                text_chunks.extend(_iter_strings([ingredient.get("title"), ingredient.get("note"), ingredient.get("food")]))
            else:
                text_chunks.extend(_iter_strings([ingredient]))

    instructions = payload.get("recipeInstructions")
    if isinstance(instructions, list):
        for step in instructions[:120]:
            if isinstance(step, dict):
                text_chunks.extend(_iter_strings([step.get("text"), step.get("title")]))
            else:
                text_chunks.extend(_iter_strings([step]))
    elif instructions:
        text_chunks.extend(_iter_strings([instructions]))

    merged_text = WHITESPACE_RE.sub(" ", " ".join(text_chunks)).strip()
    detected, confidence = detect_language_from_text(merged_text, min_confidence=min_confidence)
    if detected:
        return detected, "text", confidence

    return None, "unknown", confidence
