"""
PostgreSQL-backed activity/history store for Smart Document Finder.

The document index remains local SQLite/FTS5 because it indexes files that live on
the user's machine. User/session/search/document activity can be persisted in
PostgreSQL when DATABASE_URL is configured.

Backend selection:
- DATABASE_BACKEND=postgresql/postgres/pg -> PostgreSQL (requires DATABASE_URL)
- DATABASE_BACKEND=sqlite/local -> local SQLite history
- DATABASE_BACKEND=auto/unset -> PostgreSQL when DATABASE_URL is present,
  otherwise local SQLite.

This module intentionally contains no GUI code.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
except ImportError:  # pragma: no cover - dependency is declared in requirements
    create_engine = None
    text = None
    Engine = Any  # type: ignore


POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_history (
    id BIGSERIAL PRIMARY KEY,
    username TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    event_type TEXT NOT NULL,
    session_id BIGINT,
    event_time TIMESTAMPTZ NOT NULL,

    login_time TIMESTAMPTZ,
    logout_time TIMESTAMPTZ,
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
    searched_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER DEFAULT 0,
    results_count INTEGER DEFAULT 0,

    document_id BIGINT,
    document_name TEXT DEFAULT '',
    document_path TEXT DEFAULT '',
    source TEXT DEFAULT 'local',
    action TEXT DEFAULT 'open',
    search_history_id BIGINT,

    status TEXT NOT NULL DEFAULT 'PASS',
    error_message TEXT DEFAULT '',
    event_reason TEXT DEFAULT '',
    details_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_activity_user_time
    ON activity_history(username, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_session_time
    ON activity_history(session_id, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_event_time
    ON activity_history(event_type, event_time DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_activity_user_event
    ON activity_history(username, event_type, event_time DESC, id DESC);
"""

def backend_name() -> str:
    configured = os.getenv("DATABASE_BACKEND", "").strip().lower()
    if configured in {"postgres", "postgresql", "pg"}:
        return "postgresql"
    if configured in {"sqlite", "local", "local-sqlite"}:
        return "sqlite"
    url = os.getenv("DATABASE_URL", "").strip().lower()
    if url.startswith(("postgresql://", "postgres://", "postgresql+")):
        return "postgresql"
    return "sqlite"


def database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError(
            "PostgreSQL is selected but DATABASE_URL is not configured. "
            "Set DATABASE_URL, for example: "
            "postgresql+psycopg://smartdocument:password@localhost:5432/smartdocumentfinder"
        )
    # psycopg v3 is the project dependency. Normalize generic PostgreSQL URLs
    # so SQLAlchemy does not try to load the uninstalled psycopg2 driver.
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    if value.startswith("postgresql+psycopg://"):
        return value
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL URL such as "
        "postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE"
    )


def _require_sqlalchemy() -> None:
    if create_engine is None or text is None:
        raise RuntimeError(
            "PostgreSQL support requires SQLAlchemy. "
            "Install the project requirements before starting the application."
        )


_engine: Optional[Engine] = None
_engine_url: str = ""


def _pg_engine() -> Engine:
    global _engine, _engine_url
    _require_sqlalchemy()
    url = database_url()
    if _engine is None or _engine_url != url:
        if _engine is not None:
            _engine.dispose()
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_recycle=1800,
            future=True,
        )
        _engine_url = url
    return _engine


def is_postgresql() -> bool:
    return backend_name() == "postgresql"


def initialize_postgresql() -> None:
    """Create the PostgreSQL activity schema if it does not exist."""
    engine = _pg_engine()
    with engine.begin() as connection:
        for statement in POSTGRES_SCHEMA.strip().split(";"):
            statement = statement.strip()
            if statement:
                connection.execute(text(statement))


def _iso_to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO timestamp: {value!r}") from exc


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_identity(username: str, display_name: Optional[str] = None) -> tuple[str, str]:
    username = (username or "").strip()
    display_name = (display_name or username).strip()
    if not username:
        raise ValueError("Username cannot be empty")
    return username, display_name


def _row_dict(row) -> dict[str, Any]:
    return dict(row._mapping)


@contextmanager
def _connection() -> Iterator[Any]:
    engine = _pg_engine()
    with engine.begin() as connection:
        yield connection


def record_login_attempt_pg(username: str = "", display_name: str = "", *, status: str = "FAIL", reason: str = "") -> int:
    with _connection() as connection:
        result = connection.execute(
            text("""
                INSERT INTO activity_history(
                    username, display_name, event_type, event_time, status, event_reason
                ) VALUES (:username, :display_name, 'LOGIN_ATTEMPT', :event_time, :status, :reason)
                RETURNING id
            """),
            {
                "username": (username or "").strip(),
                "display_name": (display_name or username or "").strip(),
                "event_time": _iso_to_datetime(utc_now_iso()),
                "status": str(status).upper(),
                "reason": reason or "",
            },
        )
        return int(result.scalar_one())


