-- SmartDocumentFinder multi-user browser portal schema (PostgreSQL).
-- New deployments create these tables automatically from portal_store.py.
-- This file is provided for schema review or controlled manual provisioning.

CREATE TABLE IF NOT EXISTS sdf_web_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(40) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS sdf_web_sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    ended_at TIMESTAMPTZ,
    ip_fingerprint VARCHAR(64),
    user_agent VARCHAR(300)
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_sessions_user_id ON sdf_web_sessions(user_id);

CREATE TABLE IF NOT EXISTS sdf_web_audit_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES sdf_web_users(id) ON DELETE SET NULL,
    username VARCHAR(40) NOT NULL DEFAULT '',
    event_type VARCHAR(60) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PASS',
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_audit_events_user_id ON sdf_web_audit_events(user_id);
CREATE INDEX IF NOT EXISTS ix_sdf_web_audit_events_event_type ON sdf_web_audit_events(event_type);
CREATE INDEX IF NOT EXISTS ix_sdf_web_audit_events_created_at ON sdf_web_audit_events(created_at);

CREATE TABLE IF NOT EXISTS sdf_web_searches (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    input_mode VARCHAR(16) NOT NULL DEFAULT 'text',
    language VARCHAR(20),
    provider VARCHAR(40),
    results_count INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(16) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_searches_user_id ON sdf_web_searches(user_id);
CREATE INDEX IF NOT EXISTS ix_sdf_web_searches_created_at ON sdf_web_searches(created_at);

CREATE TABLE IF NOT EXISTS sdf_web_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    path TEXT NOT NULL,
    extension VARCHAR(16) NOT NULL,
    size INTEGER NOT NULL DEFAULT 0,
    source VARCHAR(40) NOT NULL DEFAULT 'digilocker',
    source_uri TEXT,
    issuer VARCHAR(255),
    document_type VARCHAR(80),
    remote_metadata_json TEXT NOT NULL DEFAULT '{}',
    fetched_at TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ,
    CONSTRAINT uq_sdf_user_document_path UNIQUE(user_id, path),
    CONSTRAINT uq_sdf_user_source_uri UNIQUE(user_id, source, source_uri)
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_documents_user_id ON sdf_web_documents(user_id);

CREATE TABLE IF NOT EXISTS sdf_web_timeline_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    document_id INTEGER NOT NULL REFERENCES sdf_web_documents(id) ON DELETE CASCADE,
    event_date VARCHAR(10) NOT NULL,
    event_type VARCHAR(60) NOT NULL,
    title VARCHAR(255) NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_sdf_timeline_doc_date_title UNIQUE(document_id, event_date, title)
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_timeline_events_user_id ON sdf_web_timeline_events(user_id);
CREATE INDEX IF NOT EXISTS ix_sdf_web_timeline_events_document_id ON sdf_web_timeline_events(document_id);
CREATE INDEX IF NOT EXISTS ix_sdf_web_timeline_events_event_date ON sdf_web_timeline_events(event_date);

CREATE TABLE IF NOT EXISTS sdf_web_connections (
    user_id INTEGER PRIMARY KEY REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    provider VARCHAR(40) NOT NULL DEFAULT 'digilocker',
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    expires_at TIMESTAMPTZ,
    scope_text TEXT,
    status VARCHAR(24) NOT NULL DEFAULT 'connected',
    connected_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS sdf_web_sync_jobs (
    id VARCHAR(36) PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES sdf_web_users(id) ON DELETE CASCADE,
    status VARCHAR(24) NOT NULL DEFAULT 'queued',
    total INTEGER NOT NULL DEFAULT 0,
    processed INTEGER NOT NULL DEFAULT 0,
    fetched INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    more_remaining BOOLEAN NOT NULL DEFAULT FALSE,
    message TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_sdf_web_sync_jobs_user_id ON sdf_web_sync_jobs(user_id);
CREATE INDEX IF NOT EXISTS ix_sdf_web_sync_jobs_status ON sdf_web_sync_jobs(status);
