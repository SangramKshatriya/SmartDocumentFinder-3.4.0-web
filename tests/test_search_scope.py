"""Verify that search scopes candidates before ranking them for a user."""
from pathlib import Path

import database
from indexer import index_file
from search_engine import search_documents_multilingual


def test_multilingual_search_can_be_restricted_to_user_paths(monkeypatch, tmp_path):
    db_path = tmp_path / "scoped-index.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    root_a = tmp_path / "docs" / "user-a"
    root_b = tmp_path / "docs" / "user-b"
    root_a.mkdir(parents=True)
    root_b.mkdir(parents=True)
    file_a = root_a / "aadhaar_user_a.txt"
    file_b = root_b / "aadhaar_user_b.txt"
    file_a.write_text("Aadhaar identification record for user A", encoding="utf-8")
    file_b.write_text("Aadhaar identification record for user B", encoding="utf-8")
    for path in (file_a, file_b):
        stat = path.stat()
        index_file({"name": path.name, "path": str(path), "extension": ".txt", "size": stat.st_size, "modified_time": stat.st_mtime}, force=True)

    results = search_documents_multilingual("aadhaar", canonical_query="aadhaar", limit=10, allowed_paths={str(file_a.resolve())})
    assert results
    assert {item["path"] for item in results} == {str(file_a.resolve())}
    assert all("user_b" not in item["name"] for item in results)


def test_user_document_indexes_store_text_in_separate_sqlite_files(tmp_path):
    user_a_index = tmp_path / "documents" / "users" / "1" / ".index" / "documents.db"
    user_b_index = tmp_path / "documents" / "users" / "2" / ".index" / "documents.db"
    file_a = tmp_path / "documents" / "users" / "1" / "private-a.txt"
    file_b = tmp_path / "documents" / "users" / "2" / "private-b.txt"
    file_a.parent.mkdir(parents=True)
    file_b.parent.mkdir(parents=True)
    file_a.write_text("secret alpha account data", encoding="utf-8")
    file_b.write_text("secret beta account data", encoding="utf-8")

    def metadata(path):
        stat = path.stat()
        return {"name": path.name, "path": str(path), "extension": ".txt", "size": stat.st_size, "modified_time": stat.st_mtime}

    with database.using_database(user_a_index):
        index_file(metadata(file_a), force=True)
        assert database.get_document_by_path(str(file_a)) is not None
        assert database.get_document_by_path(str(file_b)) is None
    with database.using_database(user_b_index):
        index_file(metadata(file_b), force=True)
        assert database.get_document_by_path(str(file_b)) is not None
        assert database.get_document_by_path(str(file_a)) is None
    assert user_a_index.exists() and user_b_index.exists()
    assert user_a_index != user_b_index
