from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native_name: str


# 22 Scheduled Indian languages + English, using BCP-47 style codes.
# Provider/model support can differ by capability, so the UI exposes all
# supported application languages while the provider layer validates the
# capability being requested.
LANGUAGES = [
    Language("en-IN", "English", "English"),
    Language("hi-IN", "Hindi", "हिन्दी"),
    Language("bn-IN", "Bengali", "বাংলা"),
    Language("gu-IN", "Gujarati", "ગુજરાતી"),
    Language("kn-IN", "Kannada", "ಕನ್ನಡ"),
    Language("ml-IN", "Malayalam", "മലയാളം"),
    Language("mr-IN", "Marathi", "मराठी"),
    Language("od-IN", "Odia", "ଓଡ଼ିଆ"),
    Language("pa-IN", "Punjabi", "ਪੰਜਾਬੀ"),
    Language("ta-IN", "Tamil", "தமிழ்"),
    Language("te-IN", "Telugu", "తెలుగు"),
    Language("as-IN", "Assamese", "অসমীয়া"),
    Language("ur-IN", "Urdu", "اردو"),
    Language("ne-IN", "Nepali", "नेपाली"),
    Language("kok-IN", "Konkani", "कोंकणी"),
    Language("ks-IN", "Kashmiri", "کٲشُر"),
    Language("sd-IN", "Sindhi", "सिन्धी"),
    Language("sa-IN", "Sanskrit", "संस्कृतम्"),
    Language("sat-IN", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ"),
    Language("mni-IN", "Manipuri", "মৈতৈলোন্"),
    Language("brx-IN", "Bodo", "बड़ो"),
    Language("mai-IN", "Maithili", "मैथिली"),
    Language("doi-IN", "Dogri", "डोगरी"),
]

LANGUAGE_BY_CODE: Dict[str, Language] = {lang.code: lang for lang in LANGUAGES}

SCRIPT_TO_LANGUAGE = {
    "Deva": "hi-IN",
    "Beng": "bn-IN",
    "Gujr": "gu-IN",
    "Knda": "kn-IN",
    "Mlym": "ml-IN",
    "Orya": "od-IN",
    "Guru": "pa-IN",
    "Taml": "ta-IN",
    "Telu": "te-IN",
    "Arab": "ur-IN",
    "Latn": "en-IN",
    "Mtei": "mni-IN",
    "Olck": "sat-IN",
}


def language_name(code: Optional[str]) -> str:
    if not code:
        return "Auto Detect"
    if code in LANGUAGE_BY_CODE:
        return f"{LANGUAGE_BY_CODE[code].name} ({LANGUAGE_BY_CODE[code].native_name})"
    return code
