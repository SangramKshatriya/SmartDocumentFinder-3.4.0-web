from language.intent import DOCUMENT_TERMS


def test_language_intent_dictionary_has_core_document_terms():
    assert "pan" in DOCUMENT_TERMS
    assert "पैन" in DOCUMENT_TERMS["pan"]["hi"]
    assert "marksheet" in DOCUMENT_TERMS
    assert "१२वीं" not in DOCUMENT_TERMS["marksheet"].get("hi", ())
