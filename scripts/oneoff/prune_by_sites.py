#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    # Script still works without python-dotenv; CLI args/env can be provided directly.
    pass


DEFAULT_SITES_FILE = "data/sites.json"
PER_PAGE = 1000


def _normalize_host(value: str) -> str:
    host = (value or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_from_url(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    host = _normalize_host(parsed.netloc)
    return host or None


def _source_url(recipe: Dict[str, Any]) -> Optional[str]:
    for key in ("orgURL", "originalURL", "source"):
        value = recipe.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _recipe_id(recipe: Dict[str, Any]) -> Optional[str]:
    value = recipe.get("id") or recipe.get("recipeId")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _recipe_slug(recipe: Dict[str, Any]) -> Optional[str]:
    value = recipe.get("slug")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_sites_payload(data: Any) -> List[str]:
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, str) and entry.startswith("http")]
    if isinstance(data, dict):
        sites = data.get("sites")
        if isinstance(sites, list):
            return [entry for entry in sites if isinstance(entry, str) and entry.startswith("http")]
    raise ValueError("Expected JSON array or object with a 'sites' list.")


def load_allowed_hosts(path: Path) -> Set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sites = _parse_sites_payload(payload)

    hosts: Set[str] = set()
    for site in sites:
        host = _host_from_url(site)
        if host:
            hosts.add(host)
    return hosts


def host_allowed(host: str, allowed_hosts: Set[str]) -> bool:
    if host in allowed_hosts:
        return True
    return any(host.endswith(f".{allowed}") for allowed in allowed_hosts)


