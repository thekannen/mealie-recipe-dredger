from __future__ import annotations

import argparse
import json
import logging
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
    # Still works with explicit CLI args or exported env vars.
    pass

DEFAULT_SITES_FILE = "data/sites.json"
DEFAULT_TIMEOUT = 20
PER_PAGE = 1000

LOGGER = logging.getLogger("dredger.site_alignment")


def normalize_host(value: str) -> str:
    host = (value or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def host_from_url(url: Optional[str]) -> Optional[str]:
    if not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return None
    host = normalize_host(parsed.netloc)
    return host or None


def source_url(recipe: Dict[str, Any]) -> Optional[str]:
    for key in ("orgURL", "originalURL", "source"):
        value = recipe.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def recipe_id(recipe: Dict[str, Any]) -> Optional[str]:
    value = recipe.get("id") or recipe.get("recipeId")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def recipe_slug(recipe: Dict[str, Any]) -> Optional[str]:
    value = recipe.get("slug")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_sites_payload(data: Any) -> List[str]:
    if isinstance(data, list):
        return [entry for entry in data if isinstance(entry, str) and entry.startswith("http")]
    if isinstance(data, dict):
        sites = data.get("sites")
        if isinstance(sites, list):
            return [entry for entry in sites if isinstance(entry, str) and entry.startswith("http")]
    raise ValueError("Expected JSON array or object with a 'sites' list.")


def hosts_from_sites(sites: Iterable[str]) -> Set[str]:
    hosts: Set[str] = set()
    for site in sites:
        host = host_from_url(site)
        if host:
            hosts.add(host)
    return hosts


def load_allowed_hosts(path: Path) -> Set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sites = parse_sites_payload(payload)
    return hosts_from_sites(sites)


def load_host_snapshot(path: Path) -> Optional[Set[str]]:
    if not path.exists():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    values: List[str]
    if isinstance(payload, list):
        values = [entry for entry in payload if isinstance(entry, str)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("hosts"), list):
            values = [entry for entry in payload["hosts"] if isinstance(entry, str)]
        elif isinstance(payload.get("sites"), list):
            values = [entry for entry in payload["sites"] if isinstance(entry, str)]
        else:
            raise ValueError("Expected snapshot JSON with a 'hosts' or 'sites' list.")
    else:
        raise ValueError("Expected snapshot JSON array or object.")

    hosts: Set[str] = set()
    for value in values:
        if "://" in value:
            host = host_from_url(value)
        else:
            host = normalize_host(value)
        if host:
            hosts.add(host)
    return hosts


def save_host_snapshot(path: Path, hosts: Set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "hosts": sorted(hosts),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def host_allowed(host: str, allowed_hosts: Set[str]) -> bool:
    if host in allowed_hosts:
        return True
    return any(host.endswith(f".{allowed}") for allowed in allowed_hosts)


def removed_hosts_for_diff(baseline_hosts: Set[str], current_hosts: Set[str]) -> Set[str]:
    return {host for host in baseline_hosts if not host_allowed(host, current_hosts)}


def get_recipes(
    mealie_url: str,
    token: str,
    timeout: int,
    session: Optional[requests.Session] = None,
) -> List[Dict[str, Any]]:
    client = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    recipes: List[Dict[str, Any]] = []

    while True:
        response = client.get(
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
    recipe_identifier: Optional[str],
    slug: Optional[str],
    timeout: int,
    session: Optional[requests.Session] = None,
) -> Tuple[bool, str]:
    client = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}"}
    candidates = []
    for identifier in (recipe_identifier, slug):
        if identifier and identifier not in candidates:
            candidates.append(identifier)

    if not candidates:
        return False, "missing id/slug"

    for identifier in candidates:
        endpoint = f"{mealie_url}/api/recipes/{identifier}"
        try:
            response = client.delete(endpoint, headers=headers, timeout=timeout)
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
    source_value: Optional[str]
    recipe_identifier: Optional[str]
    slug: Optional[str]


@dataclass
class AlignmentReport:
    total_recipes: int
    missing_source_count: int
    candidate_count: int
    deleted_count: int
    failed_count: int


def build_candidates(
    recipes: Iterable[Dict[str, Any]],
    should_prune_host: Callable[[str], bool],
    keep_missing_source: bool,
) -> Tuple[List[Candidate], int]:
    to_prune: List[Candidate] = []
    missing_source_count = 0

    for recipe in recipes:
        name = str(recipe.get("name") or "Unknown")
        source_value = source_url(recipe)
        host = host_from_url(source_value)
        recipe_identifier = recipe_id(recipe)
        slug = recipe_slug(recipe)

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
                source_value=source_value,
                recipe_identifier=recipe_identifier,
                slug=slug,
            )
        )

    return to_prune, missing_source_count


