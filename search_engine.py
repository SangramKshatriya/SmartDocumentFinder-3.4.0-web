from pathlib import Path
import re
from typing import Dict, List, Optional

from database import get_connection, initialize_database, mark_opened
from query_processor import (
    QueryIntent,
    detect_document_type,
    get_document_aliases,
    infer_document_type,
    normalize_text,
    parse_query,
    tokenize_text,
)


def _contains_phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.UNICODE) is not None


def _searchable_name(text: str) -> str:
    text = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", str(text))
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    return normalize_text(text)


def _token_set(text: str):
    return set(tokenize_text(text))


def _specificity_multiplier(constraints: Dict[str, str], name: str, content: str) -> int:
    name_text = _searchable_name(name)
    content_text = normalize_text(content)
    score = 0

    grade = constraints.get("grade")
    if grade:
        positive = {
            "10": ("10th", "10 th", "class 10", "10th class", "xth", "class x"),
            "12": ("12th", "12 th", "class 12", "12th class", "xiith", "xii"),
        }[grade]
        negative = {
            "10": ("12th", "12 th", "class 12", "xii"),
            "12": ("10th", "10 th", "class 10", "xth", "class x"),
        }[grade]
        if any(_contains_phrase(name_text, term) for term in positive):
            score += 100
        elif any(_contains_phrase(content_text, term) for term in positive):
            score += 45
        if any(_contains_phrase(name_text, term) for term in negative):
            score -= 150

    semester = constraints.get("semester")
    if semester:
        if _contains_phrase(name_text, f"sem {semester}") or _contains_phrase(name_text, f"semester {semester}"):
            score += 90
        elif re.search(rf"\bsem(?:ester)?\s*[-_]?\s*{re.escape(semester)}\b", content_text):
            score += 30

    year = constraints.get("year")
    if year:
        if _contains_phrase(name_text, year):
            score += 60
        elif _contains_phrase(content_text, year):
            score += 20
    return score


def calculate_document_type_score(name: str, content: str, document_type: str, intent: QueryIntent) -> int:
    name_text = _searchable_name(name)
    content_text = normalize_text(content)
    name_tokens = _token_set(name_text)
    content_tokens = _token_set(content_text)
    score = 0

    aliases = sorted({normalize_text(alias) for alias in get_document_aliases(document_type) if normalize_text(alias)}, key=len, reverse=True)
    for alias in aliases:
        if _contains_phrase(name_text, alias):
            score += 140 if " " in alias else 100
            break
    else:
        for alias in aliases:
            if _contains_phrase(content_text, alias):
                score += 35
                break

    canonical_terms = _token_set(intent.document_name or "")
    for term in canonical_terms:
        if term in name_tokens:
            score += 30
        if term in content_tokens:
            score += 5

    score += _specificity_multiplier(intent.constraints, name, content)
    return score


def calculate_generic_score(name: str, content: str, intent: QueryIntent) -> int:
    name_text = normalize_text(name)
    content_text = normalize_text(content)
    name_tokens = _token_set(name_text)
    content_tokens = _token_set(content_text)
    score = 0
    for term in intent.search_terms:
        if term in name_tokens:
            score += 28
        elif _contains_phrase(name_text, term):
            score += 18
        if term in content_tokens:
            score += 5
        elif _contains_phrase(content_text, term):
            score += 2
    return score + _specificity_multiplier(intent.constraints, name, content)


def _all_rows(connection):
    return connection.execute("SELECT * FROM documents").fetchall()


def _candidate_rows(intent: QueryIntent):
    initialize_database()
    connection = get_connection()
    try:
        rows_by_id = {}
        if intent.document_type:
            typed_rows = connection.execute(
                "SELECT * FROM documents WHERE document_type = ?",
                (intent.document_type,),
            ).fetchall()
            rows_by_id.update({int(row["id"]): row for row in typed_rows})

        # Old indexes may have a blank document_type. Re-infer those rows even
        # when newer typed rows already exist, so a legacy document is not skipped.
        if intent.document_type:
            for row in _all_rows(connection):
                if row["document_type"]:
                    continue
                inferred = infer_document_type(row["name"], row["content"] or "")
                if inferred == intent.document_type:
                    rows_by_id[int(row["id"])] = row

        terms = list(intent.search_terms)
        if terms and not intent.document_type:
            query = " OR ".join('"' + term.replace('"', ' ') + '"' for term in terms[:12])
            try:
                fts_rows = connection.execute(
                    """
                    SELECT d.* FROM documents_fts f
                    JOIN documents d ON d.id = f.rowid
                    WHERE documents_fts MATCH ?
                    """,
                    (query,),
                ).fetchall()
                rows_by_id.update({int(row["id"]): row for row in fts_rows})
            except Exception:
                pass

        if rows_by_id:
            return list(rows_by_id.values())
        return _all_rows(connection)
    finally:
        connection.close()


