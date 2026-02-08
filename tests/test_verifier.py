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