def align_mealie_recipes(
    mealie_url: str,
    token: str,
    timeout: int,
    allowed_hosts: Set[str],
    apply: bool,
    include_missing_source: bool = False,
    prune_hosts: Optional[Set[str]] = None,
    preview_limit: int = 50,
    session: Optional[requests.Session] = None,
    logger: Optional[logging.Logger] = None,
) -> AlignmentReport:
    active_logger = logger or LOGGER
    if not mealie_url:
        raise ValueError("Missing mealie_url.")
    if not token:
        raise ValueError("Missing API token.")
    if not allowed_hosts:
        raise ValueError("No valid hosts parsed from active sites list.")

    current_hosts = {normalize_host(host) for host in allowed_hosts if normalize_host(host)}
    scope_hosts: Optional[Set[str]] = None
    if prune_hosts is not None:
        scope_hosts = {normalize_host(host) for host in prune_hosts if normalize_host(host)}
        should_prune_host = lambda host: host_allowed(host, scope_hosts)
        active_logger.info(f"[align] Prune scope hosts (diff): {len(scope_hosts)}")
    else:
        should_prune_host = lambda host: not host_allowed(host, current_hosts)
        active_logger.info(f"[align] Active hosts: {len(current_hosts)}")

    recipes = get_recipes(mealie_url=mealie_url, token=token, timeout=timeout, session=session)
    candidates, missing_source_count = build_candidates(
        recipes=recipes,
        should_prune_host=should_prune_host,
        keep_missing_source=not include_missing_source,
    )

    active_logger.info(f"[align] Total recipes scanned: {len(recipes)}")
    active_logger.info(f"[align] Recipes with missing source URL: {missing_source_count}")
    active_logger.info(f"[align] Recipes to prune: {len(candidates)}")

    limit = max(0, int(preview_limit))
    for item in candidates[:limit]:
        source_display = item.source_value or "(missing)"
        host_display = item.host or "(missing)"
        active_logger.info(f"[align][plan] {item.name} | host={host_display} | source={source_display}")
    if len(candidates) > limit:
        active_logger.info(f"[align][plan] ... and {len(candidates) - limit} more")

    deleted = 0
    failed = 0
    if apply:
        for item in candidates:
            ok, detail = delete_recipe(
                mealie_url=mealie_url,
                token=token,
                recipe_identifier=item.recipe_identifier,
                slug=item.slug,
                timeout=timeout,
                session=session,
            )
            if ok:
                deleted += 1
                active_logger.info(f"[align][delete] {item.name} ({detail})")
            else:
                failed += 1
                active_logger.warning(f"[align][warn] Failed to delete '{item.name}': {detail}")
    else:
        active_logger.info("[align] Dry run complete. Re-run with apply mode to delete.")

    return AlignmentReport(
        total_recipes=len(recipes),
        missing_source_count=missing_source_count,
        candidate_count=len(candidates),
        deleted_count=deleted,
        failed_count=failed,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align existing Mealie recipes against site-domain policy. "
            "By default, prunes hosts not in --sites-file. "
            "If --baseline-sites-file is set, prunes only hosts removed from baseline -> current."
        ),
    )
    parser.add_argument(
        "--sites-file",
        default=DEFAULT_SITES_FILE,
        help="Path to sites JSON (default: data/sites.json)",
    )
    parser.add_argument(
        "--baseline-sites-file",
        default="",
        help="Optional baseline/original sites JSON. If set, only removed domains are pruned.",
    )
    parser.add_argument(
        "--mealie-url",
        default=os.getenv("MEALIE_URL", ""),
        help="Mealie base URL (or set MEALIE_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MEALIE_API_TOKEN", ""),
        help="Mealie API token (or set MEALIE_API_TOKEN)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="HTTP timeout seconds")
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
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=50,
        help="How many candidate lines to print before summarizing.",
    )
    return parser.parse_args(argv)


