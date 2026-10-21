import pytest

from language.manager import LanguageManager
from query_processor import canonical_document_query, extract_document_name


class FakeSarvam:
    name = "sarvam"

    def __init__(self, detected="hi-IN", translated="show my PAN card", script="Deva"):
        self.detected = detected
        self.translated = translated
        self.script = script
        self.calls = []

    def detect_language(self, text):
        self.calls.append(("lid", text))
        return {"language_code": self.detected, "script_code": self.script, "confidence": 0.98}

    def translate(self, text, source_language_code, target_language_code):
        self.calls.append(("translate", text, source_language_code, target_language_code))
        return self.translated

    def translate_auto(self, text, target_language_code="en-IN"):
        self.calls.append(("translate_auto", text, target_language_code))
        return self.translated

    def transliterate(self, *args, **kwargs):
        raise AssertionError("transliteration must not be required for document fetching")

    def speech_to_text(self, *args, **kwargs):
        return {}

    def text_to_speech(self, *args, **kwargs):
        return ""


def test_document_name_only_for_supported_documents():
    assert extract_document_name("Please show my PAN card immediately") == "pan card"
    assert extract_document_name("मेरा पैन कार्ड दिखाओ") == "pan card"
    assert extract_document_name("show my 12th marksheet") == "12th marksheet"


def test_manager_translates_then_extracts_document_name():
    provider = FakeSarvam(translated="please show my permanent account number card")
    prepared = LanguageManager(provider).prepare_query("मेरा पैन कार्ड दिखाओ")
    assert prepared.provider_used == "sarvam"
    assert prepared.translation_ok is True
    assert prepared.document_type == "pan"
    assert prepared.document_name == "pan card"
    assert prepared.canonical_english == "pan card"
    assert [x[0] for x in provider.calls] == ["lid", "translate"]


def test_manager_keeps_local_document_fallback_when_provider_fails():
    class Broken(FakeSarvam):
        def translate(self, *args, **kwargs):
            raise RuntimeError("network down")

    prepared = LanguageManager(Broken()).prepare_query("मेरा पैन कार्ड दिखाओ")
    assert prepared.document_type == "pan"
    assert prepared.document_name == "pan card"
    assert prepared.canonical_english == "pan card"
    assert "Translation failed" in prepared.provider_error


@pytest.mark.parametrize(
    "query, language, translation, expected",
    [
        ("माझी पॅन कार्ड दाखवा", "mr-IN", "show my PAN card", "pan card"),
        ("મારું પાન કાર્ડ બતાવો", "gu-IN", "show my PAN card", "pan card"),
        ("என் பான் கார்டை காட்டு", "ta-IN", "show my PAN card", "pan card"),
        ("నా పాన్ కార్డు చూపించు", "te-IN", "show my PAN card", "pan card"),
        ("ನನ್ನ ಪ್ಯಾನ್ ಕಾರ್ಡ್ ತೋರಿಸು", "kn-IN", "show my PAN card", "pan card"),
        ("എന്റെ പാൻ കാർഡ് കാണിക്കൂ", "ml-IN", "show my PAN card", "pan card"),
        ("আমার প্যান কার্ড দেখাও", "bn-IN", "show my PAN card", "pan card"),
        ("ਮੇਰਾ ਪੈਨ ਕਾਰਡ ਦਿਖਾਓ", "pa-IN", "show my PAN card", "pan card"),
        ("मेरा पैन कार्ड दिखाओ", "hi-IN", "show my PAN card", "pan card"),
        ("میرا پین کارڈ دکھائیں", "ur-IN", "show my PAN card", "pan card"),
        ("माझी बारावीची मार्कशीट दाखवा", "mr-IN", "show my 12th marksheet", "12th marksheet"),
    ],
)
def test_major_indic_languages_follow_same_pipeline(query, language, translation, expected):
    prepared = LanguageManager(FakeSarvam(detected=language, translated=translation)).prepare_query(query)
    assert prepared.translation_ok
    assert prepared.document_name == expected
    assert prepared.canonical_english == expected


def test_english_input_does_not_require_translation():
    provider = FakeSarvam(detected="en-IN", translated="should not be used")
    prepared = LanguageManager(provider).prepare_query("show my PAN card")
    assert prepared.document_name == "pan card"
    assert prepared.translation_ok
    assert [x[0] for x in provider.calls] == ["lid"]


def test_romanized_indic_query_prefers_sarvam_auto_translation():
    provider = FakeSarvam(detected="en-IN", translated="show my PAN card", script="Latn")
    prepared = LanguageManager(provider).prepare_query("mujhe mera pan card dikhao")
    assert prepared.document_name == "pan card"
    assert prepared.translation_ok
    assert [call[0] for call in provider.calls] == ["lid", "translate_auto"]
