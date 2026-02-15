from __future__ import annotations

from mealie_recipe_dredger.site_alignment import (
    build_candidates,
    host_allowed,
    hosts_from_sites,
    removed_hosts_for_diff,
    save_host_snapshot,
    load_host_snapshot,
)


def test_hosts_from_sites_normalizes_domains() -> None:
    hosts = hosts_from_sites(
        [
            "https://www.example.com",
            "https://blog.example.com/path",
            "https://EXAMPLE.org",
            "not-a-url",
        ]
    )

    assert hosts == {"example.com", "blog.example.com", "example.org"}


def test_removed_hosts_for_diff_ignores_subdomains_still_covered() -> None:
    baseline_hosts = {"recipes.example.com", "legacy.test.com"}
    current_hosts = {"example.com"}

    removed_hosts = removed_hosts_for_diff(baseline_hosts, current_hosts)
    assert removed_hosts == {"legacy.test.com"}


def test_build_candidates_prunes_only_removed_hosts_in_diff_mode() -> None:
    recipes = [
        {"name": "Remove Me", "orgURL": "https://old.example.com/r1", "id": "1", "slug": "remove-me"},
        {"name": "Keep Current", "orgURL": "https://active.example.com/r2", "id": "2", "slug": "keep-current"},
        {"name": "Keep Manual", "orgURL": "https://manual-user-site.com/r3", "id": "3", "slug": "keep-manual"},
    ]
    removed_hosts = {"old.example.com"}

    candidates, missing_source = build_candidates(
        recipes=recipes,
        should_prune_host=lambda host: host_allowed(host, removed_hosts),
        keep_missing_source=True,
    )

    assert missing_source == 0
    assert [candidate.name for candidate in candidates] == ["Remove Me"]


def test_host_snapshot_round_trip(tmp_path) -> None:
    snapshot_file = tmp_path / "site_alignment_hosts.json"
    save_host_snapshot(snapshot_file, {"example.com", "legacy.test.com"})

    loaded = load_host_snapshot(snapshot_file)
    assert loaded == {"example.com", "legacy.test.com"}
