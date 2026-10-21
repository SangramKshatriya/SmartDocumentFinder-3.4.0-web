import sqlite3
import threading
from pathlib import Path
from datetime import datetime, timezone
import json
from typing import Iterable, Optional
from contextlib import contextmanager
from contextvars import ContextVar

from config import DATA_DIR, DATABASE_PATH

_ACTIVE_DATABASE_PATH: ContextVar[Path | None] = ContextVar("sdf_active_document_database", default=None)
_INDEX_DATABASE_INIT_LOCK = threading.RLock()
_INITIALIZED_INDEX_DATABASES: set[str] = set()


@contextmanager
def using_database(path: str | Path):
    """Temporarily select an isolated document index for the current request/thread.

    The desktop application continues using the default database. The browser portal
    can bind each authenticated account to a separate SQLite/FTS database without
    changing every existing indexer/search API or sharing extracted document text.
    """
    token = _ACTIVE_DATABASE_PATH.set(Path(path).expanduser().resolve())
    try:
        yield
    finally:
        _ACTIVE_DATABASE_PATH.reset(token)


def get_active_database_path() -> Path:
    return _ACTIVE_DATABASE_PATH.get() or Path(DATABASE_PATH)


def get_connection() -> sqlite3.Connection:
    database_path = get_active_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_column(connection: sqlite3.Connection, name: str, definition: str) -> None:
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(documents)").fetchall()
    }
    if name not in columns:
        connection.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _migrate_legacy_activity_schema(connection: sqlite3.Connection) -> None:
    """Move pre-3.3.3 user/session/history tables into one activity table.

    The document index remains separate because it is application data rather than
    user activity. Migration is performed once and the legacy activity tables are
    removed after the rows have been copied successfully.
    """
    legacy_tables = {
        "users", "sessions", "search_history", "document_history", "audit_events"
    }
    if not any(_table_exists(connection, table) for table in legacy_tables):
        return

    migrated = connection.execute(
        "SELECT value FROM app_settings WHERE key = 'activity_schema_migrated'"
    ).fetchone()
    if migrated and migrated[0] == "1":
        return

    user_map: dict[int, tuple[str, str]] = {}
    if _table_exists(connection, "users"):
        for row in connection.execute("SELECT id, username, display_name FROM users").fetchall():
            user_map[int(row["id"])] = (row["username"], row["display_name"])

    session_map: dict[int, int] = {}
    if _table_exists(connection, "sessions"):
        rows = connection.execute(
            "SELECT * FROM sessions ORDER BY id"
        ).fetchall()
        for row in rows:
            username, display_name = user_map.get(int(row["user_id"]), ("", ""))
            cursor = connection.execute(
                """
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    login_time, logout_time, session_status, login_status,
                    logout_status, status, event_reason
                ) VALUES (?, ?, 'SESSION', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    display_name,
                    int(row["id"]),
                    row["login_time"] or utc_now_iso(),
                    row["login_time"],
                    row["logout_time"],
                    row["session_status"] or "active",
                    "PASS" if row["login_time"] else "FAIL",
                    "PASS" if row["logout_time"] else "PENDING",
                    "PASS",
                    row["ended_reason"] or "",
                ),
            )
            session_map[int(row["id"])] = int(cursor.lastrowid)

    if _table_exists(connection, "search_history"):
        rows = connection.execute("SELECT * FROM search_history ORDER BY id").fetchall()
        for row in rows:
            username, display_name = user_map.get(int(row["user_id"]), ("", ""))
            connection.execute(
                """
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    original_query, canonical_query, transliterated_query,
                    detected_language, preferred_language, input_mode, provider,
                    document_type, searched_at, completed_at, duration_ms,
                    results_count, status, error_message
                ) VALUES (?, ?, 'SEARCH', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username, display_name,
                    session_map.get(int(row["session_id"])) if row["session_id"] is not None else None,
                    row["searched_at"] or utc_now_iso(),
                    row["original_query"], row["canonical_query"] or "",
                    row["transliterated_query"] or "", row["detected_language"] or "",
                    row["preferred_language"] or "", row["input_mode"] or "text",
                    row["provider"] or "", row["document_type"] or "",
                    row["searched_at"], row["completed_at"], int(row["duration_ms"] or 0),
                    int(row["results_count"] or 0),
                    "PASS" if row["success"] else "FAIL", row["error_message"] or "",
                ),
            )

    if _table_exists(connection, "document_history"):
        rows = connection.execute("SELECT * FROM document_history ORDER BY id").fetchall()
        for row in rows:
            username, display_name = user_map.get(int(row["user_id"]), ("", ""))
            document_type = ""
            if row["document_id"] is not None:
                doc = connection.execute(
                    "SELECT document_type FROM documents WHERE id = ?", (row["document_id"],)
                ).fetchone()
                document_type = doc["document_type"] if doc else ""
            connection.execute(
                """
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    document_id, document_name, document_path, source, action,
                    document_type, status, search_history_id
                ) VALUES (?, ?, 'DOCUMENT_OPEN', ?, ?, ?, ?, ?, ?, ?, ?, 'PASS', ?)
                """,
                (
                    username, display_name,
                    session_map.get(int(row["session_id"])) if row["session_id"] is not None else None,
                    row["accessed_at"] or utc_now_iso(), row["document_id"],
                    row["document_name"], row["document_path"], row["source"] or "local",
                    row["action"] or "open", document_type, row["search_history_id"],
                ),
            )

    if _table_exists(connection, "audit_events"):
        rows = connection.execute("SELECT * FROM audit_events ORDER BY id").fetchall()
        for row in rows:
            username, display_name = user_map.get(int(row["user_id"]), ("", ""))
            connection.execute(
                """
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    status, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username, display_name, row["event_type"],
                    session_map.get(int(row["session_id"])) if row["session_id"] is not None else None,
                    row["event_time"] or utc_now_iso(),
                    "PASS",
                    row["details_json"] or "{}",
                ),
            )

    connection.execute(
        "INSERT INTO app_settings(key, value) VALUES ('activity_schema_migrated', '1') "
        "ON CONFLICT(key) DO UPDATE SET value = '1'"
    )

    # Remove the obsolete activity tables. These are not needed after the data is
    # consolidated into activity_history and would defeat the single-table design.
    for table in ("audit_events", "document_history", "search_history", "sessions", "users"):
        if _table_exists(connection, table):
            connection.execute(f"DROP TABLE {table}")


def initialize_database() -> None:
    connection = get_connection()
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                path TEXT UNIQUE NOT NULL,
                extension TEXT,
                size INTEGER DEFAULT 0,
                modified_time REAL DEFAULT 0,
                content TEXT DEFAULT '',
                content_hash TEXT DEFAULT '',
                document_type TEXT DEFAULT '',
                language TEXT DEFAULT '',
                indexed_time REAL DEFAULT 0,
                opened_time REAL DEFAULT 0,
                extraction_status TEXT DEFAULT 'ok',
                extraction_error TEXT DEFAULT ''
            )
            """
        )
        if not _using_postgresql_history():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL,
                    session_id INTEGER,
                    event_time TEXT NOT NULL,

                    login_time TEXT,
                    logout_time TEXT,
                    session_status TEXT DEFAULT '',
                    login_status TEXT DEFAULT '',
                    logout_status TEXT DEFAULT '',

                    original_query TEXT,
                    canonical_query TEXT DEFAULT '',
                    transliterated_query TEXT DEFAULT '',
                    detected_language TEXT DEFAULT '',
                    preferred_language TEXT DEFAULT '',
                    input_mode TEXT DEFAULT 'text',
                    provider TEXT DEFAULT '',
                    document_type TEXT DEFAULT '',
                    searched_at TEXT,
                    completed_at TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    results_count INTEGER DEFAULT 0,

                    document_id INTEGER,
                    document_name TEXT DEFAULT '',
                    document_path TEXT DEFAULT '',
                    source TEXT DEFAULT 'local',
                    action TEXT DEFAULT 'open',
                    search_history_id INTEGER,

                    status TEXT NOT NULL DEFAULT 'PASS',
                    error_message TEXT DEFAULT '',
                    event_reason TEXT DEFAULT '',
                    details_json TEXT DEFAULT '{}'
                )
                """
            )

            # Databases created by intermediate 3.3.x builds may already have an
            # activity_history table but miss one or more of the newer columns.
            # Keep those databases usable instead of requiring users to delete their
            # history database.
            activity_columns = (
                ("username", "TEXT NOT NULL DEFAULT ''"),
                ("display_name", "TEXT NOT NULL DEFAULT ''"),
                ("event_type", "TEXT NOT NULL DEFAULT 'UNKNOWN'"),
                ("session_id", "INTEGER"),
                ("event_time", "TEXT NOT NULL DEFAULT ''"),
                ("login_time", "TEXT"),
                ("logout_time", "TEXT"),
                ("session_status", "TEXT DEFAULT ''"),
                ("login_status", "TEXT DEFAULT ''"),
                ("logout_status", "TEXT DEFAULT ''"),
                ("original_query", "TEXT"),
                ("canonical_query", "TEXT DEFAULT ''"),
                ("transliterated_query", "TEXT DEFAULT ''"),
                ("detected_language", "TEXT DEFAULT ''"),
                ("preferred_language", "TEXT DEFAULT ''"),
                ("input_mode", "TEXT DEFAULT 'text'"),
                ("provider", "TEXT DEFAULT ''"),
                ("document_type", "TEXT DEFAULT ''"),
                ("searched_at", "TEXT"),
                ("completed_at", "TEXT"),
                ("duration_ms", "INTEGER DEFAULT 0"),
                ("results_count", "INTEGER DEFAULT 0"),
                ("document_id", "INTEGER"),
                ("document_name", "TEXT DEFAULT ''"),
                ("document_path", "TEXT DEFAULT ''"),
                ("source", "TEXT DEFAULT 'local'"),
                ("action", "TEXT DEFAULT 'open'"),
                ("search_history_id", "INTEGER"),
                ("status", "TEXT NOT NULL DEFAULT 'PASS'"),
                ("error_message", "TEXT DEFAULT ''"),
                ("event_reason", "TEXT DEFAULT ''"),
                ("details_json", "TEXT DEFAULT '{}'"),
            )
            existing_activity_columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(activity_history)"
                ).fetchall()
            }
            for column, definition in activity_columns:
                if column not in existing_activity_columns:
                    connection.execute(
                        f"ALTER TABLE activity_history ADD COLUMN {column} {definition}"
                    )

            for column, definition in (
                ("content_hash", "TEXT DEFAULT ''"),
                ("document_type", "TEXT DEFAULT ''"),
                ("language", "TEXT DEFAULT ''"),
                ("indexed_time", "REAL DEFAULT 0"),
                ("opened_time", "REAL DEFAULT 0"),
                ("extraction_status", "TEXT DEFAULT 'ok'"),
                ("extraction_error", "TEXT DEFAULT ''"),
            ):
                _ensure_column(connection, column, definition)

            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_user_time "
                "ON activity_history(username, event_time DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_session_time "
                "ON activity_history(session_id, event_time DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_activity_event_time "
                "ON activity_history(event_type, event_time DESC)"
            )

            _migrate_legacy_activity_schema(connection)

        fts_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone() is not None
        if fts_exists:
            fts_columns = {
                row[1] for row in connection.execute(
                    "PRAGMA table_info(documents_fts)"
                ).fetchall()
            }
            if not {"name", "content", "path", "document_type"}.issubset(fts_columns):
                connection.execute("DROP TABLE documents_fts")
                fts_exists = False
        if not fts_exists:
            connection.execute(
                """
                CREATE VIRTUAL TABLE documents_fts USING fts5(
                    name, content, path, document_type, tokenize='unicode61'
                )
                """
            )
            sync_fts(connection)
        else:
            doc_count = connection.execute(
                "SELECT COUNT(*) FROM documents"
            ).fetchone()[0]
            fts_count = connection.execute(
                "SELECT COUNT(*) FROM documents_fts"
            ).fetchone()[0]
            if doc_count != fts_count:
                sync_fts(connection)

        connection.commit()
    finally:
        connection.close()


def sync_fts(connection: Optional[sqlite3.Connection] = None) -> None:
    owns_connection = connection is None
    connection = connection or get_connection()
    try:
        connection.execute("DELETE FROM documents_fts")
        rows = connection.execute(
            "SELECT id, name, content, path, document_type FROM documents"
        ).fetchall()
        connection.executemany(
            """
            INSERT INTO documents_fts(rowid, name, content, path, document_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (row["id"], row["name"], row["content"] or "", row["path"], row["document_type"] or "")
                for row in rows
            ],
        )
        connection.commit()
    finally:
        if owns_connection:
            connection.close()


