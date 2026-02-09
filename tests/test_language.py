from mealie_recipe_dredger.language import detect_language_from_text


def test_detect_language_from_text_identifies_hindi_script():
    text = "यह एक स्वादिष्ट रेसिपी है जो बहुत आसान है और 20 मिनट में बनती है।"
    language, confidence = detect_language_from_text(text)
    assert language == "hi"
    assert confidence > 0


def test_detect_language_from_text_identifies_english():
    text = "This recipe is easy to make and includes ingredients with clear instructions."
    language, confidence = detect_language_from_text(text)
    assert language == "en"
    assert confidence > 0


def test_detect_language_from_text_identifies_french():
    text = "Cette recette est simple et delicieuse. Melangez les ingredients et faites cuire pendant vingt minutes."
    language, confidence = detect_language_from_text(text)
    assert language == "fr"
    assert confidence > 0
