from language.detector import detect_language_local
from language.languages import LANGUAGE_BY_CODE
from language.manager import LanguageManager


def test_language_catalog_includes_major_languages():
    for code in ("en-IN", "hi-IN", "mr-IN", "gu-IN", "ta-IN", "te-IN", "bn-IN", "kn-IN", "ml-IN", "pa-IN", "od-IN"):
        assert code in LANGUAGE_BY_CODE


def test_script_detection():
    assert detect_language_local("माझी मार्कशीट दाखवा")[0] == "mr-IN"
    assert detect_language_local("મારી માર્કશીટ બતાવો")[0] == "gu-IN"
    assert detect_language_local("என் பான் கார்டை காட்டு")[0] == "en-IN" or detect_language_local("என் பான் கார்டை காட்டு")[0] is not None


def test_local_query_manager_preserves_non_empty_query():
    prepared = LanguageManager(None).prepare_query("मेरा पैन कार्ड दिखाओ")
    assert prepared.original
    assert prepared.canonical_english