def get_setting(key: str, default: str = "") -> str:
    initialize_database()
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row and row["value"] is not None else default
    finally:
        connection.close()


def set_setting(key: str, value: str) -> None:
    initialize_database()
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO app_settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        connection.commit()
    finally:
        connection.close()


def get_document_by_path(file_path: str):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT * FROM documents WHERE path = ?", (str(Path(file_path).resolve()),)
        ).fetchone()
    finally:
        connection.close()


def upsert_document(
    *,
    name: str,
    path: str,
    extension: str,
    size: int,
    modified_time: float,
    content: str,
    content_hash: str,
    document_type: str,
    language: str,
    extraction_status: str = "ok",
    extraction_error: str = "",
) -> int:
    initialize_database()
    normalized_path = str(Path(path).resolve())
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO documents (
                name, path, extension, size, modified_time, content,
                content_hash, document_type, language, indexed_time,
                extraction_status, extraction_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name = excluded.name,
                extension = excluded.extension,
                size = excluded.size,
                modified_time = excluded.modified_time,
                content = excluded.content,
                content_hash = excluded.content_hash,
                document_type = excluded.document_type,
                language = excluded.language,
                indexed_time = excluded.indexed_time,
                extraction_status = excluded.extraction_status,
                extraction_error = excluded.extraction_error
            """,
            (
                name, normalized_path, extension, size, modified_time, content,
                content_hash, document_type, language, extraction_status, extraction_error,
            ),
        )
        row = connection.execute(
            "SELECT id FROM documents WHERE path = ?", (normalized_path,)
        ).fetchone()
        document_id = int(row["id"])
        connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (document_id,))
        connection.execute(
            """
            INSERT INTO documents_fts(rowid, name, content, path, document_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (document_id, name, content or "", normalized_path, document_type or ""),
        )
        connection.commit()
        return document_id
    finally:
        connection.close()


def mark_opened(file_path: str) -> None:
    initialize_database()
    normalized_path = str(Path(file_path).resolve())
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE documents SET opened_time = strftime('%s','now') WHERE path = ?",
            (normalized_path,),
        )
        connection.commit()
    finally:
        connection.close()


