import json
import sqlite3

import database


def _tables(db_path):
    with sqlite3.connect(db_path) as connection:
        return {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }


def test_history_uses_single_activity_table_and_tracks_session(tmp_path, monkeypatch):
    db_path = tmp_path / "history.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)

    database.initialize_database()
    user = database.get_or_create_user("tester", "Test User")
    session_id = database.start_session(user["username"], user["display_name"])
    search_id = database.record_search_history(
        username=user["username"],
        display_name=user["display_name"],
        session_id=session_id,
        original_query="मेरा पैन कार्ड दिखाओ",
        canonical_query="show my pan card",
        transliterated_query="mera pan card dikhao",
        detected_language="hi-IN",
        input_mode="voice",
        provider="sarvam",
        document_type="pan",
        duration_ms=123,
        results_count=1,
        success=True,
    )
    document_history_id = database.record_document_access(
        username=user["username"],
        display_name=user["display_name"],
        session_id=session_id,
        document_id=None,
        document_name="PAN Card.pdf",
        document_path=str(tmp_path / "PAN Card.pdf"),
        source="local",
        search_history_id=search_id,
        document_type="pan",
    )
    audit_id = database.log_audit_event(
        "DOCUMENT_REFRESH",
        username=user["username"],
        display_name=user["display_name"],
        session_id=session_id,
        details={"name": "PAN Card.pdf"},
    )

    searches = database.get_search_history(user["username"])
    documents = database.get_document_history(user["username"])
    sessions = database.get_session_history(user["username"])
    stats = database.get_user_stats(user["username"])

    assert searches[0]["original_query"] == "मेरा पैन कार्ड दिखाओ"
    assert searches[0]["input_mode"] == "voice"
    assert searches[0]["results_count"] == 1
    assert searches[0]["status"] == "PASS"
    assert documents[0]["document_name"] == "PAN Card.pdf"
    assert document_history_id == documents[0]["id"]
    assert audit_id > 0
    assert stats["searches"] == 1
    assert stats["successful_searches"] == 1
    assert stats["voice_searches"] == 1
    assert stats["document_opens"] == 1
    assert sessions[0]["login_status"] == "PASS"
    assert sessions[0]["logout_status"] == "PENDING"
    assert sessions[0]["login_time"]
    assert sessions[0]["logout_time"] is None

    tables = _tables(db_path)
    assert "activity_history" in tables
    assert "users" not in tables
    assert "sessions" not in tables
    assert "search_history" not in tables
    assert "document_history" not in tables
    assert "audit_events" not in tables

    output = tmp_path / "history.json"
    database.export_user_history_json(user["username"], str(output))
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["user"]["username"] == "tester"
    assert len(payload["search_history"]) == 1
    assert len(payload["document_history"]) == 1
    assert payload["activity_history"]

    database.end_session(session_id, "application_closed")
    sessions = database.get_session_history(user["username"])
    assert sessions[0]["session_status"] == "CLOSED"
    assert sessions[0]["logout_status"] == "PASS"
    assert sessions[0]["logout_time"]


def test_failed_search_and_login_attempt_are_status_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "history.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize_database()

    database.record_login_attempt("", "", status="FAIL", reason="username_required")
    database.record_search_history(
        username="tester",
        display_name="Test User",
        original_query="missing document",
        results_count=0,
        success=False,
        error_message="No matching document",
    )

    with database.get_connection() as connection:
        failed = connection.execute(
            "SELECT event_type, status, event_reason, error_message FROM activity_history ORDER BY id"
        ).fetchall()
    assert [(row[0], row[1]) for row in failed] == [("LOGIN_ATTEMPT", "FAIL"), ("SEARCH", "FAIL")]
    assert failed[0][2] == "username_required"
    assert failed[1][3] == "No matching document"


def test_new_login_marks_previous_unclosed_session_as_failed_logout(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "history.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)
    database.initialize_database()

    first = database.start_session("tester", "Test User")
    second = database.start_session("tester", "Test User")

    sessions = database.get_session_history("tester", 10)
    first_row = next(row for row in sessions if row["id"] == first)
    second_row = next(row for row in sessions if row["id"] == second)
    assert first_row["session_status"] == "ABNORMAL"
    assert first_row["logout_status"] == "FAIL"
    assert first_row["logout_time"]
    assert second_row["session_status"] == "ACTIVE"
    assert second_row["logout_status"] == "PENDING"
