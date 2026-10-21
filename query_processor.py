import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from document_catalog import aliases_for, display_name, iter_aliases


# Backward-compatible alias map used by older callers/tests.
DOCUMENT_ALIASES = {
    key: aliases_for(key) for _, key in iter_aliases()
}

TOKEN_TRANSLATIONS = {
    "पैन": "pan", "पैनकार्ड": "pan", "आधार": "aadhaar", "आधारकार्ड": "aadhaar",
    "मार्कशीट": "marksheet", "रिजल्ट": "marksheet", "लाइसेंस": "license",
    "ड्राइविंग": "driving", "रजिस्ट्रेशन": "registration", "वाहन": "vehicle",
    "बीमा": "insurance", "इंश्योरेंस": "insurance", "प्रदूषण": "pollution",
    "पासबुक": "passbook", "बैंक": "bank", "वोटर": "voter", "फीस": "fees",
    "शुल्क": "fee", "प्रमाण": "certificate",
}

HINGLISH_SYNONYMS = {
    "aadhar": "aadhaar", "adhhar": "aadhaar", "pann": "pan", "pancr": "pan",
    "marksheet": "marksheet", "markshit": "marksheet", "dricing": "driving",
    "licence": "license", "rcbook": "rc", "puc": "puc", "bima": "insurance",
    "passbook": "passbook", "dasvi": "10th", "10vi": "10th", "baarvi": "12th",
    "barahvi": "12th", "barvi": "12th", "मेरो": "my", "mala": "me",
}

QUERY_FILLER = {
    "show", "open", "find", "get", "give", "bring", "display", "fetch", "view", "see",
    "look", "locate", "retrieve", "access", "my", "me", "mine", "the", "a", "an",
    "please", "document", "documents", "file", "files", "paper", "papers", "of", "for",
    "to", "from", "is", "are", "where", "want", "need", "mera", "meri", "mere", "mujhe",
    "dikhao", "dikhado", "dikha", "kholo", "khol", "do", "karo", "koi", "hai", "mereko",
    "mujhko", "please", "can", "you", "could", "would", "kindly", "please",
}


@dataclass(frozen=True)
class QueryIntent:
    document_type: Optional[str] = None
    search_terms: Tuple[str, ...] = ()
    phrases: Tuple[str, ...] = ()
    constraints: Dict[str, str] = field(default_factory=dict)
    document_name: str = ""


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).lower().strip()
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[\u200b\ufeff]", "", text)
    text = "".join(
        char if (char.isalnum() or char.isspace() or char == "-" or unicodedata.category(char).startswith("M")) else " "
        for char in text
    )
    return re.sub(r"\s+", " ", text).strip()


def _canonical_aliases():
    aliases = []
    for alias, document_type in iter_aliases():
        normalized = normalize_text(alias)
        if normalized:
            aliases.append((normalized, document_type))
    return sorted(set(aliases), key=lambda pair: (len(pair[0]), len(pair[0].split())), reverse=True)


def _contains_phrase(text: str, phrase: str) -> bool:
    if not text or not phrase:
        return False
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.UNICODE) is not None


def detect_document_type(query: str) -> Optional[str]:
    normalized = normalize_text(query)
    if not normalized:
        return None
    for alias, document_type in _canonical_aliases():
        if _contains_phrase(normalized, alias):
            return document_type
    return None


def extract_constraints(query: str) -> Dict[str, str]:
    normalized = normalize_text(query)
    constraints: Dict[str, str] = {}
    if re.search(r"(?<!\w)(10th|10 th|class 10|10वीं|दसवीं|दहावी|दसमું)(?!\w)", normalized):
        constraints["grade"] = "10"
    elif re.search(r"(?<!\w)(12th|12 th|class 12|12वीं|बारहवीं|बारावी|બારમી)(?!\w)", normalized):
        constraints["grade"] = "12"

    semester = re.search(r"(?:semester|sem)\s*[-_]?\s*(\d{1,2})", normalized)
    if semester:
        constraints["semester"] = semester.group(1)

    year = re.search(r"(?<!\d)(20\d{2})(?!\d)", normalized)
    if year:
        constraints["year"] = year.group(1)
    return constraints


def tokenize_text(text: str):
    normalized = normalize_text(text)
    tokens = []
    current = []
    for char in normalized:
        category = unicodedata.category(char)
        if char.isalnum() or category.startswith("M") or char == "_":
            current.append(char)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def extract_search_terms(query: str):
    normalized = normalize_text(query)
    if not normalized:
        return []
    translated_tokens = []
    for raw_token in tokenize_text(normalized):
        token = TOKEN_TRANSLATIONS.get(raw_token, raw_token)
        token = HINGLISH_SYNONYMS.get(token, token)
        if token not in QUERY_FILLER and len(token) > 1:
            translated_tokens.append(token)
    return list(dict.fromkeys(translated_tokens))


def extract_query_phrases(query: str):
    normalized = normalize_text(query)
    return tuple(alias for alias, _ in _canonical_aliases() if _contains_phrase(normalized, alias))


def canonical_document_query(document_type: Optional[str], constraints: Optional[Dict[str, str]] = None) -> str:
    if not document_type:
        return ""
    constraints = constraints or {}
    name = display_name(document_type)
    if document_type == "marksheet" and constraints.get("grade") in {"10", "12"}:
        return f"{constraints['grade']}th marksheet"
    return name.lower()


def extract_document_name(query: str) -> str:
    """Return only the canonical English document name, with request filler removed."""
    intent = parse_query(query)
    return canonical_document_query(intent.document_type, intent.constraints)


def parse_query(query: str) -> QueryIntent:
    document_type = detect_document_type(query)
    constraints = extract_constraints(query)
    document_name = canonical_document_query(document_type, constraints)
    if document_name:
        terms = tuple(tokenize_text(document_name))
    else:
        terms = tuple(extract_search_terms(query))
    return QueryIntent(
        document_type=document_type,
        search_terms=terms,
        phrases=extract_query_phrases(query),
        constraints=constraints,
        document_name=document_name,
    )


def get_document_aliases(document_type: str):
    return aliases_for(document_type)


def normalize_filename(name: str) -> str:
    text = str(name)
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", text)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return normalize_text(text)


def infer_document_type(name: str, content: str = "") -> Optional[str]:
    name_type = detect_document_type(normalize_filename(name))
    if name_type:
        return name_type
    sample = normalize_text(content[:12000])
    return detect_document_type(sample)
