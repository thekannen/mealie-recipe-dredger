from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
    "ref_url",
    "s",
    "spm",
}

NUMERIC_SUFFIX_RE = re.compile(r"\s*\((\d+)\)\s*$")
WHITESPACE_RE = re.compile(r"\s+")


def canonicalize_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    try:
        parts = urlsplit(raw)
    except Exception:
        return raw.lower()

    if not parts.scheme or not parts.netloc:
        return raw.lower()

    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parts.path or "/"
    path = re.sub(r"/+", "/", path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    filtered_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))
    filtered_query.sort()
    query = urlencode(filtered_query, doseq=True)

    return urlunsplit((scheme, netloc, path, query, ""))


def strip_numeric_suffix(name: str | None) -> str:
    normalized = WHITESPACE_RE.sub(" ", (name or "").strip())
    normalized = NUMERIC_SUFFIX_RE.sub("", normalized)
    return normalized.strip()


def has_numeric_suffix(name: str | None) -> bool:
    return NUMERIC_SUFFIX_RE.search((name or "").strip()) is not None


def numeric_suffix_value(name: str | None) -> int:
    match = NUMERIC_SUFFIX_RE.search((name or "").strip())
    if not match:
        return 0
    try:
        return int(match.group(1))
    except ValueError:
        return 0
