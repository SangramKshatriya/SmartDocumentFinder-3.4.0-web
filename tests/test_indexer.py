from pathlib import Path

import database
import indexer


def test_file_hash_is_stable(tmp_path: Path):
    path = tmp_path / "file.txt"
    path.write_bytes(b"hello world")
    first = indexer.file_hash(path)
    second = indexer.file_hash(path)
    assert first == second
    assert len(first) == 64


def test_detect_language_mixed_text():
    assert indexer.detect_language("मेरा PAN card") == "hi+en"
    assert indexer.detect_language("PAN card") == "en"
    assert indexer.detect_language("") == ""


def test_index_file_stores_extracted_document(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "docs.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize_database()
    path = tmp_path / "PAN.pdf"
    path.write_text("fake pdf source", encoding="utf-8")
    monkeypatch.setattr(indexer, "extract_text", lambda _: "Permanent Account Number PAN card")
    info = {
        "name": path.name,
        "path": str(path),
        "extension": ".pdf",
        "size": path.stat().st_size,
        "modified_time": path.stat().st_mtime,
    }
    result = indexer.index_file(info)
    row = database.get_document_by_path(str(path))
    assert result["changed"] is True
    assert result["error"] == ""
    assert row["document_type"] == "pan"
    assert row["extraction_status"] == "ok"


def test_index_folder_reports_skipped_files(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "docs.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize_database()
    path = tmp_path / "PAN.txt"
    path.write_text("PAN card", encoding="utf-8")
    monkeypatch.setattr(indexer, "extract_text", lambda _: "PAN card document")
    first = indexer.index_folder(str(tmp_path))
    second = indexer.index_folder(str(tmp_path))
    assert first["total"] == 1
    assert first["changed"] == 1
    assert second["skipped"] == 1
