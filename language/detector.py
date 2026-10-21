import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

from language.languages import SCRIPT_TO_LANGUAGE

# Distinctive words used only as a fallback to distinguish languages that share
# a script. Sarvam LID is still preferred when it can identify the language.
LANGUAGE_HINTS: Dict[str, Tuple[str, ...]] = {
    "hi-IN": ("मेरा", "मेरी", "मेरे", "मुझे", "दिखाओ", "दिखा", "खोलो", "मेरा", "mujhe", "mera", "meri", "mere", "dikhao", "dikhana"),
    "mr-IN": ("माझा", "माझी", "माझे", "मला", "दाखवा", "दाखव", "माझं", "majha", "majhi", "majhe", "mala", "dakhva"),
    "gu-IN": ("મારો", "મારી", "મારું", "મને", "બતાવો", "બતાવ", "mari", "maru", "mane", "batavo"),
    "bn-IN": ("আমার", "আমাকে", "দেখাও", "দেখান", "আমারটা", "amar", "amake", "dekhao"),
    "as-IN": ("মোৰ", "মোক", "দেখুৱাওক", "mor", "mok", "dekhuaok"),
    "ta-IN": ("என்", "எனது", "எனக்கு", "காட்டு", "காட்டுங்கள்", "en", "enathu", "enakku", "kaatu"),
    "te-IN": ("నా", "నాకు", "చూపించు", "చూపించండి", "naa", "naaku", "choopinchu"),
    "kn-IN": ("ನನ್ನ", "ನನಗೆ", "ತೋರಿಸು", "ತೋರಿಸಿ", "nanna", "nanage", "torisu"),
    "ml-IN": ("എന്റെ", "എനിക്ക്", "കാണിക്കൂ", "കാണിക്കുക", "ente", "enikku", "kanikku"),
    "pa-IN": ("ਮੇਰਾ", "ਮੇਰੀ", "ਮੇਰੇ", "ਮੈਨੂੰ", "ਦਿਖਾਓ", "mera", "meri", "mainu", "dikhao"),
    "od-IN": ("ମୋର", "ମୋତେ", "ଦେଖାଅ", "ଦେଖାନ୍ତୁ", "mora", "mote", "dekhaa"),
    "ur-IN": ("میرا", "میری", "میرے", "مجھے", "دکھائیں", "میرا", "mera", "meri", "mujhe", "dikhaen"),
    "ne-IN": ("मेरो", "मेरी", "मलाई", "देखाउनुहोस्", "मेरो", "mero", "malai", "dekhai"),
    "kok-IN": ("म्हजो", "म्हाजी", "माका", "दाखोव", "mhajo", "maka", "dakhov"),
    "ks-IN": ("میون", "مے", "مژ", "دکھاو", "myon", "me", "maz", "dakh"),
    "sd-IN": ("منهنجو", "مون کي", "ڏيکاريو", "munhinjo", "mon khe", "dekhario"),
    "sa-IN": ("मम", "माम", "दर्शय", "मम", "darshaya"),
    "mai-IN": ("हमर", "हमरा", "हमरा के", "देखाउ", "hamar", "hamra", "dekhau"),
    "doi-IN": ("मेरा", "मेरी", "मैनू", "दिखाओ", "mainu", "dikhao"),
    "brx-IN": ("आंथि", "आं", "नां", "दिखा", "angthi", "dikh"),
}


def _script_bucket(ch: str) -> Optional[str]:
    cp = ord(ch)
    if 0x0900 <= cp <= 0x097F:
        return "Deva"
    if 0x0980 <= cp <= 0x09FF:
        return "Beng"
    if 0x0A80 <= cp <= 0x0AFF:
        return "Gujr"
    if 0x0B00 <= cp <= 0x0B7F:
        return "Orya"
    if 0x0B80 <= cp <= 0x0BFF:
        return "Taml"
    if 0x0C00 <= cp <= 0x0C7F:
        return "Telu"
    if 0x0C80 <= cp <= 0x0CFF:
        return "Knda"
    if 0x0D00 <= cp <= 0x0D7F:
        return "Mlym"
    if 0x0A00 <= cp <= 0x0A7F:
        return "Guru"
    if 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
        return "Arab"
    # Meitei Mayek
    if 0xABC0 <= cp <= 0xABFF:
        return "Mtei"
    # Ol Chiki / Santali
    if 0x1C50 <= cp <= 0x1C7F:
        return "Olck"
    if ch.isascii() and ch.isalpha():
        return "Latn"
    return None


def detect_script(text: str) -> Optional[str]:
    counts = Counter()
    for ch in str(text or ""):
        script = _script_bucket(ch)
        if script:
            counts[script] += 1
    return counts.most_common(1)[0][0] if counts else None


def _word_matches(text: str, phrase: str) -> bool:
    lowered = text.lower()
    phrase = phrase.lower()
    if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", lowered, re.UNICODE):
        return True
    return False


def guess_language_from_hints(text: str) -> Tuple[Optional[str], float]:
    score: Dict[str, int] = Counter()
    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    for code, hints in LANGUAGE_HINTS.items():
        for hint in hints:
            if _word_matches(normalized, hint):
                score[code] += 2 if len(hint) > 3 else 1
    if not score:
        return None, 0.0
    best = max(score, key=score.get)
    total = sum(score.values())
    confidence = min(0.92, 0.55 + (score[best] / max(total, 1)) * 0.35)
    return best, confidence


def language_candidates(text: str) -> List[str]:
    candidates: List[str] = []
    hint, _ = guess_language_from_hints(text)
    if hint:
        candidates.append(hint)
    script = detect_script(text)
    script_map = {
        "Mtei": "mni-IN", "Olck": "sat-IN",
    }
    if script in script_map and script_map[script] not in candidates:
        candidates.append(script_map[script])
    script_language = SCRIPT_TO_LANGUAGE.get(script)
    if script_language and script_language not in candidates:
        candidates.append(script_language)
    if "en-IN" not in candidates and script == "Latn":
        candidates.append("en-IN")
    return candidates


def detect_language_local(text: str) -> Tuple[Optional[str], Optional[str], float]:
    if not text or not str(text).strip():
        return None, None, 0.0
    script = detect_script(text)
    hint_language, hint_confidence = guess_language_from_hints(text)
    if hint_language:
        return hint_language, script, hint_confidence
    if script in {"Mtei", "Olck"}:
        return {"Mtei": "mni-IN", "Olck": "sat-IN"}[script], script, 0.90
    language = SCRIPT_TO_LANGUAGE.get(script)
    confidence = 0.85 if script and script != "Deva" else 0.60
    if script == "Latn":
        confidence = 0.55
    return language, script, confidence


def normalize_bcp47(code: Optional[str]) -> Optional[str]:
    if not code:
        return None
    code = code.strip()
    aliases = {
        "en": "en-IN", "hi": "hi-IN", "mr": "mr-IN", "gu": "gu-IN", "ta": "ta-IN",
        "te": "te-IN", "bn": "bn-IN", "kn": "kn-IN", "ml": "ml-IN", "pa": "pa-IN",
        "or": "od-IN", "od": "od-IN", "as": "as-IN", "ur": "ur-IN", "ne": "ne-IN",
        "kok": "kok-IN", "ks": "ks-IN", "sd": "sd-IN", "sa": "sa-IN", "sat": "sat-IN",
        "mni": "mni-IN", "brx": "brx-IN", "mai": "mai-IN", "doi": "doi-IN",
    }
    return aliases.get(code.lower(), code)
