import mealie_recipe_dredger.cleaner as cleaner_module
from mealie_recipe_dredger.cleaner import (
    _build_recipe_resource_urls,
    _is_no_result_error,
    _should_skip_verified,
    check_integrity,
    classify_recipe_action,
    dedupe_duplicate_source_recipes,
    is_junk_content,
    language_issue_for_payload,
    suggest_salvage_name,
    validate_instructions,
)


def test_is_junk_content_blocks_listicle_slug_without_source_url():
    assert is_junk_content(
        name="Keto Air Fryer",
        url=None,
        slug="28-best-keto-air-fryer-recipes",
    )


def test_is_junk_content_blocks_how_to_slug_without_source_url():
    assert not is_junk_content(
        name="Steak",
        url=None,
        slug="how-to-cook-t-bone-steak",
    )


def test_is_junk_content_allows_normal_recipe_slug_without_source_url():
    assert not is_junk_content(
        name="Garlic Lemon Chicken",
        url=None,
        slug="garlic-lemon-chicken",
    )


def test_is_junk_content_blocks_high_risk_keyword_in_name():
    assert is_junk_content(
        name="Holiday Gift Guide",
        url=None,
        slug="holiday-gift-guide",
    )


def test_classify_recipe_action_prefers_rename_for_how_to_slug():
    action, reason, new_name = classify_recipe_action(
        name="How to Cook T Bone Steak",
        url=None,
        slug="how-to-cook-t-bone-steak",
    )
    assert action == "rename"
    assert reason == "How-to naming cleanup"
    assert new_name == "T Bone Steak"


def test_classify_recipe_action_prefers_rename_for_how_to_make_slug():
    action, reason, new_name = classify_recipe_action(
        name="How to Make Almond Butter in a Blender",
        url=None,
        slug="how-to-make-almond-butter-in-a-blender",
    )
    assert action == "rename"
    assert reason == "How-to naming cleanup"
    assert new_name == "Almond Butter In A Blender"


def test_classify_recipe_action_keeps_clean_title_when_only_slug_has_how_to():
    action, reason, new_name = classify_recipe_action(
        name="A Double Rainbow Cake",
        url=None,
        slug="how-to-make-a-double-rainbow-cake",
    )
    assert action == "keep"
    assert reason == "How-to slug only with clean recipe title"
    assert new_name is None


def test_suggest_salvage_name_removes_how_to_prefix():
    assert suggest_salvage_name("How to Make Almond Butter in a Blender", "how-to-make-almond-butter-in-a-blender") == (
        "Almond Butter In A Blender"
    )


def test_classify_recipe_action_blocks_numbered_roundup():
    action, reason, _ = classify_recipe_action(
        name="20 Scrumptious Keto Holiday Desserts",
        url=None,
        slug="20-scrumptious-keto-holiday-desserts",
    )
    assert action == "delete"
    assert reason == "Listicle/roundup"


def test_classify_recipe_action_blocks_editorial_we_tried_title():
    action, reason, _ = classify_recipe_action(
        name="We Tried 15 Jars of Creamy Peanut Butter and There Was a Clear Winner",
        url="https://www.foodandwine.com/best-peanut-butters-8721900",
        slug="we-tried-15-jars-of-creamy-peanut-butter-and-there-was-a-clear-winner",
    )
    assert action == "delete"
    assert reason == "High-risk keyword: we tried"


def test_validate_instructions_rejects_placeholder_text_in_step_list():
    instructions = [{"text": "Could not detect instructions"}]
    assert not validate_instructions(instructions)


def test_validate_instructions_accepts_nested_step_list_with_real_text():
    instructions = [{"itemListElement": [{"text": "Whisk eggs with salt."}]}]
    assert validate_instructions(instructions)


def test_language_issue_for_payload_flags_spanish(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "LANGUAGE_DETECTION_STRICT", False)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")

    payload = {
        "name": "Receta de pollo guisado",
        "description": "Esta receta es facil y deliciosa para toda la familia.",
        "recipeIngredient": [
            "1 pollo",
            "2 cucharadas de aceite",
            "sal y pimienta",
        ],
        "recipeInstructions": [
            "Calienta el aceite y cocina el pollo por 20 minutos.",
            "Agrega sal y sirve caliente.",
        ],
    }

    assert language_issue_for_payload(payload) == "Language mismatch: es"