def delete_document_by_path(file_path: str) -> None:
    initialize_database()
    normalized_path = str(Path(file_path).resolve())
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM documents WHERE path = ?", (normalized_path,)
        ).fetchone()
        if row:
            connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (row["id"],))
        connection.execute("DELETE FROM documents WHERE path = ?", (normalized_path,))
        connection.commit()
    finally:
        connection.close()


def delete_documents_not_in_paths(valid_paths: Iterable[str], root_path: Optional[str] = None) -> int:
    initialize_database()
    normalized_paths = {str(Path(path).resolve()) for path in valid_paths}
    connection = get_connection()
    try:
        rows = connection.execute("SELECT id, path FROM documents").fetchall()
        deleted = 0
        for row in rows:
            candidate = Path(row["path"])
            if root_path:
                try:
                    inside_root = candidate.is_relative_to(Path(root_path).resolve())
                except AttributeError:
                    try:
                        candidate.relative_to(Path(root_path).resolve())
                        inside_root = True
                    except ValueError:
                        inside_root = False
                if not inside_root:
                    continue
            if row["path"] not in normalized_paths:
                connection.execute("DELETE FROM documents_fts WHERE rowid = ?", (row["id"],))
                connection.execute("DELETE FROM documents WHERE id = ?", (row["id"],))
                deleted += 1
        connection.commit()
        return deleted
    finally:
        connection.close()


