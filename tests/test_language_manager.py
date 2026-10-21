from language.manager import LanguageManager


class FakeProvider:
    name = "fake"

    def __init__(self, detected="hi-IN", translated="show my PAN card"):
        self.detected = detected
        self.translated = translated
        self.calls = []

    def detect_language(self, text):
        self.calls.append(("lid", text))
        return {"language_code": self.detected, "script_code": "Deva", "confidence": 0.98}

    def translate(self, text, source_language_code, target_language_code):
        self.calls.append(("translate", source_language_code, target_language_code))
        return self.translated

    def translate_auto(self, text, target_language_code="en-IN"):
        self.calls.append(("translate_auto", target_language_code))
        return self.translated


def test_prepare_query_uses_provider_for_indic_text():
    provider = FakeProvider()
    prepared = LanguageManager(provider).prepare_query("मेरा पैन कार्ड दिखाओ")
    assert prepared.document_type == "pan"
    assert prepared.canonical_english == "pan card"
    assert prepared.translation_ok
    assert provider.calls[0][0] == "lid"


def test_prepare_query_prefers_local_fallback_when_provider_translation_fails():
    class Broken(FakeProvider):
        def translate(self, *args, **kwargs):
            raise RuntimeError("network down")

    prepared = LanguageManager(Broken()).prepare_query("मेरा पैन कार्ड दिखाओ")
    assert prepared.document_type == "pan"
    assert prepared.canonical_english == "pan card"
    assert "Translation failed" in prepared.provider_error


def test_prepare_query_empty_text():
    prepared = LanguageManager(None).prepare_query("  ")
    assert prepared.original == ""
    assert prepared.canonical_english == ""
