from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
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
DEFAULT_TIMEOUT = 300
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


def create_mealie_backup(
    mealie_url: str,
    token: str,
    timeout: int,
    session: Optional[requests.Session] = None,
) -> Tuple[bool, str]:
    client = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"{mealie_url}/api/admin/backups"
    try:
        response = client.post(endpoint, headers=headers, timeout=timeout)
    except Exception as exc:
        return False, str(exc)

    if response.status_code in (200, 201, 202):
        message = ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("message") or "").strip()
        except Exception:
            message = ""
        return True, message or f"HTTP {response.status_code}"

    body = response.text.strip().replace("\n", " ")
    if len(body) > 180:
        body = f"{body[:177]}..."
    return False, f"HTTP {response.status_code}" + (f" - {body}" if body else "")


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
    audit_file: Optional[Path] = None,
    backup_before_apply: bool = False,
    prompt_backup_before_apply: bool = False,
    require_confirmation: bool = False,
    assume_yes: bool = False,
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

    if audit_file:
        try:
            audit_file.parent.mkdir(parents=True, exist_ok=True)
            audit_payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": "apply" if apply else "dry_run",
                "candidate_count": len(candidates),
                "missing_source_count": missing_source_count,
                "candidates": [
                    {
                        "name": item.name,
                        "host": item.host,
                        "source": item.source_value,
                        "recipe_id": item.recipe_identifier,
                        "slug": item.slug,
                    }
                    for item in candidates
                ],
            }
            audit_file.write_text(json.dumps(audit_payload, indent=2), encoding="utf-8")
            active_logger.info(f"[align][info] Candidate audit written: {audit_file}")
        except Exception as exc:
            active_logger.warning(f"[align][warn] Failed to write audit file '{audit_file}': {exc}")

    deleted = 0
    failed = 0
    if apply:
        if candidates and require_confirmation:
            if not assume_yes:
                if not sys.stdin.isatty():
                    raise RuntimeError("Refusing apply in non-interactive mode without --yes.")
                answer = input(f"[align][confirm] Delete {len(candidates)} recipe(s)? [y/N]: ").strip().lower()
                if answer not in {"y", "yes"}:
                    active_logger.info("[align] Apply cancelled by user.")
                    return AlignmentReport(
                        total_recipes=len(recipes),
                        missing_source_count=missing_source_count,
                        candidate_count=len(candidates),
                        deleted_count=0,
                        failed_count=0,
                    )

        should_backup = bool(backup_before_apply)
        if candidates and prompt_backup_before_apply and not should_backup:
            if not sys.stdin.isatty():
                active_logger.warning("[align][warn] Skipping backup prompt in non-interactive mode.")
            else:
                answer = input("[align][confirm] Create a Mealie backup before deletions? [y/N]: ").strip().lower()
                if answer in {"y", "yes"}:
                    should_backup = True

        if candidates and should_backup:
            backup_ok, backup_detail = create_mealie_backup(
                mealie_url=mealie_url,
                token=token,
                timeout=timeout,
                session=session,
            )
            if backup_ok:
                active_logger.info(
                    f"[align][backup] Backup created successfully{f': {backup_detail}' if backup_detail else ''}"
                )
            else:
                active_logger.error(f"[align][backup] Backup failed: {backup_detail}")
                if not assume_yes and sys.stdin.isatty():
                    proceed = input("[align][confirm] Continue without backup? [y/N]: ").strip().lower()
                    if proceed not in {"y", "yes"}:
                        active_logger.info("[align] Apply cancelled due to backup failure.")
                        return AlignmentReport(
                            total_recipes=len(recipes),
                            missing_source_count=missing_source_count,
                            candidate_count=len(candidates),
                            deleted_count=0,
                            failed_count=0,
                        )
                else:
                    active_logger.info("[align] Apply cancelled due to backup failure.")
                    return AlignmentReport(
                        total_recipes=len(recipes),
                        missing_source_count=missing_source_count,
                        candidate_count=len(candidates),
                        deleted_count=0,
                        failed_count=0,
                    )

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
            "By default, compares --baseline-sites-file -> --sites-file and prunes only removed domains."
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
        help="Baseline/original sites JSON used for diff scope.",
    )
    parser.add_argument(
        "--prune-outside-current",
        action="store_true",
        help=(
            "Unsafe mode: prune recipes whose host is not in current sites, even without baseline diff. "
            "Not recommended."
        ),
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
        "--yes",
        action="store_true",
        help="Skip confirmation prompt when used with --apply.",
    )
    parser.add_argument(
        "--backup-before-apply",
        action="store_true",
        help="Create a Mealie backup via API before deleting recipes.",
    )
    parser.add_argument(
        "--preview-limit",
        type=int,
        default=50,
        help="How many candidate lines to print before summarizing.",
    )
    parser.add_argument(
        "--audit-file",
        default=os.getenv("ALIGN_SITES_AUDIT_FILE", ""),
        help="Optional JSON file path to write full candidate list before apply/dry-run.",
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
    unsafe_outside_current = bool(getattr(args, "prune_outside_current", False))
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
    elif not unsafe_outside_current:
        active_logger.error(
            "[align][error] Baseline sites file is required for diff mode. "
            "Provide --baseline-sites-file (recommended), or explicitly use --prune-outside-current (unsafe)."
        )
        return 1

    active_logger.info(f"[align][info] Current hosts from {sites_file}: {len(current_hosts)}")
    if baseline_hosts is not None and prune_hosts is not None:
        active_logger.info(f"[align][info] Baseline hosts from {args.baseline_sites_file}: {len(baseline_hosts)}")
        active_logger.info(f"[align][info] Removed hosts in scope: {len(prune_hosts)}")
    if unsafe_outside_current and baseline_hosts is None:
        active_logger.warning("[align][warn] Unsafe mode enabled: pruning hosts outside current sites list.")
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
            audit_file=Path(args.audit_file) if args.audit_file else None,
            backup_before_apply=args.apply and args.backup_before_apply,
            prompt_backup_before_apply=args.apply and not args.yes and not args.backup_before_apply,
            require_confirmation=args.apply and not args.yes,
            assume_yes=args.yes,
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
