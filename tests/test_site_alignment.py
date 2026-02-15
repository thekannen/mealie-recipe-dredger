from __future__ import annotations

from argparse import Namespace

import pytest

from mealie_recipe_dredger.site_alignment import (
    build_candidates,
    align_mealie_recipes,
    host_allowed,
    hosts_from_sites,
    removed_hosts_for_diff,
    run_from_args,
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


def test_apply_requires_interactive_without_yes(monkeypatch) -> None:
    monkeypatch.setattr("mealie_recipe_dredger.site_alignment.get_recipes", lambda **kwargs: [
        {"name": "Remove Me", "orgURL": "https://old.example.com/r1", "id": "1", "slug": "remove-me"}
    ])

    with pytest.raises(RuntimeError):
        align_mealie_recipes(
            mealie_url="http://mealie.local",
            token="token",
            timeout=10,
            allowed_hosts={"active.example.com"},
            prune_hosts={"old.example.com"},
            apply=True,
            require_confirmation=True,
            assume_yes=False,
        )


def test_run_from_args_requires_baseline_by_default(tmp_path) -> None:
    sites_file = tmp_path / "sites.json"
    sites_file.write_text('["https://example.com"]', encoding="utf-8")

    args = Namespace(
        sites_file=str(sites_file),
        baseline_sites_file="",
        prune_outside_current=False,
        mealie_url="http://mealie.local",
        token="token",
        timeout=10,
        include_missing_source=False,
        apply=False,
        yes=False,
        backup_before_apply=False,
        preview_limit=5,
        audit_file="",
    )

    assert run_from_args(args) == 1


def test_run_from_args_allows_unsafe_override(tmp_path, monkeypatch) -> None:
    sites_file = tmp_path / "sites.json"
    sites_file.write_text('["https://example.com"]', encoding="utf-8")
    called = {"value": False}

    def fake_align_mealie_recipes(**kwargs):
        called["value"] = True
        assert kwargs["prune_hosts"] is None
        return type(
            "Report",
            (),
            {"candidate_count": 0, "deleted_count": 0, "failed_count": 0},
        )()

    monkeypatch.setattr("mealie_recipe_dredger.site_alignment.align_mealie_recipes", fake_align_mealie_recipes)

    args = Namespace(
        sites_file=str(sites_file),
        baseline_sites_file="",
        prune_outside_current=True,
        mealie_url="http://mealie.local",
        token="token",
        timeout=10,
        include_missing_source=False,
        apply=False,
        yes=False,
        backup_before_apply=False,
        preview_limit=5,
        audit_file="",
    )

    assert run_from_args(args) == 0
    assert called["value"] is True


def test_backup_failure_aborts_apply(monkeypatch) -> None:
    monkeypatch.setattr("mealie_recipe_dredger.site_alignment.get_recipes", lambda **kwargs: [
        {"name": "Remove Me", "orgURL": "https://old.example.com/r1", "id": "1", "slug": "remove-me"}
    ])
    monkeypatch.setattr(
        "mealie_recipe_dredger.site_alignment.create_mealie_backup",
        lambda **kwargs: (False, "backup failed"),
    )

    def fail_delete(**kwargs):
        raise AssertionError("delete_recipe should not run when backup fails")

    monkeypatch.setattr("mealie_recipe_dredger.site_alignment.delete_recipe", fail_delete)

    report = align_mealie_recipes(
        mealie_url="http://mealie.local",
        token="token",
        timeout=10,
        allowed_hosts={"active.example.com"},
        prune_hosts={"old.example.com"},
        apply=True,
        backup_before_apply=True,
        prompt_backup_before_apply=False,
        require_confirmation=False,
        assume_yes=True,
    )

    assert report.candidate_count == 1
    assert report.deleted_count == 0
    assert report.failed_count == 0