def _row_to_result(row, score: int, document_type: str = "") -> Dict:
    return {
        "id": int(row["id"]), "name": row["name"], "path": row["path"],
        "extension": row["extension"], "size": int(row["size"] or 0),
        "modified_time": float(row["modified_time"] or 0), "content": row["content"] or "",
        "document_type": document_type or row["document_type"] or None,
        "language": row["language"] or "", "score": score,
        "extraction_status": row["extraction_status"] or "ok",
        "extraction_error": row["extraction_error"] or "",
        "source": "local",
    }


def search_documents(query: str, limit: int = 5, *, document_type: Optional[str] = None, constraints: Optional[Dict[str, str]] = None, allowed_paths: Optional[set[str]] = None) -> List[Dict]:
    query = (query or "").strip()
    if not query and not document_type:
        return []

    intent = parse_query(query) if query else QueryIntent()
    if document_type:
        intent = QueryIntent(
            document_type=document_type,
            search_terms=tuple(tokenize_text(query)),
            phrases=(),
            constraints=constraints or intent.constraints,
            document_name=query,
        )
    rows = _candidate_rows(intent)
    candidates = []
    allowed = {str(Path(item).resolve()) for item in allowed_paths} if allowed_paths is not None else None
    for row in rows:
        path = str(Path(row["path"]).resolve())
        if allowed is not None and path not in allowed:
            continue
        if not Path(path).is_file():
            continue
        candidate_type = row["document_type"] or infer_document_type(row["name"], row["content"] or "") or ""
        if intent.document_type:
            if candidate_type != intent.document_type:
                continue
            score = calculate_document_type_score(row["name"], row["content"] or "", intent.document_type, intent)
            doc_type = intent.document_type
        else:
            score = calculate_generic_score(row["name"], row["content"] or "", intent)
            doc_type = candidate_type
        if score > 0:
            candidates.append(_row_to_result(row, score, doc_type))

    candidates.sort(key=lambda item: (-item["score"], item["name"].lower()))
    return candidates[: max(1, int(limit))]


def open_result(result: Dict) -> None:
    mark_opened(result["path"])


def search_documents_multilingual(
    original_query: str,
    canonical_query: str = "",
    transliterated_query: str = "",
    limit: int = 5,
    document_type: Optional[str] = None,
    constraints: Optional[Dict[str, str]] = None,
    allowed_paths: Optional[set[str]] = None,
) -> List[Dict]:
    """Search the canonical English document name first.

    The original-language sentence is not used as a relevance signal when a
    document type has been extracted. This prevents request filler and mixed
    language words from outranking the requested document.
    """
    if document_type:
        return search_documents(
            canonical_query or original_query,
            limit=limit,
            document_type=document_type,
            constraints=constraints or {},
            allowed_paths=allowed_paths,
        )

    queries = []
    for query in (canonical_query, transliterated_query, original_query):
        query = (query or "").strip()
        if query and query not in queries:
            queries.append(query)

    merged = {}
    for index, query in enumerate(queries):
        results = search_documents(query, limit=max(limit * 3, 10), allowed_paths=allowed_paths)
        for result in results:
            current = merged.get(result["id"])
            adjusted_score = int(result["score"]) + (2 if index == 0 else 0)
            if current is None or adjusted_score > current["score"]:
                clone = dict(result)
                clone["score"] = adjusted_score
                merged[result["id"]] = clone

    output = list(merged.values())
    output.sort(key=lambda item: (-item["score"], item["name"].lower()))
    return output[: max(1, int(limit))]