def get_all_documents():
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            "SELECT * FROM documents ORDER BY name COLLATE NOCASE"
        ).fetchall()
    finally:
        connection.close()


def get_recent_documents(limit: int = 10):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT * FROM documents
            WHERE opened_time > 0
            ORDER BY opened_time DESC, name COLLATE NOCASE
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        connection.close()


def get_document_count() -> int:
    initialize_database()
    connection = get_connection()
    try:
        row = connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()
        return int(row["count"])
    finally:
        connection.close()


def clear_database() -> None:
    initialize_database()
    connection = get_connection()
    try:
        connection.execute("DELETE FROM documents_fts")
        connection.execute("DELETE FROM documents")
        connection.commit()
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Local user/session/history tracking — one activity table
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return an unambiguous UTC timestamp for activity records."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_identity(username: str, display_name: Optional[str] = None) -> tuple[str, str]:
    username = (username or "").strip()
    display_name = (display_name or username).strip()
    if not username:
        raise ValueError("Username cannot be empty")
    return username, display_name


def get_or_create_user(username: str, display_name: Optional[str] = None) -> dict:
    """Return local identity data without creating a separate users table."""
    username, display_name = _clean_identity(username, display_name)
    return {"username": username, "display_name": display_name}


def record_login_attempt(
    username: str = "",
    display_name: str = "",
    *,
    status: str = "FAIL",
    reason: str = "",
) -> int:
    initialize_database()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO activity_history(
                username, display_name, event_type, event_time, status, event_reason
            ) VALUES (?, ?, 'LOGIN_ATTEMPT', ?, ?, ?)
            """,
            (
                (username or "").strip(),
                (display_name or username or "").strip(),
                utc_now_iso(),
                str(status).upper(),
                reason or "",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def start_session(username: str, display_name: Optional[str] = None) -> int:
    username, display_name = _clean_identity(username, display_name)
    now = utc_now_iso()
    initialize_database()
    connection = get_connection()
    try:
        # An active row from an earlier crash/missing shutdown is an abnormal logout.
        connection.execute(
            """
            UPDATE activity_history
            SET logout_time = ?, logout_status = 'FAIL',
                session_status = 'ABNORMAL',
                event_reason = COALESCE(NULLIF(event_reason, ''), 'previous_session_not_closed')
            WHERE event_type = 'SESSION'
              AND username = ? COLLATE NOCASE
              AND session_status = 'ACTIVE'
            """,
            (now, username),
        )
        cursor = connection.execute(
            """
            INSERT INTO activity_history(
                username, display_name, event_type, event_time,
                login_time, session_status, login_status, logout_status, status
            ) VALUES (?, ?, 'SESSION', ?, ?, 'ACTIVE', 'PASS', 'PENDING', 'PASS')
            """,
            (username, display_name, now, now),
        )
        session_id = int(cursor.lastrowid)
        connection.execute(
            "UPDATE activity_history SET session_id = ? WHERE id = ?",
            (session_id, session_id),
        )
        connection.commit()
        return session_id
    finally:
        connection.close()


def end_session(session_id: Optional[int], reason: str = "application_closed") -> None:
    if not session_id:
        return
    initialize_database()
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE activity_history
            SET logout_time = ?, logout_status = 'PASS',
                session_status = 'CLOSED', event_reason = ?, status = 'PASS'
            WHERE id = ? AND event_type = 'SESSION' AND session_status = 'ACTIVE'
            """,
            (utc_now_iso(), reason or "application_closed", int(session_id)),
        )
        connection.commit()
    finally:
        connection.close()


