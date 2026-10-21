"""Persistence and tenant-ownership tests for the web portal store."""
import pytest

import portal_store as store


def _configure(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_PORTAL_DATABASE_URL", f"sqlite:///{(tmp_path / 'portal.db').as_posix()}")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SMARTDOCUMENT_DATA_DIR", str(tmp_path / "data"))


def test_accounts_and_activity_are_scoped_to_user(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    store.initialize_store()
    first = store.create_user("test-person-a", "Person A", None, "hash-a")
    second = store.create_user("test-person-b", "Person B", None, "hash-b")
    store.add_search(first["id"], "my PAN", "voice", "en-IN", "local", 1, "PASS", 12)
    store.add_audit_event(second["id"], second["username"], "DOCUMENT_SEARCH", "PASS", {"query": "private B query"})
    assert len(store.list_searches(first["id"])) == 1
    assert store.list_searches(second["id"]) == []
    assert len(store.list_audit_events(second["id"])) == 1
    assert store.list_audit_events(first["id"]) == []


def test_document_metadata_is_deduplicated_by_user_and_uri(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    first = store.create_user("doc-user-a", "Doc User A", None, "hash-a")
    second = store.create_user("doc-user-b", "Doc User B", None, "hash-b")
    path_a = tmp_path / "users" / str(first["id"]) / "aadhaar.pdf"
    path_b = tmp_path / "users" / str(second["id"]) / "aadhaar.pdf"
    path_a.parent.mkdir(parents=True)
    path_b.parent.mkdir(parents=True)
    path_a.write_bytes(b"pdf-a")
    path_b.write_bytes(b"pdf-b")
    one = store.add_document(first["id"], "aadhaar.pdf", str(path_a), ".pdf", 5, source="digilocker", source_uri="urn:doc:one")
    duplicate = store.add_document(first["id"], "aadhaar.pdf", str(path_a), ".pdf", 5, source="digilocker", source_uri="urn:doc:one")
    other_user = store.add_document(second["id"], "aadhaar.pdf", str(path_b), ".pdf", 5, source="digilocker", source_uri="urn:doc:one")
    assert one["id"] == duplicate["id"]
    assert other_user["id"] != one["id"]
    assert store.count_documents(first["id"]) == 1
    assert store.count_documents(second["id"]) == 1


def test_disconnect_clears_stored_token_fields(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    user = store.create_user("disconnect-user", "Disconnect User", None, "hash")
    store.add_connection(user["id"], "encrypted-access", "encrypted-refresh", None, "openid")
    store.disconnect_provider(user["id"])
    connection = store.get_connection(user["id"])
    assert connection["status"] == "disconnected"
    assert connection["access_token_encrypted"] is None
    assert connection["refresh_token_encrypted"] is None


def test_sync_jobs_keep_progress_private_to_owner(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    owner = store.create_user("sync-owner", "Sync Owner", None, "hash")
    other = store.create_user("sync-other", "Sync Other", None, "hash")
    job = store.create_sync_job(owner["id"], "e4d09c1f-a5aa-4a03-b3c4-1e448047251b")
    store.update_sync_job(job["id"], owner["id"], status="running", total=10, processed=4, fetched=3, skipped=1,
                          message="Processed 4 of 10 records.")
    stored = store.get_latest_sync_job(owner["id"])
    assert stored["status"] == "running"
    assert stored["processed"] == 4
    assert stored["fetched"] == 3
    assert store.get_latest_sync_job(other["id"]) is None
    assert store.get_sync_job(other["id"], job["id"]) is None
    store.update_sync_job(job["id"], owner["id"], status="completed", processed=10, fetched=9, skipped=1,
                          message="Sync finished")
    final = store.get_latest_sync_job(owner["id"])
    assert final["status"] == "completed"
    assert final["finished_at"] is not None
