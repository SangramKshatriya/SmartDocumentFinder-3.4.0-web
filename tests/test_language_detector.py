from language.detector import (
    detect_language_local,
    detect_script,
    guess_language_from_hints,
    normalize_bcp47,
)


def test_detect_script_and_local_language():
    assert detect_script("मेरा पैन कार्ड") == "Deva"
    code, script, confidence = detect_language_local("મારો પાન કાર્ડ")
    assert code == "gu-IN"
    assert script == "Gujr"
    assert confidence > 0


def test_language_hints_and_bcp47_normalization():
    code, confidence = guess_language_from_hints("mujhe mera pan card dikhao")
    assert code == "hi-IN"
    assert confidence > 0
    assert normalize_bcp47("HI") == "hi-IN"
    assert normalize_bcp47("en-IN") == "en-IN"
