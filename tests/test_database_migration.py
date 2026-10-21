import sqlite3

import database


def test_legacy_activity_tables_migrate_into_single_table(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(database, "DATABASE_PATH", db_path)
    monkeypatch.setattr(database, "DATA_DIR", tmp_path)

    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE documents(
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
            path TEXT UNIQUE NOT NULL, extension TEXT, size INTEGER DEFAULT 0,
            modified_time REAL DEFAULT 0, content TEXT DEFAULT '', content_hash TEXT DEFAULT '',
            document_type TEXT DEFAULT '', language TEXT DEFAULT '', indexed_time REAL DEFAULT 0,
            opened_time REAL DEFAULT 0, extraction_status TEXT DEFAULT 'ok', extraction_error TEXT DEFAULT ''
        );
        CREATE TABLE users(
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL, created_at TEXT NOT NULL, last_login_at TEXT, is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE sessions(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            login_time TEXT NOT NULL, logout_time TEXT, session_status TEXT NOT NULL, ended_reason TEXT
        );
        CREATE TABLE search_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, session_id INTEGER,
            original_query TEXT NOT NULL, canonical_query TEXT DEFAULT '', transliterated_query TEXT DEFAULT '',
            detected_language TEXT DEFAULT '', preferred_language TEXT DEFAULT '', input_mode TEXT NOT NULL DEFAULT 'text',
            provider TEXT DEFAULT '', document_type TEXT DEFAULT '', searched_at TEXT NOT NULL, completed_at TEXT NOT NULL,
            duration_ms INTEGER DEFAULT 0, results_count INTEGER DEFAULT 0, success INTEGER NOT NULL DEFAULT 0,
            error_message TEXT DEFAULT ''
        );
        CREATE TABLE document_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, session_id INTEGER,
            document_id INTEGER, document_name TEXT NOT NULL, document_path TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'local', action TEXT NOT NULL DEFAULT 'open', accessed_at TEXT NOT NULL,
            search_history_id INTEGER
        );
        CREATE TABLE audit_events(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, session_id INTEGER,
            event_type TEXT NOT NULL, event_time TEXT NOT NULL, details_json TEXT DEFAULT '{}'
        );
        """)
    connection.execute(
        "INSERT INTO users(id, username, display_name, created_at) VALUES (1, 'tester', 'Test User', '2026-10-01T10:00:00+00:00')"
    )
    connection.execute(
        "INSERT INTO sessions(id, user_id, login_time, logout_time, session_status, ended_reason) VALUES (7, 1, '2026-10-01T10:00:00+00:00', '2026-10-01T11:00:00+00:00', 'closed', 'application_closed')"
    )
    connection.execute(
        "INSERT INTO search_history(user_id, session_id, original_query, canonical_query, searched_at, completed_at, success) VALUES (1, 7, 'show pan', 'pan card', '2026-10-01T10:10:00+00:00', '2026-10-01T10:10:01+00:00', 1)"
    )
    connection.execute(
        "INSERT INTO audit_events(user_id, session_id, event_type, event_time, details_json) VALUES (1, 7, 'INDEX_COMPLETED', '2026-10-01T10:05:00+00:00', '{}')"
    )
    connection.commit()
    connection.close()

    database.initialize_database()

    with database.get_connection() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        rows = connection.execute(
            "SELECT event_type, username FROM activity_history ORDER BY id"
        ).fetchall()

    assert "activity_history" in tables
    for legacy in ("users", "sessions", "search_history", "document_history", "audit_events"):
        assert legacy not in tables
    assert [tuple(row) for row in rows] == [
        ("SESSION", "tester"),
        ("SEARCH", "tester"),
        ("INDEX_COMPLETED", "tester"),
    ]
