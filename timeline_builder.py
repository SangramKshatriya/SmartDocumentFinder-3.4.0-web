"""Conservative timeline extraction from indexed document text.

Events always retain an evidence snippet and source document; inferred labels
are descriptive only and never treated as verified facts without source context.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Iterable

from content_extractor import extract_text
from portal_store import add_timeline_event

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7,
    "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(?P<d>0?[1-9]|[12]\d|3[01])[-/.](?P<m>0?[1-9]|1[0-2])[-/.](?P<y>19\d{2}|20\d{2})(?!\d)"),
    re.compile(r"(?<!\d)(?P<y>19\d{2}|20\d{2})[-/.](?P<m>0?[1-9]|1[0-2])[-/.](?P<d>0?[1-9]|[12]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\w)(?P<d>0?[1-9]|[12]\d|3[01])\s+(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s*,?\s*(?P<y>19\d{2}|20\d{2})(?!\d)", re.I),
    re.compile(r"(?<!\w)(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(?P<d>0?[1-9]|[12]\d|3[01]),?\s+(?P<y>19\d{2}|20\d{2})(?!\d)", re.I),
]


def _parsed_date(match: re.Match) -> date | None:
    group = match.groupdict()
    try:
        if group.get("month"):
            month_key = group["month"].lower().rstrip(".")
            month = _MONTHS.get(month_key)
            if month is None:
                month = _MONTHS.get(month_key[:3])
        else:
            month = int(group["m"])
        return date(int(group["y"]), int(month), int(group["d"]))
    except (ValueError, TypeError):
        return None


def _describe_context(text: str, start: int, end: int) -> tuple[str, str, str]:
    low = max(0, start - 100)
    high = min(len(text), end + 100)
    context = re.sub(r"\s+", " ", text[low:high]).strip()
    before = text[max(0, start - 80):start].lower()
    if re.search(r"date of birth|\bdob\b|born on", before):
        return "personal_date", "Date of birth mentioned", context
    if re.search(r"date of issue|issued on|issue date|date issued", before):
        return "document_issued", "Document issue date", context
    if re.search(r"admission|enrolled|enrolment", before):
        return "education", "Education admission/enrolment date", context
    if re.search(r"result|examined on|examination date", before):
        return "education", "Examination/result date", context
    if re.search(r"graduat|degree awarded|course completed|passed in", before):
        return "education", "Education milestone date", context
    if re.search(r"appointment|joining date|joined on|employment commenced", before):
        return "employment", "Employment milestone date", context
    if re.search(r"valid until|valid till|expiry|expires on", before):
        return "validity", "Validity/expiry date", context
    return "document_date", "Date mentioned in document", context


def build_timeline_for_document(user_id: int, document_id: int, path: str) -> int:
    """Index dated statements with evidence; return count of candidate events."""
    try:
        text = extract_text(path)
    except Exception:
        return 0
    if not text:
        return 0
    matches: list[tuple[int, int, re.Match]] = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text[:1_000_000]):
            matches.append((match.start(), match.end(), match))
    matches.sort(key=lambda part: part[0])
    seen: set[tuple[str, str]] = set()
    count = 0
    # A per-document cap avoids turning a long statement into hundreds of events.
    for start, end, match in matches:
        parsed = _parsed_date(match)
        if not parsed:
            continue
        event_type, title, evidence = _describe_context(text, start, end)
        key = (parsed.isoformat(), title)
        if key in seen:
            continue
        seen.add(key)
        add_timeline_event(user_id, document_id, parsed.isoformat(), event_type, title, evidence)
        count += 1
        if count >= 20:
            break
    return count
