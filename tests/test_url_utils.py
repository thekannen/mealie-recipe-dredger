from mealie_recipe_dredger.url_utils import canonicalize_url, has_numeric_suffix, numeric_suffix_value, strip_numeric_suffix


def test_canonicalize_url_normalizes_tracking_and_slash():
    source = "https://www.Example.com/recipe/chili/?utm_source=newsletter&fbclid=abc&id=5"
    assert canonicalize_url(source) == "https://example.com/recipe/chili?id=5"


def test_canonicalize_url_sorts_query_params():
    source = "https://example.com/recipe?b=2&a=1"
    assert canonicalize_url(source) == "https://example.com/recipe?a=1&b=2"


def test_strip_numeric_suffix_helpers():
    name = "Zobo Drink (Hibiscus Drink) (12)"
    assert strip_numeric_suffix(name) == "Zobo Drink (Hibiscus Drink)"
    assert has_numeric_suffix(name)
    assert numeric_suffix_value(name) == 12