def start_session_pg(username: str, display_name: Optional[str] = None) -> int:
    username, display_name = clean_identity(username, display_name)
    now = _iso_to_datetime(utc_now_iso())
    with _connection() as connection:
        connection.execute(
            text("""
                UPDATE activity_history
                SET logout_time = :now,
                    logout_status = 'FAIL',
                    session_status = 'ABNORMAL',
                    event_reason = CASE
                        WHEN COALESCE(event_reason, '') = '' THEN 'previous_session_not_closed'
                        ELSE event_reason
                    END
                WHERE event_type = 'SESSION'
                  AND LOWER(username) = LOWER(:username)
                  AND session_status = 'ACTIVE'
            """),
            {"now": now, "username": username},
        )
        result = connection.execute(
            text("""
                INSERT INTO activity_history(
                    username, display_name, event_type, event_time,
                    login_time, session_status, login_status, logout_status, status
                ) VALUES (
                    :username, :display_name, 'SESSION', :now,
                    :now, 'ACTIVE', 'PASS', 'PENDING', 'PASS'
                )
                RETURNING id
            """),
            {"username": username, "display_name": display_name, "now": now},
        )
        session_id = int(result.scalar_one())
        connection.execute(
            text("UPDATE activity_history SET session_id = :session_id WHERE id = :id"),
            {"session_id": session_id, "id": session_id},
        )
        return session_id


def end_session_pg(session_id: Optional[int], reason: str = "application_closed") -> None:
    if not session_id:
        return
    with _connection() as connection:
        connection.execute(
            text("""
                UPDATE activity_history
                SET logout_time = :now,
                    logout_status = 'PASS',
                    session_status = 'CLOSED',
                    event_reason = :reason,
                    status = 'PASS'
                WHERE id = :id
                  AND event_type = 'SESSION'
                  AND session_status = 'ACTIVE'
            """),
            {
                "now": _iso_to_datetime(utc_now_iso()),
                "reason": reason or "application_closed",
                "id": int(session_id),
            },
        )


def log_audit_event_pg(event_type: str, *, username: str = "", display_name: str = "",
                       session_id: Optional[int] = None, details: Optional[dict] = None,
                       status: str = "PASS") -> int:
    with _connection() as connection:
        result = connection.execute(
            text("""
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    status, details_json
                ) VALUES (
                    :username, :display_name, :event_type, :session_id, :event_time,
                    :status, :details
                )
                RETURNING id
            """),
            {
                "username": (username or "").strip(),
                "display_name": (display_name or "").strip(),
                "event_type": str(event_type),
                "session_id": int(session_id) if session_id is not None else None,
                "event_time": _iso_to_datetime(utc_now_iso()),
                "status": str(status).upper(),
                "details": json.dumps(details or {}, ensure_ascii=False),
            },
        )
        return int(result.scalar_one())


def record_search_history_pg(
    *, username: str, display_name: str = "", session_id: Optional[int] = None,
    original_query: str, canonical_query: str = "", transliterated_query: str = "",
    detected_language: str = "", preferred_language: str = "", input_mode: str = "text",
    provider: str = "", document_type: str = "", searched_at: Optional[str] = None,
    completed_at: Optional[str] = None, duration_ms: int = 0, results_count: int = 0,
    success: bool = False, error_message: str = "",
) -> int:
    username, display_name = clean_identity(username, display_name)
    searched_at = searched_at or utc_now_iso()
    completed_at = completed_at or searched_at
    with _connection() as connection:
        result = connection.execute(
            text("""
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    original_query, canonical_query, transliterated_query,
                    detected_language, preferred_language, input_mode, provider,
                    document_type, searched_at, completed_at, duration_ms,
                    results_count, status, error_message
                ) VALUES (
                    :username, :display_name, 'SEARCH', :session_id, :event_time,
                    :original_query, :canonical_query, :transliterated_query,
                    :detected_language, :preferred_language, :input_mode, :provider,
                    :document_type, :searched_at, :completed_at, :duration_ms,
                    :results_count, :status, :error_message
                )
                RETURNING id
            """),
            {
                "username": username,
                "display_name": display_name,
                "session_id": int(session_id) if session_id is not None else None,
                "event_time": _iso_to_datetime(searched_at),
                "original_query": original_query,
                "canonical_query": canonical_query,
                "transliterated_query": transliterated_query,
                "detected_language": detected_language,
                "preferred_language": preferred_language,
                "input_mode": input_mode or "text",
                "provider": provider,
                "document_type": document_type,
                "searched_at": _iso_to_datetime(searched_at),
                "completed_at": _iso_to_datetime(completed_at),
                "duration_ms": max(0, int(duration_ms)),
                "results_count": max(0, int(results_count)),
                "status": "PASS" if success else "FAIL",
                "error_message": error_message or "",
            },
        )
        return int(result.scalar_one())


