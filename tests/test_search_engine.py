from search_engine import calculate_document_type_score
from query_processor import parse_query


def test_12th_beats_10th_for_12th_query():
    intent = parse_query("show my 12th marksheet")
    score_12 = calculate_document_type_score(
        "12thMarksheet.pdf", "", "marksheet", intent
    )
    score_10 = calculate_document_type_score(
        "10thMarksheet.pdf", "", "marksheet", intent
    )
    assert score_12 > score_10


def test_legacy_blank_document_type_is_reinferred(tmp_path, monkeypatch):
    import database
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "docs.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize_database()
    path = tmp_path / "PAN.pdf"
    path.write_text("Permanent Account Number", encoding="utf-8")
    database.upsert_document(
        name=path.name, path=str(path), extension=".pdf", size=path.stat().st_size,
        modified_time=path.stat().st_mtime, content=path.read_text(encoding="utf-8"),
        content_hash="x", document_type="", language="en",
    )
    from search_engine import search_documents
    results = search_documents("pan card", document_type="pan")
    assert results and results[0]["name"] == "PAN.pdf"
