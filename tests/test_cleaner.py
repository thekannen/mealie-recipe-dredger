from mealie_recipe_dredger.cleaner import classify_recipe_action, is_junk_content, suggest_salvage_name


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
