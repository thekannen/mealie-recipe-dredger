import json

from mealie_recipe_dredger.app import load_sites_from_source


def test_sites_env_path_overrides_local_sites_file(tmp_path, monkeypatch):
    custom_sites_file = tmp_path / "custom_sites.json"
    custom_sites_file.write_text(
        json.dumps({"sites": ["https://example.com", "https://example.org"]}),
        encoding="utf-8",
    )

    monkeypatch.setenv("SITES", str(custom_sites_file))

    sites = load_sites_from_source(None)
    assert sites == ["https://example.com", "https://example.org"]