def test_language_issue_for_payload_allows_english(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "LANGUAGE_DETECTION_STRICT", False)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")

    payload = {
        "name": "Lemon Chicken",
        "description": "This recipe is easy and perfect for weeknight dinner.",
        "recipeIngredient": [
            "2 chicken breasts",
            "1 lemon",
            "salt and pepper",
        ],
        "recipeInstructions": [
            "Season chicken with salt and pepper.",
            "Cook for 20 minutes and serve.",
        ],
    }

    assert language_issue_for_payload(payload) is None


def test_language_issue_for_payload_strict_unknown(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "LANGUAGE_DETECTION_STRICT", True)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")
    monkeypatch.setattr(
        cleaner_module,
        "detect_language_from_recipe_payload",
        lambda payload, min_confidence=0.70: (None, "unknown", 0.0),
    )

    payload = {
        "name": "Qwrt Lkpm",
        "description": "Zxvc qwer asdf zxcv.",
        "recipeIngredient": ["qwer", "asdf"],
        "recipeInstructions": ["qwer asdf zxcv"],
    }

    assert language_issue_for_payload(payload) == "Language unknown"


def test_build_recipe_resource_urls_prefers_id_before_slug():
    urls = _build_recipe_resource_urls("my-slug", "recipe-uuid-123")
    assert urls[0].endswith("/api/recipes/recipe-uuid-123")
    assert urls[1].endswith("/api/recipes/my-slug")


def test_is_no_result_error_detects_mealie_noresultfound_payload():
    body = '{"detail":{"message":"Unknown Error","error":true,"exception":"NoResultFound"}}'
    assert _is_no_result_error(500, body)


def test_language_issue_for_payload_flags_hindi_script(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "LANGUAGE_DETECTION_STRICT", False)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")

    payload = {
        "name": "हिंदी चिकन करी",
        "description": "यह एक स्वादिष्ट और आसान रेसिपी है।",
        "recipeInstructions": ["कड़ाही गरम करें और मसाले डालें।"],
    }
    assert language_issue_for_payload(payload) == "Language mismatch: hi"


def test_should_skip_verified_when_language_cleanup_disabled(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", False)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")
    assert _should_skip_verified("slug-a", {"slug-a"})


def test_should_not_skip_verified_when_language_cleanup_enabled(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")
    assert not _should_skip_verified("slug-a", {"slug-a"})


def test_check_integrity_rechecks_verified_when_language_cleanup_enabled(monkeypatch):
    monkeypatch.setattr(cleaner_module, "LANGUAGE_FILTER_ENABLED", True)
    monkeypatch.setattr(cleaner_module, "CLEANER_REMOVE_NON_TARGET_LANGUAGE", True)
    monkeypatch.setattr(cleaner_module, "LANGUAGE_DETECTION_STRICT", False)
    monkeypatch.setattr(cleaner_module, "TARGET_LANGUAGE", "en")

    class DummyResponse:
        status_code = 200
        text = "{}"

        @staticmethod
        def json():
            return {"recipeInstructions": ["Step 1"], "name": "Lemon Chicken"}

    def fake_get(_url, headers=None, timeout=10):
        return DummyResponse()

    monkeypatch.setattr(cleaner_module.requests, "get", fake_get)

    result = check_integrity({"slug": "slug-a", "id": "id-a", "name": "Lemon Chicken"}, {"slug-a"})
    assert result is not None
    assert result[1] == "VERIFIED"


def test_dedupe_duplicate_source_recipes_deletes_same_source_duplicates(monkeypatch):
    deleted_slugs = []

    def fake_delete(slug, name, reason, rejects, verified, url=None, recipe_id=None):
        deleted_slugs.append(slug)

    monkeypatch.setattr(cleaner_module, "delete_mealie_recipe", fake_delete)

    recipes = [
        {
            "id": "id-1",
            "slug": "zobo-drink-hibiscus-drink",
            "name": "Zobo Drink (Hibiscus Drink)",
            "orgURL": "https://www.myactivekitchen.com/refreshing-zobo-drink-zobo-tutu/",
        },
        {
            "id": "id-2",
            "slug": "zobo-drink-hibiscus-drink-1",
            "name": "Zobo Drink (Hibiscus Drink) (1)",
            "orgURL": "https://myactivekitchen.com/refreshing-zobo-drink-zobo-tutu/?utm_source=site",
        },
        {
            "id": "id-3",
            "slug": "another-zobo-recipe",
            "name": "Zobo Drink",
            "orgURL": "https://example.com/another-recipe",
        },
    ]

    filtered, groups, deleted = dedupe_duplicate_source_recipes(recipes, set(), set())
    assert groups == 1
    assert deleted == 1
    assert deleted_slugs == ["zobo-drink-hibiscus-drink-1"]
    assert len(filtered) == 2