def record_document_access_pg(
    *, username: str, display_name: str = "", session_id: Optional[int],
    document_name: str, document_path: str, document_id: Optional[int] = None,
    source: str = "local", action: str = "open", search_history_id: Optional[int] = None,
    document_type: str = "", success: bool = True, error_message: str = "",
) -> int:
    username, display_name = clean_identity(username, display_name)
    with _connection() as connection:
        result = connection.execute(
            text("""
                INSERT INTO activity_history(
                    username, display_name, event_type, session_id, event_time,
                    document_id, document_name, document_path, source, action,
                    document_type, search_history_id, status, error_message
                ) VALUES (
                    :username, :display_name, 'DOCUMENT_OPEN', :session_id, :event_time,
                    :document_id, :document_name, :document_path, :source, :action,
                    :document_type, :search_history_id, :status, :error_message
                )
                RETURNING id
            """),
            {
                "username": username,
                "display_name": display_name,
                "session_id": int(session_id) if session_id is not None else None,
                "event_time": _iso_to_datetime(utc_now_iso()),
                "document_id": int(document_id) if document_id is not None else None,
                "document_name": document_name,
                "document_path": str(Path(document_path).expanduser().resolve()),
                "source": source or "local",
                "action": action or "open",
                "document_type": document_type or "",
                "search_history_id": int(search_history_id) if search_history_id is not None else None,
                "status": "PASS" if success else "FAIL",
                "error_message": error_message or "",
            },
        )
        return int(result.scalar_one())


def get_search_history_pg(username: str, limit: int = 100) -> list[dict[str, Any]]:
    with _connection() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
                  AND event_type = 'SEARCH'
                ORDER BY searched_at DESC NULLS LAST, id DESC
                LIMIT :limit
            """),
            {"username": str(username).strip(), "limit": max(1, int(limit))},
        )
        rows = []
        for row in result:
            value = _row_dict(row)
            for key in ("event_time", "searched_at", "completed_at", "login_time", "logout_time"):
                if value.get(key):
                    value[key] = value[key].isoformat()
            rows.append(value)
        return rows


def get_document_history_pg(username: str, limit: int = 100) -> list[dict[str, Any]]:
    with _connection() as connection:
        result = connection.execute(
            text("""
                SELECT ah.*,
                       COALESCE(NULLIF(ah.document_type, ''), '') AS resolved_document_type
                FROM activity_history ah
                WHERE LOWER(ah.username) = LOWER(:username)
                  AND ah.event_type = 'DOCUMENT_OPEN'
                ORDER BY ah.event_time DESC, ah.id DESC
                LIMIT :limit
            """),
            {"username": str(username).strip(), "limit": max(1, int(limit))},
        )
        rows = []
        for row in result:
            value = _row_dict(row)
            value["document_type"] = value.get("resolved_document_type") or value.get("document_type") or ""
            # Keep the old UI field name available while the schema stays normalized.
            value["accessed_at"] = value.get("event_time").isoformat() if value.get("event_time") else ""
            rows.append(value)
        return rows


def get_session_history_pg(username: str, limit: int = 50) -> list[dict[str, Any]]:
    with _connection() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
                  AND event_type = 'SESSION'
                ORDER BY login_time DESC NULLS LAST, id DESC
                LIMIT :limit
            """),
            {"username": str(username).strip(), "limit": max(1, int(limit))},
        )
        rows = []
        for row in result:
            value = _row_dict(row)
            for key in ("login_time", "logout_time", "event_time", "searched_at", "completed_at"):
                if value.get(key):
                    value[key] = value[key].isoformat()
            rows.append(value)
        return rows


def get_user_stats_pg(username: str) -> dict[str, int]:
    with _connection() as connection:
        result = connection.execute(
            text("""
                SELECT
                    COUNT(*) FILTER (WHERE event_type = 'SEARCH') AS searches,
                    COUNT(*) FILTER (WHERE event_type = 'SEARCH' AND status = 'PASS') AS successful_searches,
                    COUNT(*) FILTER (WHERE event_type = 'SEARCH' AND input_mode = 'voice') AS voice_searches,
                    COUNT(*) FILTER (WHERE event_type = 'DOCUMENT_OPEN' AND status = 'PASS') AS document_opens
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
            """),
            {"username": str(username).strip()},
        ).mappings().one()
    searches = int(result["searches"] or 0)
    successful = int(result["successful_searches"] or 0)
    return {
        "searches": searches,
        "successful_searches": successful,
        "failed_searches": searches - successful,
        "voice_searches": int(result["voice_searches"] or 0),
        "document_opens": int(result["document_opens"] or 0),
    }


