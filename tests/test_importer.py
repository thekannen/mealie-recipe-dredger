import requests

import mealie_recipe_dredger.importer as importer_module
from mealie_recipe_dredger.importer import ImportManager
from mealie_recipe_dredger.url_utils import canonicalize_url


class DummyStorage:
    pass


class DummyRateLimiter:
    def wait_if_needed(self, _url):
        return None


def test_import_to_mealie_skips_when_source_precheck_hits_duplicate(monkeypatch):
    monkeypatch.setattr(importer_module, "IMPORT_PRECHECK_DUPLICATES", True)

    session = requests.Session()
    manager = ImportManager(session, DummyStorage(), DummyRateLimiter(), dry_run=False)

    target_url = "https://www.myactivekitchen.com/refreshing-zobo-drink-zobo-tutu/?utm_source=abc"
    manager._known_source_urls = {canonicalize_url(target_url)}
    manager._source_index_loaded = True

    def fail_post(*args, **kwargs):
        raise AssertionError("POST should not be called when duplicate precheck matches")

    monkeypatch.setattr(manager.import_session, "post", fail_post)

    imported, error, transient = manager.import_to_mealie(target_url)
    assert imported is True
    assert error is None
    assert transient is False