def get_recipes(mealie_url: str, token: str, timeout: int) -> List[Dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    recipes: List[Dict[str, Any]] = []

    while True:
        response = requests.get(
            f"{mealie_url}/api/recipes",
            headers=headers,
            params={"page": page, "perPage": PER_PAGE},
            timeout=timeout,
        )
        if response.status_code == 401:
            raise RuntimeError(
                "401 Unauthorized. Check MEALIE_API_TOKEN (API token required; password won't work)."
            )
        if response.status_code == 403:
            raise RuntimeError(
                "403 Forbidden. Token is valid but lacks permission for recipe listing."
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            break
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            break
        recipes.extend(item for item in items if isinstance(item, dict))
        page += 1

    return recipes


def delete_recipe(
    mealie_url: str,
    token: str,
    recipe_id: Optional[str],
    slug: Optional[str],
    timeout: int,
) -> Tuple[bool, str]:
    headers = {"Authorization": f"Bearer {token}"}
    candidates = []
    for identifier in (recipe_id, slug):
        if identifier and identifier not in candidates:
            candidates.append(identifier)

    if not candidates:
        return False, "missing id/slug"

    for identifier in candidates:
        endpoint = f"{mealie_url}/api/recipes/{identifier}"
        try:
            response = requests.delete(endpoint, headers=headers, timeout=timeout)
        except Exception as exc:
            return False, str(exc)

        if response.status_code == 200:
            return True, identifier
        if response.status_code in (404, 405):
            continue

        body = response.text.strip().replace("\n", " ")
        if len(body) > 180:
            body = f"{body[:177]}..."
        return False, f"HTTP {response.status_code} {body}".strip()

    return False, "not found by id/slug"


@dataclass
class Candidate:
    name: str
    host: Optional[str]
    source_url: Optional[str]
    recipe_id: Optional[str]
    slug: Optional[str]


def build_candidates(
    recipes: Iterable[Dict[str, Any]],
    should_prune_host: Callable[[str], bool],
    keep_missing_source: bool,
) -> Tuple[List[Candidate], int]:
    to_prune: List[Candidate] = []
    missing_source_count = 0

    for recipe in recipes:
        name = str(recipe.get("name") or "Unknown")
        source = _source_url(recipe)
        host = _host_from_url(source)
        recipe_id = _recipe_id(recipe)
        slug = _recipe_slug(recipe)

        if not host:
            missing_source_count += 1
            if keep_missing_source:
                continue

        if host and not should_prune_host(host):
            continue

        to_prune.append(
            Candidate(
                name=name,
                host=host,
                source_url=source,
                recipe_id=recipe_id,
                slug=slug,
            )
        )

    return to_prune, missing_source_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "One-time cleanup for Mealie imports by source domain. "
            "By default, prunes hosts not in --sites-file. "
            "If --baseline-sites-file is set, prunes only hosts removed from baseline -> current."
        ),
    )
    parser.add_argument("--sites-file", default=DEFAULT_SITES_FILE, help="Path to sites JSON (default: data/sites.json)")
    parser.add_argument(
        "--baseline-sites-file",
        default="",
        help="Optional baseline/original sites JSON. If set, only removed domains are pruned.",
    )
    parser.add_argument("--mealie-url", default=os.getenv("MEALIE_URL", ""), help="Mealie base URL (or set MEALIE_URL)")
    parser.add_argument(
        "--token",
        default=os.getenv("MEALIE_API_TOKEN", ""),
        help="Mealie API token (or set MEALIE_API_TOKEN)",
    )
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds")
    parser.add_argument(
        "--include-missing-source",
        action="store_true",
        help="Also delete recipes with no source URL fields (orgURL/originalURL/source).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletions. If omitted, runs in dry-run mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    sites_file = Path(args.sites_file)
    if not sites_file.exists():
        print(f"[error] Sites file not found: {sites_file}")
        return 1

    mealie_url = args.mealie_url.rstrip("/")
    token = args.token.strip()
    if not mealie_url:
        print("[error] Missing Mealie URL. Use --mealie-url or MEALIE_URL.")
        return 1
    if not token:
        print("[error] Missing Mealie token. Use --token or MEALIE_API_TOKEN.")
        return 1
    if token in {"your-token", "your_mealie_token_here"}:
        print("[error] Placeholder token detected. Set a real Mealie API token.")
        return 1

    try:
        current_hosts = load_allowed_hosts(sites_file)
    except Exception as exc:
        print(f"[error] Failed to parse sites file: {exc}")
        return 1

    baseline_hosts: Optional[Set[str]] = None
    removed_hosts: Optional[Set[str]] = None
    if args.baseline_sites_file:
        baseline_file = Path(args.baseline_sites_file)
        if not baseline_file.exists():
            print(f"[error] Baseline sites file not found: {baseline_file}")
            return 1
        try:
            baseline_hosts = load_allowed_hosts(baseline_file)
        except Exception as exc:
            print(f"[error] Failed to parse baseline sites file: {exc}")
            return 1

        removed_hosts = {host for host in baseline_hosts if not host_allowed(host, current_hosts)}

    print(f"[info] Current hosts from {sites_file}: {len(current_hosts)}")
    if baseline_hosts is not None and removed_hosts is not None:
        print(f"[info] Baseline hosts from {args.baseline_sites_file}: {len(baseline_hosts)}")
        print(f"[info] Removed hosts in scope: {len(removed_hosts)}")
    print(f"[info] Mode: {'APPLY' if args.apply else 'DRY RUN'}")

    if removed_hosts is not None:
        should_prune_host = lambda host: host_allowed(host, removed_hosts)
    else:
        should_prune_host = lambda host: not host_allowed(host, current_hosts)

    try:
        recipes = get_recipes(mealie_url, token, args.timeout)
    except Exception as exc:
        print(f"[error] Failed to fetch recipes from Mealie: {exc}")
        return 1

    print(f"[info] Total recipes scanned: {len(recipes)}")
    candidates, missing_source_count = build_candidates(
        recipes=recipes,
        should_prune_host=should_prune_host,
        keep_missing_source=not args.include_missing_source,
    )

    print(f"[info] Recipes with missing source URL: {missing_source_count}")
    print(f"[info] Recipes to prune: {len(candidates)}")

    if not candidates:
        print("[done] No recipes to prune.")
        return 0

    for item in candidates[:50]:
        source_display = item.source_url or "(missing)"
        host_display = item.host or "(missing)"
        print(f"[plan] {item.name} | host={host_display} | source={source_display}")
    if len(candidates) > 50:
        print(f"[plan] ... and {len(candidates) - 50} more")

    if not args.apply:
        print("[done] Dry run complete. Re-run with --apply to delete.")
        return 0

    deleted = 0
    failed = 0
    for item in candidates:
        ok, detail = delete_recipe(
            mealie_url=mealie_url,
            token=token,
            recipe_id=item.recipe_id,
            slug=item.slug,
            timeout=args.timeout,
        )
        if ok:
            deleted += 1
            print(f"[delete] {item.name} ({detail})")
        else:
            failed += 1
            print(f"[warn] Failed to delete '{item.name}': {detail}")

    print(f"[done] Deleted: {deleted}, Failed: {failed}, Planned: {len(candidates)}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