def get_user_activity_pg(username: str, limit: int = 500) -> list[dict[str, Any]]:
    with _connection() as connection:
        result = connection.execute(
            text("""
                SELECT *
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
                ORDER BY event_time DESC, id DESC
                LIMIT :limit
            """),
            {"username": str(username).strip(), "limit": max(1, int(limit))},
        )
        rows = []
        for row in result:
            value = _row_dict(row)
            for key in ("event_time", "login_time", "logout_time", "searched_at", "completed_at"):
                if value.get(key):
                    value[key] = value[key].isoformat()
            rows.append(value)
        return rows


def export_user_history_json_pg(username: str, output_path: str) -> str:
    with _connection() as connection:
        identity_result = connection.execute(
            text("""
                SELECT username, display_name
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
                ORDER BY id DESC
                LIMIT 1
            """),
            {"username": str(username).strip()},
        ).mappings().first()
        if not identity_result:
            raise ValueError("User history not found")
        records = connection.execute(
            text("""
                SELECT *
                FROM activity_history
                WHERE LOWER(username) = LOWER(:username)
                ORDER BY event_time DESC, id DESC
            """),
            {"username": str(username).strip()},
        )
        converted = []
        for row in records:
            value = _row_dict(row)
            for key in ("event_time", "login_time", "logout_time", "searched_at", "completed_at"):
                if value.get(key):
                    value[key] = value[key].isoformat()
            converted.append(value)

    sessions = [row for row in converted if row["event_type"] == "SESSION"]
    searches = [row for row in converted if row["event_type"] == "SEARCH"]
    documents = [row for row in converted if row["event_type"] == "DOCUMENT_OPEN"]
    audits = [row for row in converted if row["event_type"] not in {"SESSION", "SEARCH", "DOCUMENT_OPEN"}]

    destination = Path(output_path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "exported_at": utc_now_iso(),
        "user": dict(identity_result),
        "statistics": get_user_stats_pg(username),
        "sessions": sessions,
        "search_history": searches,
        "document_history": documents,
        "audit_events": audits,
        "activity_history": converted,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return str(destination)


def migrate_sqlite_history_to_postgres(sqlite_path: str, *, overwrite: bool = False) -> dict[str, int | bool]:
    """Copy activity_history rows from the local SQLite database into PostgreSQL.

    Existing PostgreSQL rows are preserved by default. With overwrite=True the
    import runs after truncating the PostgreSQL activity table.
    """
    if not Path(sqlite_path).exists():
        return {"migrated": 0, "skipped": True}

    initialize_postgresql()

    with sqlite3.connect(sqlite_path) as sqlite_connection:
        sqlite_connection.row_factory = sqlite3.Row
        table = sqlite_connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_history'"
        ).fetchone()
        if not table:
            return {"migrated": 0, "skipped": True}
        rows = sqlite_connection.execute(
            "SELECT * FROM activity_history ORDER BY id"
        ).fetchall()
        columns = [desc[1] for desc in sqlite_connection.execute("PRAGMA table_info(activity_history)").fetchall()]

    if not rows:
        return {"migrated": 0, "skipped": False}

    # Keep only columns present in the destination schema.
    destination_columns = {
        "id", "username", "display_name", "event_type", "session_id", "event_time",
        "login_time", "logout_time", "session_status", "login_status", "logout_status",
        "original_query", "canonical_query", "transliterated_query", "detected_language",
        "preferred_language", "input_mode", "provider", "document_type", "searched_at",
        "completed_at", "duration_ms", "results_count", "document_id", "document_name",
        "document_path", "source", "action", "search_history_id", "status", "error_message",
        "event_reason", "details_json",
    }
    available = [c for c in columns if c in destination_columns]
    imported = 0

    engine = _pg_engine()
    with engine.begin() as connection:
        if overwrite:
            connection.execute(text("TRUNCATE TABLE activity_history RESTART IDENTITY"))
        else:
            existing = int(connection.execute(text("SELECT COUNT(*) FROM activity_history")).scalar_one())
            if existing:
                return {"migrated": 0, "skipped": True, "existing_rows": existing}

        for row in rows:
            values = {}
            for column in available:
                value = row[column]
                if column in {"event_time", "login_time", "logout_time", "searched_at", "completed_at"}:
                    values[column] = _iso_to_datetime(value) if value else None
                else:
                    values[column] = value
            # Sequence-safe explicit ID import.
            connection.execute(
                text(
                    "INSERT INTO activity_history (" +
                    ", ".join(available) +
                    ") VALUES (" +
                    ", ".join(":" + c for c in available) +
                    ")"
                ),
                values,
            )
            imported += 1
        connection.execute(
            text("""
                SELECT setval(
                    pg_get_serial_sequence('activity_history', 'id'),
                    COALESCE((SELECT MAX(id) FROM activity_history), 1),
                    true
                )
            """)
        )

    return {"migrated": imported, "skipped": False}
