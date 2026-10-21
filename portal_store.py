"""Multi-user persistence for the SmartDocumentFinder web portal.

The desktop index remains in its own local SQLite database for compatibility.
This store contains account ownership, connected-source credentials, per-user
file metadata, timeline entries and web audit history. It uses PostgreSQL when
DATABASE_URL / WEB_PORTAL_DATABASE_URL is configured and SQLite locally.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table,
    Text, UniqueConstraint, create_engine, select, update, insert, delete, func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

metadata = MetaData()

users = Table(
    "sdf_web_users", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(40), nullable=False, unique=True),
    Column("display_name", String(120), nullable=False),
    Column("email", String(254), nullable=True, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("last_login_at", DateTime(timezone=True), nullable=True),
    Column("is_active", Boolean, nullable=False, default=True),
)

web_sessions = Table(
    "sdf_web_sessions", metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("ip_fingerprint", String(64), nullable=True),
    Column("user_agent", String(300), nullable=True),
)

audit_events = Table(
    "sdf_web_audit_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="SET NULL"), nullable=True, index=True),
    Column("username", String(40), nullable=False, default=""),
    Column("event_type", String(60), nullable=False, index=True),
    Column("status", String(16), nullable=False, default="PASS"),
    Column("details_json", Text, nullable=False, default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

searches = Table(
    "sdf_web_searches", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("query", Text, nullable=False),
    Column("input_mode", String(16), nullable=False, default="text"),
    Column("language", String(20), nullable=True),
    Column("provider", String(40), nullable=True),
    Column("results_count", Integer, nullable=False, default=0),
    Column("status", String(16), nullable=False),
    Column("duration_ms", Integer, nullable=False, default=0),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

documents = Table(
    "sdf_web_documents", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("path", Text, nullable=False),
    Column("extension", String(16), nullable=False),
    Column("size", Integer, nullable=False, default=0),
    Column("source", String(40), nullable=False, default="digilocker"),
    Column("source_uri", Text, nullable=True),
    Column("issuer", String(255), nullable=True),
    Column("document_type", String(80), nullable=True),
    Column("remote_metadata_json", Text, nullable=False, default="{}"),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
    Column("last_accessed_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("user_id", "path", name="uq_sdf_user_document_path"),
    UniqueConstraint("user_id", "source", "source_uri", name="uq_sdf_user_source_uri"),
)

timeline_events = Table(
    "sdf_web_timeline_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("document_id", Integer, ForeignKey("sdf_web_documents.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("event_date", String(10), nullable=False, index=True),
    Column("event_type", String(60), nullable=False),
    Column("title", String(255), nullable=False),
    Column("evidence", Text, nullable=False, default=""),
    Column("created_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("document_id", "event_date", "title", name="uq_sdf_timeline_doc_date_title"),
)

connections = Table(
    "sdf_web_connections", metadata,
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), primary_key=True),
    Column("provider", String(40), nullable=False, default="digilocker"),
    Column("access_token_encrypted", Text, nullable=True),
    Column("refresh_token_encrypted", Text, nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("scope_text", Text, nullable=True),
    Column("status", String(24), nullable=False, default="connected"),
    Column("connected_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

sync_jobs = Table(
    "sdf_web_sync_jobs", metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", Integer, ForeignKey("sdf_web_users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("status", String(24), nullable=False, default="queued", index=True),
    Column("total", Integer, nullable=False, default=0),
    Column("processed", Integer, nullable=False, default=0),
    Column("fetched", Integer, nullable=False, default=0),
    Column("skipped", Integer, nullable=False, default=0),
    Column("failed", Integer, nullable=False, default=0),
    Column("more_remaining", Boolean, nullable=False, default=False),
    Column("message", Text, nullable=False, default=""),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

_engine: Optional[Engine] = None
_engine_key: Optional[str] = None
_initialized_key: Optional[str] = None
_engine_lock = threading.Lock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _database_target() -> tuple[str, dict[str, Any]]:
    url = (os.getenv("WEB_PORTAL_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        elif url.startswith("postgresql+psycopg2://"):
            url = "postgresql+psycopg://" + url[len("postgresql+psycopg2://"):]
        return url, {"pool_pre_ping": True}
    data_dir = Path(os.getenv("SMARTDOCUMENT_DATA_DIR", str(Path(__file__).resolve().parent / "data"))).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / "web_portal.db"
    return f"sqlite:///{path.as_posix()}", {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}


def get_engine() -> Engine:
    global _engine, _engine_key, _initialized_key
    url, kwargs = _database_target()
    with _engine_lock:
        if _engine is None or _engine_key != url:
            if _engine is not None:
                _engine.dispose()
            _engine = create_engine(url, future=True, **kwargs)
            _engine_key = url
            _initialized_key = None
        return _engine


def initialize_store() -> None:
    """Create missing schema once per active database URL, not on every request."""
    global _initialized_key
    engine = get_engine()
    key = str(engine.url)
    with _engine_lock:
        if _initialized_key == key:
            return
        metadata.create_all(engine)
        _initialized_key = key


def _dict(row) -> Optional[dict[str, Any]]:
    return dict(row._mapping) if row is not None else None


def create_user(username: str, display_name: str, email: str | None, password_hash: str) -> dict[str, Any]:
    initialize_store()
    now = utcnow()
    username = username.strip().lower()
    email = (email or "").strip().lower() or None
    with get_engine().begin() as conn:
        try:
            conn.execute(insert(users).values(
                username=username, display_name=display_name.strip(), email=email,
                password_hash=password_hash, created_at=now, last_login_at=None, is_active=True,
            ))
        except IntegrityError:
            raise ValueError("That username or email is already registered.") from None
        row = conn.execute(select(users).where(users.c.username == username)).first()
        return _dict(row) or {}


def get_user_by_login(identifier: str) -> Optional[dict[str, Any]]:
    initialize_store()
    identifier = (identifier or "").strip().lower()
    with get_engine().connect() as conn:
        row = conn.execute(select(users).where((users.c.username == identifier) | (users.c.email == identifier))).first()
        return _dict(row)


def get_user_by_id(user_id: int) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        return _dict(conn.execute(select(users).where(users.c.id == user_id)).first())


def mark_user_login(user_id: int) -> None:
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(update(users).where(users.c.id == user_id).values(last_login_at=utcnow()))


def start_user_session(user_id: int, session_id: str, ip_fingerprint: str = "", user_agent: str = "") -> None:
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(insert(web_sessions).values(
            id=session_id, user_id=user_id, started_at=utcnow(), ip_fingerprint=ip_fingerprint or None,
            user_agent=(user_agent or "")[:300] or None,
        ))


def end_user_session(session_id: str | None) -> None:
    if not session_id:
        return
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(update(web_sessions).where(web_sessions.c.id == session_id, web_sessions.c.ended_at.is_(None)).values(ended_at=utcnow()))


def add_audit_event(user_id: int | None, username: str, event_type: str, status: str = "PASS", details: Optional[dict[str, Any]] = None) -> None:
    initialize_store()
    safe_details = json.dumps(details or {}, ensure_ascii=False, default=str)[:12000]
    with get_engine().begin() as conn:
        conn.execute(insert(audit_events).values(
            user_id=user_id, username=(username or "")[:40], event_type=event_type[:60],
            status=(status or "PASS")[:16].upper(), details_json=safe_details, created_at=utcnow(),
        ))


def add_search(user_id: int, query: str, input_mode: str, language: str, provider: str,
               results_count: int, status: str, duration_ms: int) -> None:
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(insert(searches).values(
            user_id=user_id, query=query[:1000], input_mode=input_mode[:16], language=(language or "")[:20],
            provider=(provider or "")[:40], results_count=max(0, int(results_count)), status=status[:16].upper(),
            duration_ms=max(0, int(duration_ms)), created_at=utcnow(),
        ))


def add_document(user_id: int, name: str, path: str, extension: str, size: int, source: str = "digilocker",
                source_uri: str | None = None, issuer: str = "", document_type: str = "",
                remote_metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    initialize_store()
    now = utcnow()
    metadata_json = json.dumps(remote_metadata or {}, ensure_ascii=False, default=str)[:20000]
    engine = get_engine()
    with engine.begin() as conn:
        existing = None
        if source_uri:
            existing = conn.execute(select(documents).where(
                documents.c.user_id == user_id, documents.c.source == source, documents.c.source_uri == source_uri,
            )).first()
        if not existing:
            existing = conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.path == path)).first()
        if existing:
            record = _dict(existing) or {}
            conn.execute(update(documents).where(documents.c.id == record["id"]).values(
                name=name[:255], path=path, extension=extension[:16], size=max(0, int(size)),
                issuer=(issuer or "")[:255], document_type=(document_type or "")[:80],
                remote_metadata_json=metadata_json, fetched_at=now,
            ))
            return _dict(conn.execute(select(documents).where(documents.c.id == record["id"])).first()) or record
        try:
            with conn.begin_nested():
                conn.execute(insert(documents).values(
                    user_id=user_id, name=name[:255], path=path, extension=extension[:16], size=max(0, int(size)),
                    source=source[:40], source_uri=source_uri, issuer=(issuer or "")[:255],
                    document_type=(document_type or "")[:80], remote_metadata_json=metadata_json,
                    fetched_at=now, last_accessed_at=None,
                ))
        except IntegrityError:
            # Concurrent syncs may race on a unique path/URI; savepoint keeps transaction usable for re-read.
            pass
        row = conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.path == path)).first()
        if row is None and source_uri:
            row = conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.source == source, documents.c.source_uri == source_uri)).first()
        if row is None:
            raise RuntimeError("Could not persist document metadata")
        return _dict(row) or {}


def get_document(user_id: int, document_id: int) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        return _dict(conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.id == document_id)).first())


def get_document_by_uri(user_id: int, source: str, source_uri: str) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        return _dict(conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.source == source, documents.c.source_uri == source_uri)).first())


def list_documents(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(select(documents).where(documents.c.user_id == user_id).order_by(documents.c.fetched_at.desc()).limit(max(1, min(limit, 5000)))).all()
        return [_dict(row) or {} for row in rows]


def count_documents(user_id: int) -> int:
    initialize_store()
    with get_engine().connect() as conn:
        return int(conn.execute(select(func.count()).select_from(documents).where(documents.c.user_id == user_id)).scalar_one())


def mark_document_access(user_id: int, document_id: int) -> None:
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(update(documents).where(documents.c.user_id == user_id, documents.c.id == document_id).values(last_accessed_at=utcnow()))


def list_recent_documents(user_id: int, limit: int = 5) -> list[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(select(documents).where(documents.c.user_id == user_id, documents.c.last_accessed_at.is_not(None)).order_by(documents.c.last_accessed_at.desc()).limit(max(1, min(limit, 50)))).all()
        return [_dict(row) or {} for row in rows]


def add_timeline_event(user_id: int, document_id: int, event_date: str, event_type: str, title: str, evidence: str = "") -> None:
    initialize_store()
    event_date = event_date[:10]
    now = utcnow()
    with get_engine().begin() as conn:
        existing = conn.execute(select(timeline_events.c.id).where(
            timeline_events.c.user_id == user_id, timeline_events.c.document_id == document_id,
            timeline_events.c.event_date == event_date, timeline_events.c.title == title[:255],
        )).first()
        if existing:
            return
        try:
            with conn.begin_nested():
                conn.execute(insert(timeline_events).values(
                    user_id=user_id, document_id=document_id, event_date=event_date,
                    event_type=event_type[:60], title=title[:255], evidence=evidence[:800], created_at=now,
                ))
        except IntegrityError:
            pass


def count_timeline_events(user_id: int) -> int:
    initialize_store()
    with get_engine().connect() as conn:
        return int(conn.execute(select(func.count()).select_from(timeline_events).where(timeline_events.c.user_id == user_id)).scalar_one())


def list_timeline(user_id: int, limit: int = 200) -> list[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(timeline_events, documents.c.name.label("document_name"), documents.c.source.label("source"))
            .join(documents, timeline_events.c.document_id == documents.c.id)
            .where(timeline_events.c.user_id == user_id, documents.c.user_id == user_id)
            .order_by(timeline_events.c.event_date.desc(), timeline_events.c.id.desc())
            .limit(max(1, min(limit, 1000)))
        ).all()
        return [_dict(row) or {} for row in rows]


def add_connection(user_id: int, access_token_encrypted: str, refresh_token_encrypted: str = "",
                   expires_at: datetime | None = None, scope_text: str = "") -> None:
    initialize_store()
    now = utcnow()
    engine = get_engine()
    with engine.begin() as conn:
        current = conn.execute(select(connections.c.user_id).where(connections.c.user_id == user_id)).first()
        fields = dict(provider="digilocker", access_token_encrypted=access_token_encrypted,
                      refresh_token_encrypted=refresh_token_encrypted or None, expires_at=expires_at,
                      scope_text=scope_text[:1000], status="connected", updated_at=now)
        if current:
            conn.execute(update(connections).where(connections.c.user_id == user_id).values(**fields))
        else:
            conn.execute(insert(connections).values(user_id=user_id, connected_at=now, **fields))


def get_connection(user_id: int) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        return _dict(conn.execute(select(connections).where(connections.c.user_id == user_id)).first())


def update_connection_tokens(user_id: int, access_token_encrypted: str, refresh_token_encrypted: str | None,
                             expires_at: datetime | None) -> None:
    initialize_store()
    with get_engine().begin() as conn:
        fields: dict[str, Any] = {"access_token_encrypted": access_token_encrypted, "expires_at": expires_at, "updated_at": utcnow()}
        if refresh_token_encrypted:
            fields["refresh_token_encrypted"] = refresh_token_encrypted
        conn.execute(update(connections).where(connections.c.user_id == user_id).values(**fields))


def disconnect_provider(user_id: int) -> None:
    initialize_store()
    with get_engine().begin() as conn:
        conn.execute(update(connections).where(connections.c.user_id == user_id).values(
            access_token_encrypted=None, refresh_token_encrypted=None, expires_at=None,
            status="disconnected", updated_at=utcnow(),
        ))


def list_searches(user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(select(searches).where(searches.c.user_id == user_id).order_by(searches.c.created_at.desc()).limit(max(1, min(limit, 500)))).all()
        return [_dict(row) or {} for row in rows]


def list_audit_events(user_id: int, limit: int = 100) -> list[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(select(audit_events).where(audit_events.c.user_id == user_id).order_by(audit_events.c.created_at.desc()).limit(max(1, min(limit, 500)))).all()
        result = []
        for row in rows:
            item = _dict(row) or {}
            try:
                item["details"] = json.loads(item.pop("details_json", "{}"))
            except (ValueError, TypeError):
                item["details"] = {}
            result.append(item)
        return result


def list_all_audit_events(limit: int = 300) -> list[dict[str, Any]]:
    """System-wide audit view for accounts explicitly granted admin UI access."""
    initialize_store()
    with get_engine().connect() as conn:
        rows = conn.execute(
            select(audit_events, users.c.display_name.label("display_name"))
            .select_from(audit_events.outerjoin(users, audit_events.c.user_id == users.c.id))
            .order_by(audit_events.c.created_at.desc())
            .limit(max(1, min(limit, 1000)))
        ).all()
        result = []
        for row in rows:
            item = _dict(row) or {}
            try:
                item["details"] = json.loads(item.pop("details_json", "{}"))
            except (ValueError, TypeError):
                item["details"] = {}
            result.append(item)
        return result


def create_sync_job(user_id: int, job_id: str) -> dict[str, Any]:
    initialize_store()
    now = utcnow()
    with get_engine().begin() as conn:
        conn.execute(insert(sync_jobs).values(
            id=job_id, user_id=user_id, status="queued", total=0, processed=0,
            fetched=0, skipped=0, failed=0, more_remaining=False,
            message="Waiting to fetch authorized DigiLocker documents.",
            started_at=now, updated_at=now, finished_at=None,
        ))
        row = conn.execute(select(sync_jobs).where(sync_jobs.c.id == job_id, sync_jobs.c.user_id == user_id)).first()
        return _dict(row) or {}


def update_sync_job(job_id: str, user_id: int, **changes: Any) -> None:
    initialize_store()
    allowed_fields = {"status", "total", "processed", "fetched", "skipped", "failed", "more_remaining", "message"}
    values = {key: value for key, value in changes.items() if key in allowed_fields}
    if not values:
        return
    for key in ("total", "processed", "fetched", "skipped", "failed"):
        if key in values:
            values[key] = max(0, int(values[key]))
    if "status" in values:
        values["status"] = str(values["status"])[:24].lower()
        if values["status"] in {"completed", "partial", "failed", "cancelled"}:
            values["finished_at"] = utcnow()
    if "message" in values:
        values["message"] = str(values["message"])[:1000]
    values["updated_at"] = utcnow()
    with get_engine().begin() as conn:
        conn.execute(update(sync_jobs).where(sync_jobs.c.id == job_id, sync_jobs.c.user_id == user_id).values(**values))


def get_sync_job(user_id: int, job_id: str) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        return _dict(conn.execute(select(sync_jobs).where(sync_jobs.c.user_id == user_id, sync_jobs.c.id == job_id)).first())


def get_latest_sync_job(user_id: int) -> Optional[dict[str, Any]]:
    initialize_store()
    with get_engine().connect() as conn:
        row = conn.execute(select(sync_jobs).where(sync_jobs.c.user_id == user_id).order_by(sync_jobs.c.started_at.desc()).limit(1)).first()
        return _dict(row)


def get_active_sync_job(user_id: int, stale_after_minutes: int = 45) -> Optional[dict[str, Any]]:
    """Get a running job, marking it failed if a worker restart left it stale."""
    row = get_latest_sync_job(user_id)
    if not row or row.get("status") not in {"queued", "running"}:
        return None
    # Use last progress/update time, not job start time: large document libraries
    # can legitimately take a long time while the worker continues making progress.
    last_update = row.get("updated_at") or row.get("started_at")
    if last_update and getattr(last_update, "tzinfo", None) is None:
        last_update = last_update.replace(tzinfo=timezone.utc)
    if last_update and last_update < utcnow() - timedelta(minutes=stale_after_minutes):
        update_sync_job(row["id"], user_id, status="failed", message="The previous sync appears interrupted. Start a new fetch to continue.")
        return None
    return row


def user_stats(user_id: int) -> dict[str, int]:
    initialize_store()
    with get_engine().connect() as conn:
        search_count = conn.execute(select(func.count()).select_from(searches).where(searches.c.user_id == user_id)).scalar_one()
        fetched_count = conn.execute(select(func.count()).select_from(documents).where(documents.c.user_id == user_id)).scalar_one()
        audit_count = conn.execute(select(func.count()).select_from(audit_events).where(audit_events.c.user_id == user_id)).scalar_one()
        return {"searches": int(search_count), "documents": int(fetched_count), "events": int(audit_count)}
