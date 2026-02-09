from bs4 import BeautifulSoup

from mealie_recipe_dredger.verifier import RecipeVerifier


class DummySession:
    def get(self, url, timeout=10):  # pragma: no cover - should not be called in this test
        raise AssertionError("Network should not be called for media prefilter")


def test_prefilter_blocks_media_url_without_network_call():
    verifier = RecipeVerifier(DummySession())
    is_recipe, _soup, reason, transient = verifier.verify_recipe(
        "https://example.com/wp-content/uploads/image.jpg"
    )

    assert is_recipe is False
    assert reason == "Non-HTML media URL"
    assert transient is False


def test_paranoid_skip_blocks_listicle_slug():
    verifier = RecipeVerifier(DummySession())
    reason = verifier.is_paranoid_skip("https://example.com/28-best-keto-air-fryer-recipes/")
    assert reason is not None
    assert reason.startswith("Listicle detected:")


def test_paranoid_skip_blocks_how_to_cook_slug():
    verifier = RecipeVerifier(DummySession())
    reason = verifier.is_paranoid_skip("https://example.com/how-to-cook-rice/")
    assert reason == "How-to article"


def test_paranoid_skip_blocks_listicle_title():
    verifier = RecipeVerifier(DummySession())
    soup = BeautifulSoup("<html><head><title>28 Best Keto Air Fryer Recipes</title></head></html>", "lxml")
    reason = verifier.is_paranoid_skip("https://example.com/keto-air-fryer/", soup=soup)
    assert reason == "Listicle title"


def test_paranoid_skip_allows_single_recipe_slug():
    verifier = RecipeVerifier(DummySession())
    reason = verifier.is_paranoid_skip("https://example.com/best-ever-banana-bread-recipe/")
    assert reason is None