def run_from_args(args: argparse.Namespace, logger: Optional[logging.Logger] = None) -> int:
    active_logger = logger or LOGGER

    sites_file = Path(args.sites_file)
    if not sites_file.exists():
        active_logger.error(f"[align][error] Sites file not found: {sites_file}")
        return 1

    mealie_url = args.mealie_url.rstrip("/")
    token = args.token.strip()
    if not mealie_url:
        active_logger.error("[align][error] Missing Mealie URL. Use --mealie-url or MEALIE_URL.")
        return 1
    if not token:
        active_logger.error("[align][error] Missing Mealie token. Use --token or MEALIE_API_TOKEN.")
        return 1
    if token in {"your-token", "your_mealie_token_here"}:
        active_logger.error("[align][error] Placeholder token detected. Set a real Mealie API token.")
        return 1

    try:
        current_hosts = load_allowed_hosts(sites_file)
    except Exception as exc:
        active_logger.error(f"[align][error] Failed to parse sites file: {exc}")
        return 1

    baseline_hosts: Optional[Set[str]] = None
    prune_hosts: Optional[Set[str]] = None
    if args.baseline_sites_file:
        baseline_file = Path(args.baseline_sites_file)
        if not baseline_file.exists():
            active_logger.error(f"[align][error] Baseline sites file not found: {baseline_file}")
            return 1
        try:
            baseline_hosts = load_allowed_hosts(baseline_file)
        except Exception as exc:
            active_logger.error(f"[align][error] Failed to parse baseline sites file: {exc}")
            return 1
        prune_hosts = removed_hosts_for_diff(baseline_hosts, current_hosts)

    active_logger.info(f"[align][info] Current hosts from {sites_file}: {len(current_hosts)}")
    if baseline_hosts is not None and prune_hosts is not None:
        active_logger.info(f"[align][info] Baseline hosts from {args.baseline_sites_file}: {len(baseline_hosts)}")
        active_logger.info(f"[align][info] Removed hosts in scope: {len(prune_hosts)}")
    active_logger.info(f"[align][info] Mode: {'APPLY' if args.apply else 'DRY RUN'}")

    try:
        report = align_mealie_recipes(
            mealie_url=mealie_url,
            token=token,
            timeout=args.timeout,
            allowed_hosts=current_hosts,
            apply=args.apply,
            include_missing_source=args.include_missing_source,
            prune_hosts=prune_hosts,
            preview_limit=args.preview_limit,
        )
    except Exception as exc:
        active_logger.error(f"[align][error] Failed to align recipes: {exc}")
        return 1

    if report.candidate_count == 0:
        active_logger.info("[align][done] No recipes to prune.")
        return 0

    if args.apply:
        active_logger.info(
            f"[align][done] Deleted: {report.deleted_count}, Failed: {report.failed_count}, Planned: {report.candidate_count}"
        )
        return 0 if report.failed_count == 0 else 2

    active_logger.info("[align][done] Dry run complete.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    return run_from_args(parse_args(argv), logger=LOGGER)


if __name__ == "__main__":
    raise SystemExit(main())