def log_audit_event(
    event_type: str,
    *,
    username: str = "",
    display_name: str = "",
    session_id: Optional[int] = None,
    details: Optional[dict] = None,
    status: str = "PASS",
) -> int:
    initialize_database()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO activity_history(
                username, display_name, event_type, session_id, event_time,
                status, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (username or "").strip(), (display_name or "").strip(), str(event_type),
                int(session_id) if session_id is not None else None,
                utc_now_iso(), str(status).upper(),
                json.dumps(details or {}, ensure_ascii=False),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def record_search_history(
    *,
    username: str,
    display_name: str = "",
    session_id: Optional[int] = None,
    original_query: str,
    canonical_query: str = "",
    transliterated_query: str = "",
    detected_language: str = "",
    preferred_language: str = "",
    input_mode: str = "text",
    provider: str = "",
    document_type: str = "",
    searched_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    duration_ms: int = 0,
    results_count: int = 0,
    success: bool = False,
    error_message: str = "",
) -> int:
    username, display_name = _clean_identity(username, display_name)
    initialize_database()
    searched_at = searched_at or utc_now_iso()
    completed_at = completed_at or utc_now_iso()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO activity_history(
                username, display_name, event_type, session_id, event_time,
                original_query, canonical_query, transliterated_query,
                detected_language, preferred_language, input_mode, provider,
                document_type, searched_at, completed_at, duration_ms,
                results_count, status, error_message
            ) VALUES (?, ?, 'SEARCH', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username, display_name,
                int(session_id) if session_id is not None else None,
                searched_at, original_query, canonical_query, transliterated_query,
                detected_language, preferred_language, input_mode, provider,
                document_type, searched_at, completed_at, max(0, int(duration_ms)),
                max(0, int(results_count)), "PASS" if success else "FAIL", error_message or "",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def record_document_access(
    *,
    username: str,
    display_name: str = "",
    session_id: Optional[int],
    document_name: str,
    document_path: str,
    document_id: Optional[int] = None,
    source: str = "local",
    action: str = "open",
    search_history_id: Optional[int] = None,
    document_type: str = "",
    success: bool = True,
    error_message: str = "",
) -> int:
    username, display_name = _clean_identity(username, display_name)
    initialize_database()
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO activity_history(
                username, display_name, event_type, session_id, event_time,
                document_id, document_name, document_path, source, action,
                document_type, search_history_id, status, error_message
            ) VALUES (?, ?, 'DOCUMENT_OPEN', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username, display_name,
                int(session_id) if session_id is not None else None,
                utc_now_iso(),
                int(document_id) if document_id is not None else None,
                document_name, str(Path(document_path).resolve()), source or "local",
                action or "open", document_type or "", 
                int(search_history_id) if search_history_id is not None else None,
                "PASS" if success else "FAIL", error_message or "",
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_search_history(username: str, limit: int = 100):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT * FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'SEARCH'
            ORDER BY searched_at DESC, id DESC
            LIMIT ?
            """,
            (str(username).strip(), max(1, int(limit))),
        ).fetchall()
    finally:
        connection.close()


def get_document_history(username: str, limit: int = 100):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT ah.*, COALESCE(NULLIF(ah.document_type, ''), d.document_type, '') AS document_type
            FROM activity_history ah
            LEFT JOIN documents d ON d.id = ah.document_id
            WHERE ah.username = ? COLLATE NOCASE AND ah.event_type = 'DOCUMENT_OPEN'
            ORDER BY ah.event_time DESC, ah.id DESC
            LIMIT ?
            """,
            (str(username).strip(), max(1, int(limit))),
        ).fetchall()
    finally:
        connection.close()


def get_session_history(username: str, limit: int = 50):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT * FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'SESSION'
            ORDER BY login_time DESC, id DESC
            LIMIT ?
            """,
            (str(username).strip(), max(1, int(limit))),
        ).fetchall()
    finally:
        connection.close()


def get_user_stats(username: str) -> dict:
    initialize_database()
    connection = get_connection()
    try:
        search_count = connection.execute(
            """
            SELECT COUNT(*) FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'SEARCH'
            """, (str(username).strip(),)
        ).fetchone()[0]
        successful_searches = connection.execute(
            """
            SELECT COUNT(*) FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'SEARCH' AND status = 'PASS'
            """, (str(username).strip(),)
        ).fetchone()[0]
        voice_searches = connection.execute(
            """
            SELECT COUNT(*) FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'SEARCH' AND input_mode = 'voice'
            """, (str(username).strip(),)
        ).fetchone()[0]
        document_opens = connection.execute(
            """
            SELECT COUNT(*) FROM activity_history
            WHERE username = ? COLLATE NOCASE AND event_type = 'DOCUMENT_OPEN' AND status = 'PASS'
            """, (str(username).strip(),)
        ).fetchone()[0]
        return {
            "searches": int(search_count),
            "successful_searches": int(successful_searches),
            "failed_searches": int(search_count - successful_searches),
            "voice_searches": int(voice_searches),
            "document_opens": int(document_opens),
        }
    finally:
        connection.close()


def get_user_activity(username: str, limit: int = 500):
    initialize_database()
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT * FROM activity_history
            WHERE username = ? COLLATE NOCASE
            ORDER BY event_time DESC, id DESC
            LIMIT ?
            """,
            (str(username).strip(), max(1, int(limit))),
        ).fetchall()
    finally:
        connection.close()


def export_user_history_json(username: str, output_path: str) -> str:
    initialize_database()
    connection = get_connection()
    try:
        identity = connection.execute(
            """
            SELECT username, display_name FROM activity_history
            WHERE username = ? COLLATE NOCASE
            ORDER BY id DESC LIMIT 1
            """, (str(username).strip(),)
        ).fetchone()
        if not identity:
            raise ValueError("User history not found")
        records = connection.execute(
            """
            SELECT * FROM activity_history
            WHERE username = ? COLLATE NOCASE
            ORDER BY event_time DESC, id DESC
            """, (str(username).strip(),)
        ).fetchall()
    finally:
        connection.close()

    def row_dict(row):
        value = dict(row)
        return value

    sessions = [row_dict(row) for row in records if row["event_type"] == "SESSION"]
    searches = [row_dict(row) for row in records if row["event_type"] == "SEARCH"]
    documents = [row_dict(row) for row in records if row["event_type"] == "DOCUMENT_OPEN"]
    audits = [row_dict(row) for row in records if row["event_type"] not in {"SESSION", "SEARCH", "DOCUMENT_OPEN"}]

    payload = {
        "exported_at": utc_now_iso(),
        "user": dict(identity),
        "statistics": get_user_stats(username),
        "sessions": sessions,
        "search_history": searches,
        "document_history": documents,
        "audit_events": audits,
        "activity_history": [row_dict(row) for row in records],
    }
    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(destination)



# ---------------------------------------------------------------------------
# PostgreSQL activity-history backend
# ---------------------------------------------------------------------------
# Keep the SQLite document index above intact for local files/FTS5. When
# DATABASE_BACKEND=postgresql (or DATABASE_URL is a PostgreSQL URL), the
# activity/session/history APIs below use PostgreSQL instead of the local
# activity tables. This preserves the public database.py API used by the UI.
from history_store import (
    backend_name as history_backend_name,
    initialize_postgresql as initialize_postgresql_history,
    record_login_attempt_pg,
    start_session_pg,
    end_session_pg,
    log_audit_event_pg,
    record_search_history_pg,
    record_document_access_pg,
    get_search_history_pg,
    get_document_history_pg,
    get_session_history_pg,
    get_user_stats_pg,
    get_user_activity_pg,
    export_user_history_json_pg,
)


_sqlite_initialize_database = initialize_database
_sqlite_record_login_attempt = record_login_attempt
_sqlite_start_session = start_session
_sqlite_end_session = end_session
_sqlite_log_audit_event = log_audit_event
_sqlite_record_search_history = record_search_history
_sqlite_record_document_access = record_document_access
_sqlite_get_search_history = get_search_history
_sqlite_get_document_history = get_document_history
_sqlite_get_session_history = get_session_history
_sqlite_get_user_stats = get_user_stats
_sqlite_get_user_activity = get_user_activity
_sqlite_export_user_history_json = export_user_history_json


def _using_postgresql_history() -> bool:
    return history_backend_name() == "postgresql"


def initialize_database() -> None:
    """Initialize the active document index and, for the desktop DB, activity backend.

    Portal account indexes are separate SQLite files that contain document text only;
    they do not need to initialize the desktop's global activity-history backend.
    """
    override_path = _ACTIVE_DATABASE_PATH.get()
    if override_path is not None:
        key = str(Path(override_path).expanduser().resolve())
        with _INDEX_DATABASE_INIT_LOCK:
            if key in _INITIALIZED_INDEX_DATABASES and Path(key).is_file():
                return
            _sqlite_initialize_database()
            _INITIALIZED_INDEX_DATABASES.add(key)
        return
    _sqlite_initialize_database()
    if _using_postgresql_history():
        initialize_postgresql_history()


def record_login_attempt(
    username: str = "",
    display_name: str = "",
    *,
    status: str = "FAIL",
    reason: str = "",
) -> int:
    if _using_postgresql_history():
        return record_login_attempt_pg(
            username=username, display_name=display_name, status=status, reason=reason
        )
    return _sqlite_record_login_attempt(
        username=username, display_name=display_name, status=status, reason=reason
    )


def start_session(username: str, display_name: Optional[str] = None) -> int:
    if _using_postgresql_history():
        return start_session_pg(username, display_name)
    return _sqlite_start_session(username, display_name)


def end_session(session_id: Optional[int], reason: str = "application_closed") -> None:
    if _using_postgresql_history():
        return end_session_pg(session_id, reason)
    return _sqlite_end_session(session_id, reason)


def log_audit_event(
    event_type: str,
    *,
    username: str = "",
    display_name: str = "",
    session_id: Optional[int] = None,
    details: Optional[dict] = None,
    status: str = "PASS",
) -> int:
    if _using_postgresql_history():
        return log_audit_event_pg(
            event_type,
            username=username,
            display_name=display_name,
            session_id=session_id,
            details=details,
            status=status,
        )
    return _sqlite_log_audit_event(
        event_type,
        username=username,
        display_name=display_name,
        session_id=session_id,
        details=details,
        status=status,
    )


def record_search_history(
    *,
    username: str,
    display_name: str = "",
    session_id: Optional[int] = None,
    original_query: str,
    canonical_query: str = "",
    transliterated_query: str = "",
    detected_language: str = "",
    preferred_language: str = "",
    input_mode: str = "text",
    provider: str = "",
    document_type: str = "",
    searched_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    duration_ms: int = 0,
    results_count: int = 0,
    success: bool = False,
    error_message: str = "",
) -> int:
    if _using_postgresql_history():
        return record_search_history_pg(
            username=username,
            display_name=display_name,
            session_id=session_id,
            original_query=original_query,
            canonical_query=canonical_query,
            transliterated_query=transliterated_query,
            detected_language=detected_language,
            preferred_language=preferred_language,
            input_mode=input_mode,
            provider=provider,
            document_type=document_type,
            searched_at=searched_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            results_count=results_count,
            success=success,
            error_message=error_message,
        )
    return _sqlite_record_search_history(
        username=username,
        display_name=display_name,
        session_id=session_id,
        original_query=original_query,
        canonical_query=canonical_query,
        transliterated_query=transliterated_query,
        detected_language=detected_language,
        preferred_language=preferred_language,
        input_mode=input_mode,
        provider=provider,
        document_type=document_type,
        searched_at=searched_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        results_count=results_count,
        success=success,
        error_message=error_message,
    )


def record_document_access(
    *,
    username: str,
    display_name: str = "",
    session_id: Optional[int],
    document_name: str,
    document_path: str,
    document_id: Optional[int] = None,
    source: str = "local",
    action: str = "open",
    search_history_id: Optional[int] = None,
    document_type: str = "",
    success: bool = True,
    error_message: str = "",
) -> int:
    if _using_postgresql_history():
        return record_document_access_pg(
            username=username,
            display_name=display_name,
            session_id=session_id,
            document_name=document_name,
            document_path=document_path,
            document_id=document_id,
            source=source,
            action=action,
            search_history_id=search_history_id,
            document_type=document_type,
            success=success,
            error_message=error_message,
        )
    return _sqlite_record_document_access(
        username=username,
        display_name=display_name,
        session_id=session_id,
        document_name=document_name,
        document_path=document_path,
        document_id=document_id,
        source=source,
        action=action,
        search_history_id=search_history_id,
        document_type=document_type,
        success=success,
        error_message=error_message,
    )


def get_search_history(username: str, limit: int = 100):
    if _using_postgresql_history():
        return get_search_history_pg(username, limit)
    return _sqlite_get_search_history(username, limit)


def get_document_history(username: str, limit: int = 100):
    if _using_postgresql_history():
        return get_document_history_pg(username, limit)
    return _sqlite_get_document_history(username, limit)


def get_session_history(username: str, limit: int = 50):
    if _using_postgresql_history():
        return get_session_history_pg(username, limit)
    return _sqlite_get_session_history(username, limit)


def get_user_stats(username: str) -> dict:
    if _using_postgresql_history():
        return get_user_stats_pg(username)
    return _sqlite_get_user_stats(username)


def get_user_activity(username: str, limit: int = 500):
    if _using_postgresql_history():
        return get_user_activity_pg(username, limit)
    return _sqlite_get_user_activity(username, limit)


def export_user_history_json(username: str, output_path: str) -> str:
    if _using_postgresql_history():
        return export_user_history_json_pg(username, output_path)
    return _sqlite_export_user_history_json(username, output_path)


def get_database_backend() -> str:
    return history_backend_name()
