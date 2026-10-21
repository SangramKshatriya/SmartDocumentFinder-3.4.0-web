from pathlib import Path
import tempfile

import database
from database import initialize_database, upsert_document
from search_engine import search_documents_multilingual


def test_multilingual_search_wrapper_merges_queries(monkeypatch, tmp_path):
    # Redirect DB path to an isolated temporary DB.
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "docs.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    initialize_database()
    file_path = tmp_path / "12thMarksheet.pdf"
    file_path.write_text("12th marksheet result", encoding="utf-8")
    upsert_document(
        name=file_path.name,
        path=str(file_path),
        extension=".pdf",
        size=file_path.stat().st_size,
        modified_time=file_path.stat().st_mtime,
        content="12th marksheet result",
        content_hash="x",
        document_type="marksheet",
        language="en",
    )
    results = search_documents_multilingual(
        "मेरी बारहवीं की मार्कशीट दिखाओ",
        canonical_query="show my 12th marksheet",
        limit=5,
    )
    assert results
    assert results[0]["name"] == "12thMarksheet.pdf"
