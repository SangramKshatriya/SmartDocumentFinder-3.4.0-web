import database


def test_search_history_uses_status_column(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DATABASE_PATH", tmp_path / "history.db")
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)

    database.initialize_database()
    user = database.get_or_create_user("tester", "Test User")
    database.record_search_history(
        username=user["username"],
        display_name=user["display_name"],
        original_query="show pan",
        results_count=1,
        success=True,
    )

    row = database.get_search_history(user["username"], 1)[0]

    # The consolidated schema deliberately stores PASS/FAIL in `status`.
    # Older UI code tried to access the removed `success` column and crashed.
    assert "status" in row.keys()
    assert row["status"] == "PASS"
    assert "success" not in row.keys()
