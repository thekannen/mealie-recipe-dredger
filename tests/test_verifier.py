from bs4 import BeautifulSoup

from mealie_recipe_dredger.verifier import RecipeVerifier


class DummySession:
    def get(self, url, timeout=10):  # pragma: no cover - should not be called in this test
        raise AssertionError("Network should not be called for media prefilter")


class DummyHttpResponse:
    def __init__(self, html: str, status_code: int = 200):
        self.status_code = status_code
        self.text = html
        self.content = html.encode("utf-8")


class DummyHttpSession:
    def __init__(self, html: str, status_code: int = 200):
        self.response = DummyHttpResponse(html=html, status_code=status_code)

    def get(self, url, timeout=10):
        return self.response


def test_prefilter_blocks_media_url_without_network_call():
    verifier = RecipeVerifier(DummySession())
    is_recipe, _soup, reason, transient = verifier.verify_recipe(
        "https://example.com/wp-content/uploads/image.jpg"
    )

    assert is_recipe is False
    assert reason == "Non-HTML media URL"
    assert transient is False


def test_prefilter_blocks_known_non_recipe_route_family():
    verifier = RecipeVerifier(DummySession())
    is_recipe, _soup, reason, transient = verifier.verify_recipe(
        "https://example.com/g/home/r/we-tried-15-jars-of-creamy-peanut-butter-and-there-was-a-clear-winner"
    )

    assert is_recipe is False
    assert reason == "Non-recipe path"
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


def test_paranoid_skip_blocks_digest_slug():
    verifier = RecipeVerifier(DummySession())
    reason = verifier.is_paranoid_skip("https://example.com/friday-finds-4-10-15/")
    assert reason == "Digest/non-recipe post"


def test_paranoid_skip_blocks_we_tried_roundup_slug():
    verifier = RecipeVerifier(DummySession())
    reason = verifier.is_paranoid_skip(
        "https://example.com/we-tried-15-jars-of-creamy-peanut-butter-and-there-was-a-clear-winner/"
    )
    assert reason == "Bad keyword: we tried"


def test_verify_recipe_rejects_weak_recipe_schema():
    html = """
    <html lang="en">
      <head>
        <title>Not really a recipe post</title>
        <script type="application/ld+json">{"@type":"Recipe","name":"Post Teaser"}</script>
      </head>
      <body><p>This is a roundup post.</p></body>
    </html>
    """
    verifier = RecipeVerifier(DummyHttpSession(html))
    is_recipe, _soup, reason, transient = verifier.verify_recipe("https://example.com/not-recipe")

    assert is_recipe is False
    assert reason == "Weak recipe schema"
    assert transient is False


def test_verify_recipe_rejects_spanish_page():
    html = """
    <html lang="es">
      <head>
        <title>Tortilla Espanola</title>
        <script type="application/ld+json">{"@type":"Recipe","recipeIngredient":["egg"],"recipeInstructions":"Mix and cook."}</script>
      </head>
      <body></body>
    </html>
    """
    verifier = RecipeVerifier(DummyHttpSession(html))
    is_recipe, _soup, reason, transient = verifier.verify_recipe("https://example.com/tortilla")

    assert is_recipe is False
    assert reason == "Language mismatch: es"
    assert transient is False


def test_verify_recipe_allows_english_page():
    html = """
    <html lang="en">
      <head>
        <title>Lemon Chicken Recipe</title>
        <script type="application/ld+json">{"@type":"Recipe","recipeIngredient":["chicken"],"recipeInstructions":"Bake."}</script>
      </head>
      <body></body>
    </html>
    """
    verifier = RecipeVerifier(DummyHttpSession(html))
    is_recipe, _soup, reason, transient = verifier.verify_recipe("https://example.com/lemon-chicken")

    assert is_recipe is True
    assert reason is None
    assert transient is False


def test_verify_recipe_rejects_spanish_text_without_lang_attribute():
    html = """
    <html>
      <head>
        <title>Receta de pollo al horno</title>
        <script type="application/ld+json">{"@type":"Recipe","recipeIngredient":["pollo"],"recipeInstructions":"Hornear."}</script>
      </head>
      <body>
        <p>Esta receta es facil y deliciosa para toda la familia.</p>
        <p>Cocinar por 20 minutos y servir con arroz.</p>
      </body>
    </html>
    """
    verifier = RecipeVerifier(DummyHttpSession(html))
    is_recipe, _soup, reason, transient = verifier.verify_recipe("https://example.com/pollo")

    assert is_recipe is False
    assert reason == "Language mismatch: es"
    assert transient is False
